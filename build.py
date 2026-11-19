#!/usr/bin/env python3
"""AutoBeam static site generator.
Reads data/olx_raw.json (exported from OLX shop) and writes the site into ./site
Run:  python3 build.py
"""
import collections, os, json, re, html, shutil, datetime
from pathlib import Path

ROOT = Path(__file__).parent
SRC = ROOT / "src"
OUT = Path(os.environ.get("AB_OUT", ROOT / "site"))
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
try:   # on the server: today's rate (monobank sell + 1) for prices in the static HTML
    _r = json.loads(Path(os.environ.get("AB_RATE", "/nonexistent")).read_text())["rate"]
    if 20 < _r < 200: CFG["rate_fallback"] = _r
except Exception:
    pass

MODELS = {k: v for k, v in json.loads((ROOT / "data" / "models.json").read_text(encoding="utf-8")).items() if not k.startswith("_")}
ALIASES = json.loads((ROOT / "data" / "aliases.json").read_text(encoding="utf-8"))
def mslug(brand, name):
    n = name[len(brand):] if name.lower().startswith(brand.lower()) else name
    return re.sub(r"[^a-z0-9]+", "-", (brand + " " + n).lower()).strip("-")
BRANDS = sorted(MODELS, key=len, reverse=True) + ["Land Rover", "Mercedes", "Volkswagen", "Chevrolet", "Infiniti", "Hyundai", "Toyota", "Nissan",
          "Subaru", "Lexus", "Mazda", "Honda", "Acura", "Audi", "Jeep", "Ford", "Kia"]

def esc(s): return html.escape(str(s), quote=True)

def img(pid, size="800x600"):
    return f"https://ireland.apollo.olxcdn.com/v1/files/{pid}/image;s={size};q=80"

