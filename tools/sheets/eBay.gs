// =====================================================
// eBay → «Входящие операции» → «Общая таблица»
//
// Окремий файл: Код.gs і "Продана".gs не змінюються.
// Встановлення (один раз):
//   1) Налаштування проєкту (шестерня) → Властивості скрипта → додати
//      EBAY_FEED_KEY = ключ із консолі хостингу (php ~/autobeam_repo/tools/setup_api.php sheets)
//   2) Тут вибрати функцію ebaySetup → «Выполнить» → дозволити доступ.
//
// Як працює:
//   • кожні 6 годин (і з меню «eBay → Оновити зараз») нові покупки eBay
//     додаються вгору аркуша «Входящие операции», одна покупка = одна фара (qty 2 → 2 рядки);
//   • сума = скільки eBay фактично списав (ціна + доставка + податок), поділена на штуки;
//   • позиція DATA підбирається автоматично, якщо збіг однозначний; інакше — порожньо,
//     а в колонці «Варіанти DATA» підказки; вибираєте самі зі списку;
//   • ставите ✔ → рядок переноситься в перший вільний рядок «Общей таблицы»:
//     D посилання, E кабінет (з кольором), F позиція, G дата, H сума; трек США — приміткою на D;
//   • покупки, які вже є в «Общей таблице» (той самий лот, ±3 дні), позначаються «Вже в обліку»
//     і не переносяться повторно. Скасовані на eBay — «Скасовано», без галочки.
// =====================================================

const EB = {
  FEED_URL: 'https://autobeam.com.ua/admin/ebay_feed.php',
  IN: 'Входящие операции',
  MAIN: 'Общая таблица',
  DATA: 'DATA',
  // колонки «Входящих»
  C_OK: 1, C_STATE: 2, C_KAB: 3, C_DATE: 4, C_TITLE: 5, C_NAME: 6, C_SUM: 7, C_LINK: 8, C_TRACK: 9, C_STATUS: 10, C_HINT: 11, C_ID: 12, C_ROW: 13, C_PHOTO: 14,
  NCOL: 14,
  HEAD: ['✔', 'Стан', 'Кабінет', 'Дата', 'Лот eBay', 'Позиція DATA', 'Сума, $', 'Посилання', 'Трек США', 'Статус eBay', 'Варіанти DATA', 'ID', 'Рядок', 'Фото (Google Диск)'],
  // кольори кабінетів як в «Общей таблице»
  KAB: {
    'КАБ1': { bg: '#00ff00', fg: '#434343' },
    'КАБ2': { bg: '#ff0000', fg: '#434343' },
    'КАБ3': { bg: '#ff00ff', fg: '#000000' },
    'КАБ4': { bg: '#ffff00', fg: '#434343' },
  },
  S_NEW: 'Новий',
  S_DONE: 'Перенесено ✓',
  S_HAVE: 'Вже в обліку',
  S_CANCEL: 'Скасовано eBay',
};


// =====================================================
// ВСТАНОВЛЕННЯ
// =====================================================

function ebaySetup() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();

  // тригери (без дублів)
  ScriptApp.getProjectTriggers()
    .filter(t => ['ebayOnEdit', 'ebaySync', 'ebayOnOpen'].indexOf(t.getHandlerFunction()) >= 0)
    .forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('ebayOnEdit').forSpreadsheet(ss).onEdit().create();
  ScriptApp.newTrigger('ebayOnOpen').forSpreadsheet(ss).onOpen().create();
  ScriptApp.newTrigger('ebaySync').timeBased().everyHours(6).create();

  ebayPrepareSheet_();

  if (!PropertiesService.getScriptProperties().getProperty('EBAY_FEED_KEY')) {
    throw new Error('Тригери встановлено. Додайте EBAY_FEED_KEY у Властивості скрипта і запустіть ebaySync.');
  }
  ebaySync();
}

function ebayOnOpen() {
  SpreadsheetApp.getUi()
    .createMenu('eBay')
    .addItem('🔄 Оновити покупки зараз', 'ebaySync')
    .addItem('📥 Завантажити за 90 днів', 'ebaySync90')
    .addItem('✂️ Розділити вибраний рядок на пару (ліва + права)', 'ebaySplitPair')
    .addItem('📷 Завантажити фото лотів', 'ebayPhotos')
    .addToUi();
}

function ebayPrepareSheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sh = ss.getSheetByName(EB.IN) || ss.insertSheet(EB.IN);
  const head = sh.getRange(1, 1, 1, EB.NCOL);
  if (head.getValues()[0].join('|') !== EB.HEAD.join('|')) {
    head.setValues([EB.HEAD]).setFontWeight('bold').setBackground('#ff9900').setFontColor('#000000')
      .setVerticalAlignment('middle').setWrap(true);
    sh.setFrozenRows(1);
    const widths = [34, 150, 60, 82, 330, 260, 70, 70, 190, 160, 330, 60, 50, 120];
    widths.forEach((w, i) => sh.setColumnWidth(i + 1, w));
    sh.hideColumns(EB.C_ID, 2);
  }
}


// =====================================================
// ЗАВАНТАЖЕННЯ ПОКУПОК
// =====================================================

