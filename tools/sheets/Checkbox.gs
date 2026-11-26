// =====================================================
// Checkbox: чек аванса (оплата на IBAN) + прив'язка залишку наложки до ЕН Нової пошти
//
// ЛИШЕ ВРУЧНУ: стати на будь-яку клітинку рядка з ТТН («Общая таблица» або «Відправки НП») →
// меню «Нова пошта → 🧾 Створити чек» → вікно з сумами → «Так».
// Те саме, що ви робите вручну: аванс (передоплата на рахунок ФОП) → чек одразу;
// залишок наложки прив'язується до ЕН → Checkbox сам видає чек, коли клієнт забере посилку.
// Створювати ДО того, як клієнт забере посилку. Одна ТТН = один чек (повтор не створюється).
//
// Властивості скрипта (вводите самі):
//   CHECKBOX_LICENSE_KEY = ключ ліцензії каси (my.checkbox.ua → Каси → каса → «Ключ ліцензії»)
//   CHECKBOX_LOGIN / CHECKBOX_PASSWORD = логін і пароль касира  (або CHECKBOX_PIN = PIN-код касира)
//   Товар у чеку — за каталогом Checkbox (CB_GOODS нижче): фара=1, ліхтар=2, блок=23, скло=24, маска=25, корпус=33
//   CB_IBAN_LABEL       ← назва оплати для аванса (необов'язково), за замовчуванням «Інтернет банкінг» (так друкує Checkbox для типу «За реквізитами (IBAN)»)
//
// Суми: аванс = Q рядка «Общей таблицы»; наложка = з ТТН (аркуш «Відправки НП»), якщо там є, інакше R.
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

// Меню «Нова пошта → 🧾 Створити чек (вибраний рядок)»
function cbCreateForSelection() {
  const ui = SpreadsheetApp.getUi();
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getActiveSheet();
  const cur = sheet.getActiveRange().getRow();
  const main = ss.getSheetByName(NP.MAIN);
  const np = ss.getSheetByName(NP.SHEET);

  // ТТН і рядок «Общей таблицы»
  let ttn = '', mainRow = 0;
  if (sheet.getName() === NP.MAIN && cur > 1) {
    mainRow = cur;
    ttn = String(main.getRange(cur, NP.M_P).getValue()).replace(/\s/g, '');
  } else if (sheet.getName() === NP.SHEET && cur > 1) {
    ttn = String(np.getRange(cur, NP.C_TTN).getValue()).replace(/\s/g, '');
    mainRow = npMainIndex_(main).byTtn[ttn] || Number(np.getRange(cur, NP.C_ROW).getValue()) || 0;
  } else {
    ui.alert('Станьте на рядок з ТТН в «Общей таблице» або на аркуші «Відправки НП».');
    return;
  }
  if (!/^\d{14}$/.test(ttn)) { ui.alert('У цьому рядку немає ТТН (14 цифр).'); return; }
  if (!mainRow) { ui.alert('ТТН ' + ttn + ' ще не прив\'язана до рядка «Общей таблицы». Впишіть рядок і поставте ✔ на «Відправки НП».'); return; }

  const props = PropertiesService.getScriptProperties();
  const done = JSON.parse(props.getProperty('CB_DONE') || '{}');
  if (done[ttn]) { ui.alert('Чек для ТТН ' + ttn + ' вже створено:\n' + done[ttn]); return; }

  const m = main.getRange(mainRow, 1, 1, NP.M_R).getValues()[0];
  const name = String(m[NP.M_F - 1]).trim();
  const prepay = Number(m[NP.M_Q - 1]) || 0;
  const rTable = Number(m[NP.M_R - 1]) || 0;
  // наложка з ТТН (аркуш «Відправки НП»)
  let npRow = 0, codTtn = 0;
  if (np && np.getLastRow() > 1) {
    const col = np.getRange(2, NP.C_TTN, np.getLastRow() - 1, 1).getValues();
    for (let i = 0; i < col.length; i++) if (String(col[i][0]).trim() === ttn) { npRow = i + 2; break; }
    if (npRow) codTtn = Number(np.getRange(npRow, NP.C_COD).getValue()) || 0;
  }
  const cod = codTtn || rTable;
  if (!name) { ui.alert('Рядок ' + mainRow + ': порожня позиція (F).'); return; }
  if (!(cod > 0)) { ui.alert('Немає наложки (ні в ТТН, ні в R) — чек на ЕН не потрібен.'); return; }

  const lines = [
    'Рядок ' + mainRow + ': ' + name,
    'Товар у чеку: «' + cbGood_(name).name + '» (код ' + cbGood_(name).code + ')',
    'ТТН ' + ttn,
    '',
    'Аванс (IBAN, чек зараз): ' + cbMoney_(prepay),
    'Наложка на ЕН (чек при отриманні): ' + cbMoney_(cod),
    'Разом у чеку: ' + cbMoney_(prepay + cod),
  ];
  if (codTtn && rTable && codTtn !== rTable) lines.push('', '⚠ У ТТН наложка ' + cbMoney_(codTtn) + ', а в R — ' + cbMoney_(rTable) + '. У чек іде сума з ТТН.');
  if (!prepay) lines.push('', 'Q порожня → без аванса, уся сума на ЕН.');
  lines.push('', 'Створити чек?');
  if (ui.alert('🧾 Checkbox', lines.join('\n'), ui.ButtonSet.YES_NO) !== ui.Button.YES) return;

  const lock = LockService.getDocumentLock();
  if (!lock.tryLock(30000)) { ui.alert('Зайнято, спробуйте ще раз за кілька секунд.'); return; }
  let note;
  try {
    note = cbForShipment_({ ttn: ttn, name: name, row: mainRow, prepay: prepay, cod: cod });
    done[ttn] = Utilities.formatDate(new Date(), 'Europe/Kyiv', 'dd.MM.yyyy HH:mm') + ' — ' + note;
    props.setProperty('CB_DONE', JSON.stringify(done));
  } catch (e) {
    note = '⚠ ' + String(e.message || e).slice(0, 300);
  } finally {
    lock.releaseLock();
  }
  if (npRow) np.getRange(npRow, NP.C_CB).setValue(note);
  ui.alert(note.indexOf('⚠') === 0 ? 'Checkbox ⚠' : 'Checkbox ✓', note, ui.ButtonSet.OK);
}

