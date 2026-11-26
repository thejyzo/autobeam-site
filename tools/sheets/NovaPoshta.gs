// =====================================================
// Нова пошта → «Відправки НП» → «Общая таблица»
//
// Окремий файл: Код.gs не змінюється. «Продана» ставиться через ВАШ onEdit (той самий код,
// що й при ручному виборі): заливка A:X зеленим, S = сьогодні, T = Q + R.
//
// Встановлення (один раз):
//   1) Налаштування проєкту (шестерня) → Властивості скрипта → додати:
//        NP_API_KEY = API-ключ з бізнес-кабінету НП (Налаштування → Безпека).
//                     Кілька кабінетів — через кому.
//        NP_PHONE   = номер телефону відправника (380…) — для повного статусу.
//   2) Вибрати функцію npSetup → «Выполнить» → дозволити доступ.
//
// Як працює:
//   • кожні 30 хв (і з меню «Нова пошта → Оновити») нові ТТН з кабінету за 14 днів
//     додаються вгору аркуша «Відправки НП»: дата, ТТН, місто, опис, наложка (контроль оплати);
//   • ТТН, які вже є в колонці P «Общей таблицы», позначаються «Вже в обліку (рядок N)»;
//   • вписуєте номер рядка «Общей таблицы» → підставляється позиція (F) і передоплата (Q);
//     ставите ✔ → у рядок пишуться O (дата відправки), P (ТТН), R (наложка), Q (передоплата, якщо була порожня).
//     L не чіпаємо;
//   • чек Checkbox — вручну: стати на рядок з ТТН і меню «Нова пошта → 🧾 Створити чек» (Checkbox.gs);
//   • статуси відстежуються для ВСІХ ТТН з колонки P (і внесених вручну) за останні 45 днів:
//       посилку отримано → L = «Продана» через ваш onEdit;
//       відмова / повернення / припинено зберігання → повідомлення в Telegram (бот моніторингу), L не змінюється.
// =====================================================

const NP = {
  URL: 'https://api.novaposhta.ua/v2.0/json/',
  SHEET: 'Відправки НП',
  MAIN: 'Общая таблица',
  SOLD: 'Продана',
  DAYS_NEW: 14,       // за скільки днів забирати нові ТТН з кабінету
  DAYS_TRACK: 45,     // скільки днів після відправки стежити за статусом
  // колонки аркуша «Відправки НП»
  C_OK: 1, C_STATE: 2, C_DATE: 3, C_TTN: 4, C_CITY: 5, C_DESC: 6, C_COD: 7, C_ROW: 8, C_NAME: 9, C_PRE: 10, C_STATUS: 11, C_CB: 12, C_CODE: 13, C_ALERT: 14,
  NCOL: 14,
  HEAD: ['✔', 'Стан', 'Дата', 'ТТН', 'Місто', 'Опис (НП)', 'Наложка, грн', 'Рядок «Общей»', 'Позиція (F)', 'Передоплата, грн (Q)', 'Статус НП', 'Checkbox', 'Код статусу', 'Сповіщено'],
  // «Общая таблица»
  M_F: 6, M_L: 12, M_O: 15, M_P: 16, M_Q: 17, M_R: 18,
  S_NEW: 'Новий',
  S_DONE: 'Перенесено ✓',
  S_HAVE: 'Вже в обліку',
  S_SKIP: 'Пропущено',
  // коди статусів НП
  RECEIVED: [9, 10, 11, 106],
  PROBLEM: [102, 103, 105, 108, 111],
  FINAL: [2, 3, 9, 10, 11, 106, 102, 103, 105, 108, 111],
};


// =====================================================
// ВСТАНОВЛЕННЯ
// =====================================================

function npSetup() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  ScriptApp.getProjectTriggers()
    .filter(t => ['npOnEdit', 'npSync', 'npOnOpen'].indexOf(t.getHandlerFunction()) >= 0)
    .forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('npOnEdit').forSpreadsheet(ss).onEdit().create();
  ScriptApp.newTrigger('npOnOpen').forSpreadsheet(ss).onOpen().create();
  ScriptApp.newTrigger('npSync').timeBased().everyMinutes(30).create();
  npPrepareSheet_();
  if (!npKeys_().length) throw new Error('Тригери встановлено. Додайте NP_API_KEY і NP_PHONE у Властивості скрипта і запустіть npSync.');
  npSync();
}

function npOnOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Нова пошта')
    .addItem('🔄 Оновити ТТН і статуси', 'npSync')
    .addItem('🙈 Пропустити вибрані рядки', 'npSkip')
    .addItem('↩️ Повернути пропущені (вибрані)', 'npUnskip')
    .addSeparator()
    .addItem('🧾 Створити чек (вибраний рядок)', 'cbCreateForSelection') // з Checkbox.gs
    .addItem('🔌 Checkbox: перевірити підключення', 'cbCheck')
    .addToUi();
}

function npPrepareSheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sh = ss.getSheetByName(NP.SHEET) || ss.insertSheet(NP.SHEET);
  const head = sh.getRange(1, 1, 1, NP.NCOL);
  if (head.getValues()[0].join('|') !== NP.HEAD.join('|')) {
    head.setValues([NP.HEAD]).setFontWeight('bold').setBackground('#e31e24').setFontColor('#ffffff')
      .setVerticalAlignment('middle').setWrap(true);
    sh.setFrozenRows(1);
    [34, 170, 82, 130, 150, 220, 90, 75, 260, 95, 260, 240, 50, 60].forEach((w, i) => sh.setColumnWidth(i + 1, w));
    sh.hideColumns(NP.C_CODE, 2);
  }
  return sh;
}


// =====================================================
// СИНХРОНІЗАЦІЯ: нові ТТН + статуси
// =====================================================

function npSync() {
  const lock = LockService.getDocumentLock();
  if (!lock.tryLock(30000)) return; // наступний запуск через 30 хв
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const sh = npPrepareSheet_();
    const main = ss.getSheetByName(NP.MAIN);
    const inMain = npMainIndex_(main);
    npLoadNew_(sh, inMain);
    npFillPre_(sh, inMain);
    npTrack_(ss, sh, main, inMain);
  } finally {
    lock.releaseLock();
  }
}

// Передоплата (J) = Q «Общей таблицы» для всіх рядків, прив'язаних до рядка (оновлюється при кожній синхронізації)
function npFillPre_(sh, inMain) {
  const last = sh.getLastRow();
  if (last < 2) return;
  const rows = sh.getRange(2, NP.C_ROW, last - 1, 1).getValues();
  const pre = sh.getRange(2, NP.C_PRE, last - 1, 1).getValues();
  const st = sh.getRange(2, NP.C_STATE, last - 1, 1).getValues();
  let changed = false;
  rows.forEach((r, i) => {
    const m = Number(r[0]);
    if (!m || !(m in inMain.name)) return;
    const want = inMain.pre[m] || '';
    // у ще не перенесеному рядку не стираємо передоплату, яку ви вписали вручну (вона піде в Q при ✔)
    if (want === '' && String(st[i][0]).indexOf(NP.S_HAVE) !== 0 && String(st[i][0]).indexOf(NP.S_DONE) !== 0) return;
    if (String(pre[i][0]) !== String(want)) { pre[i][0] = want; changed = true; }
  });
  if (changed) sh.getRange(2, NP.C_PRE, last - 1, 1).setValues(pre);
}