function ebaySync90() { ebaySync_(90); }
function ebaySync() { ebaySync_(30); }

function ebaySync_(days) {
  const lock = LockService.getDocumentLock();
  if (!lock.tryLock(30000)) return;
  try {
    const key = PropertiesService.getScriptProperties().getProperty('EBAY_FEED_KEY');
    if (!key) throw new Error('Немає EBAY_FEED_KEY у Властивостях скрипта');

    const resp = UrlFetchApp.fetch(EB.FEED_URL + '?days=' + days, {
      headers: { 'X-AB-Key': key }, muteHttpExceptions: true,
    });
    if (resp.getResponseCode() !== 200) throw new Error('Сервер: ' + resp.getResponseCode() + ' ' + resp.getContentText().slice(0, 200));
    const feed = JSON.parse(resp.getContentText()).rows || [];

    const ss = SpreadsheetApp.getActiveSpreadsheet();
    ebayPrepareSheet_();
    const sh = ss.getSheetByName(EB.IN);
    const main = ss.getSheetByName(EB.MAIN);

    // що вже є у «Входящих»
    const last = sh.getLastRow();
    const cur = last > 1 ? sh.getRange(2, 1, last - 1, EB.NCOL).getValues() : [];
    const byId = {};
    const claimed = {};
    cur.forEach((r, i) => {
      if (r[EB.C_ID - 1]) byId[r[EB.C_ID - 1]] = i + 2;
      String(r[EB.C_ROW - 1]).split(',').filter(x => x.trim()).forEach(x => claimed[Number(x)] = true);
    });

    const hist = ebayMainIndex_(main);
    const data = ebayDataNames_(ss);

    // оновлення існуючих: трек і статус
    feed.forEach(f => [f.id, f.id + 'L', f.id + 'R'].forEach(id => {
      const row = byId[id];
      if (!row) return;
      const r = cur[row - 2];
      if (String(r[EB.C_TRACK - 1]) !== f.tracking) {
        sh.getRange(row, EB.C_TRACK).setValue(f.tracking);
        const mrow = Number(r[EB.C_ROW - 1]);
        if (f.tracking && mrow && String(r[EB.C_STATE - 1]).indexOf(EB.S_DONE) === 0) ebaySetNote_(main, mrow, r[EB.C_LINK - 1], f.tracking, r[EB.C_PHOTO - 1]);
      }
      if (String(r[EB.C_STATUS - 1]) !== f.status) sh.getRange(row, EB.C_STATUS).setValue(f.status);
    }));

    // ще не перенесені рядки: якщо тим часом внесли вручну — «Вже в обліку»
    cur.forEach((r, i) => {
      const st = String(r[EB.C_STATE - 1]);
      if (st !== EB.S_NEW && st.indexOf('⚠') !== 0) return;
      const row = i + 2;
      const m = String(r[EB.C_LINK - 1]).match(/itm\/(\d+)/);
      const d = r[EB.C_DATE - 1];
      if (!m || !(d instanceof Date)) return;
      const iso = Utilities.formatDate(d, ss.getSpreadsheetTimeZone(), 'yyyy-MM-dd');
      const have = ebayFindInMain_(hist, claimed, { item_id: m[1], date: iso, kab: String(r[EB.C_KAB - 1]).trim(), amount: r[EB.C_SUM - 1] });
      if (!have) return;
      have.rows.forEach(x => claimed[x] = true);
      sh.getRange(row, EB.C_OK).clearDataValidations().setValue('');
      sh.getRange(row, EB.C_STATE).setValue(EB.S_HAVE + ' (' + have.label + ')');
      sh.getRange(row, EB.C_ROW).setValue(have.rows.join(','));
      ebayPaintState_(sh, row, EB.S_HAVE);
    });

    // нові: від старих до нових, щоб «Вже в обліку» розбиралися по порядку
    // лот «пара» (Pair / Left and Right / Both) = 2 рядки: ліва і права, сума навпіл — як ви ведете облік
    const fresh = [];
    feed.filter(f => !byId[f.id] && !byId[f.id + 'L']).forEach(f => {
      if (ebaySideOf_(f.item) === 'LR' && !f.cancelled) ebayHalves_(f).forEach(h => fresh.push(h));
      else fresh.push(f);
    });
    fresh.sort((a, b) => a.date < b.date ? -1 : a.date > b.date ? 1 : 0);
    const out = [];
    fresh.forEach(f => {
      const link = 'https://www.ebay.com/itm/' + f.item_id;
      let state = EB.S_NEW, mrow = '', name = '', hint = '';
      const have = ebayFindInMain_(hist, claimed, f);
      if (have) {
        state = EB.S_HAVE + ' (' + have.label + ')';
        mrow = have.rows.join(',');
        have.rows.forEach(x => claimed[x] = true);
        name = have.name;
      } else if (f.cancelled) {
        state = EB.S_CANCEL;
      } else {
        const m = ebayMatch_(f.item, f.item_id, data, hist, f.side);
        name = m.name;
        hint = m.hint;
      }
      const tag = (f.unit !== '1/1' ? f.unit : '') + (f.side ? (f.unit !== '1/1' ? ', ' : '') + (f.side === 'LH' ? 'пара: ліва' : 'пара: права') : '');
      out.push({ f: f, v: ['', state, f.kab, ebaySerial_(f.date), f.item + (tag ? '  [' + tag + ']' : ''), name, f.amount, link, f.tracking, f.status, hint, f.id, mrow, ''] });
    });
    if (!out.length) { ebayPhotosSafe_(); return; }

    out.reverse(); // нові — зверху
    sh.insertRowsBefore(2, out.length);
    const rng = sh.getRange(2, 1, out.length, EB.NCOL);
    rng.clearDataValidations().clearNote();
    rng.setValues(out.map(o => o.v)).setBackground(null).setFontColor('#000000').setFontLine('none')
      .setFontWeight('normal').setWrap(false);
    sh.getRange(2, EB.C_DATE, out.length, 1).setNumberFormat('dd.mm.yyyy');
    sh.getRange(2, EB.C_SUM, out.length, 1).setNumberFormat('0.00');
    sh.getRange(2, EB.C_NAME, out.length, 1).setDataValidation(
      SpreadsheetApp.newDataValidation().requireValueInRange(ss.getSheetByName(EB.DATA).getRange('A1:A'), true).setAllowInvalid(false).build());
    sh.getRange(2, EB.C_KAB, out.length, 1).setDataValidation(
      SpreadsheetApp.newDataValidation().requireValueInList(Object.keys(EB.KAB), true).setAllowInvalid(false).build());

    out.forEach((o, i) => {
      const row = i + 2;
      ebayPaintKab_(sh.getRange(row, EB.C_KAB), o.f.kab);
      const st = o.v[1];
      const ok = sh.getRange(row, EB.C_OK);
      if (st === EB.S_NEW) {
        ok.insertCheckboxes();
      } else {
        ok.clearDataValidations();
        ebayPaintState_(sh, row, st);
      }
    });
    SpreadsheetApp.flush();
    ebayPhotosSafe_();
  } finally {
    lock.releaseLock();
  }
}


