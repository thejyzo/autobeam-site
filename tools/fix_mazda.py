#!/usr/bin/env python3
"""Mazda fixes from the reference check: KL2L = AFS (official Mazda catalog)."""
import json, sqlite3, os, time
from pathlib import Path
DB = Path(os.environ["HOME"]) / "autobeam_data/products.sqlite"
con = sqlite3.connect(str(DB)); now = int(time.time())
def get(i): d = con.execute("SELECT data FROM products WHERE id=?", (i,)).fetchone()[0]; return d, json.loads(d)
def put(i, old, p): con.execute("INSERT INTO history (id,data,ts,ip) VALUES (?,?,?,?)", (i, old, now, "fix_mazda")); con.execute("UPDATE products SET data=?, updated=? WHERE id=?", (json.dumps(p, ensure_ascii=False), now, i))
d, p = get("AB-0150")
assert "KL2L" in (p.get("pn") or "").upper(), p.get("pn")
p["key"] = "Mazda CX-5 17-21 LED AFS LH"; p["note"] = (p.get("note") or "") + "; KL2L = AFS за каталогом Mazda — перенесено з позиції без AFS"
put("AB-0150", d, p); print("AB-0150 ->", p["key"])
d, q = get("AB-0153")
if not q.get("photos") and not q.get("olx_id") and q.get("key") == "Mazda CX-5 17-21 LED AFS LH":
    q["archived"] = True; q["show"] = False; q["note"] = "архів: порожня картка, позицію закриває AB-0150"; put("AB-0153", d, q); print("AB-0153 archived")
con.commit(); (DB.parent / "publish").touch()