// Нові ТТН з кабінету(ів) → вгору аркуша
function npLoadNew_(sh, inMain) {
  const last = sh.getLastRow();
  const have = {};
  if (last > 1) sh.getRange(2, NP.C_TTN, last - 1, 1).getValues().forEach(r => { if (r[0]) have[String(r[0]).trim()] = true; });

  const to = new Date(), from = new Date(Date.now() - NP.DAYS_NEW * 86400000);
  const fmt = d => Utilities.formatDate(d, 'Europe/Kyiv', 'dd.MM.yyyy');
  const fresh = [];
  npKeys_().forEach(key => {
    for (let page = 1; page <= 10; page++) {
      const r = npCall_(key, 'InternetDocument', 'getDocumentList', {
        DateTimeFrom: fmt(from), DateTimeTo: fmt(to), GetFullList: '1', Page: String(page),
      });
      const docs = r.data || [];
      docs.forEach(d => {
        const ttn = String(d.IntDocNumber || '').trim();
        if (!/^\d{14}$/.test(ttn) || have[ttn]) return;
        if (String(d.StateId) === '2' || /видал/i.test(String(d.StateName || ''))) return; // видалені
        have[ttn] = true;
        fresh.push(d);
      });
      if (docs.length < 100) break;
    }
  });
  if (!fresh.length) return;

  fresh.sort((a, b) => String(b.DateTime).localeCompare(String(a.DateTime)));
  const rows = fresh.map(d => {
    const ttn = String(d.IntDocNumber).trim();
    const cod = npCod_(d);
    const date = npDate_(d.DateTime);
    const mainRow = inMain.byTtn[ttn];
    return {
      v: [false, mainRow ? NP.S_HAVE + ' (рядок ' + mainRow + ')' : NP.S_NEW, date, ttn,
          String(d.CityRecipientDescription || d.CityRecipient || d.RecipientCityName || ''),
          String(d.Description || ''), cod || '', mainRow || '', mainRow ? inMain.name[mainRow] || '' : '', mainRow ? inMain.pre[mainRow] || '' : '',
          String(d.StateName || ''), '', '', ''],
      have: !!mainRow,
    };
  });
  sh.insertRowsBefore(2, rows.length);
  const rng = sh.getRange(2, 1, rows.length, NP.NCOL);
  rng.setValues(rows.map(o => o.v)).setBackground(null).setFontColor('#000000').setFontWeight('normal');
  sh.getRange(2, NP.C_DATE, rows.length, 1).setNumberFormat('dd.MM.yyyy');
  sh.getRange(2, NP.C_TTN, rows.length, 1).setNumberFormat('@');
  rows.forEach((o, i) => {
    const row = 2 + i;
    if (o.have) sh.getRange(row, NP.C_OK).clearDataValidations().setValue('');
    else sh.getRange(row, NP.C_OK).insertCheckboxes();
    npPaint_(sh, row, o.v[NP.C_STATE - 1]);
  });
}

// Статуси: усі ТТН з P «Общей таблицы» (останні 45 днів, ще не «Продана») + рядки аркуша без кінцевого статусу
function npTrack_(ss, sh, main, inMain) {
  const phone = npPhone_();
  const keys = npKeys_();
  if (!keys.length) return;

  const want = {}; // ttn → {mainRow?, sheetRow?}
  Object.keys(inMain.byTtn).forEach(ttn => {
    const row = inMain.byTtn[ttn];
    if (inMain.sold[row]) return;
    const o = inMain.sent[row];
    if (o && Date.now() - o.getTime() > NP.DAYS_TRACK * 86400000) return;
    want[ttn] = { mainRow: row };
  });
  const last = sh.getLastRow();
  const vals = last > 1 ? sh.getRange(2, 1, last - 1, NP.NCOL).getValues() : [];
  vals.forEach((v, i) => {
    const ttn = String(v[NP.C_TTN - 1]).trim();
    const code = Number(v[NP.C_CODE - 1]);
    if (!ttn || NP.FINAL.indexOf(code) >= 0) return;
    if (String(v[NP.C_STATE - 1]).indexOf(NP.S_SKIP) === 0) return; // пропущені не відстежуємо
    const d = v[NP.C_DATE - 1];
    if (d instanceof Date && Date.now() - d.getTime() > NP.DAYS_TRACK * 86400000) return;
    want[ttn] = want[ttn] || {};
    want[ttn].sheetRow = i + 2;
  });
  // сповіщення для ТТН з «Общей», яких нема на аркуші — пам'ять у властивостях
  const props = PropertiesService.getScriptProperties();
  const alerted = JSON.parse(props.getProperty('NP_ALERTED') || '{}');

  const list = Object.keys(want);
  for (let i = 0; i < list.length; i += 100) {
    const chunk = list.slice(i, i + 100);
    const r = npCall_(keys[0], 'TrackingDocument', 'getStatusDocuments', {
      Documents: chunk.map(n => ({ DocumentNumber: n, Phone: phone })),
    });
    (r.data || []).forEach(d => {
      const ttn = String(d.Number || '').trim();
      const w = want[ttn];
      if (!w) return;
      const code = Number(d.StatusCode);
      const status = String(d.Status || '');

      if (w.sheetRow) {
        sh.getRange(w.sheetRow, NP.C_STATUS).setValue(status);
        sh.getRange(w.sheetRow, NP.C_CODE).setValue(code);
      }
      const mainRow = w.mainRow || inMain.byTtn[ttn];

      // отримано → «Продана» через onEdit власника
      if (NP.RECEIVED.indexOf(code) >= 0 && mainRow && !inMain.sold[mainRow]) {
        npMarkSold_(ss, main, mainRow, ttn);
        inMain.sold[mainRow] = true;
      }
      // проблема → одне сповіщення
      if (NP.PROBLEM.indexOf(code) >= 0 && !alerted[ttn]) {
        const name = mainRow ? inMain.name[mainRow] : '';
        npNotify_('⚠️ <b>Нова пошта: ' + monitorEsc_(status) + '</b>\nТТН ' + ttn +
          (mainRow ? '\nРядок ' + mainRow + (name ? ': ' + monitorEsc_(name) : '') : '') +
          '\nСтатус у «Общей таблице» не змінено.');
        alerted[ttn] = Date.now();
        if (w.sheetRow) sh.getRange(w.sheetRow, NP.C_STATUS).setBackground('#f4cccc');
      }
    });
  }
  // чистимо старі сповіщення (> 60 днів)
  Object.keys(alerted).forEach(k => { if (Date.now() - alerted[k] > 60 * 86400000) delete alerted[k]; });
  props.setProperty('NP_ALERTED', JSON.stringify(alerted));
}

