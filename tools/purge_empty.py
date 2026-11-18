#!/usr/bin/env python3
"""Delete empty cards (no position, title, part number, price, photos, description, OLX id).
Python 3.6. Usage: python3 tools/purge_empty.py         -> list only
                   python3 tools/purge_empty.py --yes   -> delete (a copy stays in the history table)"""
import json, os, sqlite3, sys, time
from pathlib import Path

DB = os.environ.get("AB_DB", str(Path.home() / "autobeam_data/products.sqlite"))
FIELDS = ("key", "title", "pn", "pn_alt", "price", "photos", "description", "short", "olx_id", "model", "note")

con = sqlite3.connect(DB)
empty = []
for pid, data in con.execute("SELECT id, data FROM products"):
    p = json.loads(data)
    if not any(p.get(f) for f in FIELDS):
        empty.append((pid, p))
print("порожніх карток:", len(empty), " ".join(pid for pid, _ in empty))
if "--yes" in sys.argv and empty:
    for pid, p in empty:
        con.execute("INSERT INTO history (id,data,ts,ip) VALUES (?,?,?,?)", (pid, json.dumps(dict(p, deleted=True), ensure_ascii=False), int(time.time()), "purge_empty"))
        con.execute("DELETE FROM products WHERE id=?", (pid,))
    con.commit()
    Path(Path(DB).parent / "publish").touch()
    print("видалено:", len(empty))