// =====================================================
// ПЕРЕНЕСЕННЯ ПІСЛЯ ✔
// =====================================================

function ebayOnEdit(e) {
  if (!e || !e.range) return;
  const sh = e.range.getSheet();
  if (sh.getName() !== EB.IN) return;
  const c1 = e.range.getColumn(), c2 = e.range.getLastColumn();
  if (c1 > EB.C_OK || c2 < EB.C_OK) return;

  const lock = LockService.getDocumentLock();
  if (!lock.tryLock(30000)) {
    SpreadsheetApp.getActive().toast('Зайнято, поставте ✔ ще раз через кілька секунд', 'eBay', 5);
    return;
  }
  try {
    for (let row = Math.max(2, e.range.getRow()); row <= e.range.getLastRow(); row++) {
      const v = sh.getRange(row, 1, 1, EB.NCOL).getValues()[0];
      const ticked = v[EB.C_OK - 1] === true;
      const state = String(v[EB.C_STATE - 1]);
      if (state.indexOf(EB.S_DONE) === 0) {
        if (!ticked) {
          sh.getRange(row, EB.C_OK).setValue(true);
          SpreadsheetApp.getActive().toast('Рядок уже перенесено в «Общую таблицу» (рядок ' + v[EB.C_ROW - 1] + '). Якщо помилка — виправте там вручну.', 'eBay', 8);
        }
        continue;
      }
      if (!ticked) continue;
      if (state !== EB.S_NEW && state.indexOf('⚠') !== 0) { sh.getRange(row, EB.C_OK).setValue(false); continue; }
      ebayTransfer_(sh, row, v);
    }
  } finally {
    lock.releaseLock();
  }
}

function ebayTransfer_(sh, row, v) {
  const name = String(v[EB.C_NAME - 1]).trim();
  const kab = String(v[EB.C_KAB - 1]).trim();
  const warn = msg => {
    sh.getRange(row, EB.C_OK).setValue(false);
    sh.getRange(row, EB.C_STATE).setValue('⚠ ' + msg);
  };
  if (!name) return warn('Оберіть позицію DATA');
  if (!EB.KAB[kab]) return warn('Оберіть кабінет');
  if (v[EB.C_ROW - 1]) return warn('Вже має рядок ' + v[EB.C_ROW - 1]);

  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const main = ss.getSheetByName(EB.MAIN);

  // повторна перевірка саме зараз: раптом цю покупку вже внесли вручну після завантаження
  const have = ebayAlreadyInMain_(sh, main, row, v);
  if (have) {
    sh.getRange(row, EB.C_OK).clearDataValidations().setValue('');
    sh.getRange(row, EB.C_STATE).setValue(EB.S_HAVE + ' (' + have.label + ')');
    sh.getRange(row, EB.C_ROW).setValue(have.rows.join(','));
    ebayPaintState_(sh, row, EB.S_HAVE);
    ss.toast('Ця покупка вже є в «Общей таблице» (' + have.label + '). Не переношу.', 'eBay', 8);
    return;
  }

  const target = ebayTargetRow_(main);
  const link = String(v[EB.C_LINK - 1]);
  const dateCell = v[EB.C_DATE - 1];
  const date = dateCell instanceof Date ? ebaySerialFromDate_(dateCell) : dateCell;

  main.getRange(target, 4, 1, 5).setValues([[link, kab, name, date, Number(v[EB.C_SUM - 1])]]);
  // одразу фіксуємо перенесення у «Входящих», щоб збій оформлення нижче не призвів до повтору
  sh.getRange(row, EB.C_STATE).setValue(EB.S_DONE + ' рядок ' + target);
  sh.getRange(row, EB.C_ROW).setValue(target);
  // G — стовпець таблиці з типом «Дата»: формат не чіпаємо (число дати й так показується як дд.мм.рррр)
  try { ebayPaintKab_(main.getRange(target, 5), kab); } catch (err) { console.warn('КАБ колір: ' + err); }
  try { ebaySetNote_(main, target, link, v[EB.C_TRACK - 1], v[EB.C_PHOTO - 1]); } catch (err) { console.warn('примітка: ' + err); }

  ebayPaintState_(sh, row, EB.S_DONE);
  SpreadsheetApp.flush();
  ss.toast(name + ' → рядок ' + target, 'eBay: перенесено', 5);
}