// Ставить L = «Продана» і викликає onEdit власника з тими ж даними, що й при ручному виборі.
function npMarkSold_(ss, main, row, ttn) {
  if (String(main.getRange(row, NP.M_P).getValue()).trim() !== ttn) return; // рядок зсунули — не чіпаємо
  const cell = main.getRange(row, NP.M_L);
  const old = cell.getValue();
  if (old === NP.SOLD) return;
  cell.setValue(NP.SOLD);
  SpreadsheetApp.flush();
  onEdit({ range: cell, value: NP.SOLD, oldValue: old, source: ss }); // Код.gs: заливка A:X, S = сьогодні, T = Q + R
  SpreadsheetApp.flush();
  console.log('Продана: рядок ' + row + ', ТТН ' + ttn);
}


// =====================================================
// ✔ і номер рядка
// =====================================================

function npOnEdit(e) {
  if (!e || !e.range) return;
  const sh = e.range.getSheet();
  if (sh.getName() !== NP.SHEET) return;
  const c1 = e.range.getColumn(), c2 = e.range.getLastColumn();
  const touchesRow = c1 <= NP.C_ROW && c2 >= NP.C_ROW;
  const touchesOk = c1 <= NP.C_OK && c2 >= NP.C_OK;
  if (!touchesRow && !touchesOk) return;

  const lock = LockService.getDocumentLock();
  if (!lock.tryLock(30000)) {
    SpreadsheetApp.getActive().toast('Зайнято, повторіть через кілька секунд', 'Нова пошта', 5);
    return;
  }
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const main = ss.getSheetByName(NP.MAIN);
    for (let row = Math.max(2, e.range.getRow()); row <= e.range.getLastRow(); row++) {
      const v = sh.getRange(row, 1, 1, NP.NCOL).getValues()[0];
      const state = String(v[NP.C_STATE - 1]);
      if (state.indexOf(NP.S_SKIP) === 0) {
        if (touchesOk && v[NP.C_OK - 1] === true) sh.getRange(row, NP.C_OK).setValue(false);
        continue;
      }
      if (state.indexOf(NP.S_DONE) === 0 || state.indexOf(NP.S_HAVE) === 0) {
        if (touchesOk && state.indexOf(NP.S_DONE) === 0 && v[NP.C_OK - 1] !== true) sh.getRange(row, NP.C_OK).setValue(true);
        continue;
      }
      if (touchesRow) npFillFromRow_(sh, main, row, v);
      if (touchesOk && sh.getRange(row, NP.C_OK).getValue() === true) {
        npTransfer_(ss, sh, main, row, sh.getRange(row, 1, 1, NP.NCOL).getValues()[0]);
      }
    }
  } finally {
    lock.releaseLock();
  }
}

// Меню: «Пропустити» / «Повернути» для виділених рядків аркуша «Відправки НП» (можна кілька рядків)
function npSkip() { npSkipToggle_(true); }
function npUnskip() { npSkipToggle_(false); }

