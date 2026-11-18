#!/usr/bin/env python3
"""Rename product kind 'ДХО' -> 'ДХВ' (Ukrainian term). Python 3.6. Writes history, touches publish."""
import json, os, sqlite3, time
from pathlib import Path
DB = os.environ.get("AB_DB", str(Path.home() / "autobeam_data/products.sqlite"))
con = sqlite3.connect(DB); n = 0
for pid, data in con.execute("SELECT id, data FROM products").fetchall():
    p = json.loads(data)
    if p.get("kind") == "ДХО":
        con.execute("INSERT INTO history (id,data,ts,ip) VALUES (?,?,?,?)", (pid, data, int(time.time()), "fix_kind"))
        p["kind"] = "ДХВ"
        con.execute("UPDATE products SET data=?, updated=? WHERE id=?", (json.dumps(p, ensure_ascii=False), int(time.time()), pid)); n += 1
con.commit()
if n: Path(Path(DB).parent / "publish").touch()
print("ДХО -> ДХВ:", n)
