#!/usr/bin/env python3
"""Check cards against the verified reference (data/reference/*.json). Python 3.6 compatible.
For every card part number found in the reference: side, AFS/adaptive and model must agree with the card's position."""
import json, re, sqlite3, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent

def npn(s):
    s = re.sub(r"[^0-9A-Z]", "", str(s or "").upper())
    return s[1:] if re.match(r"^P\d{8}", s) else s

def load_ref():
    idx = {}
    for f in sorted((ROOT / "data/reference").glob("*.json")):
        ref = json.loads(f.read_text(encoding="utf-8"))
        for it in ref["items"]:
            for side, lst in (("Права", it.get("right", [])), ("Ліва", it.get("left", []))):
                for pn in lst + [x for x in it.get("label", []) if ("прав" in x and side == "Права") or ("лів" in x and side == "Ліва")]:
                    k = npn(pn.split(" ")[0])
                    if len(k) >= 6: idx[k] = dict(it, side=side, brand=ref["brand"], pn=pn)
                for pn in it.get("superseded", []):
                    k = npn(pn.split("*")[0])
                    if len(k) >= 8: idx.setdefault(k, dict(it, side="", brand=ref["brand"], pn=pn))
    return idx

def find(idx, pn):
    k = npn(pn)
    if k in idx: return idx[k]
    # Mazda: production label without revision letter, 030 <-> 031 / 040 <-> 041 are the same lamp
    m = re.match(r"^([A-Z0-9]{4})51(0[34])([01])([A-Z]?)$", k)
    if m:
        for c in idx:
            mm = re.match(r"^([A-Z0-9]{4})51(0[34])([01])([A-Z]?)$", c)
            if mm and mm.group(1) == m.group(1) and mm.group(2) == m.group(2): return idx[c]
    for c in idx:                       # revision letter differs
        if len(k) >= 8 and (c.startswith(k) or k.startswith(c)) and abs(len(c) - len(k)) <= 1: return idx[c]
    return None

def main():
    dbf = Path(os.environ.get("AB_DB", str(Path.home() / "autobeam_data/products.sqlite")))
    if dbf.exists():
        P = [json.loads(r[0]) for r in sqlite3.connect(str(dbf)).execute("SELECT data FROM products")]
    else:
        P = json.loads((ROOT / "data/products.json").read_text(encoding="utf-8"))
    idx = load_ref()
    brands = {v["brand"] for v in idx.values()}
    out = []
    for p in P:
        if p.get("archived") or p.get("brand") not in brands: continue
        for pn in [p.get("pn")] + list(p.get("pn_alt") or []):
            if not pn: continue
            r = find(idx, pn)
            if not r:
                out.append((p["id"], "НЕМАЄ В ДОВІДНИКУ", pn, p.get("key"), "")); continue
            probs = []
            if r["side"] and p.get("side") in ("Ліва", "Права") and r["side"] != p["side"]: probs.append("бік: довідник=%s, картка=%s" % (r["side"], p["side"]))
            afs_ref = bool(re.search(r"AFS|adaptive", r["variant"], re.I)) and not re.search(r"без (AFS|adaptive)", r["variant"], re.I)
            afs_key = "AFS" in (p.get("key") or "") and "N-AFS" not in (p.get("key") or "")
            if p.get("key") and r.get("keys") and p["key"] not in r["keys"] and afs_ref != afs_key:
                probs.append("AFS: довідник=%s, позиція=%s" % ("так" if afs_ref else "ні", "так" if afs_key else "ні"))
            if p.get("key") and r.get("keys") and p["key"] not in r["keys"] and not probs:
                probs.append("позиція не з цього рядка довідника (%s)" % ", ".join(r["keys"][:2]))
            out.append((p["id"], "ПОМИЛКА" if probs else "ок", pn, p.get("key"), "; ".join(probs) + " | " + r["model"] + " " + r["years"] + " " + r["variant"]))
    bad = [o for o in out if o[1] != "ок"]
    print("перевірено номерів:", len(out), "| ок:", len(out) - len(bad), "| розбіжностей:", len(bad))
    for o in sorted(bad): print("%s | %s | %s | %s | %s" % o)

if __name__ == "__main__":
    main()
