#!/usr/bin/env python3
"""Dump card fields needed for part-number checks as JSON to stdout (no prices). Python 3.6."""
import json, os, sqlite3
from pathlib import Path
DB = os.environ.get("AB_DB", str(Path.home() / "autobeam_data/products.sqlite"))
F = ("id", "key", "kind", "side", "brand", "model", "body", "years", "trim", "title", "pn", "pn_alt", "pn_source", "olx_id", "olx_active", "archived", "note")
rows = [json.loads(d) for (d,) in sqlite3.connect(DB).execute("SELECT data FROM products")]
print(json.dumps([{k: r.get(k) for k in F} for r in rows], ensure_ascii=False))