// Перший вільний рядок після останнього заповненого (D–H), перед рядком TOTAL.
// Якщо заготовлених рядків немає — вставляє новий перед TOTAL з тими ж формулами (C, J, N, U, V).
function ebayTargetRow_(main) {
  const last = main.getLastRow();
  const vals = main.getRange(1, 1, last, 24).getValues();
  let total = last + 1;
  for (let i = last - 1; i >= 1; i--) {
    if (String(vals[i][23]).indexOf('TOTAL') >= 0) { total = i + 1; break; }
  }
  let filled = 1;
  for (let i = total - 2; i >= 1; i--) {
    const r = vals[i];
    if ([3, 4, 5, 6, 7].some(c => r[c] !== '' && r[c] !== null)) { filled = i + 1; break; }
  }
  let target = filled + 1;
  if (target >= total) {
    main.insertRowsBefore(total, 1);
    target = total;
    main.getRange(target - 1, 1, 1, 24).copyTo(main.getRange(target, 1, 1, 24), SpreadsheetApp.CopyPasteType.PASTE_FORMAT, false);
    const n = target;
    main.getRange(n, 3).setFormula('=HYPERLINK("https://novaposhtaglobal.ua/track/?Tracking_ID=" & B' + n + '; B' + n + ')');
    main.getRange(n, 10).setFormula('=H' + n + '+I' + n + '+N' + n);
    main.getRange(n, 14).setFormula('=M' + n + '/$X$3');
    main.getRange(n, 21).setFormula('=T' + n + '/$X$3');
    main.getRange(n, 22).setFormula('=IF(OR(U' + n + '=0; U' + n + '=""); ""; U' + n + ' - J' + n + ')');
  }
  return target;
}

// Примітка на D в «Общей таблице»: трек США і папка з фото
function ebaySetNote_(main, row, link, tracking, photo) {
  const d = main.getRange(row, 4);
  if (String(d.getValue()).indexOf(String(link).replace(/\?.*$/, '')) !== 0) return; // рядок зсунули/змінили — не чіпаємо
  const lines = [];
  if (tracking) lines.push('Трек США: ' + tracking);
  if (photo && /^https:/.test(String(photo))) lines.push('Фото: ' + photo);
  if (lines.length) d.setNote(lines.join('\n'));
}


// =====================================================
// ПОШУК В «ОБЩЕЙ ТАБЛИЦЕ» І DATA
// =====================================================

function ebayMainIndex_(main) {
  const last = main.getLastRow();
  const v = main.getRange(2, 4, last - 1, 5).getValues(); // D E F G H
  const out = [];
  v.forEach((r, i) => {
    const m = String(r[0]).match(/ebay\.com\/itm\/(\d+)/);
    if (!m) return;
    const d = r[3] instanceof Date ? r[3] : null;
    out.push({ row: i + 2, item: m[1], kab: String(r[1]).trim(), name: String(r[2]).trim(), date: d, sum: Number(r[4]) || 0 });
  });
  return out;
}

// той самий лот, дата ±3 дні; спочатку той самий кабінет, потім найближча дата
function ebayFindInMain_(hist, claimed, f) {
  const fd = ebayDateFromIso_(f.date);
  let best = null, bestScore = 1e9;
  hist.forEach(h => {
    if (h.item !== String(f.item_id) || claimed[h.row] || !h.date) return;
    const diff = Math.abs((h.date - fd) / 86400000);
    if (diff > 3) return;
    const score = diff + (h.kab === f.kab ? 0 : 10);
    if (score < bestScore) { bestScore = score; best = h; }
  });
  if (!best) return null;
  best = Object.assign({}, best, { rows: [best.row] });
  // пара одним лотом, внесена двома рядками: сума eBay = сума двох рядків
  const amt = Number(f.amount) || 0;
  const tol = Math.max(1, amt * 0.01); // вручну суму часто округлюють (329,75 → 2 × 165,00)
  if (amt && Math.abs(best.sum - amt) > tol) {
    const p = hist.find(h => h.item === String(f.item_id) && h.row !== best.row && !claimed[h.row] && h.date &&
      Math.abs((h.date - fd) / 86400000) <= 3 && Math.abs(best.sum + h.sum - amt) <= tol);
    if (p) best.rows = [best.row, p.row].sort((a, b) => a - b);
  }
  best.label = best.rows.length > 1 ? 'рядки ' + best.rows.join(', ') : 'рядок ' + best.row;
  return best;
}

