#!/usr/bin/env python3
"""Build the master product base from: DATA (list of positions), OLX exports (active + inactive),
avto.pro price list. Output: data/products.json (+ data/master_report.md for review).

Every product = one position (DATA name) or an extra OLX-only item (glass, housings...).
"""
import csv, json, re, sys, collections
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
import build, make_db as m

def nk(s):
    for a, b in (("_", " "), ("Chervrolet", "Chevrolet"), ("Atlass", "Atlas")): s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()

def npn(s): return re.sub(r"[^0-9A-Z]", "", str(s).upper())

def _old_split_pns(s):
    if not s: return []
    parts = re.split(r"[,;/|]+|\s{1,}(?=[A-Z0-9]{2,}[-A-Z0-9]*\d)", str(s).strip())
    return [p.strip(" .") for p in parts if len(npn(p)) >= 6]

def pn_side(pn):
    """Side encoded in OEM part number (most makers). Returns 'Ліва'/'Права'/'' ."""
    p = npn(pn).lstrip("P")
    rules = [(r"^8111\d", "R"), (r"^8115\d", "L"),                     # Toyota / Lexus
             (r"^2601\d", "R"), (r"^2606\d", "L"),                     # Nissan / Infiniti
             (r"^3310\d", "R"), (r"^3315\d", "L"),                     # Honda / Acura
             (r"^92101", "L"), (r"^92102", "R"),                         # Hyundai / Kia
             (r"51030[A-Z]?$", "R"), (r"51040[A-Z]?$", "L"),             # Mazda
             (r"13E014", "R"), (r"13E015", "L"), (r"13W029", "R"), (r"13W030", "L"),   # Ford / JLR
 (r"13404", "R"), (r"13405", "L"),
             (r"941035", "L"), (r"941036", "R"), (r"941005", "L"), (r"941006", "R"),   # VAG
             (r"941029", "L"), (r"941030", "R"), (r"941039", "L"), (r"941040", "R"),
             (r"941043", "L"), (r"941044", "R"), (r"941081", "L"), (r"941082", "R"),
             (r"941773", "L"), (r"941774", "R"), (r"941033", "L"), (r"941034", "R")]
    for rx, sd in rules:
        if re.search(rx, p): return {"L": "Ліва", "R": "Права"}[sd]
    return ""

def pns_side(pns):
    sides = {pn_side(x) for x in pns} - {""}
    return sides.pop() if len(sides) == 1 else ("Пара (ліва + права)" if len(sides) == 2 else "")

def split_pns(s):
    s = (s or "").upper().replace("\n", " ")
    s = re.sub(r"\b([A-Z0-9]{4})\s+(\d{2})\s+(\d{3}[A-Z]?)\b", r"\1-\2-\3", s)            # Mazda: KL2L 51 030
    s = re.sub(r"\b([A-Z0-9]{4})\s+(\d{2}[A-Z]\d{3}|\d{5})\s+([A-Z]{1,2})\b", r"\1-\2-\3", s)  # Ford/JLR: KT4B 13W029 BF
    parts = re.split(r"[,;/|]+|\s+", s)
    out = []
    for p in parts:
        p = p.strip(" .")
        if len(re.sub(r"[^0-9A-Z]", "", p)) >= 6 and re.search(r"\d", p) and p not in out: out.append(p)
    return out


OLX_CAT = {"2544": "Фари передні", "2545": "Ліхтарі задні", "2550": "Корпуси / скло фар"}

def load_olx():
    rows, seen = [], set()
    for f in sorted((ROOT / "data/olx_export").glob("*.csv")):
        cat = re.match(r"(\d+)", f.name).group(1)
        active = not f.stem.endswith("_b")          # *_b = inactive export
        for r in csv.DictReader(open(f, encoding="utf-8")):
            if r["id"] in seen: continue
            seen.add(r["id"]); r["_cat"] = cat; r["_active"] = active; rows.append(r)
    return rows

