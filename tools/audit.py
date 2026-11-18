#!/usr/bin/env python3
"""Audit of the admin DB: duplicates and questionable cards. Python 3.6 compatible.
Run on the server:  python3 ~/autobeam_repo/tools/audit.py  (writes ~/autobeam_data/audit.json and prints a report)."""
import json, re, sqlite3, collections, os
from pathlib import Path

HOME = Path(os.environ.get("HOME"))
DB = Path(os.environ.get("AB_DB", str(HOME / "autobeam_data/products.sqlite")))
STOCK = Path(os.environ.get("AB_STOCK", str(HOME / "autobeam_data/stock.json")))
KEYS = Path(os.environ.get("AB_KEYS", str(HOME / "autobeam_data/data_keys.json")))

def npn(s):
    s = re.sub(r"[^0-9A-Z]", "", str(s or "").upper())
    return s[1:] if re.match(r"^P\d{8}", s) else s

def pn_side(pn):
    p = npn(pn)
    rules = [(r"^8111\d", "R"), (r"^8115\d", "L"), (r"^2601\d", "R"), (r"^2606\d", "L"), (r"^3310\d", "R"), (r"^3315\d", "L"),
             (r"^92101", "L"), (r"^92102", "R"), (r"51030[A-Z]?$", "R"), (r"51040[A-Z]?$", "L"), (r"51031[A-Z]?$", "R"), (r"51041[A-Z]?$", "L"),
             (r"13E014", "R"), (r"13E015", "L"), (r"13W029", "R"), (r"13W030", "L"), (r"13005[A-Z]{0,2}$", "R"), (r"13008[A-Z]{0,2}$", "L"),
             (r"13404", "R"), (r"13405", "L"), (r"94103[35]", "L"), (r"94103[46]", "R"), (r"941005", "L"), (r"941006", "R"),
             (r"941029", "L"), (r"941030", "R"), (r"941039", "L"), (r"941040", "R"), (r"941043", "L"), (r"941044", "R"),
             (r"941081", "L"), (r"941082", "R"), (r"941011", "L"), (r"941012", "R"), (r"941773", "L"), (r"941774", "R")]
    for rx, sd in rules:
        if re.search(rx, p): return sd
    return ""

def key_side(k):
    if re.search(r"LH\s*\+\s*RH", k): return "P"
    if re.search(r"\bLH\b", k): return "L"
    if re.search(r"\bRH\b", k): return "R"
    return ""