// Чи є ця покупка (рядок «Входящих») уже в «Общей таблице»: той самий лот, ±3 дні, рядок ще не зайнятий іншою покупкою.
function ebayAlreadyInMain_(sh, main, row, v) {
  const m = String(v[EB.C_LINK - 1]).match(/itm\/(\d+)/);
  if (!m) return null;
  const d = v[EB.C_DATE - 1];
  const iso = d instanceof Date ? Utilities.formatDate(d, SpreadsheetApp.getActive().getSpreadsheetTimeZone(), 'yyyy-MM-dd') : '';
  if (!iso) return null;
  const claimed = {};
  const last = sh.getLastRow();
  if (last > 1) sh.getRange(2, EB.C_ROW, last - 1, 1).getValues().forEach((r, i) => {
    if (i + 2 !== row) String(r[0]).split(',').filter(x => x.trim()).forEach(x => claimed[Number(x)] = true);
  });
  return ebayFindInMain_(ebayMainIndex_(main), claimed, { item_id: m[1], date: iso, kab: String(v[EB.C_KAB - 1]).trim(), amount: v[EB.C_SUM - 1] });
}

// одна покупка → ліва + права, сума навпіл до цента
function ebayHalves_(f) {
  const c = Math.round(Number(f.amount) * 100), a = Math.floor(c / 2);
  return [
    Object.assign({}, f, { id: f.id + 'L', side: 'LH', amount: a / 100 }),
    Object.assign({}, f, { id: f.id + 'R', side: 'RH', amount: (c - a) / 100 }),
  ];
}

// Меню: розділити вибраний «Новий» рядок на пару, якщо в назві лоту не було слова Pair
function ebaySplitPair() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sh = ss.getActiveSheet();
  if (sh.getName() !== EB.IN) return ss.toast('Відкрийте «Входящие операции» і виберіть рядок', 'eBay', 6);
  const row = sh.getActiveRange().getRow();
  if (row < 2) return;
  const v = sh.getRange(row, 1, 1, EB.NCOL).getValues()[0];
  const st = String(v[EB.C_STATE - 1]);
  if ((st !== EB.S_NEW && st.indexOf('⚠') !== 0) || /[LR]$/.test(String(v[EB.C_ID - 1]))) {
    return ss.toast('Розділити можна лише новий, ще не розділений рядок', 'eBay', 6);
  }
  const f = { id: String(v[EB.C_ID - 1]), amount: Number(v[EB.C_SUM - 1]) };
  const h = ebayHalves_(f);
  const hist = ebayMainIndex_(ss.getSheetByName(EB.MAIN));
  const data = ebayDataNames_(ss);
  const itemId = (String(v[EB.C_LINK - 1]).match(/itm\/(\d+)/) || [])[1] || '';
  const title = String(v[EB.C_TITLE - 1]).replace(/\s+\[.*\]$/, '');
  sh.insertRowsAfter(row, 1);
  sh.getRange(row, 1, 1, EB.NCOL).copyTo(sh.getRange(row + 1, 1, 1, EB.NCOL));
  h.forEach((x, i) => {
    const r = row + i;
    const m = ebayMatch_(title, itemId, data, hist, x.side);
    sh.getRange(r, EB.C_OK).setValue(false);
    sh.getRange(r, EB.C_STATE).setValue(EB.S_NEW);
    sh.getRange(r, EB.C_TITLE).setValue(title + '  [пара: ' + (x.side === 'LH' ? 'ліва' : 'права') + ']');
    sh.getRange(r, EB.C_NAME).setValue(m.name);
    sh.getRange(r, EB.C_SUM).setValue(x.amount);
    sh.getRange(r, EB.C_HINT).setValue(m.hint);
    sh.getRange(r, EB.C_ID).setValue(x.id);
  });
}

function ebayDataNames_(ss) {
  return ss.getSheetByName(EB.DATA).getRange('A1:A').getValues()
    .map(r => String(r[0]).trim()).filter(s => s);
}

