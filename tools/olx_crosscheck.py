#!/usr/bin/env python3
"""Cross-check every card against its OLX listing (title + description + part-number field). Python 3.6.
Reports only; changes nothing. Output: one line per card with a problem."""
import csv, json, os, re, sqlite3, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from refcheck import load_ref, find, heur_side, npn  # noqa: E402

DB = os.environ.get("AB_DB", str(Path.home() / "autobeam_data/products.sqlite"))

PN_RX = [r"^[A-Z0-9]{4}13[A-Z0-9]{3,4}[A-Z]{1,2}$",            # Ford / Land Rover
         r"^P?68\d{6}[A-Z]{2}$", r"^55\d{6}[A-Z]{2}$",          # Mopar
         r"^81\d{3}[0-9A-Z]{5}$", r"^10[01]008A[0-9A-Z]{2}$",   # Toyota / Koito
         r"^33[01]\d0[0-9A-Z]{3}[A-Z]\d{2}$",                   # Honda
         r"^9210[12][0-9A-Z]{5}$",                              # Hyundai / Kia
         r"^26\d{3}[0-9A-Z]{5}$",                               # Nissan / Infiniti
         r"^[0-9A-Z]{3}941\d{3}[A-Z]{0,2}$",                     # VAG
         r"^84\d{3}[A-Z]{2}\d{2,3}[A-Z]?$", r"^840[A-Z0-9]{7}$", # Subaru
         r"^[A-Z0-9]{4}51\d{3}[A-Z]?$", r"^[A-Z0-9]{4}67890[A-Z]?$",  # Mazda
         r"^A?2\d{9}$", r"^4\d{7}$"]                             # Mercedes, GM

def pn_tokens(text):
    s = (text or "").upper().replace("\n", " ")
    s = re.sub(r"\b([A-Z0-9]{4})[\s-]+(\d{2})[\s-]+(\d{3}[A-Z]?)\b", r"\1\2\3", s)            # KL2L 51 030
    s = re.sub(r"\b([A-Z0-9]{4})[\s-]+(1[3]\w{3,4})[\s-]+([A-Z]{1,2})\b", r"\1\2\3", s)       # KT4B 13W029 BF
    s = re.sub(r"\b(\d{5})[\s-]+([0-9A-Z]{5})\b", r"\1\2", s)                                  # 81110 0R360
    out = []
    for t in re.split(r"[\s,;/|()+]+", s):
        k = npn(t.strip(".:"))
        if 7 <= len(k) <= 14 and any(re.match(rx, k) for rx in PN_RX) and k not in out:
            out.append(k)
    return out

PAIR_RX = re.compile(r"(лів\w*\W{0,4}(і|та|и|,|\+|/|&)?\W{0,4}прав)|(прав\w*\W{0,4}(і|та|и|,|\+|/|&)?\W{0,4}лів)|\bпар[аиу]\b|\bкомплект\b|"
                     r"\bLH\s*\+\s*RH\b|\bL\s*\+\s*R\b|лев\w*\W{0,4}(и)?\W{0,4}прав", re.I)

def title_side(t):
    t = t.lower()
    l = bool(re.search(r"\bлів|\bлев|\blh\b|\bleft", t)); r = bool(re.search(r"\bправ|\brh\b|\bright", t))
    return "Пара" if l and r else "Ліва" if l else "Права" if r else ""