PRODS = []
def keys_list():
    return list(dict.fromkeys(nk(l) for l in (ROOT / "data/data_sheet.txt").read_text(encoding="utf-8").splitlines() if l.strip()))

def collect():
    global PRODS
    keys = list(dict.fromkeys(nk(l) for l in (ROOT / "data/data_sheet.txt").read_text(encoding="utf-8").splitlines() if l.strip()))
    global STOCK
    stock = STOCK = {nk(l) for l in (ROOT / "data/stock_keys.txt").read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")}
    prods = []
    for k in keys:
        p = m.parse_acc(k); p.update(key=k, model=build.mslug(p["brand"], p["mname"]), olx=[], avto=[])
        prods.append(p)
    PRODS = prods
    olx = load_olx()
    extra = []
    for r in olx:
        pn_field = r["part_number"] or r["part_num"]
        t = re.sub(r"\bVW\b", "Volkswagen", r["title"]); t = re.sub(r"^(?!.*Land Rover)(.*?)Range Rover", r"\1Land Rover Range Rover", t)
        if re.search(r"3CN94103[56]", npn(pn_field)): t = t.replace("Atlas / Atlas Cross Sport", "Atlas Cross Sport")
        it = build.parse([int(r["id"]), t, 0, pn_field, r["state"], r["parts_type"], "", ""])
        it["_r"] = r
        if it["kind"] in ("Скло фари", "Корпус фари") or r["_cat"] == "2550": extra.append(it); continue
        best, bs = match(it, split_pns(pn_field))
        if best is None: extra.append(it); continue
        best["olx"].append((it, bs))

    # avto.pro
    import openpyxl
    wb = openpyxl.load_workbook(ROOT / "data/olx_export/avtopro_kharkiv.xlsx", read_only=True)
    arows = [dict(zip(["maker", "code", "price", "qty", "desc", "bu", "rest", "photos"], r[:8])) for r in list(wb.active.iter_rows(values_only=True))[1:] if r[1]]
    pn_index = collections.defaultdict(list)
    for p in prods:
        for it, _ in p["olx"]:
            for x in split_pns(it["_r"]["part_number"] or it["_r"]["part_num"]): pn_index[npn(x)].append(p)
    avto_unmatched = []
    for a in arows:
        hits = pn_index.get(npn(a["code"]))
        if not hits:
            it = build.parse([0, str(a["desc"]), 0, str(a["code"]), "", "", "", ""])
            b, _ = match(it, [str(a["code"])]) if it["kind"] not in ("Скло фари", "Корпус фари") else (None, 0)
            hits = [b] if b else None
        if hits: hits[0]["avto"].append(a)
        else: avto_unmatched.append(a)
    return prods, extra, arows, avto_unmatched, stock

def match(it, pns):
        side = {"Ліва": "Ліва", "Права": "Права", "Ліва + права": "Пара (ліва + права)"}.get(it["side"], "")
        ps = pns_side(pns)
        if ps: side = ps                     # part number is more reliable than the (SEO) title
        kind = {"Ліхтар": "Ліхтар", "ДХО": "ДХО"}.get(it["kind"], "Фара")
        h = m.hints(it["title"])
        best, bs = None, -99
        for p in PRODS:
            if p["model"] != it["model"] or p["kind"] != kind: continue
            stock = STOCK
            if side in ("Ліва", "Права") and p["side"] in ("Ліва", "Права") and p["side"] != side: continue
            if not m.overlap(p["years"], it["years"]): continue
            sc = (1 if p["key"] in stock else 0) + (4 if side and p["side"] == side else 0)
            if side == "Пара (ліва + права)" and p["side"] in ("Ліва", "Права"): sc += 1
            rh = m.hints(p["trim"] + " " + p["key"])
            for kk in ("afs", "full", "hal", "xen", "bi", "sx"):
                if h[kk] and rh[kk]: sc += 2
                elif h[kk] and not rh[kk] and kk in ("afs", "hal", "xen", "bi", "sx"): sc -= 2
                elif rh[kk] and not h[kk] and kk in ("afs", "xen", "bi"): sc -= 1
            ra, rb = m.yr_range(p["years"]), m.yr_range(it["years"])
            if ra and rb: sc += 3 if ra[0] == rb[0] else (1 if abs(ra[0] - rb[0]) <= 1 else 0)
            if p["body"] and re.search(r"\b" + re.escape(p["body"]) + r"\b", it["title"]): sc += 4
            # part-number agreement with avto/older data is checked later
            if ps and p["side"] == ps: sc += 3
            if sc > bs: best, bs = p, sc
        return best, bs

def main():
    global PRODS
    prods, extra, arows, avto_unmatched, stock = collect()

    out, n = [], 0
    def photos_of(r): return [u.replace(":443", "").split(";s=")[0] + ";s=1200x900;q=80" for u in (r["images"] or "").split("|") if u]
    used_avto = set()
    def avto_for(pns, key_prod):
        res = []
        for i, a in enumerate(arows):
            if i in used_avto: continue
            if npn(a["code"]) in {npn(x) for x in pns}: res.append(i)
        for i in res: used_avto.add(i)
        return [arows[i] for i in res]
    def card(base, it, key, extra_inactive=()):
        nonlocal n
        n += 1
        r = it["_r"] if it else None
        pns = split_pns(r["part_number"] or r["part_num"]) if r else []
        av = avto_for(pns, base) if pns else []
        side = base["side"]
        ps = pns_side(pns)
        if ps: side = ps
        price, cur = "", "USD"
        if r: price, cur = int(float(r["price_value"] or 0)) or "", r["price_currency"] or "USD"
        note = []
        if r and not r["_active"]: note.append("оголошення OLX неактивне — перевірити наявність / актуальність")
        return dict(
            id=f"AB-{n:04d}", key=key, kind=base["kind"], brand=base["brand"], model=base["mname"], body=base.get("body", ""),
            years=base["years"], side=side, trim=base.get("trim", ""),
            pn=pns[0] if pns else "", pn_alt=pns[1:],
            title=(r["title"].replace("\n", " ") if r else ""), description=(r["description"] if r else ""),
            short=(str(av[0]["desc"]) if av else ""),
            price=price, currency=cur, state=("Нове" if r and r["state"] == "new" else "Вживане"),
            original=("Аналог" if r and r["parts_type"] == "analog" else "Оригінал"),
            photos=photos_of(r) if r else [],
            olx_id=(r["id"] if r else ""), olx_active=bool(r and r["_active"]), olx_dupes=list(extra_inactive),
            olx_category=(r["_cat"] if r else ""), olx_brand=(r["car_brand"] if r else ""), olx_compat=(r["compatibility_list"] if r else ""),
            avto_maker=(str(av[0]["maker"]) if av else ""), avto_code=(str(av[0]["code"]) if av else ""),
            show=True, status_manual="", note="; ".join(note))
    for p in prods:
        act = [it for it, _ in sorted(p["olx"], key=lambda x: -x[1]) if it["_r"]["_active"]]
        ina = [it for it, _ in p["olx"] if not it["_r"]["_active"]]
        if act:
            act_pns = {npn(x) for it in act for x in split_pns(it["_r"]["part_number"] or it["_r"]["part_num"])}
            dup, keep = [], []
            for it in ina:
                ip = {npn(x) for x in split_pns(it["_r"]["part_number"] or it["_r"]["part_num"])}
                (dup if (not ip or ip & act_pns) else keep).append(it)
            for j, it in enumerate(act): out.append(card(p, it, p["key"], [d["_r"]["id"] for d in dup] if j == 0 else ()))
            for it in keep: out.append(card(p, it, p["key"]))
        elif ina:
            for it in ina: out.append(card(p, it, p["key"]))
        else:
            out.append(card(p, None, p["key"]))
    for it in extra:
        base = dict(kind=it["kind"] if it["kind"] in ("Скло фари", "Корпус фари", "Ліхтар", "ДХО") else "Фара", brand=it["brand"],
                    mname=next((mn for mn, rx, _ in build.MODELS.get(it["brand"], []) if build.mslug(it["brand"], mn) == it["model"]), ""),
                    years=it["years"], side={"Ліва + права": "Пара (ліва + права)"}.get(it["side"], it["side"]), trim=it["light"])
        o = card(base, it, "")
        if base["kind"] not in ("Скло фари", "Корпус фари"): o["note"] = (o["note"] + "; " if o["note"] else "") + "не прив'язано до позиції DATA — обрати позицію"
        out.append(o)
    # avto.pro rows not used by a listing -> attach to the card of their position (by description match)
    for i, a in enumerate(arows):
        if i in used_avto: continue
        tgt = None
        for p in prods:
            if a in p["avto"]: tgt = p["key"]
        c = next((o for o in out if o["key"] == tgt and not o["avto_code"]), None) if tgt else None
        if c:
            c["avto_maker"], c["avto_code"], c["short"] = str(a["maker"]), str(a["code"]), str(a["desc"])
            if not c["pn"]: c["pn"] = str(a["code"])
            if not c["price"]: c["price"] = int(a["price"])
            if not c["photos"]: c["photos"] = [u for u in str(a["photos"] or "").split(",") if u]
            used_avto.add(i)
    avto_unmatched = [a for i, a in enumerate(arows) if i not in used_avto]
    json.dump(out, open(ROOT / "data/products.json", "w"), ensure_ascii=False, indent=1)
    json.dump(keys_list(), open(ROOT / "data/data_keys.json", "w"), ensure_ascii=False)

    # report
    rep = ["# Звіт збирання бази", ""]
    c = collections.Counter
    rep.append(f"- Позицій DATA: {len(prods)}; додаткових (скло, корпуси, не з DATA): {len(extra)}; разом карток: {len(out)}")
    rep.append(f"- Карток з активним OLX: {sum(1 for o in out if o['olx_active'])}; з неактивним: {sum(1 for o in out if o['olx_id'] and not o['olx_active'])}; без оголошення (лише позиція): {sum(1 for o in out if not o['olx_id'])}")
    rep.append(f"- Позицій DATA з хоча б однією карткою-оголошенням: {len({o['key'] for o in out if o['olx_id'] and o['key']})} з {len(prods)}")
    rep.append(f"- З парт-номером: {sum(1 for o in out if o['pn'])}; з описом: {sum(1 for o in out if o['description'])}; з фото: {sum(1 for o in out if o['photos'])}; з ціною: {sum(1 for o in out if o['price'])}")
    rep.append(f"- avto.pro: {len(arows)} позицій, прив'язано {len(arows)-len(avto_unmatched)}, не прив'язано {len(avto_unmatched)}")
    rep += ["", "## Неактивні оголошення OLX (окремі картки, перевірити)"]
    rep += [f"- {o['id']} {o['title']} | {o['pn']} | → {o['key']}" for o in out if o['olx_id'] and not o['olx_active']]
    rep += ["", "## Неактивні, що дублюють активні (приховано в картці)"]
    rep += [f"- {o['id']} {o['title']}: {', '.join(o['olx_dupes'])}" for o in out if o['olx_dupes']]
    rep += ["", "## avto.pro без пари"] + [f"- {a['maker']} {a['code']}: {str(a['desc'])[:90]}" for a in avto_unmatched]
    rep += ["", "## Без прив'язки до DATA"] + [f"- {o['id']} [{o['kind']}] {o['title']}" for o in out if not o['key']]
    (ROOT / "data/master_report.md").write_text("\n".join(rep), encoding="utf-8")
    print("\n".join(rep[:6]))

if __name__ == "__main__":
    main()