// Підбір позиції DATA за назвою лоту. Повертає {name, hint}: name — лише якщо збіг однозначний.
function ebayMatch_(title, itemId, names, hist, side) {
  const t = ebayParseTitle_(title);
  if (side) t.side = side;

  // 1) цей лот уже купували — та сама позиція (з урахуванням сторони)
  const prev = {};
  hist.forEach(h => { if (h.item === String(itemId) && h.name) prev[h.name] = true; });
  let prevNames = Object.keys(prev).filter(n => names.indexOf(n) >= 0);
  if (t.side) prevNames = prevNames.filter(n => { const s = ebaySideOf_(n); return !s || s === t.side; });
  if (prevNames.length === 1) return { name: prevNames[0], hint: 'той самий лот купували раніше' };

  // 2) збіг за маркою / моделлю / роками / стороною / типом
  const scored = [];
  names.forEach(n => {
    const s = ebayScore_(t, ebayParseName_(n));
    if (s !== null) scored.push({ n: n, s: s });
  });
  scored.sort((a, b) => b.s - a.s);
  const top = scored.filter(x => x.s >= scored[0].s - 1.5).slice(0, 4);
  const hint = (prevNames.length ? prevNames : top.map(x => x.n)).join(' | ');
  if (!scored.length) return { name: '', hint: '' };
  const clear = t.side && (scored.length === 1 || scored[0].s - scored[1].s >= 1);
  return { name: clear && !prevNames.length ? scored[0].n : '', hint: hint };
}

const EB_BRANDS = ['ford', 'jeep', 'kia', 'honda', 'acura', 'toyota', 'mazda', 'nissan', 'audi', 'volkswagen', 'subaru', 'infiniti', 'lexus',
  'hyundai', 'dodge', 'land rover', 'chevrolet', 'mercedes', 'tesla'];
const EB_BRAND_ALIAS = { 'vw': 'volkswagen', 'chervrolet': 'chevrolet', 'chevy': 'chevrolet', 'mercedes-benz': 'mercedes', 'mercedes benz': 'mercedes', 'range rover': 'land rover' };
const EB_TECH = ['halogen', 'xenon', 'led', 'full', 'afs', 'nafs', 'drl', 'bi', 'base', 'premium', 'auto', 'silver', 'black', 'upper', 'lower',
  'xle', 'xse', 'sx', 'limited', 'titanium', 'center'];

function ebayNorm_(s) {
  return String(s).toLowerCase()
    .replace(/n-afs|non[\s-]?afs|w\/o\s*afs|without\s*afs|no\s*afs/g, ' nafs ')
    .replace(/bi-led/g, 'bi led')
    .replace(/\batlass\b/g, 'atlas')
    .replace(/([a-z])-(?=[a-z0-9])/g, '$1');
}

function ebayYears_(s) {
  const ys = {};
  const add = (a, b) => { for (let y = a; y <= b && y - a < 15; y++) ys[y] = true; };
  const full = y => (y < 100 ? 2000 + y : y);
  let m;
  const re = /\b((?:19|20)?\d{2})\s*[-–\/]\s*((?:19|20)?\d{2})\b|\b((?:19|20)\d{2})\b|\b(\d{2})\+/g;
  while ((m = re.exec(s))) {
    if (m[1]) { const a = full(+m[1]), b = full(+m[2]); if (a >= 2000 && b >= a && b <= 2035) add(a, b); }
    else if (m[3]) { const y = +m[3]; if (y >= 2000 && y <= 2035) ys[y] = true; }
    else if (m[4]) add(full(+m[4]), 2030);
  }
  return Object.keys(ys).map(Number);
}

function ebaySideOf_(s) {
  const n = ' ' + String(s).toLowerCase() + ' ';
  const l = /\b(lh|left|driver|l\/h)\b|\bl\s+head(light|lamp)|левая|ліва|лівий|левый/.test(n);
  const r = /\b(rh|right|passenger|r\/h)\b|\br\s+head(light|lamp)|правая|права|правий|правый/.test(n);
  if ((l && r) || /\b(pair|both sides|set of 2|set|lh\s*&\s*rh)\b/.test(n)) return 'LR';
  return l ? 'LH' : r ? 'RH' : '';
}

function ebayKind_(s) {
  const n = String(s).toLowerCase();
  if (/tail\s*light|taillight|tail\s*lamp|фонар/.test(n)) return 'tail';
  if (/\blens\b|стекло|скло/.test(n)) return 'lens';
  if (/housing|корпус/.test(n)) return 'housing';
  if (/headl|head\s*lamp|фар/.test(n)) return 'head';
  if (/signal|turn\s*lamp/.test(n)) return 'signal';
  return '';
}

function ebayBrand_(n) {
  for (const a in EB_BRAND_ALIAS) if (n.indexOf(a) >= 0) return EB_BRAND_ALIAS[a];
  for (const b of EB_BRANDS) if (new RegExp('\\b' + b + '\\b').test(n)) return b;
  return '';
}

function ebayParseTitle_(title) {
  const n = ebayNorm_(title);
  return { n: n, words: ' ' + n.replace(/[^a-z0-9а-яіїє+]+/g, ' ') + ' ', brand: ebayBrand_(n), years: ebayYears_(n), side: ebaySideOf_(title), kind: ebayKind_(title) };
}