function npSkipToggle_(skip) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sh = ss.getActiveSheet();
  if (sh.getName() !== NP.SHEET) {
    SpreadsheetApp.getUi().alert('Виділіть рядки на аркуші «' + NP.SHEET + '».');
    return;
  }
  const lock = LockService.getDocumentLock();
  if (!lock.tryLock(30000)) return;
  let n = 0;
  try {
    const ranges = sh.getActiveRangeList() ? sh.getActiveRangeList().getRanges() : [sh.getActiveRange()];
    ranges.forEach(rg => {
      for (let row = Math.max(2, rg.getRow()); row <= rg.getLastRow(); row++) {
        const state = String(sh.getRange(row, NP.C_STATE).getValue());
        if (!sh.getRange(row, NP.C_TTN).getValue()) continue;
        if (skip && (state === NP.S_NEW || state.indexOf('⚠') === 0)) {
          sh.getRange(row, NP.C_OK).clearDataValidations().setValue('');
          sh.getRange(row, NP.C_STATE).setValue(NP.S_SKIP);
          npPaint_(sh, row, NP.S_SKIP);
          n++;
        } else if (!skip && state.indexOf(NP.S_SKIP) === 0) {
          sh.getRange(row, NP.C_STATE).setValue(NP.S_NEW);
          sh.getRange(row, 1, 1, NP.NCOL - 2).setBackground(null).setFontColor('#000000');
          sh.getRange(row, NP.C_OK).insertCheckboxes();
          n++;
        }
      }
    });
  } finally {
    lock.releaseLock();
  }
  ss.toast((skip ? 'Пропущено: ' : 'Повернуто: ') + n + (n ? '' : ' (пропустити можна лише «Новий»; перенесені й «Вже в обліку» не змінюються)'), 'Нова пошта', 6);
}

// вписали номер рядка → позиція (F) і передоплата (Q) з «Общей таблицы»
function npFillFromRow_(sh, main, row, v) {
  const r = Number(v[NP.C_ROW - 1]);
  if (!Number.isInteger(r) || r < 2 || r > main.getLastRow()) {
    sh.getRange(row, NP.C_NAME).setValue(v[NP.C_ROW - 1] ? '⚠ немає такого рядка' : '');
    return;
  }
  const m = main.getRange(r, 1, 1, NP.M_R).getValues()[0];
  sh.getRange(row, NP.C_NAME).setValue(String(m[NP.M_F - 1]) + (m[NP.M_P - 1] ? '  ⚠ вже є ТТН ' + m[NP.M_P - 1] : ''));
  if (!v[NP.C_PRE - 1] && Number(m[NP.M_Q - 1])) sh.getRange(row, NP.C_PRE).setValue(Number(m[NP.M_Q - 1]));
}

function npTransfer_(ss, sh, main, row, v) {
  const warn = msg => {
    sh.getRange(row, NP.C_OK).setValue(false);
    sh.getRange(row, NP.C_STATE).setValue('⚠ ' + msg);
    npPaint_(sh, row, '⚠');
  };
  const ttn = String(v[NP.C_TTN - 1]).trim();
  const r = Number(v[NP.C_ROW - 1]);
  if (!Number.isInteger(r) || r < 2 || r > main.getLastRow()) return warn('Впишіть номер рядка «Общей таблицы»');

  const m = main.getRange(r, 1, 1, NP.M_R).getValues()[0];
  const p = String(m[NP.M_P - 1]).trim();
  if (p && p !== ttn) return warn('У рядку ' + r + ' вже ТТН ' + p);
  if (!String(m[NP.M_F - 1]).trim()) return warn('Рядок ' + r + ' порожній');
  const other = npMainIndex_(main).byTtn[ttn];
  if (other && other !== r) return warn('Ця ТТН уже в рядку ' + other);

  const cod = Number(v[NP.C_COD - 1]) || 0;
  const pre = Number(v[NP.C_PRE - 1]) || 0;
  const date = v[NP.C_DATE - 1] instanceof Date ? v[NP.C_DATE - 1] : new Date();

  // O, P, R (+ Q якщо порожня). Порожні наявні значення не перезаписуємо чужими.
  if (!m[NP.M_O - 1]) main.getRange(r, NP.M_O).setValue(date).setNumberFormat('dd.MM.yyyy');
  main.getRange(r, NP.M_P).setNumberFormat('@').setValue(ttn);
  if (pre && !Number(m[NP.M_Q - 1])) main.getRange(r, NP.M_Q).setValue(pre);
  if (cod && !Number(m[NP.M_R - 1])) main.getRange(r, NP.M_R).setValue(cod);
  sh.getRange(row, NP.C_STATE).setValue(NP.S_DONE + ' рядок ' + r);
  sh.getRange(row, NP.C_NAME).setValue(String(m[NP.M_F - 1]));
  npPaint_(sh, row, NP.S_DONE);
  SpreadsheetApp.flush();
  // чек Checkbox — лише вручну: меню «Нова пошта → 🧾 Створити чек» (Checkbox.gs)
  ss.toast(String(m[NP.M_F - 1]) + ' → рядок ' + r + '\nЧек: меню «Нова пошта → 🧾 Створити чек»', 'НП: перенесено', 8);
}


