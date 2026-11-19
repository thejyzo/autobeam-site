#!/usr/bin/env python3
"""Apply owner-verified card fixes from a JSON file. Python 3.6.
Usage:  python3 tools/apply_fixes.py data/fixes/2026-11-19.json          # dry run: shows before -> after
        python3 tools/apply_fixes.py data/fixes/2026-11-19.json --yes    # apply (history + publish)
JSON: [{"id": "AB-0001", "set": {"side": "Права", "pn": "..."}, "pn_alt_add": [...], "pn_alt_remove": [...], "why": "..."}]
"""
import json, os, re, sqlite3, sys, time
from pathlib import Path

DB = os.environ.get("AB_DB", str(Path.home() / "autobeam_data/products.sqlite"))
norm = lambda s: re.sub(r"[^0-9A-Z]", "", str(s or "").upper())

def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    fixes = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    apply = "--yes" in sys.argv
    con = sqlite3.connect(DB)
    changed = 0
    for fx in fixes:
        row = con.execute("SELECT data FROM products WHERE id=?", (fx["id"],)).fetchone()
        if not row:
            print("!! {} не знайдено".format(fx["id"])); continue
        old = json.loads(row[0]); p = dict(old)
        for k, v in fx.get("set", {}).items():
            p[k] = v
        alt = list(p.get("pn_alt") or [])
        rm = {norm(x) for x in fx.get("pn_alt_remove", [])} | {norm(p.get("pn"))}
        alt = [a for a in alt if norm(a) not in rm]
        for a in fx.get("pn_alt_add", []):
            if norm(a) not in {norm(x) for x in alt} and norm(a) != norm(p.get("pn")):
                alt.append(a)
        p["pn_alt"] = alt
        diff = {k: (old.get(k), p.get(k)) for k in set(old) | set(p) if old.get(k) != p.get(k)}
        print("{}  {}".format(fx["id"], fx.get("why", "")))
        if not diff:
            print("   без змін"); continue
        for k, (a, b) in sorted(diff.items()):
            print("   {}: {!r} -> {!r}".format(k, a, b))
        if apply:
            con.execute("INSERT INTO history (id,data,ts,ip) VALUES (?,?,?,?)", (fx["id"], row[0], int(time.time()), "apply_fixes"))
            con.execute("UPDATE products SET data=?, updated=? WHERE id=?", (json.dumps(p, ensure_ascii=False), int(time.time()), fx["id"]))
            changed += 1
    if apply:
        con.commit()
        if changed:
            Path(Path(DB).parent / "publish").touch()
        print("Застосовано: {}".format(changed))
    else:
        print("\nЦе попередній перегляд. Щоб застосувати, додайте --yes")

main()
