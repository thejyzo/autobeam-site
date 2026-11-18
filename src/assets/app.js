(function () {
  var C = window.AB_CONFIG || {};

  /* ---------- Analytics (Google Ads / GA4) ---------- */
  window.dataLayer = window.dataLayer || [];
  function gtag() { dataLayer.push(arguments); }
  window.gtag = window.gtag || gtag;
  if (C.gtag_id) {
    var s = document.createElement('script');
    s.async = true; s.src = 'https://www.googletagmanager.com/gtag/js?id=' + C.gtag_id;
    document.head.appendChild(s);
    gtag('js', new Date()); gtag('config', C.gtag_id);
  }
  function track(kind, ctx) {
    var pid = (document.querySelector('[data-pid]') || {}).dataset;
    gtag('event', 'contact_' + kind, { method: kind, placement: ctx || '', item_id: pid ? pid.pid : '' });
    var conv = (C.ads_conversion || {})[kind];
    if (conv) gtag('event', 'conversion', { send_to: conv });
  }

  function toast(msg) {
    var t = document.createElement('div'); t.className = 'toast'; t.textContent = msg;
    document.body.appendChild(t); setTimeout(function () { t.remove(); }, 3500);
  }
  function copy(text) {
    if (navigator.clipboard) return navigator.clipboard.writeText(text).catch(function () {});
  }

  document.addEventListener('click', function (e) {
    var a = e.target.closest('[data-track]');
    if (a) {
      track(a.dataset.track, a.dataset.ctx);
      // On a product page, put a ready-made message in the clipboard before opening the messenger
      var prod = document.querySelector('.product');
      if (prod && (a.dataset.track === 'telegram' || a.dataset.track === 'viber')) {
        var name = document.querySelector('.p-info h1').textContent.trim();
        var pn = (document.querySelector('.copy') || {}).dataset;
        var msg = 'Доброго дня! Цікавить: ' + name + (pn && pn.copy ? ' (парт-номер ' + pn.copy + ')' : '') + '\n' + location.href;
        copy(msg); toast('Текст запиту скопійовано — вставте його в чат');
      }
    }
    var c = e.target.closest('.copy');
    if (c) { copy(c.dataset.copy); c.textContent = 'скопійовано'; }
    var th = e.target.closest('.thumb');
    if (th) {
      document.getElementById('gmain').src = th.dataset.src;
      document.querySelectorAll('.thumb').forEach(function (x) { x.classList.toggle('active', x === th); });
    }
  });

  /* ---------- Catalog ---------- */
  var data = window.CATALOG, grid = document.getElementById('grid');
  if (!data || !grid) return;
  var st = { q: '', brand: '', side: '', sort: 'new' };
  var params = new URLSearchParams(location.search);
  st.q = params.get('q') || ''; st.brand = params.get('brand') || '';

  var norm = function (s) { return (s || '').toLowerCase().replace(/[\s\-–.\/()]/g, ''); };
  data.forEach(function (d, i) { d._i = i; d._s = norm(d.name + d.pn + d.brand + d.years + d.light + d.side + d.kind); });
  var esc = function (s) { return String(s || '').replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); };
  var fmt = function (p) { return p.toLocaleString('uk-UA').replace(/,/g, ' ') + ' грн'; };

  function render() {
    var words = st.q.toLowerCase().split(/\s+/).filter(Boolean).map(norm);
    var list = data.filter(function (d) {
      return (!st.brand || d.brand === st.brand) &&
        (!st.side || d.side === st.side || (st.side !== 'Ліва + права' && d.side === 'Ліва + права')) &&
        words.every(function (w) { return d._s.indexOf(w) > -1; });
    });
    if (st.sort === 'cheap') list.sort(function (a, b) { return a.price - b.price; });
    else if (st.sort === 'exp') list.sort(function (a, b) { return b.price - a.price; });
    else list.sort(function (a, b) { return a._i - b._i; });
    grid.innerHTML = list.map(function (d) {
      var meta = [d.side, d.light, d.years].filter(Boolean).join(' · ');
      return '<a class="card" href="fary/' + d.slug + '.html"><div class="card-img"><img loading="lazy" src="' + d.img + '" alt="' + esc(d.name) + '"></div>' +
        '<div class="card-body"><div class="card-brand">' + esc(d.brand) + ' · ' + esc(d.kind) + '</div><h3>' + esc(d.name) + '</h3>' +
        '<div class="card-meta">' + esc(meta) + '</div>' + (d.pn ? '<div class="card-pn">' + esc(d.pn) + '</div>' : '') +
        '<div class="card-price">' + fmt(d.price) + '</div></div></a>';
    }).join('');
    var filtered = st.q || st.brand || st.side;
    document.getElementById('count').textContent = filtered ? 'знайдено ' + list.length : '';
    document.getElementById('empty').hidden = list.length > 0;
    document.querySelectorAll('#brands .chip').forEach(function (b) { b.classList.toggle('active', b.dataset.brand === st.brand); });
    document.querySelectorAll('#sides .chip').forEach(function (b) { b.classList.toggle('active', b.dataset.side === st.side); });
  }

  var q2 = document.getElementById('q2'), q = document.getElementById('q');
  q2.value = st.q;
  var timer;
  q2.addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(function () { st.q = q2.value; render(); }, 120); });
  document.getElementById('sort').addEventListener('change', function (e) { st.sort = e.target.value; render(); });
  document.getElementById('brands').addEventListener('click', function (e) { var b = e.target.closest('.chip'); if (b) { st.brand = b.dataset.brand; render(); } });
  document.getElementById('sides').addEventListener('click', function (e) { var b = e.target.closest('.chip'); if (b) { st.side = b.dataset.side; render(); } });
  function go() {
    st.q = q2.value = q.value; render();
    gtag('event', 'search', { search_term: q.value });
    document.getElementById('catalog').scrollIntoView();
  }
  document.getElementById('finder-go').addEventListener('click', go);
  q.addEventListener('keydown', function (e) { if (e.key === 'Enter') go(); });
  if (st.q || st.brand) { render(); document.getElementById('catalog').scrollIntoView(); }
})();