def main():
    con = sqlite3.connect(str(DB))
    P = [json.loads(r[0]) for r in con.execute("SELECT data FROM products ORDER BY id")]
    stock = json.loads(STOCK.read_text(encoding="utf-8")) if STOCK.exists() else {}
    keys = json.loads(KEYS.read_text(encoding="utf-8")) if KEYS.exists() else []
    live = [p for p in P if not p.get("archived")]
    issues = collections.OrderedDict((k, []) for k in [
        "olx_id_dup", "pn_dup", "same_key_title", "bare_redundant", "side_conflict", "key_not_in_data",
        "stock_without_card", "instock_no_photos", "instock_no_price", "instock_no_desc", "inactive_olx", "no_key", "no_pn"])

    # 1. same OLX id on several cards
    by_olx = collections.defaultdict(list)
    for p in live:
        if p.get("olx_id"): by_olx[str(p["olx_id"])].append(p["id"])
    for o, ids in by_olx.items():
        if len(ids) > 1: issues["olx_id_dup"].append({"olx": o, "ids": ids})

    # 2. same part number on several cards (same side) -> likely duplicates
    by_pn = collections.defaultdict(list)
    for p in live:
        for x in set([npn(p.get("pn"))] + [npn(a) for a in p.get("pn_alt") or []]):
            if len(x) >= 6: by_pn[x].append(p)
    seen = set()
    for x, ps in by_pn.items():
        ids = tuple(sorted(set(q["id"] for q in ps)))
        if len(ids) > 1 and ids not in seen:
            seen.add(ids)
            issues["pn_dup"].append({"pn": x, "ids": list(ids), "titles": [q.get("title") or q.get("key") for q in ps],
                                     "olx": [(q.get("olx_id") or "") + ("" if q.get("olx_active") else " (неакт.)") for q in ps]})

    # 3. same position + same title
    by_kt = collections.defaultdict(list)
    for p in live:
        if p.get("title"): by_kt[(p.get("key"), re.sub(r"\W+", "", p["title"].lower()))].append(p["id"])
    for k, ids in by_kt.items():
        if len(ids) > 1: issues["same_key_title"].append({"key": k[0], "ids": ids})

    # 4. bare placeholder card while the position already has a real card
    real = collections.defaultdict(list)
    for p in live:
        if p.get("key") and (p.get("photos") or p.get("olx_id")): real[p["key"]].append(p["id"])
    for p in live:
        if p.get("key") and not p.get("photos") and not p.get("olx_id") and real.get(p["key"]):
            issues["bare_redundant"].append({"id": p["id"], "key": p["key"], "real": real[p["key"]]})

    # 5. side conflicts: part number vs card side vs position side
    SD = {"Ліва": "L", "Права": "R", "Пара (ліва + права)": "P"}
    for p in live:
        pns = [p.get("pn")] + list(p.get("pn_alt") or [])
        s = set(filter(None, (pn_side(x) for x in pns)))
        pside = "P" if s == {"L", "R"} else (s.pop() if len(s) == 1 else "")
        cside, kside = SD.get(p.get("side"), ""), key_side(p.get("key") or "")
        prob = []
        if pside and cside and pside != cside: prob.append("парт-номер=%s, картка=%s" % (pside, cside))
        if kside and cside and kside != cside and not (cside == "P"): prob.append("позиція=%s, картка=%s" % (kside, cside))
        if prob: issues["side_conflict"].append({"id": p["id"], "key": p.get("key"), "title": p.get("title"), "pn": p.get("pn"), "why": "; ".join(prob)})

    # 6. card bound to a name that is neither in DATA nor in the accounting
    kset = set(keys)
    for p in live:
        if p.get("key") and p["key"] not in kset and p["key"] not in stock:
            issues["key_not_in_data"].append({"id": p["id"], "key": p["key"]})

    # 7. accounting has goods on hand/on the way that no card points to
    used = set(p.get("key") for p in live)
    junk = re.compile(r"запчаст|Максим|Ray-Ban|Levis|Royal|Суппорт|Блок|Федя|Grille|^\w{8,14}$", re.I)
    for name, s in stock.items():
        if name not in used and (s[0] + s[1] + s[2]) > 0 and not junk.search(name):
            issues["stock_without_card"].append({"name": name, "sklad": s[0], "remont": s[1], "road": s[2]})

    # 8-10. in stock / soon but the card is not sellable
    for p in live:
        s = stock.get(p.get("key") or "")
        if not s or not p.get("show") or (s[0] + s[1] + s[2]) == 0: continue
        cards = [q for q in live if q.get("key") == p.get("key")]
        if not any(q.get("photos") for q in cards) and p is cards[0]: issues["instock_no_photos"].append({"id": p["id"], "key": p["key"], "stock": s[:3]})
        if p.get("photos") and not p.get("price"): issues["instock_no_price"].append({"id": p["id"], "key": p["key"]})
        if p.get("photos") and not p.get("description"): issues["instock_no_desc"].append({"id": p["id"], "key": p["key"]})

    for p in live:
        if p.get("olx_id") and not p.get("olx_active"):
            s = stock.get(p.get("key") or "") or [0, 0, 0]
            others = [q["id"] for q in live if q.get("key") == p.get("key") and q.get("olx_active") and q["id"] != p["id"]]
            issues["inactive_olx"].append({"id": p["id"], "key": p.get("key"), "title": p.get("title"), "pn": p.get("pn"), "stock": s[:3], "active_same_pos": others})
        if not p.get("key"): issues["no_key"].append({"id": p["id"], "title": p.get("title")})
        if p.get("photos") and not p.get("pn") and p.get("kind") == "Фара": issues["no_pn"].append({"id": p["id"], "key": p.get("key"), "title": p.get("title")})

    out = {"cards": len(P), "live": len(live), "issues": issues}
    (DB.parent / "audit.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("cards", len(P), "live", len(live), "history", con.execute("SELECT COUNT(*) FROM history").fetchone()[0])
    for k, v in issues.items(): print("%-20s %d" % (k, len(v)))

if __name__ == "__main__":
    main()
