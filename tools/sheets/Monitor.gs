// =====================================================
// Монітор нових лотів eBay → Telegram @autobeam_monitor_bot
//
// Окремий файл (поруч з eBay.gs — використовує його підбір позицій DATA).
// Встановлення: функція monitorSetup → «Выполнить» (один раз).
//
// Аркуш «Запити»: A Увімк. | B Позиція DATA | C Макс. $ (з доставкою) | D Запит eBay | E Мінус-слова | F Примітка
//   • однаковий запит у кількох рядках = один пошук (бот сам визначає позицію за назвою лота);
//   • позиція не з DATA — бот перевіряє лише запит і ціну;
//   • кожні 2–6 хвилин (залежить від кількості запитів): нові оголошення з США (Buy It Now / Best Offer), ціна + доставка ≤ ліміту;
//   • кожен лот приходить один раз; повторно — лише якщо ціну знизили.
// =====================================================

const MON = {
  SHEET: 'Запити',
  SEEN: 'eBay бачені',
  DAY_BUDGET: 4800,         // пошуків eBay на добу (ліміт 5 000, запас 200)
  MIN_INTERVAL: 2,          // хв — частіше не можна через ліміт часу роботи скриптів Google (90 хв/добу)
  MAX_MSG: 15,              // не більше повідомлень за одну перевірку
  // загальні мінус-слова: не фара в зборі / не оригінал
  MINUS: ['lens only', 'replacement lens', 'headlight lens', 'lens cover', 'lens replacement', 'housing only', 'headlight housing', 'back housing', 'bulb', 'ballast', 'bracket', 'tab repair', 'repair kit', 'module only',
          ' depo', ' tyc', 'aftermarket', 'replacement for', 'sticker', 'decal', ' tint', ' film', 'harness', 'pigtail',
          'socket', 'screw', 'bolt kit', 'diecast', ' toy ', 'manual'],
};


function monitorSetup() {
  ScriptApp.getProjectTriggers()
    .filter(t => t.getHandlerFunction() === 'monitorRun')
    .forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('monitorRun').timeBased().everyMinutes(1).create(); // сам вирішує, чи час перевіряти
  monitorSeenSheet_();
  monitorRun();
}

function monitorRun() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(5000)) return;
  try {
    monitorRun_();
  } finally {
    lock.releaseLock();
  }
}

function monitorRun_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sh = ss.getSheetByName(MON.SHEET);
  const key = PropertiesService.getScriptProperties().getProperty('EBAY_FEED_KEY');
  if (!sh || !key) return;
  const last = sh.getLastRow();
  if (last < 2) return;

  const dataNames = ebayDataNames_(ss);
  const inData = {};
  dataNames.forEach(n => inData[n] = true);

  // увімкнені рядки → групи за запитом
  const groups = {};
  sh.getRange(2, 1, last - 1, 6).getValues().forEach(r => {
    const on = r[0] === true, name = String(r[1]).trim(), max = Number(r[2]), q = String(r[3]).trim().toLowerCase();
    if (!on || !name || !(max > 0) || !q) return;
    const minus = String(r[4]).toLowerCase().split(/[,\s]+/).map(w => w.replace(/^-/, '')).filter(w => w);
    (groups[q] = groups[q] || []).push({ name: name, max: max, minus: minus, data: !!inData[name], side: ebaySideOf_(name) });
  });
  let queries = Object.keys(groups).sort();
  if (!queries.length) return;

  // частота від кількості запитів: 3 запити — кожні 2 хв, 17 — кожні 6 хв (щоб уміститися в 5 000 пошуків/добу)
  const props = PropertiesService.getScriptProperties();
  const interval = Math.max(MON.MIN_INTERVAL, Math.ceil(queries.length * 1440 / MON.DAY_BUDGET));
  const lastRun = Number(props.getProperty('MON_LAST')) || 0;
  if (Date.now() - lastRun < interval * 60000 - 20000) return;
  props.setProperty('MON_LAST', String(Date.now()));
  if (props.getProperty('MON_INTERVAL') !== String(interval)) {
    if (props.getProperty('MON_INTERVAL')) {
      monitorSend_(key, '⏱ Увімкнено запитів: ' + queries.length + '. Перевіряю кожні ' + interval + ' хв.');
    }
    props.setProperty('MON_INTERVAL', String(interval));
  }

  const seen = monitorSeenLoad_();
  const fresh = [];
  let sent = 0;

  queries.forEach(q => {
    const rows = groups[q];
    const maxLimit = Math.max.apply(null, rows.map(r => r.max)) * 2; // ×2 — щоб не пропустити пари (ліва + права)
    const resp = UrlFetchApp.fetch(EB.FEED_URL + '?search=' + encodeURIComponent(q) + '&max=' + maxLimit, {
      headers: { 'X-AB-Key': key }, muteHttpExceptions: true,
    });
    if (resp.getResponseCode() !== 200) { console.warn('Пошук «' + q + '»: ' + resp.getContentText().slice(0, 200)); return; }
    const items = JSON.parse(resp.getContentText()).items || [];

    items.forEach(it => {
      if (!it.id || sent >= MON.MAX_MSG) return;
      const title = String(it.title);
      const tl = ' ' + title.toLowerCase() + ' ';
      if (MON.MINUS.some(w => tl.indexOf(w) >= 0)) return;
      if (monitorAftermarket_(title, it.condition)) return; // аналог / Китай — не надсилаємо, лише OEM
      const total = Math.round((it.price + (it.ship || 0)) * 100) / 100;

      const hit = monitorWhich_(title, rows, dataNames);
      if (!hit) return;
      if (hit.minus.some(w => tl.indexOf(w) >= 0)) return;
      if (total > hit.max) return;

      const prev = seen[it.id];
      if (prev !== undefined && total >= prev - 1) return; // вже надсилали за цю або нижчу ціну

      const shipTxt = it.ship === null || it.ship === undefined ? ' + доставка ?' : (it.ship > 0 ? ' + $' + it.ship.toFixed(2) + ' доставка' : ' (доставка безкоштовна)');
      const drop = prev !== undefined ? '📉 <b>Знижка:</b> було $' + prev.toFixed(2) + '\n' : '';
      const text =
        '🔔 <b>' + monitorEsc_(hit.label) + '</b>\n' +
        drop +
        '💵 $' + it.price.toFixed(2) + shipTxt + ' = <b>$' + total.toFixed(2) + '</b> (ліміт $' + hit.max + ')\n' +
        monitorEsc_(title) + '\n' +
        (it.listed ? '🕒 виставлено ' + monitorAgo_(it.listed) + '\n' : '') +
        [it.condition, it.options.indexOf('BEST_OFFER') >= 0 ? 'можна торгуватись' : 'Buy It Now', it.fb !== null ? 'продавець ' + it.fb + '%' : '']
          .filter(x => x).join(' · ') + '\n' +
        '<a href="' + it.url + '">Відкрити лот</a>';
      if (monitorSend_(key, text, it.img)) {
        sent++;
        seen[it.id] = total;
        fresh.push([it.id, total, new Date()]);
      }
    });
  });

  monitorSeenSave_(fresh);
}