def main():
    olx = {}
    for f in (ROOT / "data/olx_export").glob("*.csv"):
        for r in csv.DictReader(open(str(f), encoding="utf-8")): olx[r["id"]] = r
    idx = load_ref()
    P = [json.loads(d) for (d,) in sqlite3.connect(DB).execute("SELECT data FROM products")]
    rows = []
    for p in sorted(P, key=lambda x: x["id"]):
        if p.get("archived"): continue
        r = olx.get(str(p.get("olx_id") or ""))
        card = [npn(x) for x in [p.get("pn")] + list(p.get("pn_alt") or []) if x]
        if not r:
            if p.get("olx_id"): rows.append((p["id"], p["olx_id"], "оголошення немає в експорті OLX", "", p.get("key")))
            continue
        title, desc = r["title"], r["description"]
        field = pn_tokens(r["part_number"] or r["part_num"])
        intext = [t for t in pn_tokens(title + " \n " + desc) if t not in field]
        dsc = desc.lower()
        pair = (bool(PAIR_RX.search(title)) or title_side(title) == "Пара"
                or bool(re.search(r"сторона\s*:?\s*(ліва|права)\s*(/|і|та|,|\+)\s*(ліва|права)", dsc))
                or bool(re.search(r"продаю?ться\s+(передні\s+|задні\s+|зовнішні\s+)*(фари|ліхтарі)\b", dsc)))
        declared = {}                          # "KT4B-13W030-CH — ліва" written in the description
        for m in re.finditer(r"([A-Z0-9][A-Z0-9 .\-]{5,20}?)\s*[—–-]+\s*(ліва|права|левая|правая)", (title + "\n" + desc).upper().replace("ЛІВА", "ліва").replace("ПРАВА", "права").replace("ЛЕВАЯ", "ліва").replace("ПРАВАЯ", "права")):
            k = npn(m.group(1))
            if len(k) >= 7: declared[k] = "Ліва" if m.group(2) == "ліва" else "Права"
        tside = title_side(title)
        def side(k):
            ref = find(idx, k)
            if ref and ref.get("side"): return ref["side"]
            return heur_side(p.get("brand"), k)[0] or declared.get(k, "")
        def close(a, b):                       # same lamp family, other side: same length, <=2 chars differ
            return len(a) == len(b) and sum(x != y for x, y in zip(a, b)) <= 2
        fs = {side(k) for k in field} - {""}
        extra_card = [k for k in card if k not in field]
        probs = []
        if not field:
            probs.append("поле «Парт-номер» на OLX порожнє" + ("; в описі: " + ", ".join(intext[:6]) if intext else ""))
        if pair:
            have = {side(k) for k in field + extra_card} - {""}
            for miss in ({"Ліва", "Права"} - have if field else set()):
                cand = [k for k in intext if side(k) == miss and any(close(k, f) for f in field)]
                probs.append("ПАРНЕ: немає номера %s фари%s" % ("лівої" if miss == "Ліва" else "правої",
                             ("; в описі є відповідник: " + ", ".join(cand[:3])) if cand else "; в описі відповідника теж немає"))
            filled = [k for k in extra_card if side(k) and side(k) not in fs]
            if filled and field: probs.append("ПАРНЕ: другий бік доповнено номером з avto.pro: " + ", ".join(filled))
        else:
            if len(fs) == 2: probs.append("НЕ парне за назвою, але в полі номери обох боків")
            if tside in ("Ліва", "Права") and fs and tside not in fs: probs.append("бік у назві = %s, а номер у полі = %s" % (tside, "/".join(fs)))
            if p.get("side") in ("Ліва", "Права") and fs and p["side"] not in fs: probs.append("бік у картці = %s, а номер у полі OLX = %s" % (p["side"], "/".join(fs)))
            bad = [k for k in extra_card if side(k) and fs and side(k) not in fs]
            if bad: probs.append("у картці є номер з avto.pro іншого боку: " + ", ".join(bad))
        for k, ds in declared.items():
            ref = find(idx, k); cs = (ref or {}).get("side") or heur_side(p.get("brand"), k)[0] or ""
            if cs and cs != ds: probs.append("в описі %s — %s, а за каталогом/правилом це %s" % (k, ds.lower(), cs.lower()))
        odd = [k for k in extra_card if not side(k)]
        if odd: probs.append("у картці є номер, якого немає в оголошенні: " + ", ".join(odd))
        if probs:
            rows.append((p["id"], r["id"], " | ".join(probs), ("ПАРА " if pair else "") + title[:80], p.get("key")))
    print("карток з проблемами:", len(rows))
    for x in rows: print("%s | OLX %s | %s | назва: %s | позиція: %s" % x)

if __name__ == "__main__":
    main()
