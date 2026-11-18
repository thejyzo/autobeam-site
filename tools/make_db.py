#!/usr/bin/env python3
"""One-off: build initial rows for the 'Товари' sheet from accounting names + OLX export."""
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import build  # reuse MODELS, mslug, parse()

FIX = [("Chervrolet", "Chevrolet"), ("Atlass", "Atlas"), ("Grand_Highlander", "Grand Highlander")]
BODY = r"\b(BM|BP|B8\.5|B9\.5|B9|8Y|L462|L405|KL|WK2|WL|W257|W206|NMS2|B9 NMS2|Juniper)\b"
TRIM_TR = [(r"\bN-AFS\b", "без AFS"), (r"\bhalogen\b", "Галоген"), (r"\bxenon\b", "Ксенон"), (r"\bBLACK\b", "чорна маска"),
           (r"\bSILVER\b", "срібна маска"), (r"upper \+ lower", "верх + низ"), (r"\bBASE AUTO\b", "Base (авто-коректор)"),
           (r"\bBASE\b", "Base"), (r"\bPREMIUM\b", "Premium / Summit"), (r"\bFULL\b", "Full")]

def yrs(a, b=None):
    f = lambda y: int(y) + (2000 if int(y) < 100 else 0)
    return f"{f(a)}–{f(b)}" if b else f"{f(a)}"

def parse_acc(raw):
    s = raw
    for a, b in FIX: s = s.replace(a, b)
    kind, side = "Фара", ""
    if s.startswith("For Ford Mustang"):
        return dict(brand="Ford", mname="Mustang", years="2024–2025", side="Пара (ліва + права)", kind="Повторювач", body="", trim="LED")
    brand = next((b for b in sorted(build.MODELS, key=len, reverse=True) if s.lower().startswith(b.lower())), None)
    mname = next((m for m, rx, _ in build.MODELS[brand] if re.search(rx, s, re.I)), None)
    t = s[len(brand):].strip()
    if re.search(r"ФОНАРЬ", t): kind = "Ліхтар"; t = re.sub(r"ФОНАРЬ( ВНЕШНИЙ)?", "", t)
    if re.search(r"Signal", t, re.I): kind = "Повторювач"; t = re.sub(r"Signal Lamp", "", t, flags=re.I)
    if re.search(r"\bcenter\b", t): kind = "ДХО"; side = "Центральна"; t = t.replace("center", "")
    if re.search(r"\bDRL\b", t) and not re.search(r"LED|Halogen|Xenon", t, re.I): kind = "ДХО"
    if re.search(r"LH \+ RH", t): side = "Пара (ліва + права)"; t = t.replace("LH + RH", "")
    elif re.search(r"\bLH\b", t): side = side or "Ліва"; t = re.sub(r"\bLH\b", "", t)
    elif re.search(r"\bRH\b", t): side = side or "Права"; t = re.sub(r"\bRH\b", "", t)
    m = re.search(r"\b(20\d\d|\d\d)\s*-\s*(20\d\d|\d\d)\b", t) or re.search(r"\b(\d\d)\+", t) or re.search(r"\b(20\d\d)\b", t)
    years = ""
    if m:
        years = yrs(m.group(1), m.group(2)) if m.lastindex == 2 else (yrs(m.group(1)) + ("+" if "+" in m.group(0) else ""))
        t = t.replace(m.group(0), " ")
    body = " ".join(re.findall(BODY, t))
    t = re.sub(BODY, " ", t)
    # strip the model words from the rest
    for w in re.split(r"[\s/]+", mname): t = re.sub(r"(?i)(?<![\w-])" + re.escape(w) + r"(?![\w-])", " ", t)
    t = re.sub(r"(?i)\b(70|cross|sport|5)\b", " ", t) if brand in ("Toyota", "Volkswagen", "Land Rover") else t
    for a, b in TRIM_TR: t = re.sub(a, b, t, flags=re.I)
    trim = re.sub(r"\s+", " ", t).strip(" +/") or ""
    if kind == "ДХО" and trim == "DRL": trim = "LED"
    return dict(brand=brand, mname=mname, years=years, side=side, kind=kind, body=body, trim=trim)

def yr_range(y):
    n = [int(x) for x in re.findall(r"20\d\d", y)]
    if not n: return None
    return (n[0], n[-1] if len(n) > 1 else (2027 if "+" in y else n[0]))

def overlap(a, b):
    ra, rb = yr_range(a), yr_range(b)
    return True if not ra or not rb else ra[0] <= rb[1] and rb[0] <= ra[1]

def hints(text):
    t = text.lower()
    return dict(afs=("afs" in t and "без afs" not in t and "n-afs" not in t), full=("full" in t), hal=bool(re.search("галоген|halogen", t)),
                xen=bool(re.search("ксенон|xenon", t)), bi=("bi-led" in t), sx=bool(re.search(r"\bsx|limited", t)))