// Яка увімкнена позиція підходить під назву лота. Повертає {label, max, minus} або null.
function monitorWhich_(title, rows, dataNames) {
  // окреме ДХВ / протитуманка: якщо в DATA-рядках запиту немає окремого ДХВ — шукаємо як фару, але з позначкою
  const drlRows = rows.filter(r => r.data && ebayKind_(r.name, true) === 'drl');
  if (ebayKind_(title) === 'drl' && !drlRows.length) {
    const h = monitorWhich_(title + ' headlight', rows, dataNames);
    return h ? Object.assign(h, { label: '💡 ДХВ / не фара — ' + h.label }) : null;
  }
  const free = rows.filter(r => !r.data);
  // без року в назві лота не відрізнити старе покоління від потрібного (Escape 17–19 vs 23+) — такі лоти не шлемо,
  // якщо позиція з роками (власник 23.11: «старі ескейпи, не потрібно»). Рядки без позиції DATA — як і раніше.
  if (!ebayYears_(title).length && rows.some(r => r.data && ebayYears_(r.name).length)) {
    if (!free.length) return null;
    rows = free;
  }
  const byName = {};
  rows.filter(r => r.data).forEach(r => byName[r.name] = r);

  // пара в одному лоті — лише якщо ввімкнені обидві сторони; ліміт = сума
  if (ebaySideOf_(title) === 'LR') {
    const L = ebayMatch_(title, '', dataNames, [], 'LH'), R = ebayMatch_(title, '', dataNames, [], 'RH');
    const l = monitorPick_(L, byName), r = monitorPick_(R, byName);
    if (l && r) return { label: 'Пара: ' + l.name + ' + ' + r.name, max: l.max + r.max, minus: l.minus.concat(r.minus) };
  } else if (Object.keys(byName).length) {
    const m = ebayMatch_(title, '', dataNames, [], null);
    const p = monitorPick_(m, byName);
    if (p) return { label: p.name + (p.maybe ? ' (уточніть по фото)' : ''), max: p.max, minus: p.minus };
  }
  if (free.length) {
    const f = free.reduce((a, b) => (a.max >= b.max ? a : b));
    return { label: f.name, max: f.max, minus: f.minus };
  }
  return null;
}

// однозначний збіг — та позиція; кілька варіантів — увімкнена з найбільшим лімітом, позначка «схоже»
function monitorPick_(m, byName) {
  if (m.name) return byName[m.name] ? Object.assign({ maybe: false }, byName[m.name]) : null;
  const cands = String(m.hint || '').split(' | ').map(s => s.trim()).filter(s => byName[s]);
  if (!cands.length) return null;
  const best = cands.map(c => byName[c]).reduce((a, b) => (a.max >= b.max ? a : b));
  return Object.assign({ maybe: true }, best, { name: cands.join(' / ') });
}

