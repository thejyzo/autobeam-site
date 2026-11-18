#!/usr/bin/env python3
"""One-off clean-up of the admin DB after the audit (Python 3.6). Dry run by default; --apply writes.
Every changed card is saved to `history` first (can be restored), nothing is deleted — only archived."""
import json, re, sqlite3, sys, os, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from audit import npn, pn_side

HOME = Path(os.environ["HOME"])
DB = HOME / "autobeam_data/products.sqlite"
STOCK = json.loads((HOME / "autobeam_data/stock.json").read_text(encoding="utf-8"))
KEYS = set(json.loads((HOME / "autobeam_data/data_keys.json").read_text(encoding="utf-8")))
APPLY = "--apply" in sys.argv
con = sqlite3.connect(str(DB))
P = {r[0]: json.loads(r[1]) for r in con.execute("SELECT id, data FROM products")}
changed, log = set(), []

def note(p, t):
    p["note"] = (p.get("note") + "; " if p.get("note") else "") + t
def archive(p, why):
    p["archived"] = True; p["show"] = False; note(p, "архів: " + why); changed.add(p["id"]); log.append("ARCHIVE %s | %s | %s" % (p["id"], (p.get("title") or p.get("key") or "")[:60], why))
def setf(p, **kw):
    for k, v in kw.items():
        if p.get(k) != v: log.append("SET %s %s: %r -> %r" % (p["id"], k, p.get(k), v)); p[k] = v; changed.add(p["id"])

live = lambda: [p for p in P.values() if not p.get("archived")]
pns = lambda p: {npn(x) for x in [p.get("pn")] + list(p.get("pn_alt") or []) if len(npn(x)) >= 6}
stk = lambda p: STOCK.get(p.get("key") or "") or [0, 0, 0, 0]

# 1. empty cards (created with "+ Нова" and never filled)
for p in live():
    if not p.get("brand") and not p.get("title") and not p.get("key") and not p.get("photos"):
        archive(p, "порожня картка")

# 2. inactive OLX cards that duplicate an active card of the same position
for p in live():
    if not p.get("olx_id") or p.get("olx_active"): continue
    act = [q for q in live() if q["id"] != p["id"] and q.get("key") == p.get("key") and p.get("key") and q.get("olx_active")]
    if not act: continue
    same_pn = [q for q in act if pns(q) & pns(p)]
    s = stk(p)
    if same_pn:
        q = same_pn[0]; q.setdefault("olx_dupes", []); q["olx_dupes"] = sorted(set(q["olx_dupes"] + [str(p["olx_id"])])); changed.add(q["id"])
        archive(p, "дубль активного %s (той самий парт-номер)" % q["id"])
    elif s[0] + s[1] + s[2] == 0:
        archive(p, "неактивне оголошення; позиція вже має активну картку %s, на складі 0" % ", ".join(q["id"] for q in act))
    else:
        note(p, "є в наявності (склад %d, ремонт %d, дорога %d) — окреме оголошення варто активувати на OLX" % tuple(s[:3])); changed.add(p["id"])

# 3. inactive cards with stock and no active card at all -> remind to re-activate on OLX
for p in live():
    if p.get("olx_id") and not p.get("olx_active") and "активувати" not in (p.get("note") or ""):
        s = stk(p)
        if s[0] + s[1] + s[2] > 0:
            note(p, "є в наявності (склад %d, ремонт %d, дорога %d) — активувати оголошення на OLX" % tuple(s[:3])); changed.add(p["id"])

# 4. part number missing but present in the description text
for p in live():
    if p.get("pn") or not p.get("description"): continue
    m = re.search(r"Номер(?:и)?\s+запчастин[иі]?\s*:\s*([^\n]+)", p["description"])
    if m:
        found = [x.strip(" .") for x in re.split(r"[,;/]|\s+(?=[A-Z0-9]{2,}[-A-Z0-9]*\d)", m.group(1)) if len(npn(x)) >= 6]
        if found: setf(p, pn=found[0], pn_alt=found[1:])

# 5. side from the part number when the card says otherwise (single side only)
SIDE = {"L": "Ліва", "R": "Права"}
for p in live():
    s = {pn_side(x) for x in [p.get("pn")] + list(p.get("pn_alt") or [])} - {""}
    if len(s) == 1 and p.get("side") in ("Ліва", "Права") and SIDE[s.copy().pop()] != p["side"]:
        new = SIDE[s.pop()]
        k = p.get("key") or ""
        setf(p, side=new)
        if "LH + RH" in k or not k: continue
        nk = re.sub(r"\bLH\b", "RH", k) if new == "Права" else re.sub(r"\bRH\b", "LH", k)
        if "AFS" in (p.get("title") or "") and "AFS" not in nk and (nk.replace(" LED ", " LED AFS ", 1) in KEYS): nk = nk.replace(" LED ", " LED AFS ", 1)
        if nk != k and nk in KEYS: setf(p, key=nk)
        elif nk != k: note(p, "сторона за парт-номером: %s; позиції %s немає в DATA" % (new, nk))

# 6. explicit fixes from the audit
if "AB-0049" in P and "AB-0050" in P and not P["AB-0050"].get("archived"):
    a, b = P["AB-0049"], P["AB-0050"]          # Jeep Compass 68441586AG is the RIGHT headlight
    setf(a, key="Jeep Compass 22-26 LED RH", side="Права")
    for f in ("avto_maker", "avto_code", "short"):
        if b.get(f) and not a.get(f): setf(a, **{f: b[f]})
    archive(b, "обʼєднано з AB-0049 (той самий парт-номер 68441586AG)")

for l in log: print(l)
print("changed cards:", len(changed), "| apply" if APPLY else "| DRY RUN (add --apply)")
if APPLY and changed:
    now = int(time.time())
    for i in changed:
        old = con.execute("SELECT data FROM products WHERE id=?", (i,)).fetchone()[0]
        con.execute("INSERT INTO history (id,data,ts,ip) VALUES (?,?,?,?)", (i, old, now, "fix_db"))
        P[i]["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        con.execute("UPDATE products SET data=?, updated=? WHERE id=?", (json.dumps(P[i], ensure_ascii=False), now, i))
    con.commit()
    (HOME / "autobeam_data/publish").touch()
    print("saved; site will rebuild on next deploy")