// =====================================================
// ДОПОМІЖНЕ
// =====================================================

// «Общая таблица»: ТТН у P → рядок; позиції; продані; дати відправки
function npMainIndex_(main) {
  const last = main.getLastRow();
  const vals = main.getRange(1, 1, last, NP.M_R).getValues();
  const idx = { byTtn: {}, name: {}, sold: {}, sent: {}, pre: {} };
  for (let i = 1; i < vals.length; i++) {
    const row = i + 1, v = vals[i];
    const ttn = String(v[NP.M_P - 1]).replace(/\s/g, '');
    idx.name[row] = String(v[NP.M_F - 1]);
    idx.pre[row] = Number(v[NP.M_Q - 1]) || '';
    if (String(v[NP.M_L - 1]).trim() === NP.SOLD) idx.sold[row] = true;
    if (v[NP.M_O - 1] instanceof Date) idx.sent[row] = v[NP.M_O - 1];
    if (/^\d{14}$/.test(ttn)) idx.byTtn[ttn] = row;
  }
  return idx;
}

function npCall_(key, model, method, props) {
  const res = UrlFetchApp.fetch(NP.URL, {
    method: 'post', contentType: 'application/json', muteHttpExceptions: true,
    payload: JSON.stringify({ apiKey: key, modelName: model, calledMethod: method, methodProperties: props || {} }),
  });
  const j = JSON.parse(res.getContentText() || '{}');
  if (!j.success) console.warn('НП ' + model + '.' + method + ': ' + JSON.stringify(j.errors || j).slice(0, 300));
  return j;
}

function npKeys_() {
  return String(PropertiesService.getScriptProperties().getProperty('NP_API_KEY') || '')
    .split(',').map(s => s.trim()).filter(Boolean);
}
function npPhone_() {
  return String(PropertiesService.getScriptProperties().getProperty('NP_PHONE') || '').replace(/\D/g, '');
}

// Наложка: контроль оплати (AfterpaymentOnGoodsCost) або класичний грошовий переказ (BackwardDelivery…)
function npCod_(d) {
  const cands = [d.AfterpaymentOnGoodsCost, d.BackwardDeliveryMoney, d.RedeliverySum, d.RedeliveryAmount];
  (d.BackwardDeliveryData || []).forEach(b => { if (/money|гроші/i.test(String(b.CargoType || b.PayerType || ''))) cands.push(b.RedeliveryString); });
  return cands.map(Number).filter(x => x > 0).reduce((a, b) => Math.max(a, b), 0);
}

// «2026-11-21 10:22:11» або «21.11.2026 10:22» → Date (без часу)
function npDate_(s) {
  s = String(s || '');
  let m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (m) return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  m = s.match(/^(\d{2})\.(\d{2})\.(\d{4})/);
  if (m) return new Date(Number(m[3]), Number(m[2]) - 1, Number(m[1]));
  return new Date();
}

function npPaint_(sh, row, state) {
  const r = sh.getRange(row, 1, 1, NP.NCOL - 2);
  if (String(state).indexOf(NP.S_DONE) === 0) r.setBackground('#d9ead3');
  else if (String(state).indexOf(NP.S_HAVE) === 0 || String(state).indexOf(NP.S_SKIP) === 0) r.setBackground('#eeeeee').setFontColor('#777777');
  else if (String(state).indexOf('⚠') === 0) sh.getRange(row, NP.C_STATE).setBackground('#f4cccc');
  else r.setBackground(null);
}

// Telegram через той самий канал, що й монітор eBay (ключ EBAY_FEED_KEY)
function npNotify_(text) {
  const key = PropertiesService.getScriptProperties().getProperty('EBAY_FEED_KEY');
  if (!key) return false;
  try { return monitorSend_(key, text, ''); } catch (e) { console.warn('Telegram: ' + e); return false; }
}