// photo — фото лота: повідомлення приходить з картинкою (підпис = текст)
// Аналог (Китай, aftermarket): типові ознаки в назві + «новий» без слова OEM/Genuine/Factory.
// Б/в і «на запчастини» майже завжди оригінал — їх пропускаємо, якщо в назві немає явних ознак аналога.
const MON_AFTER_BRANDS = ['depo', 'tyc', 'spyder', 'anzo', 'morimoto', 'sockir', 'ecotric', 'partsam', 'labwork', 'kiwi master',
  'dna motoring', 'auto dynasty', 'eagle eye', 'k-metal', 'akkon', 'winjet', 'xtune', 'x-tune', 'alpha owls', 'oracle', 'recon',
  'goodyear', 'garage-pro', 'garage pro', 'keystone', 'replacement', 'aftermarket', 'non-oem', 'non oem', 'oe style', 'oem style',
  'oe-style', 'oem-style', 'capa', 'nsf certified', 'brand new pair', 'smoked', 'black housing', 'sequential', 'demon eye', 'halo'];
function monitorAftermarket_(title, condition) {
  const t = ' ' + String(title).toLowerCase().replace(/[^a-z0-9 \-]+/g, ' ') + ' ';
  const oem = /\b(oem|genuine|factory|original|oe)\b/.test(t) && !/\b(oem|oe)[\s-]style\b/.test(t);
  if (/^\s*(for|fits|fit)\s/.test(t)) return true;                                  // «For 2022-2025 Mazda CX-5 …» — класика Китаю
  if (/\b(fits|compatible with|replaces|replace for)\b/.test(t) && !oem) return true;
  if (/\bpair\b.*\b(left|right|driver|passenger)\b.*\bnew\b/.test(t) && !oem) return true;
  if (MON_AFTER_BRANDS.some(b => t.indexOf(' ' + b + ' ') >= 0 || t.indexOf(' ' + b) >= 0 && b.length > 5)) return true;
  if (/^new\b/i.test(String(condition || '')) && !oem) return true;                 // новий без OEM у назві — найчастіше аналог
  return false;
}

function monitorSend_(key, text, photo) {
  const img = photo ? String(photo).replace(/\/s-l\d+\./, '/s-l800.') : '';
  const r = UrlFetchApp.fetch(EB.FEED_URL + '?notify=1', {
    method: 'post', contentType: 'application/json', payload: JSON.stringify({ text: text, photo: img }),
    headers: { 'X-AB-Key': key }, muteHttpExceptions: true,
  });
  return r.getResponseCode() === 200 && /"ok":true/.test(r.getContentText());
}

function monitorAgo_(iso) {
  const min = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (min < 60) return min + ' хв тому';
  if (min < 48 * 60) return Math.round(min / 60) + ' год тому';
  return Math.round(min / 1440) + ' дн тому';
}

function monitorEsc_(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}


// ---------- які лоти вже надсилали (прихований аркуш, зберігається 30 днів) ----------

function monitorSeenSheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(MON.SEEN);
  if (!sh) {
    sh = ss.insertSheet(MON.SEEN);
    sh.getRange(1, 1, 1, 3).setValues([['Лот', 'Ціна $', 'Коли']]).setFontWeight('bold');
    sh.hideSheet();
  }
  return sh;
}

function monitorSeenLoad_() {
  const sh = monitorSeenSheet_();
  const last = sh.getLastRow();
  const out = {};
  if (last < 2) return out;
  sh.getRange(2, 1, last - 1, 2).getValues().forEach(r => {
    if (r[0] === '') return;
    const id = String(r[0]), p = Number(r[1]);
    if (out[id] === undefined || p < out[id]) out[id] = p;
  });
  return out;
}

function monitorSeenSave_(fresh) {
  const sh = monitorSeenSheet_();
  if (fresh.length) sh.getRange(sh.getLastRow() + 1, 1, fresh.length, 3).setValues(fresh);
  // раз на добу прибираємо записи старші 30 днів
  const props = PropertiesService.getScriptProperties();
  const today = new Date().toDateString();
  if (props.getProperty('MON_PRUNE') === today) return;
  props.setProperty('MON_PRUNE', today);
  const last = sh.getLastRow();
  if (last < 3) return;
  const cut = Date.now() - 30 * 86400000;
  const keep = sh.getRange(2, 1, last - 1, 3).getValues().filter(r => r[2] instanceof Date && r[2].getTime() >= cut);
  sh.getRange(2, 1, last - 1, 3).clearContent();
  if (keep.length) sh.getRange(2, 1, keep.length, 3).setValues(keep);
}
