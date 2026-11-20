#!/usr/bin/env python3
"""Create or fill a product card from a spec in the repo (photos included). Python 3.6.
Usage:  python3 tools/publish_card.py data/cards/<name>.json          # preview: which card, what changes
        python3 tools/publish_card.py data/cards/<name>.json --yes    # apply: photos -> www/media/<id>/, card saved (history + publish)

Spec: {"key": "<DATA position>", "photos_dir": "data/cards/<name>", "set": {field: value, ...}}
Card choice: an existing card with the same `key` that has no photos and no price (an empty placeholder);
otherwise a new card AB-xxxx is created. A card that already has photos or a price is never overwritten —
the script stops and says which card it is, so the owner decides.
Photos: every NN.jpg (+ NN_400.jpg thumbnail) from photos_dir is copied to www/media/<id>/; EXIF is already stripped in the repo."""
import json, os, re, shutil, sqlite3, sys, time
from pathlib import Path

HOME = Path.home()
REPO = Path(__file__).resolve().parent.parent
DB = os.environ.get("AB_DB", str(HOME / "autobeam_data/products.sqlite"))
MEDIA = Path(os.environ.get("AB_MEDIA", str(HOME / "autobeam.com.ua/www/media")))


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    spec = json.loads((REPO / sys.argv[1]).read_text(encoding="utf-8")) if not Path(sys.argv[1]).is_absolute() \
        else json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    apply = "--yes" in sys.argv
    key = spec["key"].strip()
    con = sqlite3.connect(DB)
    rows = [(pid, json.loads(raw)) for pid, raw in con.execute("SELECT id, data FROM products ORDER BY id")]
    same = [(pid, p) for pid, p in rows if (p.get("key") or "").strip() == key]
    empty = [(pid, p) for pid, p in same if not p.get("photos") and not p.get("price")]
    busy = [pid for pid, p in same if (pid, p) not in empty]

    pn = re.sub(r"[^0-9A-Z]", "", str(spec.get("set", {}).get("pn", "")).upper())
    done = [pid for pid, q in same if pn and re.sub(r"[^0-9A-Z]", "", str(q.get("pn", "")).upper()) == pn and q.get("photos")]
    if done:
        print("Картка вже створена раніше: {} ({}, {}). Повторно не створюю.".format(", ".join(done), key, pn)); return
    if empty:
        cid, old = empty[0]
        print("Заповнюю порожню картку {} ({})".format(cid, key))
    else:
        cid = "AB-%04d" % (max(int(pid[3:]) for pid, _ in rows if re.match(r"AB-\d{4}$", pid)) + 1)
        old = None
        print("Створюю нову картку {} ({})".format(cid, key))
    if busy:
        print("   (з цією позицією вже є заповнені картки: {} — їх не чіпаю)".format(", ".join(busy)))

    pdir = REPO / spec["photos_dir"]
    pics = sorted(f for f in pdir.glob("*.jpg") if not f.name.endswith("_400.jpg"))
    urls = ["/media/{}/{}".format(cid, f.name) for f in pics]

    base = dict(id=cid, key=key, kind="Фара", brand="", model="", body="", years="", side="", trim="", pn="", pn_alt=[],
                title="", description="", short="", price="", currency="USD", state="Вживане", original="Оригінал",
                photos=[], olx_id="", olx_active=False, olx_dupes=[], show=True, status_manual="", note="")
    p = dict(old or base)
    p.update(spec.get("set", {}))
    p["id"], p["key"], p["photos"] = cid, key, urls

    for k in sorted(set(p) | set(old or {})):
        a, b = (old or {}).get(k), p.get(k)
        if a != b:
            s = repr(b)
            print("   {}: {}".format(k, s if len(s) < 140 else s[:137] + "..."))
    print("   фото: {} шт. -> {}/{}/".format(len(pics), MEDIA, cid))
    if not apply:
        print("\nЦе попередній перегляд. Щоб застосувати, додайте --yes"); return

    dest = MEDIA / cid
    dest.mkdir(parents=True, exist_ok=True)
    for f in pics:
        shutil.copyfile(str(f), str(dest / f.name))
        th = f.with_name(f.stem + "_400.jpg")
        if th.exists():
            shutil.copyfile(str(th), str(dest / th.name))
    now = int(time.time())
    if old:
        con.execute("INSERT INTO history (id,data,ts,ip) VALUES (?,?,?,?)", (cid, json.dumps(old, ensure_ascii=False), now, "publish_card"))
        con.execute("UPDATE products SET data=?, updated=? WHERE id=?", (json.dumps(p, ensure_ascii=False), now, cid))
    else:
        con.execute("INSERT INTO products (id,data,updated) VALUES (?,?,?)", (cid, json.dumps(p, ensure_ascii=False), now))
    con.commit()
    (Path(DB).parent / "publish").touch()
    print("Готово: {} збережено, сайт і фід avto.pro оновляться при наступній збірці (sh ~/autobeam_repo/deploy.sh — одразу).".format(cid))


main()