function ebayParseName_(name) {
  const n = ebayNorm_(name);
  const brand = ebayBrand_(n);
  const yrs = ebayYears_(n);
  // модель = слова після марки до першого року / технології / сторони
  const words = n.replace(/[^a-z0-9а-яіїє+.]+/g, ' ').trim().split(' ');
  const skip = brand.split(' ').length;
  const model = [], tech = [];
  let inModel = true;
  for (let i = skip; i < words.length; i++) {
    const w = words[i];
    if (!w) continue;
    if (/^(lh|rh|\+)$/.test(w)) { inModel = false; continue; }
    if (/^\d{2}(\d{2})?$/.test(w) && inModel && model.length) { inModel = false; continue; }
    if (/^\d{2}\+$|^\d{2}-\d{2}$/.test(w)) { inModel = false; continue; }
    if (EB_TECH.indexOf(w) >= 0) { inModel = false; tech.push(w); continue; }
    if (inModel) model.push(w); else if (/[a-z]/.test(w)) tech.push(w);
  }
  // «CX-70 / CX-90», «Outback / Legacy» — достатньо будь-якої з назв
  const alt = (n.match(/([a-z0-9]+)\s*\/\s*([a-z0-9]+)/) || []).slice(1).filter(w => model.indexOf(w) >= 0);
  return { name: name, brand: brand, model: model, alt: alt.length === 2 ? alt : [], years: yrs, side: ebaySideOf_(name.replace(/\s+\+\s+/g, ' and ')), pair: /lh\s*\+\s*rh/i.test(name), tech: tech, kind: ebayKind_(name) || 'head' };
}

// null = не підходить; інакше бал (більше — краще)
function ebayScore_(t, c) {
  if (!t.brand || c.brand !== t.brand || !c.model.length) return null;
  // модель: перше слово моделі обов'язкове; генераційні коди (70, BM, WK2, L405…) — бонус, якщо є
  const has = w => t.words.indexOf(' ' + w + ' ') >= 0 || t.n.indexOf(w) >= 0 && w.length >= 4;
  const altHit = c.alt.length && c.alt.some(has);
  if (!has(c.model[0]) && !altHit) return null;
  let s = 0;
  c.model.forEach((w, i) => {
    if (has(w)) s += 2;
    else if (c.alt.indexOf(w) >= 0 && altHit) s += 2;
    else if (i > 0 && w.length >= 4 && !/\d/.test(w)) s -= 2;
  });
  // вид деталі
  const tk = t.kind || 'head';
  if (c.kind !== tk) return null;
  // сторона
  if (c.pair) { if (t.side !== 'LR') return null; s += 1; }
  else if (t.side === 'LR') return null;
  else if (t.side && c.side && c.side !== t.side) return null;
  // роки
  if (t.years.length && c.years.length) {
    const inC = t.years.filter(y => c.years.indexOf(y) >= 0).length;
    if (!inC) return null;
    s += 3 * inC / t.years.length;
  }
  // технологія
  const tl = /\bled\b/.test(t.words), th = /\bhalogen\b/.test(t.words), tx = /\b(xenon|hid)\b/.test(t.words);
  const tafs = /\b(afs|adaptive)\b/.test(t.words), tnafs = /\bnafs\b/.test(t.words);
  const ch = c.tech.indexOf('halogen') >= 0, cx = c.tech.indexOf('xenon') >= 0, cl = c.tech.indexOf('led') >= 0;
  const cafs = c.tech.indexOf('afs') >= 0, cnafs = c.tech.indexOf('nafs') >= 0;
  if (ch && !cl && tl && !th) return null;
  if (cl && !ch && !cx && th && !tl) return null;
  if (cx && tl && !tx && !th) s -= 2;
  if (th && ch) s += 1;
  if (tx && cx) s += 1;
  if (tl && cl) s += 0.5;
  if (cafs) { if (tnafs) return null; s += tafs ? 2 : -1; }
  else if (tafs && !tnafs) s -= 2;
  if (cnafs && tnafs) s += 1;
  if (c.tech.indexOf('full') >= 0) s += /\bfull\b/.test(t.words) ? 1 : -0.5;
  ['base', 'premium', 'auto', 'silver', 'black', 'xle', 'xse', 'sx', 'limited', 'titanium', 'drl', 'bi'].forEach(w => {
    if (c.tech.indexOf(w) >= 0) s += new RegExp('\\b' + w + '\\b').test(t.words) ? 1 : -0.5;
  });
  return s;
}


// =====================================================
// ФОТО ЛОТІВ → Google Диск («eBay фото / рррр-мм / номер лота – назва»)
// Лише для себе (звірка стану/комплектації). На сайт і OLX ці фото не йдуть.
// Завантажуються для нових і перенесених покупок; «Вже в обліку» і скасовані — ні.
// =====================================================

function ebayPhotos() {
  const lock = LockService.getDocumentLock();
  if (!lock.tryLock(30000)) return;
  try {
    const n = ebayPhotos_();
    SpreadsheetApp.getActive().toast('Фото збережено для лотів: ' + n, 'eBay', 5);
  } finally {
    lock.releaseLock();
  }
}

function ebayPhotosSafe_() {
  try { ebayPhotos_(); } catch (err) { console.warn('Фото: ' + err); }
}

