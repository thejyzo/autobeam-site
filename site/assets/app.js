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

  /* ---------- Prices: USD in data, UAH shown at today's rate (/rate.json = bank sell rate + 1 UAH) ---------- */
  var RATE = C.rate_fallback || 46;
  var sp = function (n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ' '); };
  function priceHtml(u) {
    var h = '<b class="uah">' + sp(Math.ceil(u * RATE / 100) * 100) + ' грн</b>';
    if (C.show_usd) h += ' <small class="usd">$' + sp(u) + '</small>';
    return h;
  }
  window.ABPrice = priceHtml;
  function refreshPrices() { document.querySelectorAll('[data-usd]').forEach(function (el) { el.innerHTML = priceHtml(+el.dataset.usd); }); }
  fetch(C.rate_url || '/rate.json', { cache: 'no-cache' }).then(function (r) { return r.json(); })
    .then(function (r) { if (r && r.rate > 20 && r.rate < 200) { RATE = r.rate; refreshPrices(); } }).catch(function () {});

  /* ---------- "Any part from USA" request ---------- */
  var modal = document.getElementById('req-modal'), form = document.getElementById('req-form'), msg = document.getElementById('req-msg');
  function openReq(ctx, part) {
    modal.hidden = false; msg.hidden = true;
    if (part && !form.part.value) form.part.value = part;
    setTimeout(function () { (form.part.value ? form.phone : form.part).focus(); }, 50);
    gtag('event', 'request_open', { placement: ctx || '' });
  }
  document.addEventListener('click', function (e) {
    var t = e.target.closest('[data-req]');
    if (t) { e.preventDefault(); openReq(t.dataset.req, t.dataset.part); }
    if (e.target.closest('[data-req-close]')) modal.hidden = true;
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') modal.hidden = true; });
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var data = {}; new FormData(form).forEach(function (v, k) { data[k] = v; });
    data.page = location.href;
    if (!data.part.trim() || data.phone.replace(/\D/g, '').length < 9) {
      msg.hidden = false; msg.className = 'req-msg err'; msg.textContent = 'Вкажіть, що потрібно знайти, і телефон.'; return;
    }
    var btn = form.querySelector('button[type=submit]'); btn.disabled = true; btn.textContent = 'Надсилаємо…';
    fetch(C.request_endpoint || '/api/request.php', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
      .then(function (r) { return r.json(); })
      .then(function (r) {
        if (!r.ok) throw new Error(r.error || 'err');
        msg.hidden = false; msg.className = 'req-msg ok'; msg.textContent = 'Дякуємо! Запит отримали — звʼяжемося з вами найближчим часом.';
        form.reset(); track('request', 'form');
        var conv = (C.ads_conversion || {}).request; if (conv) gtag('event', 'conversion', { send_to: conv });
      })
      .catch(function () { msg.hidden = false; msg.className = 'req-msg err'; msg.textContent = 'Не вдалося надіслати. Напишіть нам у Telegram або Viber.'; })
      .finally(function () { btn.disabled = false; btn.textContent = 'Надіслати запит'; });
  });

  /* ---------- Catalog ---------- */
  var data = window.CATALOG, grid = document.getElementById('grid');
  if (!data || !grid) return;
  var st = { q: '', brand: '', model: '', side: '', av: '', sort: 'new' };
  var MODELS = window.MODELS || {};
  var params = new URLSearchParams(location.search);
  st.q = params.get('q') || ''; st.brand = params.get('brand') || ''; st.model = params.get('model') || '';
  if (st.model && MODELS[st.model]) st.brand = MODELS[st.model].brand;

  var norm = function (s) { return (s || '').toLowerCase().replace(/[\s\-–.\/()]/g, ''); };
  data.forEach(function (d, i) { d._i = i; d._s = norm(d.name + d.pn + d.brand + d.years + d.light + d.side + d.kind); });
  var esc = function (s) { return String(s || '').replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); };
  var fmt = function (u) { return priceHtml(u); };

  function render() {
    var words = st.q.toLowerCase().split(/\s+/).filter(Boolean).map(norm);
    var list = data.filter(function (d) {
      return (!st.av || st.av === (d.st || (d.order ? 'order' : 'in'))) && (!st.brand || d.brand === st.brand) && (!st.model || d.model === st.model) &&
        (!st.side || d.side === st.side || (d.side || '').indexOf('Пара') === 0 && st.side === 'Ліва + права' || (st.side !== 'Ліва + права' && d.side === 'Ліва + права')) &&
        words.every(function (w) { return d._s.indexOf(w) > -1; });
    });
    var RK = {in: 0, soon: 1, order: 2}; var ob = function (a, b) { return (RK[a.st] || 0) - (RK[b.st] || 0) || (a.order ? 1 : 0) - (b.order ? 1 : 0); };
    var pr = function (d) { return d.uah ? d.uah / RATE : d.price; };
    if (st.sort === 'cheap') list.sort(function (a, b) { return ob(a, b) || pr(a) - pr(b); });
    else if (st.sort === 'exp') list.sort(function (a, b) { return ob(a, b) || pr(b) - pr(a); });
    else list.sort(function (a, b) { return a._i - b._i; });
    grid.innerHTML = list.map(function (d) {
      if (d.order) return '<a class="card card-order" href="fary/' + d.slug + '.html"><div class="card-img ph"><span class="ph-brand">' + esc(d.brand) + '</span><span class="ph-model">' + esc((MODELS[d.model] || {}).name || '') + '</span><span class="badge">Під замовлення</span></div>' +
        '<div class="card-body"><div class="card-brand">' + esc(d.brand) + ' · ' + esc(d.kind) + '</div><h3>' + esc(d.name) + '</h3><div class="card-meta">' + esc([d.side, d.years].filter(Boolean).join(' · ')) + '</div><div class="card-price card-price-order">Ціна за запитом</div></div></a>';
      var meta = [d.side, d.light, d.years].filter(Boolean).join(' · ');
      var badge = d.st === 'soon' ? '<span class="badge badge-soon">Незабаром у наявності</span>' : d.st === 'order' ? '<span class="badge badge-order">Під замовлення</span>' : '';
      return '<a class="card" href="fary/' + d.slug + '.html"><div class="card-img"><img loading="lazy" src="' + d.img + '" alt="' + esc(d.name) + '">' + badge + '</div>' +
        '<div class="card-body"><div class="card-brand">' + esc(d.brand) + ' · ' + esc(d.kind) + '</div><h3>' + esc(d.name) + '</h3>' +
        '<div class="card-meta">' + esc(meta) + '</div>' + (d.pn ? '<div class="card-pn">' + esc(d.pn) + '</div>' : '') +
        (d.uah ? '<div class="card-price"><b class="uah">' + sp(d.uah) + ' грн</b></div>' : d.price ? '<div class="card-price" data-usd="' + d.price + '">' + fmt(d.price) + '</div>' : '<div class="card-price card-price-order">Ціна за запитом</div>') + '</div></a>';
    }).join('');
    var filtered = st.q || st.brand || st.side || st.model || st.av;
    document.getElementById('count').textContent = filtered ? 'знайдено ' + list.length : '';
    var m = MODELS[st.model], label = m ? m.brand + ' ' + m.name : st.brand;
    document.getElementById('cat-title').firstChild.nodeValue = label ? 'Фари ' + label + ' ' : 'Каталог ';
    document.getElementById('empty-title').textContent = label ? 'Фар для ' + label + ' зараз немає в наявності' : 'Такої фари зараз немає в наявності';
    document.getElementById('empty').hidden = list.length > 0;
    var inStock = list.filter(function (d) { return (d.st || 'in') === 'in'; }).length;
    if (label && !st.av && list.length && !inStock) document.getElementById('count').textContent = 'зараз немає в наявності — під замовлення ' + list.length;
    document.querySelectorAll('#side button[data-brand]').forEach(function (b) {
      b.classList.toggle('active', b.dataset.model === st.model && (b.dataset.model ? true : b.dataset.brand === st.brand && !st.brand));
    });
    document.querySelectorAll('.side-brand').forEach(function (d) {
      var on = d.dataset.brand === st.brand; d.classList.toggle('active-brand', on); if (on) d.open = true;
    });
    document.querySelectorAll('#sides .chip').forEach(function (b) { b.classList.toggle('active', b.dataset.side === st.side); });
    document.querySelectorAll('#avail .chip').forEach(function (b) { b.classList.toggle('active', b.dataset.av === st.av); });
    // availability counts follow the current brand/model/search; hide the block inside one model
    var scope = data.filter(function (d) { return (!st.brand || d.brand === st.brand) && (!st.model || d.model === st.model) && words.every(function (w) { return d._s.indexOf(w) > -1; }); });
    var cnt = {in: 0, soon: 0, order: 0}; scope.forEach(function (d) { cnt[d.st || (d.order ? 'order' : 'in')]++; });
    var av = document.getElementById('avail');
    ['in', 'soon', 'order'].forEach(function (k) { var b = av.querySelector('[data-av=' + k + ']'); if (b) { b.querySelector('span').textContent = cnt[k]; b.hidden = !cnt[k] && k === 'soon'; } });
    av.hidden = !!st.model;
    var act = document.querySelector('#side .side-model.active');
    if (act) { var sb = document.getElementById('side'); sb.scrollTop = act.offsetTop - sb.clientHeight / 2; }
    try {
      var u = new URL(location.href); ['q', 'brand', 'model'].forEach(function (k) { u.searchParams.delete(k); });
      if (st.model) u.searchParams.set('model', st.model); else if (st.brand) u.searchParams.set('brand', st.brand);
      if (st.q) u.searchParams.set('q', st.q);
      history.replaceState(null, '', u.pathname + u.search + u.hash);
    } catch (e) {}
  }

  var side = document.getElementById('side'), backdrop = document.getElementById('side-backdrop');
  function sideOpen(on) { side.classList.toggle('open', on); backdrop.classList.toggle('open', on); }
  document.querySelector('.side-open').addEventListener('click', function () { sideOpen(true); });
  document.querySelector('.side-close').addEventListener('click', function () { sideOpen(false); });
  backdrop.addEventListener('click', function () { sideOpen(false); });
  side.addEventListener('click', function (e) {
    var b = e.target.closest('button[data-brand]');
    if (b) {
      st.brand = b.dataset.brand; st.model = b.dataset.model; if (st.model) st.av = '';
      gtag('event', 'select_model', { brand: st.brand, model: st.model });
      render(); sideOpen(false);
      if (window.innerWidth < 900) document.getElementById('catalog').scrollIntoView();
      return;
    }
    var sm = e.target.closest('summary');
    if (sm) {
      e.preventDefault();
      var d = sm.parentElement;
      if (d.open && st.brand === d.dataset.brand && !st.model) { d.open = false; return; }
      st.brand = d.dataset.brand; st.model = ''; render(); d.open = true;
    }
  });

  var q2 = document.getElementById('q2'), q = document.getElementById('q');
  q2.value = st.q;
  var timer;
  q2.addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(function () { st.q = q2.value; render(); }, 120); });
  document.getElementById('sort').addEventListener('change', function (e) { st.sort = e.target.value; render(); });
  document.getElementById('avail').addEventListener('click', function (e) { var b = e.target.closest('.chip'); if (b) { st.av = b.dataset.av; render(); } });
  document.getElementById('sides').addEventListener('click', function (e) { var b = e.target.closest('.chip'); if (b) { st.side = b.dataset.side; render(); } });
  function go() {
    st.q = q2.value = q.value; render();
    gtag('event', 'search', { search_term: q.value });
    document.getElementById('catalog').scrollIntoView();
  }
  document.getElementById('finder-go').addEventListener('click', go);
  q.addEventListener('keydown', function (e) { if (e.key === 'Enter') go(); });
  if (st.q || st.brand || st.model) { render(); document.getElementById('catalog').scrollIntoView(); }
})();
