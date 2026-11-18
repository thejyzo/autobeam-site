#!/usr/bin/env python3
"""Create a bare card for a DATA position (used when accounting has goods but no card points to it)."""
import json, sqlite3, os, sys, time, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); import make_db as m
DB = Path(os.environ["HOME"]) / "autobeam_data/products.sqlite"
con = sqlite3.connect(str(DB)); key = sys.argv[1]
n = max(int(r[0][3:]) for r in con.execute("SELECT id FROM products")) + 1
p = m.parse_acc(key); cid = "AB-%04d" % n
card = dict(id=cid, key=key, kind=p["kind"], brand=p["brand"], model=p["mname"], body=p["body"], years=p["years"], side=p["side"], trim=p["trim"],
            pn="", pn_alt=[], title="", description="", short="", price="", currency="USD", state="Вживане", original="Оригінал", photos=[],
            olx_id="", olx_active=False, olx_dupes=[], show=True, status_manual="", note="створено автоматично: є в обліку, не було картки")
con.execute("INSERT INTO products (id,data,updated) VALUES (?,?,?)", (cid, json.dumps(card, ensure_ascii=False), int(time.time()))); con.commit()
(DB.parent / "publish").touch(); print(cid, key)