// Товар у чеку — з каталогу Checkbox власника (26.11.2026), за назвою позиції (F):
//   1  автомобільна фара (вживана)   — за замовчуванням
//   23 Блок для фари (вживаний)      — «блок»
//   24 Скло для фари                 — «скло» / «стекло»
//   25 Маска декоративна для фари    — «маска»
//   2  Ліхтар автомобільний (вживаний) — «ліхтар» / «фонарь» / «фонар»
//   33 Корпус для фари               — «корпус»
const CB_GOODS = [
  { re: /блок/i, code: '23', name: 'Блок для фари (вживаний)' },
  { re: /скло|стекло/i, code: '24', name: 'Скло для фари' },
  { re: /маск/i, code: '25', name: 'Маска декоративна для фари' },
  { re: /ліхтар|фонар/i, code: '2', name: 'Ліхтар автомобільний (вживаний)' },
  { re: /корпус/i, code: '33', name: 'Корпус для фари' },
];
function cbGood_(position) {
  const p = String(position || '');
  for (let i = 0; i < CB_GOODS.length; i++) if (CB_GOODS[i].re.test(p)) return CB_GOODS[i];
  return { code: '1', name: 'автомобільна фара (вживана)' };
}

function cbMoney_(x) {
  return Number(x || 0).toLocaleString('uk-UA') + ' грн';
}

function cbForShipment_(o) {
  const props = PropertiesService.getScriptProperties();
  if (!(o.cod > 0)) return 'без наложки — чек не створюю';
  const total = Math.round((o.prepay + o.cod) * 100);
  const pre = Math.round(o.prepay * 100), cod = Math.round(o.cod * 100);
  const g = cbGood_(o.name);
  const good = { good: { code: g.code, name: g.name, price: total }, quantity: 1000, is_return: false };

  const token = cbToken_();
  cbEnsureShift_(token);

  if (pre > 0) {
    const relation = 'AB-' + o.ttn;
    const label = props.getProperty('CB_IBAN_LABEL') || 'Інтернет банкінг';
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
      '\nЧеки: вручну — меню «Нова пошта → 🧾 Створити чек»',
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
