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
                    if len(k) >= 6: idx[k] = dict(it, side=side, brands=ref.get("brands") or [ref["brand"]], pn=pn)
                for pn in it.get("superseded", []):
                    k = npn(pn.split("*")[0])
                    if len(k) >= 8: idx.setdefault(k, dict(it, side="", brands=ref.get("brands") or [ref["brand"]], pn=pn))
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

def heur_side(brand, pn):
    """Side by numbering rules (data/reference/*.json 'rules'); only a hint for the report."""
    k = npn(pn)
    if brand in ("Toyota", "Lexus"):
        if re.match(r"^(81110|81130|81140|81145)", k): return "Права", "код Toyota"
        if re.match(r"^(81150|81170|81160|81070|81185)", k): return "Ліва", "код Toyota"
        if k.startswith("100008A"): return "Права", "Koito 10000 (неперевірено)"
        if k.startswith("101008A"): return "Ліва", "Koito 10100 (неперевірено)"
        if re.match(r"^\d{3}11[A-Z0-9]{3}AS2$", k): return "", "номер DEPO (аналог!), не оригінал"
    if brand in ("Honda", "Acura"):
        if k.startswith("33100"): return "Права", "код Honda 33100"
        if k.startswith("33150"): return "Ліва", "код Honda 33150"
    if brand in ("Hyundai", "Kia"):
        if k.startswith("92102"): return "Права", "код Hyundai/Kia 92102"
        if k.startswith("92101"): return "Ліва", "код Hyundai/Kia 92101"
    if brand in ("Nissan", "Infiniti"):
        if re.match(r"^(26010|26120)", k): return "Права", "код Nissan"
        if re.match(r"^(26060|26125)", k): return "Ліва", "код Nissan"
    if brand in ("Volkswagen", "Audi"):
        m = re.match(r"^[0-9A-Z]{3}941(\d{3})", k)
        if m and m.group(1)[0] == "0" or (m and m.group(1)[0] == "7"):
            return ("Права" if int(m.group(1)) % 2 == 0 else "Ліва"), "парність VAG"
    if brand == "Subaru":
        m = re.match(r"^8400[12][A-Z]{2}(\d)(\d)", k)
        if m: return ("Права" if int(m.group(1) + m.group(2)) % 2 == 0 else "Ліва"), "парність Subaru (2 цифри після літер)"
    if brand in ("Ford", "Land Rover"):
        if re.search(r"13W029|13E014|13404", k): return "Права", "інженерний код Ford"
        if re.search(r"13W030|13E015|13405", k): return "Ліва", "інженерний код Ford"
    if re.search(r"(^PC\d|DEPO|TYC)", k): return "", "схоже на номер аналога, не оригінал"
    if brand in ("Jeep", "Dodge", "Chrysler", "RAM") and re.match(r"^68\d{6}[A-Z]{2}$", k):
        return ("Права" if int(k[7]) % 2 == 0 else "Ліва"), "парність Mopar"
    return None, ""

def main():
    dbf = Path(os.environ.get("AB_DB", str(Path.home() / "autobeam_data/products.sqlite")))
    if dbf.exists():
        P = [json.loads(r[0]) for r in sqlite3.connect(str(dbf)).execute("SELECT data FROM products")]
    else:
        P = json.loads((ROOT / "data/products.json").read_text(encoding="utf-8"))
    idx = load_ref()
    brands = {b for v in idx.values() for b in v["brands"]}
    out = []
    for p in P:
        if p.get("archived") or p.get("brand") not in brands: continue
        pns = [x for x in [p.get("pn")] + list(p.get("pn_alt") or []) if x]
        sides = {(find(idx, x) or {}).get("side") for x in pns} - {None, ""}
        hsides = {heur_side(p.get("brand"), x)[0] for x in pns if not find(idx, x)} - {None, ""}
        allsides = sides | hsides
        pair = len(allsides) == 2 or "LH + RH" in (p.get("key") or "")
        if len(allsides) == 2 and "LH + RH" not in (p.get("key") or ""):
            out.append((p["id"], "перевірити", " / ".join(pns), p.get("key"), "у картці на один бік є номери ЛІВОЇ і ПРАВОЇ фари — це пара чи помилка в полі парт-номера?"))
        for pn in pns:
            r = find(idx, pn)
            if not r:
                hs, why = heur_side(p.get("brand"), pn)
                if hs and not pair and p.get("side") in ("Ліва", "Права") and hs != p["side"]:
                    out.append((p["id"], "перевірити", pn, p.get("key"), "бік за правилом (%s) = %s, картка = %s" % (why, hs, p["side"])))
                else:
                    out.append((p["id"], "НЕМАЄ В ДОВІДНИКУ", pn, p.get("key"), why + (" — бік збігається" if hs else "")))
                continue
            probs = []
            if r["side"] and not pair and p.get("side") in ("Ліва", "Права") and r["side"] != p["side"]: probs.append("бік: довідник=%s, картка=%s" % (r["side"], p["side"]))
            afs_ref = bool(re.search(r"AFS|adaptive", r["variant"], re.I)) and not re.search(r"без (AFS|adaptive)", r["variant"], re.I)
            afs_key = "AFS" in (p.get("key") or "") and "N-AFS" not in (p.get("key") or "")
            if p.get("key") and r.get("keys") and p["key"] not in r["keys"] and afs_ref != afs_key:
                probs.append("AFS: довідник=%s, позиція=%s" % ("так" if afs_ref else "ні", "так" if afs_key else "ні"))
            note = ""
            if p.get("key") and r.get("keys") and p["key"].strip() not in [k.strip() for k in r["keys"]] and not probs:
                note = "позиція не з цього рядка довідника (%s)" % ", ".join(r["keys"][:2])
            out.append((p["id"], "ПОМИЛКА" if probs else ("перевірити" if note else "ок"), pn, p.get("key"), "; ".join(probs or [note]) + " | " + r["model"] + " " + r["years"] + " " + r["variant"]))
    out = sorted(set(out))
    cnt = {}
    for o in out: cnt[o[1]] = cnt.get(o[1], 0) + 1
    print("перевірено номерів:", len(out), cnt)
    order = {"ПОМИЛКА": 0, "перевірити": 1, "НЕМАЄ В ДОВІДНИКУ": 2}
    for o in sorted([o for o in out if o[1] != "ок"], key=lambda o: (order[o[1]], o[0])): print("%s | %s | %s | %s | %s" % o)

if __name__ == "__main__":
    main()