def usd(p): return round(p / CFG["olx_rate"])          # OLX shows USD prices converted at this rate
def sp(n): return f"{n:,}".replace(",", " ")
def uah(u): return int(-(-u * CFG["rate_fallback"] // 100) * 100)   # always round UP to 100 UAH
def price_html(u):
    """Price block; UAH is the legal price (refreshed in the browser from /rate.json), USD optional."""
    s = f'<b class="uah">{sp(uah(u))} грн</b>'
    if CFG.get("show_usd"): s += f' <small class="usd">${sp(u)}</small>'
    return s

def parse(row):
    oid, title, price, pn, state, ptype, olx_slug, photos = row
    t = title.lower()
    brand = next((b for b in BRANDS if b.lower() in t), "Інше")
    if t.startswith("скло"): kind = "Скло фари"
    elif "корпус" in t: kind = "Корпус фари"
    elif "ліхтар" in t: kind = "Ліхтар"
    elif t.startswith("дхо") : kind = "ДХВ"
    else: kind = "Фара"
    left, right = ("ліва" in t or "ліве" in t or "лів" in t.split()), ("права" in t or "праве" in t or "правий" in t)
    side = "Ліва + права" if left and right else "Ліва" if left else "Права" if right else ""
    if "full led" in t: light = "Full LED"
    elif "bi-led" in t: light = "Bi-LED"
    elif "ксенон" in t or "xenon" in t: light = "Ксенон"
    elif "галоген" in t: light = "Галоген"
    elif "led" in t: light = "LED"
    else: light = ""
    years = re.search(r"(20\d\d)\s*[–-]\s*(20\d\d)|(20\d\d)\+|(20\d\d)", title)
    yrs = ""
    if years:
        yrs = f"{years.group(1)}–{years.group(2)}" if years.group(1) else (years.group(3) + "+" if years.group(3) else years.group(4))
    slug = re.sub(r"-ID[0-9A-Za-z]+\.html$", "", olx_slug)
    clean = re.sub(r"\s+", " ", title.replace("ОРИГІНАЛ", "").replace("оригінал", "")).strip(" ,")
    pns = [x for x in re.split(r"[,\s]+(?=[A-Z0-9P])", pn.strip()) if x] if pn else []
    model = ""
    for mname, rx, _ in MODELS.get(brand, []):
        if re.search(rx, title, re.I):
            model = mslug(brand, mname); break
    return dict(model=model, id=oid, title=title, name=clean, price=usd(price), price_txt="",
                pn=pn, state=state, type=ptype or "Оригінал", brand=brand, kind=kind, side=side,
                light=light, years=yrs, slug=slug, olx=f"https://www.olx.ua/d/uk/obyavlenie/{olx_slug}",
                photos=photos.split(","))

def contact_buttons(ctx, cls="", part=""):
    c = CFG
    req = (f'\n  <button class="btn btn-req" type="button" data-req="{ctx}" data-part="{esc(part)}"><svg><use href="#i-box"/></svg>Залишити заявку</button>' if part else "")
    return f'''<div class="cta-row {cls}">{req}
  <a class="btn btn-tg" href="{c['telegram']}" target="_blank" rel="noopener" data-track="telegram" data-ctx="{ctx}"><svg><use href="#i-tg"/></svg>Telegram</a>
  <a class="btn btn-viber" href="{c['viber']}" data-track="viber" data-ctx="{ctx}"><svg><use href="#i-viber"/></svg>Viber</a>
  <a class="btn btn-call" href="tel:{c['phone_intl']}" data-track="call" data-ctx="{ctx}"><svg><use href="#i-phone"/></svg>{c['phone_display']}</a>
</div>'''

VER = datetime.datetime.now().strftime("%y%m%d%H%M")
TR = dict(zip("абвгґдеєжзиіїйклмнопрстуфхцчшщьюя", ["a","b","v","h","g","d","e","ie","zh","z","y","i","i","i","k","l","m","n","o","p","r","s","t","u","f","kh","ts","ch","sh","shch","","iu","ia"]))
def slugify(t):
    t = "".join(TR.get(ch, ch) for ch in t.lower())
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")

def load_orders():
    """On-order variants = rows of the stock DB (all ever-bought variants, exact side) that are not on sale now.
    A variant is skipped if the same model/years/trim is in stock for the same side (or as a pair)."""
    rows = json.loads((ROOT / "data" / "db_initial.json").read_text(encoding="utf-8"))
    rows = [r for r in rows if r["key"] and r["brand"] in MODELS and r["mname"]]
    norm = lambda r: (r["brand"], r["mname"], r["kind"], r["years"], re.sub(r"[^a-z0-9а-яії]+", "", r["trim"].lower()))
    stock = {}
    for r in rows:
        if r["olx"]: stock.setdefault(norm(r), set()).add(r["side"])
    PAIR = "Пара (ліва + права)"
    out, seen = [], set()
    for r in rows:
        if r["olx"]: continue
        have = stock.get(norm(r), set())
        if r["side"] in have or PAIR in have or (r["side"] == PAIR and {"Ліва", "Права"} <= have): continue
        k = norm(r) + (r["side"],)
        if k in seen: continue
        seen.add(k)
        side_txt = {"Ліва": "ліва", "Права": "права", PAIR: "ліва / права", "Центральна": "центральна"}.get(r["side"], "")
        model_txt = r["mname"] if r["mname"].startswith(r["brand"]) else r["brand"] + " " + r["mname"]
        name = re.sub(r"\s+", " ", f'{r["kind"]} {side_txt} {model_txt} {r["body"]} {r["years"]} {r["trim"]}').strip()
        out.append(dict(order=1, id="o" + str(len(out)), name=name, brand=r["brand"], mname=r["mname"], model=mslug(r["brand"], r["mname"]),
                        kind=r["kind"], side=r["side"], light=r["trim"], years=r["years"], trim=r["trim"] or "—",
                        slug="pid-zamovlennia-" + slugify(name), price=0, pn="", type="Оригінал"))
    return out

def page(tpl_name, **kw):
    tpl = (SRC / tpl_name).read_text(encoding="utf-8")
    shell = (SRC / "_shell.html").read_text(encoding="utf-8")
    body = tpl
    for k, v in kw.items():
        body = body.replace("{{" + k + "}}", str(v))
    out = shell.replace("{{body}}", body)
    for a in ("style.css", "app.js", "config.js", "catalog.js"):
        out = out.replace(f"assets/{a}\"", f"assets/{a}?v={VER}\"")
    for k, v in {**CFG, **kw}.items():
        out = out.replace("{{" + k + "}}", str(v))
    return out

MEDIA_DIR = Path(os.environ.get("AB_MEDIA", Path.home() / "autobeam.com.ua/www/media"))

def pimg(u, size="800x600"):
    """Photo URL in the wanted size. OLX CDN resizes on the fly; own /media files have an optional *_400.jpg thumbnail."""
    if "olxcdn.com" in u: return re.sub(r";s=\d+x\d+(;q=\d+)?", "", u) + f";s={size};q=80"
    if u.startswith("/media/") and int(size.split("x")[0]) <= 400:
        small = re.sub(r"\.(jpe?g|png|webp)$", r"_400.jpg", u)
        if small != u and (MEDIA_DIR / small[len("/media/"):]).exists(): return small
    return u

def aimg(u, size="1200x900"):
    """Absolute photo URL (for og:image, JSON-LD, feeds)."""
    p = pimg(u, size)
    return p if p.startswith("http") else CFG["site_url"] + p

ST_LABEL = {"in": "В наявності", "soon": "Незабаром у наявності", "order": "Під замовлення"}

REDIRECTS = []   # (old pair slug, new slug) — pair pages replaced by single-side cards
PAIR_REPORT = []

def pn_side(brand, num):
    """'L' / 'R' / None from a part number, by the maker's numbering rules (see headlights-reference)."""
    n = re.sub(r"[^0-9A-Z]", "", (num or "").upper())
    n = n[1:] if re.match(r"^P\d{8}", n) else n
    if brand in ("Toyota", "Lexus"):
        if n[:5] in ("81110", "81130", "81140", "81145"): return "R"
        if n[:5] in ("81150", "81170", "81160", "81070", "81185"): return "L"
    elif brand in ("Honda", "Acura"):
        if n.startswith("33100"): return "R"
        if n.startswith("33150"): return "L"
    elif brand in ("Hyundai", "Kia"):
        if n.startswith("92101"): return "L"
        if n.startswith("92102"): return "R"
    elif brand in ("Nissan", "Infiniti"):
        if n.startswith("26010") or n.startswith("26120"): return "R"
        if n.startswith("26060") or n.startswith("26125"): return "L"
    elif brand in ("Volkswagen", "Audi"):
        m = re.search(r"941(\d{3})", n)
        if m: return "L" if int(m.group(1)) % 2 else "R"
    elif brand in ("Ford", "Land Rover"):
        if re.search(r"13(W029|E014|404)", n) or re.search(r"^PR3B13005", n): return "R"   # Mustang S650: 13005 = R, 13006 = L (owner)
        if re.search(r"13(W030|E015|405)", n) or re.search(r"^PR3B13006", n): return "L"
    elif brand in ("Jeep", "Dodge", "Chrysler"):
        m = re.match(r"^(\d{8})", n)
        if m: return "L" if int(m.group(1)) % 2 else "R"
    elif brand == "Mazda":
        if re.search(r"51(030|031|0K0)", n): return "R"
        if re.search(r"51(040|041|0L0)", n): return "L"
    elif brand == "Subaru":
        m = re.match(r"^\d{5}[A-Z]{2}(\d{2})", n)
        if m: return "L" if int(m.group(1)) % 2 else "R"
    elif brand == "Mercedes":
        m = re.match(r"^A?\d{9}(\d)", n)
        if m: return "L" if int(m.group(1)) % 2 else "R"
    return None

GENDER = {"Ліхтар": "m", "Повторювач": "m", "Корпус фари": "m", "Скло фари": "n"}   # Фара, ДХВ: feminine (default)
SIDE_FORMS = {"m": {"Ліва": "Лівий", "Права": "Правий", "Пара": "Лівий / правий"},
              "n": {"Ліва": "Ліве", "Права": "Праве", "Пара": "Ліве / праве"},
              "f": {"Ліва": "Ліва", "Права": "Права", "Пара": "Ліва / права"}}

def side_label(kind, side):
    """Side as shown to people, in the right gender: ліхтар лівий, скло ліве, фара ліва."""
    forms = SIDE_FORMS[GENDER.get(kind, "f")]
    key = "Пара" if (side or "").startswith("Пара") else side
    return forms.get(key, side or "")

def gender_name(it):
    """Fix the side word in the display name (the slug stays as it was, so links do not change)."""
    g = GENDER.get(it["kind"])
    if not g: return it["name"]
    f = SIDE_FORMS[g]
    n = it["name"].replace("ліва / права", f["Пара"].lower(), 1)
    n = re.sub(r"(?<=^" + re.escape(it["kind"]) + r" )ліва\b", f["Ліва"].lower(), n)
    n = re.sub(r"(?<=^" + re.escape(it["kind"]) + r" )права\b", f["Права"].lower(), n)
    return n


def split_pairs(items, stock, seen):
    """Site shows single-side cards only (owner, 19.11). A pair card is replaced by its left/right singles:
    an existing single card with that side's number is used; otherwise a card is generated from the pair
    (that side's number, the pair's photos). Pairs stay in the admin DB and on OLX."""
    nrm = lambda x: re.sub(r"[^0-9A-Z]", "", (x or "").upper()).lstrip("P") if re.match(r"^P\d{8}", re.sub(r"[^0-9A-Z]", "", (x or "").upper())) else re.sub(r"[^0-9A-Z]", "", (x or "").upper())
    singles = [i for i in items if not i["side"].startswith("Пара")]
    out, redirects = list(singles), []
    for it in items:
        if not it["side"].startswith("Пара"): continue
        nums = [x for x in [it["pn"]] + list(it["pn_alt"]) if x]
        by = {"L": [], "R": []}
        for x in nums:
            sd = pn_side(it["brand"], x)
            if sd and nrm(x) not in [nrm(y) for y in by[sd]]: by[sd].append(x)
        if not by["L"] or not by["R"]:
            out.append(it); PAIR_REPORT.append(f'{it["id"]}: сторону номерів не визначено ({", ".join(nums) or "без номера"}) — лишається парою')
            continue
        target = None
        for sd, label in (("L", "Ліва"), ("R", "Права")):
            want = {nrm(x) for x in by[sd]}
            ex = next((s for s in singles if s["brand"] == it["brand"] and s["model"] == it["model"] and s["kind"] == it["kind"]
                       and want & {nrm(y) for y in [s["pn"]] + list(s["pn_alt"])}), None)
            if ex:
                if not ex["photos"] and it["photos"]: ex["photos"] = list(it["photos"])   # pair photos fit the single side too (owner)
                if ex["st"] == "order" and it["st"] != "order" and not ex.get("status_manual_set"): ex["st"] = it["st"]
                PAIR_REPORT.append(f'{it["id"]} {label.lower()}: вже є {ex["id"]}')
                target = target or ex
                continue
            v = dict(it)
            v["id"] = f'{it["id"]}-{sd}'
            v["side"] = label
            v["pn"], v["pn_alt"] = by[sd][0], by[sd][1:]
            v["avto_code"] = ""   # the pair's avto.pro code may hold the other side's number
            v["name"] = it["name"].replace("ліва / права", label.lower(), 1)
            slug = slugify(v["name"])
            if slug in seen: slug += "-" + v["id"].lower()
            seen.add(slug); v["slug"] = slug
            k = it.get("key") or ""
            sk = re.sub(r"\bRH\b", "LH", k.replace("LH + RH", "LH")) if sd == "L" else re.sub(r"\bLH\b", "RH", k.replace("LH + RH", "RH"))
            if stock and sk in stock and not it.get("status_manual_set"):
                q = stock[sk]
                v["st"] = "in" if int(q[0]) > 0 else ("soon" if int(q[1]) + int(q[2]) > 0 else it["st"])
                v["qty"] = int(q[0])
            v["pair_of"] = it["id"]
            out.append(v); target = target or v
            PAIR_REPORT.append(f'{it["id"]} {label.lower()}: створено {v["id"]} ({v["pn"]})')
        if target: redirects.append((it["slug"], target["slug"]))
    return out, redirects

def load_db():
    """Cards from the admin DB (server) or data/products.json (local) + stock from accounting."""
    import sqlite3, os
    dbf = Path(os.environ.get("AB_DB", Path.home() / "autobeam_data/products.sqlite"))
    if dbf.exists():
        con = sqlite3.connect(str(dbf))
        rows = [json.loads(r[0]) for r in con.execute("SELECT data FROM products ORDER BY id")]
    else:
        rows = json.loads((ROOT / "data" / "products.json").read_text(encoding="utf-8"))
    sf = Path(os.environ.get("AB_STOCK", Path.home() / "autobeam_data/stock.json"))
    stock = json.loads(sf.read_text(encoding="utf-8")) if sf.exists() else {}
    SIDE_TXT = {"Ліва": "ліва", "Права": "права", "Пара (ліва + права)": "ліва / права", "Центральна": "центральна"}
    items, seen = [], set()
    for p in rows:
        if p.get("archived") or not p.get("show") or p.get("status_manual") == "Приховати": continue
        if not p.get("brand"): continue
        sm = p.get("status_manual") or ""
        s = stock.get(p.get("key") or "")
        if (p.get("side") or "").startswith("Пара") and stock and p.get("key"):
            # pair card: in stock if at least one side is (owner, 19.11) — DATA may hold "X LH + RH", "X LH", "X RH"
            k = p["key"]
            ks = {k, k.replace("LH + RH", "LH"), k.replace("LH + RH", "RH"), re.sub(r"\bLH\b", "RH", k), re.sub(r"\bRH\b", "LH", k)}
            hits = [stock[x] for x in ks if x in stock]
            if hits:
                s = [sum(int(h[i]) for h in hits) for i in range(3)]
        if sm: st = {"В наявності": "in", "Незабаром у наявності": "soon"}.get(sm, "order")
        elif not stock: st = "in" if p.get("olx_active") else "order"          # stock feed not connected yet
        elif s and int(s[0]) > 0: st = "in"
        elif s and int(s[1]) + int(s[2]) > 0: st = "soon"
        else: st = "order"
        model_txt = p["model"] if p.get("model", "").startswith(p["brand"]) else f'{p["brand"]} {p.get("model", "")}'
        name = re.sub(r"\s+", " ", f'{p["kind"]} {SIDE_TXT.get(p.get("side"), "")} {model_txt} {p.get("body", "")} {p.get("years", "")} {p.get("trim", "")}').strip()
        if p.get("original") == "Аналог":
            name += " — аналог" + (" " + p["avto_maker"] if p.get("avto_maker") else "")
        slug = slugify(name) if st != "order" or p.get("photos") else "pid-zamovlennia-" + slugify(name)
        if slug in seen: slug += "-" + p["id"].lower()
        seen.add(slug)
        price = p.get("price") or 0
        uah_fixed = int(price) if p.get("currency") == "UAH" and price else 0
        items.append(dict(id=p["id"], name=name, title=p.get("title", ""), price=(0 if uah_fixed else int(price or 0)), uah=uah_fixed,
                          pn=p.get("pn", ""), pn_alt=p.get("pn_alt", []), brand=p["brand"], mname=p.get("model", ""),
                          model=mslug(p["brand"], p.get("model", "")) if p.get("model") else "", kind=p["kind"], side=p.get("side", ""),
                          light=p.get("trim", ""), trim=p.get("trim", "") or "—", years=p.get("years", ""), type=p.get("original", "Оригінал"),
                          state=p.get("state", "Вживане"), slug=slug, photos=p.get("photos", []), short=p.get("short", ""),
                          olx=(f'https://www.olx.ua/d/{p["olx_id"]}/' if p.get("olx_id") and p.get("olx_active") else ""), st=st,
                          avto_maker=p.get("avto_maker", ""), avto_code=p.get("avto_code", ""), qty=(int(s[0]) if s else 0), key=p.get("key") or "", status_manual_set=bool(sm)))
    items, REDIRECTS[:] = split_pairs(items, stock, seen)
    for it in items:
        it["name"] = gender_name(it)
        it["sl"] = side_label(it["kind"], it["side"])
    order_rank = {"in": 0, "soon": 1, "order": 2}
    items.sort(key=lambda x: (order_rank[x["st"]], 0 if x["photos"] else 1, x["brand"], x["name"]))
    return [i for i in items if i["photos"]], [i for i in items if not i["photos"]], bool(stock)

def pprice(it):
    if it.get("uah"): return f'<b class="uah">{sp(it["uah"])} грн</b>'
    if not it["price"]: return '<b class="uah">Ціна за запитом</b>'
    return price_html(it["price"])

MAKER = {"Toyota": "TOYOTA", "Lexus": "TOYOTA", "Volkswagen": "VAG", "Audi": "VAG", "Jeep": "CHRYSLER", "Dodge": "CHRYSLER",
         "Kia": "HYUNDAI", "Hyundai": "HYUNDAI", "Nissan": "NISSAN", "Infiniti": "NISSAN", "Honda": "HONDA", "Acura": "HONDA",
         "Land Rover": "LAND ROVER", "Mazda": "MAZDA", "Ford": "FORD", "Subaru": "SUBARU", "Mercedes": "MERCEDES-BENZ",
         "Tesla": "TESLA", "Chevrolet": "GENERAL MOTORS"}

def describe(it):
    """Product description from card data: plain text paragraphs (for the page) — natural wording, model aliases once."""
    m = it["mname"] or ""
    full = m if m.lower().startswith(it["brand"].lower()) else f'{it["brand"]} {m}'.strip()
    kind = it["kind"]
    masc = kind == "Ліхтар"
    side = {"Ліва": "лівий (з боку водія)" if masc else "ліва (з боку водія)", "Права": "правий (з боку пасажира)" if masc else "права (з боку пасажира)",
            "Пара (ліва + права)": "ліва або права (є обидві сторони)", "Центральна": "центральна"}.get(it["side"], "")
    kind_l = {"Фара": "Фара", "Ліхтар": "Задній ліхтар", "ДХВ": "Денні ходові вогні (ДХВ)"}.get(kind, kind)
    light = it["light"] if it["light"] and it["light"] != "—" else ""
    p1 = f'{kind_l} {side} для {full}' + (f' {it["years"]}' if it["years"] else "") + (f', {light}' if light else "") + "."
    if it["type"] == "Аналог":
        p1 += f' Це аналог {it["avto_maker"] or ""} (не оригінал) для авто з ринку США' + (f', відповідник оригіналу {", ".join(it["pn_alt"][:3])}' if it["pn_alt"] else "") + "."
    else:
        p1 += " Оригінал з авто для ринку США."
    g = "m" if masc else ("pl" if kind == "ДХВ" else "f")
    p1 += " Стан: " + ({"m": "новий.", "f": "нова.", "pl": "нові."}[g] if it["state"] == "Нове" else {"m": "вживаний, перевірений перед продажем.", "f": "вживана, перевірена перед продажем.", "pl": "вживані, перевірені перед продажем."}[g])
    nums = [it["pn"]] + [x for x in it["pn_alt"] if x != it["pn"]] if it["pn"] else []
    if it["type"] == "Аналог" and nums:
        p2 = f'Номер {it["avto_maker"] or "аналога"}: {nums[0]}. '
    else:
        p2 = (f'Парт-номер: {nums[0]}' + (f' (також {", ".join(nums[1:4])})' if len(nums) > 1 else "") + ". ") if nums else ""
    p2 += "Звірте номер з етикеткою на корпусі або надішліть нам VIN — перевіримо сумісність до оплати."
    p3 = ("Ціна вказана за одну фару; якщо потрібна пара — повідомте, підготуємо обидві. " if it["side"].startswith("Пара") else "") + "Гарантія 14 днів на перевірку працездатності. Відправка Новою поштою по Україні, з наявності — в день замовлення."
    aka = list(dict.fromkeys(ALIASES["brands"].get(it["brand"], [])[:1] + ALIASES["models"].get(it["brand"] + "|" + m, [])[:3]))
    kw = ALIASES["kinds"].get(kind, [kind.lower()])
    alt = []
    if m:
        bc = ALIASES["brands"].get(it["brand"], [""])[0]
        alt = [f'{kw[0]} {m}', f'{kw[2] if len(kw) > 2 else kw[0]} {full}'] + [f'{kw[0]} {a}' for a in aka[1:]] + \
              ([f'{kw[0]} {bc} {aka[1]}'] if bc and len(aka) > 1 else []) + ([f'{kw[-3]} {full}'] if len(kw) > 3 else [])
    p4 = ("Також шукають як: " + ", ".join(dict.fromkeys(alt)) + ".") if alt else ""
    return [x for x in (p1, p2, p3, p4) if x]


def write_feeds(all_items):
    """avto.pro price list (auto-update by URL): Виробник; Код; Ціна; Кількість; Опис; Б/У; Фото.
    In stock -> real quantity; soon (on the way / repair) -> 1 with a note, like before. Prices in USD."""
    import csv, io
    tok = CFG.get("feed_token")
    if not tok: return
    (OUT / "feeds").mkdir(exist_ok=True)
    buf = io.StringIO(); w = csv.writer(buf, delimiter=";")
    w.writerow(["Производитель", "Код", "Цена", "Количество", "Описание", "Б/У", "Реставрация", "Фото"])   # same column order as the current avto.pro mapping (Фото = 8/H)
    seen = set()
    for it in all_items:
        code = it.get("avto_code") or it["pn"]
        if it["st"] not in ("in", "soon") or not code or not (it["price"] or it["uah"]): continue
        key = re.sub(r"[^0-9A-Z]", "", code.upper())
        if key in seen: continue
        seen.add(key)
        price = it["price"] or round(it["uah"] / CFG["rate_fallback"])
        desc = it["short"] or f'{"ОРИГІНАЛ " if it["type"] == "Оригінал" else ""}{it["name"]} США. {"Нове" if it["state"] == "Нове" else "Б/У"}. Номер запчастини: {it["pn"]}. Ціна за 1 шт.'
        if it["st"] == "soon" and "уточнюйте" not in desc: desc += " В дорозі. Термін постачання уточнюйте."
        photos = ",".join((u if u.startswith("http") else CFG["site_url"] + u) for u in it["photos"][:5])
        w.writerow([it.get("avto_maker") or MAKER.get(it["brand"], it["brand"].upper()), code, price,
                    max(1, it.get("qty") or 1), desc, "+" if it["state"] != "Нове" else "", "", photos])
    (OUT / "feeds" / f"avtopro-{tok}.csv").write_text("\ufeff" + buf.getvalue(), encoding="utf-8")
    (OUT / "feeds" / "index.html").write_text("", encoding="utf-8")

    # Google Merchant Center feed (RSS 2.0 + g: namespace): only in-stock cards with a price, prices as on the page
    from xml.sax.saxutils import escape as xe
    rows = []
    for it in all_items:
        if it["st"] != "in" or not (it["price"] or it["uah"]) or not it.get("photos"): continue
        if not (it["pn"] or it.get("avto_code")): continue   # no part number anywhere -> no Google traffic (owner, 19.11)
        price = it["uah"] or uah(it["price"])
        imgs = [aimg(u) for u in it["photos"][:11]]
        desc = it["short"] or " ".join(describe(it)[:3])
        g = [("g:id", it["id"]), ("g:title", it["name"][:150]), ("g:description", desc[:5000]),
             ("g:link", f'{CFG["site_url"]}/fary/{it["slug"]}.html'), ("g:image_link", imgs[0]),
             *[("g:additional_image_link", u) for u in imgs[1:]],
             ("g:availability", "in_stock"), ("g:price", f"{price} UAH"),
             ("g:condition", "new" if it["state"] == "Нове" else "used"), ("g:brand", it["avto_maker"] if it["type"] == "Аналог" and it["avto_maker"] else it["brand"]),
             ("g:product_type", f'{it["kind"]} > {it["brand"]}')]
        if it["pn"]: g.append(("g:mpn", it["pn"]))
        else: g.append(("g:identifier_exists", "no"))
        rows.append("<item>" + "".join(f"<{k}>{xe(str(v))}</{k}>" for k, v in g) + "</item>")
    (OUT / "feeds" / "google-merchant.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0"><channel>'
        f'<title>AutoBeam</title><link>{CFG["site_url"]}</link><description>Оригінальні фари зі США</description>\n'
        + "\n".join(rows) + "\n</channel></rss>\n", encoding="utf-8")

def main():
    items, orders, have_stock = load_db()
    for o in orders: o["order"] = 1
    if OUT.exists(): shutil.rmtree(OUT)
    (OUT / "fary").mkdir(parents=True)
    shutil.copytree(SRC / "assets", OUT / "assets")
    shutil.copytree(SRC / "api", OUT / "api")
    shutil.copytree(SRC / "admin", OUT / "admin")

    # catalog for client-side filtering
    keys = ("id", "name", "price", "uah", "pn", "brand", "model", "kind", "side", "light", "years", "type", "slug", "st", "sl")
    def pnorm(x):
        x = re.sub(r"[^0-9a-z]", "", x.lower())
        return x[1:] if re.match(r"^p\d{8}", x) else x
    pns = lambda it: sorted({pnorm(x) for x in [it["pn"]] + list(it.get("pn_alt") or []) + [it.get("avto_code") or ""] if len(pnorm(x)) >= 5})
    slim = [dict({k: it.get(k, "") for k in keys}, img=pimg(it["photos"][0], "400x300"), pns=pns(it)) for it in items]
    slim += [dict({k: o.get(k, "") for k in keys}, order=1, pns=pns(o)) for o in orders]
    (OUT / "assets" / "config.js").write_text("window.AB_CONFIG=" + json.dumps(CFG, ensure_ascii=False) + ";", encoding="utf-8")

    # left sidebar: all brands/models ever handled (data/models.json) with in-stock counts
    side = ['<button class="side-all active" data-brand="" data-model="">Усі фари <span>%d</span></button>' % (len(items) + len(orders))]
    models_js = {}
    for b in sorted(MODELS):
        bc = sum(x["brand"] == b and x["st"] == "in" for x in items)
        lis = []
        for mname, rx, yrs in MODELS[b]:
            sl = mslug(b, mname); c = sum(x["model"] == sl and x["st"] == "in" for x in items); oc = sum(o["model"] == sl for o in orders)
            models_js[sl] = {"brand": b, "name": mname, "years": yrs, "aka": " ".join(ALIASES["brands"].get(b, []) + ALIASES["models"].get(b + "|" + mname, []))}
            lis.append(f'<li><button class="side-model{"" if c else " none"}" data-brand="{esc(b)}" data-model="{sl}">'
                       f'<b>{esc(mname)}</b><small>{yrs}</small><span>{str(c) + " в наявн." if c else "під замовлення"}</span></button></li>')
        side.append(f'<details class="side-brand" data-brand="{esc(b)}"><summary><b>{esc(b)}</b><span>{bc or ""}</span></summary><ul>{"".join(lis)}</ul></details>')
    sidebar = "\n".join(side)
    (OUT / "assets" / "catalog.js").write_text("window.CATALOG=" + json.dumps(slim, ensure_ascii=False) + ";window.MODELS=" + json.dumps(models_js, ensure_ascii=False) + ";window.SYN=" + json.dumps({"kinds": ALIASES["kinds"], "sides": ALIASES["sides"]}, ensure_ascii=False) + ";", encoding="utf-8")

    # SSR cards (SEO + no-JS), JS re-renders on filter
    def card(it, base=""):
        meta = " · ".join(x for x in (it.get("sl") or it["side"], it["light"], it["years"]) if x)
        badge = f'<span class="badge badge-{it["st"]}">{ST_LABEL[it["st"]]}</span>' if it["st"] != "in" else ""
        return f'''<a class="card" href="{base}fary/{it['slug']}.html">
  <div class="card-img"><img loading="lazy" src="{pimg(it['photos'][0], '400x300')}" alt="{esc(it['name'])}">{badge}</div>
  <div class="card-body"><div class="card-brand">{esc(it['brand'])} · {esc(it['kind'])}</div>
  <h3>{esc(it['name'])}</h3><div class="card-meta">{esc(meta)}</div>
  {f'<div class="card-pn">{esc(it["pn"])}</div>' if it['pn'] else ''}
  <div class="card-price"{f' data-usd="{it["price"]}"' if it["price"] else ''}>{pprice(it)}</div></div></a>'''

    def ocard(o, base=""):
        return f'''<a class="card card-order" href="{base}fary/{o['slug']}.html">
  <div class="card-img ph"><span class="ph-brand">{esc(o['brand'])}</span><span class="ph-model">{esc(o['mname'])}</span><span class="badge">{ST_LABEL[o.get('st', 'order')]}</span></div>
  <div class="card-body"><div class="card-brand">{esc(o['brand'])} · {esc(o['kind'])}</div>
  <h3>{esc(o['name'])}</h3><div class="card-meta">{esc(" · ".join(x for x in (o['side'], o['years']) if x))}</div>
  <div class="card-price card-price-order">{pprice(o) if (o.get('price') or o.get('uah')) else 'Ціна за запитом'}</div></div></a>'''

    ld_org = json.dumps({"@context": "https://schema.org", "@type": "AutoPartsStore", "name": "AutoBeam",
        "url": CFG["site_url"], "telephone": CFG["phone_intl"], "areaServed": "UA",
        "sameAs": [CFG["telegram"]]}, ensure_ascii=False)

    idx = page("index.html", base="", title="AutoBeam — оригінальна оптика зі США для вашого авто",
               description=f"Оригінальні фари, ліхтарі та ДХВ зі США для Toyota, Mazda, Ford, Jeep, Nissan, VW та інших. Великий вибір в наявності, підбір за VIN і привезення під замовлення. Пошук за парт-номером, доставка по Україні.",
               canonical=CFG["site_url"] + "/", og_image=CFG["site_url"] + "/assets/og.png?v=2", jsonld=ld_org,
               count=len(items), sidebar=sidebar, model_count=len(models_js), brand_count=len(MODELS), cards="\n".join([card(i) for i in items] + [ocard(o) for o in orders]), order_count=sum(i["st"] == "order" for i in items + orders),
               stock_count=sum(i["st"] == "in" for i in items), soon_count=sum(i["st"] == "soon" for i in items + orders),
               cta_hero=contact_buttons("hero"), cta_request=contact_buttons("request", "center"), cta_contacts=contact_buttons("contacts"))
    (OUT / "index.html").write_text(idx, encoding="utf-8")

    for it in items:
        rel = [x for x in items if x["brand"] == it["brand"] and x["id"] != it["id"] and x["st"] == "in"][:4]
        thumbs = "".join(f'<button class="thumb{" active" if n==0 else ""}" data-src="{pimg(p, "1200x900")}"><img src="{pimg(p, "200x150")}" alt=""></button>' for n, p in enumerate(it["photos"]))
        specs = [("Наявність", ST_LABEL[it["st"]]), *((("Номер " + (it["avto_maker"] or "аналога"), it["pn"]), ("Відповідник оригіналу", ", ".join(it["pn_alt"]))) if it["type"] == "Аналог" else
                   (("Парт-номер", ", ".join([it["pn"]] + it["pn_alt"]) if it["pn"] else ""),)), ("Марка", it["brand"]), ("Тип", it["kind"]), ("Сторона", (it.get("sl", "").lower() + " — ціна за 1 шт.") if it["side"].startswith("Пара") else it.get("sl") or it["side"]),
                 ("Світло", it["light"]), ("Роки", it["years"]), ("Стан", it["state"]), ("Походження", ("Аналог " + it["avto_maker"] + ", для авто з ринку США").replace("  ", " ") if it["type"] == "Аналог" else "Оригінал, США")]
        spec_html = "".join(f"<tr><th>{k}</th><td>{esc(v)}</td></tr>" for k, v in specs if v)
        ld = json.dumps({"@context": "https://schema.org", "@type": "Product", "name": it["name"], "sku": it["pn"] or str(it["id"]),
            "mpn": it["pn"] or None, "brand": {"@type": "Brand", "name": it["brand"]}, "image": [aimg(p) for p in it["photos"]],
            "offers": {"@type": "Offer", "priceCurrency": "UAH", "price": it["uah"] or uah(it["price"]) or None,
                       "availability": {"in": "https://schema.org/InStock", "soon": "https://schema.org/PreOrder", "order": "https://schema.org/BackOrder"}[it["st"]],
                       "itemCondition": "https://schema.org/UsedCondition" if it["state"] == "Вживане" else "https://schema.org/NewCondition",
                       "url": f"{CFG['site_url']}/fary/{it['slug']}.html"}}, ensure_ascii=False)
        p = page("product.html", base="../", title=f"{it['name']} — купити | AutoBeam",
                 description=f"{it['name']}. {('Парт-номер ' + it['pn'] + '. ') if it['pn'] else ''}{ST_LABEL[it['st']]}. {('Аналог ' + it['avto_maker'] + ' (не оригінал)') if it['type'] == 'Аналог' else 'Оригінал зі США'}, гарантія 14 днів. Доставка по Україні.",
                 canonical=f"{CFG['site_url']}/fary/{it['slug']}.html", og_image=aimg(it["photos"][0]), jsonld=ld,
                 name=esc(it["name"]), brand=esc(it["brand"]), kind=esc(it["kind"]), price_usd=it["price"], price_html=pprice(it), model=it["model"],
                 price_attr=(f'data-usd="{it["price"]}"' if it["price"] else ""), status_html=f'<span class="p-status p-{it["st"]}">{ST_LABEL[it["st"]]}</span>',
                 olx_html=(f'<a class="olx-link" href="{it["olx"]}" target="_blank" rel="noopener" data-track="olx" data-ctx="product">Це оголошення на OLX →</a>' if it["olx"] else ""),
                 origin_tag=(f'аналог {esc(it["avto_maker"])}' if it["type"] == "Аналог" else "оригінал США"), model_label=esc(it["brand"] + " " + next((m for m, rx, _ in MODELS.get(it["brand"], []) if mslug(it["brand"], m) == it["model"]), "")), pn=esc(it["pn"] or "—"),
                 main_img=pimg(it["photos"][0], "1200x900"), thumbs=thumbs, specs=spec_html, olx_url=it["olx"],
                 cta=contact_buttons("product", part=it["name"] + (" (" + it["pn"] + ")" if it["pn"] else "")), related="\n".join(card(r, "../") for r in rel), pn_raw=esc(it["pn"]), pid=it["id"],
                 desc="".join(("<p class='muted small'>" if t.startswith("Також шукають") else "<p>") + esc(t) + "</p>" for t in describe(it)))
        (OUT / "fary" / f"{it['slug']}.html").write_text(p, encoding="utf-8")

    for o in orders:
        rel = [x for x in items if x["model"] == o["model"] and x["st"] == "in"][:4] or [x for x in items if x["brand"] == o["brand"] and x["st"] == "in"][:4]
        ld = json.dumps({"@context": "https://schema.org", "@type": "Product", "name": o["name"], "brand": {"@type": "Brand", "name": o["brand"]},
            "offers": {"@type": "Offer", "priceCurrency": "UAH", "availability": {"in": "https://schema.org/InStock", "soon": "https://schema.org/PreOrder", "order": "https://schema.org/BackOrder"}[o.get("st", "order")], "url": f"{CFG['site_url']}/fary/{o['slug']}.html"}}, ensure_ascii=False)
        st_txt = ST_LABEL[o.get("st", "order")]
        p = page("product_order.html", base="../", title=f"{o['name']} — {st_txt.lower()} | AutoBeam",
                 description=f"{o['name']} — оригінал зі США, {st_txt.lower()}. Підбір за VIN або парт-номером, гарантія 14 днів, доставка по Україні.", status=st_txt,
                 canonical=f"{CFG['site_url']}/fary/{o['slug']}.html", og_image=CFG["site_url"] + "/assets/og.png?v=2", jsonld=ld,
                 name=esc(o["name"]), brand=esc(o["brand"]), mname=esc(o["mname"]), kind=esc(o["kind"]), years=esc(o["years"]), trim=esc(o["trim"]),
                 side=esc(o["side"] or "—"), model=o["model"], cta=contact_buttons("order", part=o["name"]), pid=o["id"],
                 related_title=("В наявності для " + esc(o["brand"] + " " + o["mname"])) if any(x["model"] == o["model"] and x["st"] == "in" for x in items) else ("В наявності для " + esc(o["brand"])),
                 related="\n".join(card(r, "../") for r in rel) or '<p class="muted">Зараз немає — привеземо під замовлення.</p>')
        (OUT / "fary" / f"{o['slug']}.html").write_text(p, encoding="utf-8")

    # Service pages (delivery, warranty, contacts, privacy)
    fop = CFG.get("fop_name", "")
    seller_html = f'<p><b>Продавець:</b> ФОП {esc(fop)}</p>' if fop else ""
    seller_inline = f" Власник сайту й оператор даних — ФОП {esc(fop)}." if fop else ""
    INFO = [("dostavka-oplata", "Доставка й оплата", "Доставка Новою поштою по Україні, оплата при отриманні або на рахунок ФОП, строки відправки й під замовлення зі США."),
            ("garantiia-povernennia", "Гарантія й повернення", "Гарантія 14 днів з дня отримання, безкоштовне повернення через «Легке повернення» Нової пошти у разі дефекту."),
            ("kontakty", "Контакти", "Телефон, Telegram, Viber і графік роботи AutoBeam — оригінальні фари зі США."),
            ("privacy", "Політика конфіденційності", "Які дані збирає сайт AutoBeam, навіщо й як їх видалити.")]
    for slug, ttl, desc in INFO:
        content = (SRC / "pages" / f"{slug}.html").read_text(encoding="utf-8")
        content = content.replace("{{cta}}", contact_buttons("info")).replace("{{seller_html}}", seller_html).replace("{{seller_inline}}", seller_inline)
        html = page("info.html", base="", title=f"{ttl} | AutoBeam", description=desc, canonical=f"{CFG['site_url']}/{slug}.html",
                    og_image=CFG["site_url"] + "/assets/og.png?v=2", jsonld=ld_org, crumb=esc(ttl), content=content)
        (OUT / f"{slug}.html").write_text(html, encoding="utf-8")

    for old, new in REDIRECTS:
        if (OUT / "fary" / f"{old}.html").exists(): continue
        (OUT / "fary" / f"{old}.html").write_text(
            f'<!doctype html><meta charset="utf-8"><meta name="robots" content="noindex"><link rel="canonical" href="{CFG["site_url"]}/fary/{new}.html">'
            f'<meta http-equiv="refresh" content="0;url={new}.html"><script>location.replace("{new}.html"+location.search)</script>'
            f'<a href="{new}.html">Перейти</a>', encoding="utf-8")
    if PAIR_REPORT:   # private: outside the web root on the server
        rp = Path(os.environ.get("AB_REPORTS", Path.home() / "autobeam_data")) if (Path.home() / "autobeam_data").exists() else ROOT
        (rp / "pairs_report.txt").write_text("\n".join(PAIR_REPORT) + "\n", encoding="utf-8")
    write_feeds(items + orders)
    today = datetime.date.today().isoformat()
    urls = [CFG["site_url"] + "/"] + [f"{CFG['site_url']}/{s}.html" for s in ("dostavka-oplata", "garantiia-povernennia", "kontakty", "privacy")] + [f"{CFG['site_url']}/fary/{i['slug']}.html" for i in items + orders]
    (OUT / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
        "\n".join(f"<url><loc>{u}</loc><lastmod>{today}</lastmod></url>" for u in urls) + "\n</urlset>\n", encoding="utf-8")
    (OUT / "robots.txt").write_text(f"User-agent: *\nDisallow: /admin/\nAllow: /\nSitemap: {CFG['site_url']}/sitemap.xml\n", encoding="utf-8")
    c = collections.Counter(i["st"] for i in items + orders)
    print(f"Built {len(items)} cards with photos + {len(orders)} without; in={c['in']} soon={c['soon']} order={c['order']}; stock feed={'yes' if have_stock else 'no'} -> {OUT}")

if __name__ == "__main__":
    main()
