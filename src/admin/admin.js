/* AutoBeam admin */
(function () {
  'use strict';
  var CSRF = document.querySelector('meta[name=csrf]').content;
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); };
  var ROWS = [], KEYS = [], CUR = null, DIRTY = false, STOCK = null;

  function api(a, body, isForm) {
    return fetch('/admin/api.php?a=' + a, {
      method: 'POST', credentials: 'same-origin',
      headers: isForm ? {'X-CSRF': CSRF} : {'X-CSRF': CSRF, 'Content-Type': 'application/json'},
      body: isForm ? body : JSON.stringify(body || {})
    }).then(function (r) {
      if (r.status === 401) { location.reload(); throw new Error('auth'); }
      return r.json();
    });
  }
  function toast(t, bad) { var el = $('#toast'); el.textContent = t; el.className = 'on' + (bad ? ' bad' : ''); clearTimeout(el._t); el._t = setTimeout(function () { el.className = ''; }, 2600); }

  /* ---------- status ---------- */
  function statusOf(r, stock) {
    if (r.status_manual) return r.status_manual;
    var s = stock === undefined ? r.stock : stock;
    if (!r.key) return 'Під замовлення';
    if (!s) return 'Під замовлення';
    if (+s[0] > 0) return 'В наявності';
    if (+s[1] + +s[2] > 0) return 'Незабаром у наявності';
    return 'Під замовлення';
  }
  var SCLS = {'В наявності': 'st-in', 'Незабаром у наявності': 'st-soon', 'Під замовлення': 'st-ord', 'Приховати': 'st-hid'};

  /* ---------- list ---------- */
  function load() {
    return api('list').then(function (d) {
      ROWS = d.rows; render();
      $('#b-pub').classList.toggle('hot', !!d.dirty);
    });
  }
  function norm(s) { return String(s || '').toLowerCase().replace(/[\s\-_.]/g, ''); }
  function render() {
    var q = norm($('#q').value), fs = $('#f-status').value, fx = $('#f-extra').value;
    var rows = ROWS.filter(function (r) {
      if (fx === 'arch') { if (!r.archived) return false; } else if (r.archived) return false;
      if (fs && statusOf(r) !== fs) return false;
      if (fx === 'olx' && !(r.olx && r.olx_active)) return false;
      if (fx === 'olxoff' && !(r.olx && !r.olx_active)) return false;
      if (fx === 'noolx' && r.olx) return false;
      if (fx === 'nophoto' && r.nphotos) return false;
      if (fx === 'nodesc' && r.hasdesc) return false;
      if (fx === 'note' && !r.note) return false;
      if (fx === 'hidden' && r.show) return false;
      if (q) { var hay = norm([r.id, r.key, r.title, r.brand, r.model, r.pn, r.years, r.side].join(' ')); if (hay.indexOf(q) < 0) return false; }
      return true;
    });
    $('#count').textContent = rows.length + ' з ' + ROWS.filter(function (r) { return !r.archived; }).length;
    $('#list').innerHTML = rows.map(function (r) {
      var st = statusOf(r);
      var name = r.title || [r.kind, r.side, r.brand, r.model, r.years, r.trim].filter(Boolean).join(' ');
      return '<a class="row' + (CUR && CUR.id === r.id ? ' on' : '') + (r.show ? '' : ' off') + '" data-id="' + r.id + '">' +
        (r.photo ? '<img loading="lazy" src="' + esc(r.photo) + '">' : '<span class="noimg">' + esc(r.kind || '') + '</span>') +
        '<span class="t"><b>' + esc(name) + '</b><small>' + r.id + (r.pn ? ' · ' + esc(r.pn) : '') + '</small>' +
        '<small><i class="st ' + (SCLS[st] || '') + '">' + st + '</i>' + (r.price ? ' · ' + r.price + (r.currency === 'UAH' ? ' грн' : ' $') : '') +
        (r.olx ? (r.olx_active ? ' · OLX' : ' · <s>OLX</s>') : '') + (r.note ? ' · ⚑' : '') + '</small></span></a>';
    }).join('');
  }
  $('#list').addEventListener('click', function (e) {
    var a = e.target.closest('.row'); if (!a) return;
    if (DIRTY && !confirm('Є незбережені зміни. Перейти без збереження?')) return;
    open(a.dataset.id);
  });
  ['#q', '#f-status', '#f-extra'].forEach(function (s) { $(s).addEventListener('input', render); });

  /* ---------- editor ---------- */
  var KINDS = ['Фара', 'Ліхтар', 'ДХО', 'Повторювач', 'Скло фари', 'Корпус фари', 'Інше'];
  var SIDES = ['Ліва', 'Права', 'Пара (ліва + права)', 'Центральна', ''];
  var STATUSES = ['', 'В наявності', 'Незабаром у наявності', 'Під замовлення', 'Приховати'];
  function sel(name, opts, v) { return '<select name="' + name + '">' + opts.map(function (o) { return '<option' + (o === v ? ' selected' : '') + ' value="' + esc(o) + '">' + esc(o || '—') + '</option>'; }).join('') + '</select>'; }
  function inp(name, v, ph, extra) { return '<input name="' + name + '" value="' + esc(v) + '" placeholder="' + esc(ph || '') + '" ' + (extra || '') + '>'; }
  function fld(label, html, cls) { return '<label class="f ' + (cls || '') + '"><span>' + label + '</span>' + html + '</label>'; }

  function open(id) {
    api('get', {id: id}).then(function (d) {
      if (!d.ok) return toast('Не знайдено', 1);
      CUR = d.p; STOCK = d.stock; DIRTY = false; draw(); render();
      if (window.innerWidth < 900) $('#ed').scrollIntoView();
    });
  }
  function draw() {
    var p = CUR, s = STOCK;
    var st = statusOf({status_manual: p.status_manual, key: p.key}, s);
    var olxUrl = p.olx_id ? 'https://www.olx.ua/d/' + p.olx_id + '/' : '';
    $('#ed').innerHTML =
      '<div class="edh"><div><b class="id">' + p.id + '</b> <i class="st ' + (SCLS[st] || '') + '">' + st + '</i>' +
      (s ? '<small class="stock">склад ' + s[0] + ' · ремонт ' + s[1] + ' · в дорозі ' + s[2] + '</small>' : (p.key ? '<small class="stock">немає в обліку</small>' : '')) +
      '</div><div class="acts">' +
      (olxUrl ? '<a class="ghost btn" target="_blank" rel="noopener" href="' + olxUrl + '">OLX ↗</a>' : '') +
      '<button type="button" class="ghost" data-do="copy">Копія</button>' +
      '<button type="button" class="ghost" data-do="arch">' + (p.archived ? 'З архіву' : 'В архів') + '</button>' +
      '<button type="button" data-do="save" class="save">Зберегти</button></div></div>' +
      (p.note ? '<div class="note">⚑ ' + esc(p.note) + '</div>' : '') +
      '<form id="pf" autocomplete="off">' +
      '<fieldset><legend>Позиція</legend>' +
      fld('Позиція з DATA (наявність)', inp('key', p.key, 'напр. Mazda CX-5 22-25 LED AFS LH', 'list="keys"'), 'w2') +
      fld('Тип', sel('kind', KINDS, p.kind)) + fld('Сторона', sel('side', SIDES, p.side || '')) +
      fld('Марка', inp('brand', p.brand)) + fld('Модель', inp('model', p.model)) + fld('Кузов', inp('body', p.body, 'KF, WL…')) +
      fld('Роки', inp('years', p.years, '2022–2025')) + fld('Виконання', inp('trim', p.trim, 'LED AFS'), 'w2') +
      '</fieldset>' +
      '<fieldset><legend>Парт-номери і ціна</legend>' +
      fld('Основний парт-номер', inp('pn', p.pn)) + fld('Інші номери (через кому)', inp('pn_alt', (p.pn_alt || []).join(', ')), 'w2') +
      fld('Ціна', inp('price', p.price, '', 'inputmode="numeric"')) + fld('Валюта', sel('currency', ['USD', 'UAH'], p.currency || 'USD')) +
      fld('Стан', sel('state', ['Вживане', 'Нове'], p.state || 'Вживане')) + fld('Оригінал', sel('original', ['Оригінал', 'Аналог'], p.original || 'Оригінал')) +
      fld('Статус вручну', sel('status_manual', STATUSES, p.status_manual || '')) +
      '<label class="f chk"><input type="checkbox" name="show"' + (p.show ? ' checked' : '') + '><span>Показувати на сайті</span></label>' +
      '</fieldset>' +
      '<fieldset><legend>Фото <small>(перше — головне; перетягуйте стрілками)</small></legend><div id="ph"></div>' +
      '<div class="phadd"><label class="btn ghost">Додати фото<input type="file" id="up" accept="image/*" multiple hidden></label>' +
      '<input id="phurl" placeholder="…або вставте посилання на фото"><button type="button" class="ghost" data-do="addurl">Додати</button></div></fieldset>' +
      '<fieldset><legend>Тексти</legend>' +
      fld('Заголовок OLX <small id="c-title"></small>', inp('title', p.title, '', 'maxlength="70"'), 'w3') +
      '<div class="gen"><button type="button" class="ghost" data-do="gtitle">Згенерувати заголовок</button><button type="button" class="ghost" data-do="ctitle">Скопіювати</button></div>' +
      fld('Опис OLX з ключовими словами <small id="c-desc"></small>', '<textarea name="description" rows="14">' + esc(p.description) + '</textarea>', 'w3') +
      '<div class="gen"><button type="button" class="ghost" data-do="gdesc">Згенерувати опис + ключові слова</button><button type="button" class="ghost" data-do="cdesc">Скопіювати</button></div>' +
      fld('Короткий опис (avto.pro, сайт)', '<textarea name="short" rows="3">' + esc(p.short) + '</textarea>', 'w3') +
      '<div class="gen"><button type="button" class="ghost" data-do="gshort">Згенерувати</button></div>' +
      '</fieldset>' +
      '<fieldset><legend>Майданчики</legend>' +
      fld('OLX ID оголошення', inp('olx_id', p.olx_id)) +
      '<label class="f chk"><input type="checkbox" name="olx_active"' + (p.olx_active ? ' checked' : '') + '><span>Оголошення OLX активне</span></label>' +
      fld('OLX категорія', sel('olx_category', ['', '2544', '2545', '2550'], p.olx_category || '')) +
      fld('OLX марка (car_brand)', inp('olx_brand', p.olx_brand, 'mazda')) + fld('OLX сумісність (compatibility_list)', inp('olx_compat', p.olx_compat), 'w2') +
      fld('avto.pro виробник', inp('avto_maker', p.avto_maker, 'MAZDA / VAG / CHRYSLER')) + fld('avto.pro код', inp('avto_code', p.avto_code)) +
      '</fieldset>' +
      '<fieldset><legend>Примітка</legend>' + fld('', '<textarea name="note" rows="2">' + esc(p.note) + '</textarea>', 'w3') + '</fieldset>' +
      '</form><datalist id="keys">' + KEYS.map(function (k) { return '<option value="' + esc(k) + '">'; }).join('') + '</datalist>';
    drawPhotos(); counters();
  }
  function drawPhotos() {
    $('#ph').innerHTML = (CUR.photos || []).map(function (u, i) {
      return '<div class="pt"><img src="' + esc(u) + '"><div><button type="button" data-ph="l" data-i="' + i + '">←</button><button type="button" data-ph="r" data-i="' + i + '">→</button><button type="button" data-ph="x" data-i="' + i + '">×</button></div></div>';
    }).join('') || '<p class="hint">Фото немає</p>';
  }
  function counters() {
    var f = $('#pf'); if (!f) return;
    $('#c-title').textContent = f.title.value.length + '/70';
    $('#c-desc').textContent = f.description.value.length + '/9000';
  }
  function collect() {
    var f = $('#pf'), p = Object.assign({}, CUR);
    ['key', 'kind', 'side', 'brand', 'model', 'body', 'years', 'trim', 'pn', 'price', 'currency', 'state', 'original', 'status_manual', 'title', 'description', 'short', 'olx_id', 'olx_category', 'olx_brand', 'olx_compat', 'avto_maker', 'avto_code', 'note']
      .forEach(function (k) { p[k] = f[k].value; });
    p.pn_alt = f.pn_alt.value.split(/[,;\n]+/).map(function (x) { return x.trim(); }).filter(Boolean);
    p.show = f.show.checked; p.olx_active = f.olx_active.checked;
    return p;
  }
  function save() {
    var p = collect();
    return api('save', {p: p}).then(function (d) {
      if (!d.ok) return toast('Помилка збереження', 1);
      CUR = d.p; DIRTY = false; toast('Збережено');
      var i = ROWS.findIndex(function (r) { return r.id === p.id; });
      load();
    });
  }

  $('#ed').addEventListener('input', function (e) { if (e.target.closest('#pf')) { DIRTY = true; counters(); } });
  $('#ed').addEventListener('change', function (e) {
    if (e.target.id === 'up') {
      var fd = new FormData(); fd.append('id', CUR.id);
      Array.prototype.forEach.call(e.target.files, function (f) { fd.append('files[]', f); });
      toast('Завантажую фото…');
      api('upload', fd, true).then(function (d) {
        if (!d.ok || !d.urls.length) return toast('Фото не завантажено', 1);
        CUR = collect(); CUR.photos = (CUR.photos || []).concat(d.urls); DIRTY = true; drawPhotos(); toast('Додано ' + d.urls.length + ' фото — не забудьте зберегти');
      });
    }
  });
  $('#ed').addEventListener('click', function (e) {
    var b = e.target.closest('button'); if (!b) return;
    if (b.dataset.ph) {
      var i = +b.dataset.i, a = CUR.photos; CUR = collect(); CUR.photos = a;
      if (b.dataset.ph === 'x') a.splice(i, 1);
      if (b.dataset.ph === 'l' && i > 0) a.splice(i - 1, 0, a.splice(i, 1)[0]);
      if (b.dataset.ph === 'r' && i < a.length - 1) a.splice(i + 1, 0, a.splice(i, 1)[0]);
      DIRTY = true; drawPhotos(); return;
    }
    var f = $('#pf');
    switch (b.dataset.do) {
      case 'save': save(); break;
      case 'addurl': var u = $('#phurl').value.trim(); if (/^(https:\/\/|\/media\/)/.test(u)) { var ph = CUR.photos || []; CUR = collect(); CUR.photos = ph.concat([u]); DIRTY = true; drawPhotos(); $('#phurl').value = ''; } break;
      case 'gtitle': f.title.value = G.title(collect()); DIRTY = true; counters(); break;
      case 'gdesc':
        if (f.description.value && !confirm('Замінити поточний опис згенерованим?')) return;
        f.description.value = G.desc(collect()); DIRTY = true; counters(); break;
      case 'gshort': f.short.value = G.short(collect()); DIRTY = true; break;
      case 'ctitle': copy(f.title.value); break;
      case 'cdesc': copy(f.description.value); break;
      case 'copy': (DIRTY ? save() : Promise.resolve()).then(function () { return api('create', {copy: CUR.id}); }).then(function (d) { load().then(function () { open(d.p.id); toast('Створено копію ' + d.p.id); }); }); break;
      case 'arch':
        if (!CUR.archived && !confirm('Перенести картку в архів? Вона зникне з сайту, але її можна буде повернути.')) return;
        api('archive', {id: CUR.id, on: !CUR.archived}).then(function (d) { CUR = d.p; draw(); load(); }); break;
    }
  });
  function copy(t) { navigator.clipboard.writeText(t).then(function () { toast('Скопійовано'); }, function () { toast('Не вдалося скопіювати', 1); }); }
  document.addEventListener('keydown', function (e) { if ((e.ctrlKey || e.metaKey) && e.key === 's' && CUR) { e.preventDefault(); save(); } });
  window.addEventListener('beforeunload', function (e) { if (DIRTY) { e.preventDefault(); e.returnValue = ''; } });

  $('#b-new').onclick = function () { api('create', {}).then(function (d) { load().then(function () { open(d.p.id); }); }); };
  $('#b-pub').onclick = function () { api('publish').then(function () { toast('Сайт і фіди оновляться протягом кількох хвилин'); $('#b-pub').classList.remove('hot'); }); };
  $('#b-exp').onchange = function () { var v = this.value.split(':'); if (v[0]) location.href = '/admin/export.php?cat=' + v[0] + '&mode=' + v[1]; this.value = ''; };
  $('#b-out').onclick = function () { api('logout').then(function () { location.reload(); }); };

  /* ---------- text generator (OLX rules of AutoBeam) ---------- */
  var BR_CYR = {Mazda: ['Мазда'], Ford: ['Форд'], Toyota: ['Тойота'], Honda: ['Хонда'], Nissan: ['Ніссан', 'Ниссан'], Hyundai: ['Хюндай', 'Хендай', 'Хундай'],
    Kia: ['Кіа', 'Киа'], Jeep: ['Джип'], Subaru: ['Субару'], Volkswagen: ['Фольксваген', 'VW'], Audi: ['Ауді', 'Ауди'], Lexus: ['Лексус'],
    Infiniti: ['Інфініті', 'Инфинити'], Acura: ['Акура'], 'Land Rover': ['Ленд Ровер', 'Лэнд Ровер'], Mercedes: ['Мерседес'], Tesla: ['Тесла'],
    Chevrolet: ['Шевроле'], Dodge: ['Додж']};
  var MD_CYR = {'Escape': ['Ескейп', 'Эскейп', 'Kuga'], 'Edge': ['Едж', 'Эдж'], 'Fusion': ['Фьюжн', 'Фьюжен'], 'EcoSport': ['Екоспорт', 'Экоспорт'], 'Mustang Mach-E': ['Мустанг Мак-І', 'Мустанг Мах-Е', 'Mach E'],
    'Mustang': ['Мустанг'], 'Compass': ['Компас'], 'Cherokee': ['Черокі', 'Чероки'], 'Grand Cherokee': ['Гранд Черокі', 'Гранд Чероки'], 'Grand Wagoneer': ['Гранд Вагонір', 'Гранд Вагонир'],
    'Sorento': ['Соренто'], 'Niro': ['Ніро', 'Ниро'], 'Accord': ['Акорд', 'Аккорд'], 'Civic': ['Сівік', 'Цивик'], 'CR-V': ['СРВ', 'ЦРВ', 'CRV'], 'Pilot': ['Пілот', 'Пилот'], 'MDX': ['МДХ'],
    'Corolla': ['Королла', 'Корола'], 'RAV4': ['Рав4', 'Рав 4', 'RAV 4'], 'Camry': ['Камрі', 'Камри'], 'Venza': ['Венза'], 'Highlander': ['Хайлендер', 'Хайлэндер'],
    'Grand Highlander': ['Гранд Хайлендер'], 'Prius': ['Пріус', 'Приус'], 'Prius Prime': ['Пріус Прайм', 'Приус Прайм'], 'Yaris': ['Яріс', 'Ярис'], 'bZ4X': ['БЗ4Х', 'bZ4X'],
    '3': ['3', 'тройка'], '6': ['6', 'шістка'], 'CX-5': ['СХ-5', 'СХ5', 'ЦХ5', 'CX5'], 'CX-9': ['СХ-9', 'СХ9', 'CX9'], 'CX-30': ['СХ-30', 'СХ30', 'CX30'], 'CX-50': ['СХ-50', 'СХ50', 'CX50'],
    'CX-70 / CX-90': ['СХ-90', 'СХ-70', 'CX90', 'CX70'], 'Rogue': ['Рог', 'Роуг'], 'Rogue Sport': ['Рог Спорт', 'Qashqai', 'Кашкай'], 'Pathfinder': ['Патфайндер'], 'Kicks': ['Кікс', 'Кикс'],
    'Sentra': ['Сентра'], 'Murano': ['Мурано'], 'Ariya': ['Арія', 'Ария'], 'A3': ['А3'], 'A4': ['А4'], 'e-tron': ['Етрон', 'Е-трон'], 'Atlas': ['Атлас'], 'Atlas Cross Sport': ['Атлас Крос Спорт', 'Атлас Кросс Спорт'],
    'Jetta': ['Джетта'], 'Passat': ['Пассат'], 'Tiguan': ['Тігуан', 'Тигуан'], 'Taos': ['Таос'], 'Outback / Legacy': ['Аутбек', 'Аутбэк', 'Легасі', 'Легаси'], 'Forester': ['Форестер'],
    'QX50 / QX55': ['QX50', 'QX55', 'КуХ50'], 'QX60': ['КуХ60'], 'RX': ['РХ', 'RX350', 'RX450h'], 'NX': ['НХ', 'NX350'], 'Elantra': ['Елантра', 'Элантра'], 'Ioniq 5': ['Іоні 5', 'Ионик 5'],
    'Kona': ['Кона'], 'Santa Fe': ['Санта Фе'], 'Sonata': ['Соната'], 'Palisade': ['Палісейд', 'Палисад'], 'Dart': ['Дарт'], 'Discovery': ['Діскавері', 'Дискавери'],
    'Discovery Sport': ['Діскавері Спорт', 'Дискавери Спорт'], 'Range Rover Evoque': ['Евок', 'Эвок', 'Evoque'], 'Range Rover': ['Рендж Ровер', 'Ренж Ровер'], 'Defender': ['Дефендер'],
    'Bolt EV / EUV': ['Болт', 'Bolt EV', 'Bolt EUV'], 'CLA': ['ЦЛА', 'CLA250'], 'C-Class': ['С-клас', 'C300', 'W206'], 'Model Y': ['Модел Y', 'Model Y Juniper']};
  // noun, gender (f/m/n) by language
  var KW = {
    'Фара': {ua: ['фара', 'фара передня', 'передня фара', 'фара головного світла', 'оптика'], ru: ['фара', 'фара передняя', 'передняя фара', 'оптика'], en: ['headlight', 'headlamp', 'head light', 'front lamp'], g: 'f', n: 'фара', what: 'фари'},
    'Ліхтар': {ua: ['ліхтар', 'задній ліхтар', 'ліхтар задній', 'задня оптика'], ru: ['фонарь', 'задний фонарь', 'стоп', 'задняя оптика'], en: ['tail light', 'taillight', 'tail lamp', 'rear lamp'], g: 'm', n: 'ліхтар', what: 'ліхтаря'},
    'ДХО': {ua: ['ДХО', 'ДХВ', 'ДХО ДХВ', 'денні ходові вогні'], ru: ['ДХО', 'дневные ходовые огни'], en: ['DRL', 'daytime running light', 'daytime running lamp'], g: 'm', n: 'ДХО ДХВ', what: 'ДХО'},
    'Повторювач': {ua: ['повторювач', 'повторювач повороту', 'поворот'], ru: ['повторитель', 'повторитель поворота', 'поворотник'], en: ['turn signal', 'turn signal light', 'side marker'], g: 'm', n: 'повторювач повороту', what: 'повторювача'},
    'Скло фари': {ua: ['скло фари', 'скло на фару', 'стекло фари'], ru: ['стекло фары', 'стекло на фару'], en: ['headlight lens', 'headlamp lens', 'headlight cover'], g: 'n', n: 'скло фари', what: 'скла'},
    'Корпус фари': {ua: ['корпус фари', 'корпус на фару', 'маска фари'], ru: ['корпус фары', 'маска фары'], en: ['headlight housing', 'headlamp housing', 'headlight bezel'], g: 'm', n: 'корпус фари', what: 'корпусу'}
  };
  var SIDE_W = {
    'Ліва': {f: 'ліва', m: 'лівий', n: 'ліве', ru: ['левая', 'левый'], en: ['left', 'LH', 'driver side'], full: 'ліва (водійська)'},
    'Права': {f: 'права', m: 'правий', n: 'праве', ru: ['правая', 'правый'], en: ['right', 'RH', 'passenger side'], full: 'права (пасажирська)'},
    'Пара (ліва + права)': {f: 'ліва та права', m: 'лівий та правий', n: 'ліве та праве', ru: ['левая правая', 'комплект'], en: ['left right', 'pair', 'LH RH'], full: 'ліва + права (комплект)'},
    'Центральна': {f: 'центральна', m: 'центральний', n: 'центральне', ru: ['центральный'], en: ['center'], full: 'центральний'}
  };
  function years(y) {
    var m = String(y || '').match(/(\d{4})\s*[–-]\s*(\d{4})/), p = String(y || '').match(/(\d{4})\+/), s = String(y || '').match(/^(\d{4})$/);
    var a = [];
    if (m) for (var i = +m[1]; i <= +m[2]; i++) a.push(i);
    else if (p) a = [+p[1], +p[1] + 1];
    else if (s) a = [+s[1]];
    return a;
  }
  function yshort(y) { var a = years(y); return a.length > 1 ? a[0] + '-' + a[a.length - 1] : (a[0] || ''); }
  function pnVariants(pn) {
    var c = String(pn).toUpperCase().replace(/^P(?=\d{8})/, ''), raw = c.replace(/[^0-9A-Z]/g, '');
    var out = [String(pn).trim(), raw, c.replace(/-/g, ' ')];
    if (/^\d{8}[A-Z]{2}$/.test(raw)) out.push('P' + raw);                    // Mopar
    return out;
  }
  function uniq(a) { var s = {}, o = []; a.forEach(function (x) { x = String(x).replace(/\s+/g, ' ').trim(); var k = x.toLowerCase(); if (x && !s[k]) { s[k] = 1; o.push(x); } }); return o; }
  var G = {
    title: function (p) {
      var k = KW[p.kind] || KW['Фара'], sw = SIDE_W[p.side];
      var t = [p.kind === 'ДХО' ? 'ДХО ДХВ' : p.kind, sw ? sw[k.g] : '', p.brand, p.model, yshort(p.years), p.trim, 'США', p.original === 'Аналог' ? '' : 'ОРИГІНАЛ'].filter(Boolean).join(' ');
      return t.replace(/\s+/g, ' ').slice(0, 70).trim();
    },
    names: function (p) {
      var b = p.brand || '', models = String(p.model || '').split(/\s*\/\s*/).filter(Boolean), out = [];
      models.forEach(function (m) {
        out.push(b + ' ' + m, b + ' ' + m.replace(/-/g, ''), b + ' ' + m.replace(/-/g, ' '));
        (MD_CYR[p.model] || MD_CYR[m] || []).forEach(function (mc) {
          out.push(b + ' ' + mc); (BR_CYR[b] || []).forEach(function (bc) { out.push(bc + ' ' + mc); });
        });
        (BR_CYR[b] || []).forEach(function (bc) { out.push(bc + ' ' + m); });
        if (p.body) out.push(b + ' ' + m + ' ' + p.body);
      });
      return uniq(out);
    },
    keywords: function (p) {
      var k = KW[p.kind] || KW['Фара'], sw = SIDE_W[p.side] || null, names = G.names(p), ys = years(p.years), out = [];
      var main = names.slice(0, 3);
      names.forEach(function (n) { out.push(n); });
      main.forEach(function (n) { ys.forEach(function (y) { out.push(n + ' ' + y); }); out.push(n + ' ' + yshort(p.years), n + ' USA', n + ' США', n + ' Америка', n + ' US Spec'); if (p.trim) out.push(n + ' ' + p.trim); });
      names.forEach(function (n) {
        k.ua.forEach(function (w) { out.push(w + ' ' + n); if (sw) out.push((sw[k.g] || '') + ' ' + w + ' ' + n); });
        k.ru.forEach(function (w) { out.push(w + ' ' + n); if (sw) sw.ru.forEach(function (s) { out.push(s + ' ' + w + ' ' + n); }); });
      });
      main.forEach(function (n) {
        k.en.forEach(function (w) { out.push(n + ' ' + w); if (sw) sw.en.forEach(function (s) { out.push(n + ' ' + s + ' ' + w); }); ys.forEach(function (y) { out.push(n + ' ' + y + ' ' + w); }); });
        out.push(n + ' OEM ' + k.en[0], 'Genuine ' + n + ' ' + k.en[0], 'original ' + n + ' ' + k.en[0], 'оригінал ' + n, 'оригинал ' + n);
      });
      [p.pn].concat(p.pn_alt || []).filter(Boolean).forEach(function (pn) {
        pnVariants(pn).forEach(function (v) { out.push(v, p.brand + ' ' + v, main[0] + ' ' + v); if (sw) out.push(sw.en[1] + ' ' + v); });
      });
      return uniq(out);
    },
    desc: function (p) {
      var k = KW[p.kind] || KW['Фара'], sw = SIDE_W[p.side], g = k.g;
      var adj = {f: ['оригінальна', 'нова'], m: ['оригінальний', 'новий'], n: ['оригінальне', 'нове']}[g];
      var isNew = p.state === 'Нове', orig = p.original !== 'Аналог';
      var pr = g === 'f' ? 'Продається' : 'Продається';
      var lead = pr + ' ' + (orig ? adj[0] + ' ' : '') + (isNew ? adj[1] + ' ' : '') + (sw ? sw[g] + ' ' : '') + (p.kind === 'Фара' ? 'передня фара' : k.n) +
        ' ' + p.brand + ' ' + p.model + ' ' + (p.years || '') + ' (' + [p.body, p.trim ? 'виконання ' + p.trim : '', 'USA'].filter(Boolean).join(', ') + ').';
      var cond = p.kind === 'Фара' ? 'Фара у гарному стані, комплектність та стан відповідають фотографіям.' : 'Стан і комплектність відповідають фотографіям.';
      var pns = [p.pn].concat(p.pn_alt || []).filter(Boolean);
      var lines = [lead.replace(/\s+/g, ' ').replace(' ()', '') + ' ' + cond, ''];
      if (p.trim) lines.push('Тип: ' + p.trim);
      if (sw) lines.push('Сторона: ' + sw.full);
      if (pns.length) lines.push('Номер запчастини: ' + uniq(pns.concat(pns.map(function (x) { return x.replace(/[^0-9A-Z]/gi, ''); }))).join(', '));
      lines.push('', (orig ? 'Оригінальна заводська оптика ' + p.brand + ' для американського ринку.' : 'Якісний аналог, повна відповідність оригіналу за кріпленнями та розʼємами.'), '',
        'За додатковим запитом буде наданий детальний відеоогляд ' + k.what + '.', '', '');
      var text = lines.join('\n'), kw = G.keywords(p), room = 9000 - text.length - 10, sel = [], len = 0;
      for (var i = 0; i < kw.length; i++) { if (len + kw[i].length + 2 > room) break; sel.push(kw[i]); len += kw[i].length + 2; }
      return text + sel.join(', ') + '.';
    },
    short: function (p) {
      var k = KW[p.kind] || KW['Фара'], sw = SIDE_W[p.side];
      return [(p.original === 'Аналог' ? '' : 'ОРИГІНАЛ'), p.kind === 'ДХО' ? 'ДХО ДХВ' : p.kind, sw ? sw[k.g] : '', p.brand, p.model, p.years, p.trim, 'США.'].filter(Boolean).join(' ') +
        ' ' + (p.state === 'Нове' ? 'Нове.' : 'Б/У.') + (p.pn ? ' Номер запчастини: ' + p.pn + '.' : '') + ' Ціна за 1 шт.';
    }
  };

  api('keys').then(function (d) { KEYS = d.keys || []; });
  load();
})();