function ebayPhotos_() {
  const t0 = Date.now();
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sh = ss.getSheetByName(EB.IN);
  const main = ss.getSheetByName(EB.MAIN);
  const key = PropertiesService.getScriptProperties().getProperty('EBAY_FEED_KEY');
  const last = sh.getLastRow();
  if (last < 2 || !key) return 0;
  const vals = sh.getRange(2, 1, last - 1, EB.NCOL).getValues();
  const tz = ss.getSpreadsheetTimeZone();

  // лот → посилання на папку (якщо вже є в іншому рядку, напр. пара)
  const have = {};
  const todo = {}; // лот → {title, month, rows: []}
  vals.forEach((r, i) => {
    const id = (String(r[EB.C_LINK - 1]).match(/itm\/(\d+)/) || [])[1];
    if (!id) return;
    const ph = String(r[EB.C_PHOTO - 1]);
    if (ph) { if (/^https:/.test(ph)) have[id] = ph; return; }
    const st = String(r[EB.C_STATE - 1]);
    if (!(st === EB.S_NEW || st.indexOf('⚠') === 0 || st.indexOf(EB.S_DONE) === 0)) return;
    const d = r[EB.C_DATE - 1];
    const month = d instanceof Date ? Utilities.formatDate(d, tz, 'yyyy-MM') : 'без дати';
    const title = String(r[EB.C_TITLE - 1]).replace(/\s+\[.*\]$/, '');
    (todo[id] = todo[id] || { title: title, month: month, rows: [] }).rows.push(i + 2);
  });

  const ids = Object.keys(todo);
  let done = 0;
  const root = ebayFolder_(DriveApp.getRootFolder(), 'eBay фото');
  for (let b = 0; b < ids.length && Date.now() - t0 < 240000; b += 10) {
    const batch = ids.slice(b, b + 10).filter(id => !have[id]);
    let pics = {};
    if (batch.length) {
      const resp = UrlFetchApp.fetch(EB.FEED_URL + '?pics=' + batch.join(','), { headers: { 'X-AB-Key': key }, muteHttpExceptions: true });
      if (resp.getResponseCode() !== 200) throw new Error('Сервер (фото): ' + resp.getResponseCode());
      pics = JSON.parse(resp.getContentText()).pics || {};
    }
    ids.slice(b, b + 10).forEach(id => {
      if (Date.now() - t0 > 270000) return;
      const job = todo[id];
      let url = have[id] || '';
      if (!url) {
        const list = pics[id] || [];
        if (!list.length) { url = 'немає фото'; }
        else {
          const month = ebayFolder_(root, job.month);
          const name = (id + ' – ' + job.title).replace(/[\\/:*?"<>|]+/g, ' ').slice(0, 90);
          const folder = ebayFolder_(month, name);
          if (!folder.getFiles().hasNext()) {
            const res = UrlFetchApp.fetchAll(list.slice(0, 24).map(u => ({ url: u, muteHttpExceptions: true })));
            res.forEach((r, k) => {
              if (r.getResponseCode() === 200) folder.createFile(r.getBlob().setName(String(k + 1).padStart(2, '0') + '.jpg'));
            });
          }
          url = folder.getUrl();
          done++;
        }
        have[id] = url;
      }
      job.rows.forEach(row => {
        sh.getRange(row, EB.C_PHOTO).setValue(url);
        const v = vals[row - 2];
        if (String(v[EB.C_STATE - 1]).indexOf(EB.S_DONE) === 0 && v[EB.C_ROW - 1]) {
          try { ebaySetNote_(main, Number(v[EB.C_ROW - 1]), v[EB.C_LINK - 1], v[EB.C_TRACK - 1], url); } catch (err) {}
        }
      });
    });
  }
  return done;
}

function ebayFolder_(parent, name) {
  const it = parent.getFoldersByName(name);
  return it.hasNext() ? it.next() : parent.createFolder(name);
}


// =====================================================
// ДРІБНИЦІ
// =====================================================

function ebayPaintKab_(cell, kab) {
  const k = EB.KAB[kab];
  if (k) cell.setBackground(k.bg).setFontColor(k.fg);
}

function ebayPaintState_(sh, row, state) {
  const r = sh.getRange(row, 1, 1, EB.NCOL);
  if (state.indexOf(EB.S_DONE) === 0) r.setBackground('#d9ead3');
  else if (state.indexOf(EB.S_HAVE) === 0) r.setFontColor('#999999');
  else if (state.indexOf(EB.S_CANCEL) === 0) r.setFontColor('#999999').setFontLine('line-through');
  ebayPaintKab_(sh.getRange(row, EB.C_KAB), String(sh.getRange(row, EB.C_KAB).getValue()));
}

// дата як число таблиці (не залежить від часового поясу скрипта)
function ebaySerial_(iso) {
  const p = String(iso).split('-').map(Number);
  return (Date.UTC(p[0], p[1] - 1, p[2]) - Date.UTC(1899, 11, 30)) / 86400000;
}
function ebaySerialFromDate_(d) {
  const tz = SpreadsheetApp.getActive().getSpreadsheetTimeZone();
  return ebaySerial_(Utilities.formatDate(d, tz, 'yyyy-MM-dd'));
}
function ebayDateFromIso_(iso) {
  const p = String(iso).split('-').map(Number);
  return new Date(p[0], p[1] - 1, p[2]);
}