def main():
    def normkey(k):
        for a, b in (("_", " "), ("Chervrolet", "Chevrolet"), ("Atlass", "Atlas")): k = k.replace(a, b)
        return re.sub(r"\s+", " ", k).strip()
    acc = list(dict.fromkeys(normkey(l) for l in (ROOT / "data/accounting_names.txt").read_text(encoding="utf-8").splitlines() if l.strip()))
    rows = []
    for a in acc:
        p = parse_acc(a); p["key"] = a; p["model"] = build.mslug(p["brand"], p["mname"]); p["olx"] = []
        rows.append(p)
    stock = {normkey(l) for l in (ROOT / "data/stock_keys.txt").read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")}
    olx = [build.parse(r) for r in json.loads((ROOT / "data/olx_raw.json").read_text(encoding="utf-8"))]
    unmatched = []
    for it in olx:
        side = {"Ліва": "Ліва", "Права": "Права", "Ліва + права": "Пара (ліва + права)"}.get(it["side"], "")
        kind = {"Ліхтар": "Ліхтар", "ДХО": "ДХО"}.get(it["kind"], "Фара")
        if it["kind"] in ("Скло фари", "Корпус фари"): unmatched.append(it); continue
        h = hints(it["title"])
        def pick(strict_years):
            best, bs, tie = None, -99, False
            for r in rows:
                if r["model"] != it["model"] or r["kind"] != kind: continue
                if side in ("Ліва", "Права") and r["side"] in ("Ліва", "Права") and r["side"] != side: continue   # never the opposite side
                yr_ok = overlap(r["years"], it["years"])
                if strict_years and not yr_ok: continue
                if not strict_years and (r["key"] not in stock or (side and r["side"] != side)): continue
                sc = 3 if r["key"] in stock else 0
                if side == "Пара (ліва + права)" and r["side"] == side and r["key"] not in stock: sc -= 2
                if side and r["side"] == side: sc += 4
                elif side == "Пара (ліва + права)" and r["side"] in ("Ліва", "Права"): sc += 2
                rh = hints(r["trim"] + " " + r["key"])
                for k in ("afs", "full", "hal", "xen", "bi", "sx"):
                    if h[k] and rh[k]: sc += 2
                    elif h[k] != rh[k] and k in ("afs", "hal", "xen", "bi", "sx"): sc -= 2
                ra, rb = yr_range(r["years"]), yr_range(it["years"])
                if ra and rb: sc += 2 if ra[0] == rb[0] else (1 if abs(ra[0] - rb[0]) <= 1 else 0)
                if not strict_years: sc -= 1
                if sc > bs: best, bs, tie = r, sc, False
                elif sc == bs: tie = True
            return best, bs, tie
        best, bs, tie = pick(True)
        if best is None or (side in ("Ліва", "Права") and best["key"] not in stock):
            b2, s2, t2 = pick(False)
            if b2 is not None: best, bs, tie = b2, s2, True   # matched despite different years -> flag for review
        if best is None: unmatched.append(it); continue
        best["olx"].append((it, bs, tie))
    out = []
    for i, r in enumerate(rows, 1):
        o = r["olx"][0][0] if r["olx"] else None
        note = []
        if r["olx"]:
            if r["olx"][0][2] or r["olx"][0][1] < 4: note.append("перевірити збіг з OLX")
            if len(r["olx"]) > 1: note.append(f"ще {len(r['olx'])-1} оголош. OLX: " + ", ".join(x[0]["olx"] for x in r["olx"][1:]))
        out.append(dict(id=f"AB-{i:04d}", key=r["key"], kind=r["kind"], brand=r["brand"], mname=r["mname"], body=r["body"], years=r["years"],
                        side=r["side"], trim=r["trim"], pn=o["pn"] if o else "", state=o["state"] if o else "Вживане",
                        orig=o["type"] if o else "Оригінал", price=o["price"] if o else "",
                        photos=",".join(build.img(p, "1200x900") for p in o["photos"]) if o else "",
                        olx=o["olx"] if o else "", note="; ".join(note)))
    n = len(out)
    for it in unmatched:
        n += 1
        out.append(dict(id=f"AB-{n:04d}", key="", kind=it["kind"], brand=it["brand"], mname=(build.MODELS.get(it["brand"]) and next((m for m, rx, _ in build.MODELS[it["brand"]] if build.mslug(it["brand"], m) == it["model"]), "")) or "",
                        body="", years=it["years"], side={"Ліва + права": "Пара (ліва + права)"}.get(it["side"], it["side"]), trim=it["light"], pn=it["pn"],
                        state=it["state"], orig=it["type"], price=it["price"], photos=",".join(build.img(p, "1200x900") for p in it["photos"]),
                        olx=it["olx"], note="є на OLX, не знайдено в обліку — додати назву з Headlights або приховати"))
    json.dump(out, open(ROOT / "data/db_initial.json", "w"), ensure_ascii=False, indent=0)
    # OLX listing -> accounting variant (true side & clean title; OLX titles often say "ліва права" for SEO)
    omap = {}
    for r in rows:
        for it, sc, tie in r["olx"]:
            omap[str(it["id"])] = dict(key=r["key"], side=r["side"], kind=r["kind"], brand=r["brand"], mname=r["mname"],
                                       body=r["body"], years=r["years"], trim=r["trim"], sure=(sc >= 6 and not tie), in_stock=r["key"] in stock)
    json.dump(omap, open(ROOT / "data/olx_map.json", "w"), ensure_ascii=False, indent=0)
    print(len(rows), "accounting rows;", sum(1 for r in rows if r["olx"]), "with OLX;", len(unmatched), "OLX unmatched")
    for r in rows[:400]:
        print(f'{r["key"]:<55} | {r["kind"]:<10} {r["brand"]} {r["mname"]} | {r["body"]} | {r["years"]} | {r["side"]} | {r["trim"]} | olx={len(r["olx"])}')
    print("UNMATCHED:"); [print("  ", u["title"]) for u in unmatched]

if __name__ == "__main__":
    main()
