#!/usr/bin/env python3
"""Ford service numbers (xxxZ-13008-x) are used for BOTH sides -> 4 cards were put on the left position by mistake."""
import json, sqlite3, os, time
from pathlib import Path
DB = Path(os.environ["HOME"]) / "autobeam_data/products.sqlite"
con = sqlite3.connect(str(DB))
FIX = {"AB-0001": ("Ford EcoSport 18-22 Halogen + DRL RH", "Права"),
       "AB-0036": ("Ford Fusion 17-20 LED RH", "Права"),
       "AB-0040": ("Ford Mustang Mach-E 20-23 LED RH", "Права")}
now = int(time.time())
for i, (key, side) in FIX.items():
    d = con.execute("SELECT data FROM products WHERE id=?", (i,)).fetchone()[0]; p = json.loads(d)
    print(i, p.get("key"), "->", key, "|", (p.get("title") or "")[:60])
    con.execute("INSERT INTO history (id,data,ts,ip) VALUES (?,?,?,?)", (i, d, now, "fix_ford"))
    p["key"], p["side"] = key, side
    con.execute("UPDATE products SET data=?, updated=? WHERE id=?", (json.dumps(p, ensure_ascii=False), now, i))
con.commit(); (DB.parent / "publish").touch()
