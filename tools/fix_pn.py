#!/usr/bin/env python3
"""Part numbers = the OLX "part number" field (owner's choice: OLX is the starting point, not SEO text / avto.pro).
- cards with an OLX listing: pn / pn_alt re-read from the OLX export field, spaced formats joined (KL2L 51 030 -> KL2L-51-030, KT4B 13W029 BF -> KT4B-13W029-BF)
- if the OLX field is empty: the number stays, but is marked as coming from avto.pro (to verify)
Dry run by default, --apply to write (history kept)."""
import csv, json, re, sqlite3, os, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
DB = Path(os.environ["HOME"]) / "autobeam_data/products.sqlite"
APPLY = "--apply" in sys.argv

def parse_field(s):
    s = (s or "").upper().replace("\n", " ")
    s = re.sub(r"\b([A-Z0-9]{4})\s+(\d{2})\s+(\d{3}[A-Z]?)\b", r"\1-\2-\3", s)            # Mazda: KL2L 51 030
    s = re.sub(r"\b([A-Z0-9]{4})\s+(\d{2}[A-Z]\d{3}|\d{5})\s+([A-Z]{1,2})\b", r"\1-\2-\3", s)  # Ford/JLR: KT4B 13W029 BF
    parts = re.split(r"[,;/|]+|\s+", s)
    out = []
    for p in parts:
        p = p.strip(" .")
        if len(re.sub(r"[^0-9A-Z]", "", p)) >= 6 and re.search(r"\d", p) and p not in out: out.append(p)
    return out

OLX = {}
for f in (ROOT / "data/olx_export").glob("*.csv"):
    for r in csv.DictReader(open(str(f), encoding="utf-8")): OLX[r["id"]] = r

con = sqlite3.connect(str(DB)); now = int(time.time()); n = 0
for cid, data in con.execute("SELECT id, data FROM products").fetchall():
    p = json.loads(data); old = (p.get("pn"), list(p.get("pn_alt") or []), p.get("pn_source"))
    r = OLX.get(str(p.get("olx_id") or ""))
    if r is not None:
        pns = parse_field(r["part_number"] or r["part_num"])
        if pns:
            p["pn"], p["pn_alt"], p["pn_source"] = pns[0], pns[1:], "olx"
        elif p.get("pn"):
            p["pn_source"] = "avto"
    elif p.get("pn"):
        p["pn_source"] = p.get("pn_source") or "avto"
    if p.get("pn_source") == "avto" and "з avto.pro" not in (p.get("note") or ""):
        p["note"] = ((p.get("note") + "; ") if p.get("note") else "") + "парт-номер з avto.pro (в OLX поле порожнє) — перевірити за етикеткою"
    new = (p.get("pn"), list(p.get("pn_alt") or []), p.get("pn_source"))
    if new != old:
        n += 1
        if old[0] != new[0] or old[1] != new[1]: print(cid, old[0], old[1], "->", new[0], new[1], "|", new[2])
        if APPLY:
            con.execute("INSERT INTO history (id,data,ts,ip) VALUES (?,?,?,?)", (cid, data, now, "fix_pn"))
            con.execute("UPDATE products SET data=?, updated=? WHERE id=?", (json.dumps(p, ensure_ascii=False), now, cid))
print("changed:", n, "| apply" if APPLY else "| DRY RUN")
if APPLY: con.commit(); (DB.parent / "publish").touch()
