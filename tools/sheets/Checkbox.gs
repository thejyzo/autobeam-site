// =====================================================
// Checkbox: чек аванса (оплата на IBAN) + прив'язка залишку наложки до ЕН Нової пошти
//
// Викликається з NovaPoshta.gs після ✔ на аркуші «Відправки НП».
// Те саме, що ви робите вручну: аванс (передоплата на рахунок ФОП) → чек одразу;
// залишок наложки прив'язується до ЕН → Checkbox сам видає чек, коли клієнт забере посилку.
//
// Властивості скрипта (вводите самі):
//   CHECKBOX_LICENSE_KEY = ключ ліцензії каси (my.checkbox.ua → Каси → каса → «Ключ ліцензії»)
//   CHECKBOX_LOGIN / CHECKBOX_PASSWORD = логін і пароль касира  (або CHECKBOX_PIN = PIN-код касира)
//   CB_ENABLED = 1      ← поки немає, чеки НЕ створюються (лише перевірка cbCheck)
//   CB_IBAN_LABEL       ← назва оплати для аванса (необов'язково), за замовчуванням «Переказ з поточного рахунку»
//
// Сума товару в чеку = передоплата + наложка (= T у «Общей таблице»). Назва товару = позиція (F).
//   • є передоплата і наложка → чек передоплати (CASHLESS) + /ettn/prepayment (наложка на ЕН);
//   • передоплати немає       → /ettn (уся сума на ЕН, чек видасться при отриманні);
//   • наложки немає (повна оплата на IBAN) → нічого не робимо (як і зараз).
// =====================================================

const CB = {
  API: 'https://api.checkbox.ua/api/v1',
  CLIENT: 'AutoBeam-Sheets',
  VERSION: '1.0',
};

function cbForShipment_(o) {
  const props = PropertiesService.getScriptProperties();
  if (props.getProperty('CB_ENABLED') !== '1') return '';
  if (!(o.cod > 0)) return 'без наложки — чек не створюю';
  const total = Math.round((o.prepay + o.cod) * 100);
  const pre = Math.round(o.prepay * 100), cod = Math.round(o.cod * 100);
  const good = { good: { code: 'AB-' + o.row, name: o.name.slice(0, 250), price: total }, quantity: 1000, is_return: false };

  const token = cbToken_();
  cbEnsureShift_(token);

  if (pre > 0) {
    const relation = 'AB-' + o.ttn;
    const label = props.getProperty('CB_IBAN_LABEL') || 'Переказ з поточного рахунку';
    const rec = cbCall_(token, 'post', '/prepayment-receipts', {
      goods: [good],
      payments: [{ type: 'CASHLESS', value: pre, label: label }],
      custom_relation_id: relation,
    });
    const rel = rec.pre_payment_relation_id || rec.prepayment_relation_id || rec.relation_id ||
                (rec.prepayment_relation && rec.prepayment_relation.id) || relation;
    cbWaitReceipt_(token, rec.id);
    const ettn = cbCall_(token, 'post', '/ettn/prepayment', {
      receipt_body: { payments: [{ value: cod, ettn: o.ttn }], relationId: rel },
      receiptRelationId: rel,
      provider: 'novapost',
    });
    return '✓ аванс ' + o.prepay + ' грн (чек ' + cbShort_(rec) + ') + наложка ' + o.cod + ' на ЕН' + (ettn.id ? ' (' + String(ettn.id).slice(0, 8) + ')' : '');
  }

  const ettn = cbCall_(token, 'post', '/ettn', {
    receipt_body: { goods: [good], payments: [{ value: cod, ettn: o.ttn }] },
    provider: 'novapost',
  });
  return '✓ наложка ' + o.cod + ' грн на ЕН' + (ettn.id ? ' (' + String(ettn.id).slice(0, 8) + ')' : '');
}

// Меню «Нова пошта → Checkbox: перевірити підключення»: вхід касира і стан зміни, без чеків
function cbCheck() {
  const ui = SpreadsheetApp.getUi();
  try {
    const token = cbToken_();
    const shift = cbCall_(token, 'get', '/cashier/shift');
    const me = cbCall_(token, 'get', '/cashier/me');
    ui.alert('Checkbox ✓', 'Касир: ' + (me.full_name || me.username || '—') +
      '\nЗміна: ' + (shift && shift.status ? shift.status : 'закрита (відкриється сама при першому чеку)') +
      '\nСтворення чеків: ' + (PropertiesService.getScriptProperties().getProperty('CB_ENABLED') === '1' ? 'УВІМКНЕНО' : 'вимкнено (CB_ENABLED ≠ 1)'),
      ui.ButtonSet.OK);
  } catch (e) {
    ui.alert('Checkbox ⚠', String(e.message || e), ui.ButtonSet.OK);
  }
}


// ---------- API ----------

function cbToken_() {
  const props = PropertiesService.getScriptProperties();
  const cache = CacheService.getScriptCache();
  const cached = cache.get('cb_token');
  if (cached) return cached;
  const pin = props.getProperty('CHECKBOX_PIN');
  const r = pin
    ? cbCall_(null, 'post', '/cashier/signinPinCode', { pin_code: pin })
    : cbCall_(null, 'post', '/cashier/signin', { login: props.getProperty('CHECKBOX_LOGIN'), password: props.getProperty('CHECKBOX_PASSWORD') });
  if (!r.access_token) throw new Error('Checkbox: не вдалося увійти касиром');
  cache.put('cb_token', r.access_token, 6 * 3600);
  return r.access_token;
}

function cbEnsureShift_(token) {
  let s = cbCall_(token, 'get', '/cashier/shift');
  if (s && s.status === 'OPENED') return;
  if (!s || !s.status || s.status === 'CLOSED') s = cbCall_(token, 'post', '/shifts', {});
  for (let i = 0; i < 15; i++) {
    Utilities.sleep(2000);
    s = cbCall_(token, 'get', '/cashier/shift');
    if (s && s.status === 'OPENED') return;
  }
  throw new Error('Checkbox: зміна не відкрилась за 30 с');
}

function cbWaitReceipt_(token, id) {
  if (!id) return;
  for (let i = 0; i < 10; i++) {
    const r = cbCall_(token, 'get', '/receipts/' + id);
    if (r.status === 'DONE') return;
    if (r.status === 'ERROR') throw new Error('Checkbox: чек аванса з помилкою — ' + JSON.stringify(r.transaction || r).slice(0, 200));
    Utilities.sleep(1500);
  }
}

function cbCall_(token, method, path, body) {
  const key = PropertiesService.getScriptProperties().getProperty('CHECKBOX_LICENSE_KEY');
  if (!key) throw new Error('Checkbox: немає CHECKBOX_LICENSE_KEY у Властивостях скрипта');
  const headers = { 'X-Client-Name': CB.CLIENT, 'X-Client-Version': CB.VERSION, 'X-License-Key': key };
  if (token) headers.Authorization = 'Bearer ' + token;
  const opt = { method: method, headers: headers, muteHttpExceptions: true, contentType: 'application/json' };
  if (body !== undefined && method !== 'get') opt.payload = JSON.stringify(body);
  const res = UrlFetchApp.fetch(CB.API + path, opt);
  const code = res.getResponseCode();
  const text = res.getContentText();
  if (code === 401 && token) CacheService.getScriptCache().remove('cb_token');
  if (code >= 400) throw new Error('Checkbox ' + path + ' → ' + code + ': ' + text.slice(0, 300));
  return text ? JSON.parse(text) : {};
}

function cbShort_(r) {
  return r.fiscal_code || (r.id ? String(r.id).slice(0, 8) : '—');
}
