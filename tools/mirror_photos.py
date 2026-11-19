#!/usr/bin/env python3
"""Copy product photos from the OLX CDN to our own server (www/media/AB-xxxx/) and point the cards at them.
Python 3.6. Usage:
  python3 tools/mirror_photos.py            # dry run: how many photos would be downloaded
  python3 tools/mirror_photos.py --yes      # download + update cards (history + publish)
  python3 tools/mirror_photos.py --yes --limit 5   # only the first 5 cards (test)
For every OLX photo two files are saved: <id>.jpg (1600x1200) and <id>_400.jpg (thumbnail).
A card is updated only if all its OLX photos downloaded fine; otherwise it keeps the OLX links."""
import json, os, re, sqlite3, sys, time, urllib.request
from pathlib import Path

HOME = Path.home()
DB = os.environ.get("AB_DB", str(HOME / "autobeam_data/products.sqlite"))
MEDIA = Path(os.environ.get("AB_MEDIA", HOME / "autobeam.com.ua/www/media"))
RX = re.compile(r"olxcdn\.com/v1/files/([^/;]+)/image")

def fetch(url, dest):
    if dest.exists() and dest.stat().st_size > 2000:
        return True
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 AutoBeam media mirror"})
            data = urllib.request.urlopen(req, timeout=30).read()
            if len(data) < 2000 or data[:2] != b"\xff\xd8":
                raise ValueError("not a jpeg (%d bytes)" % len(data))
            tmp = dest.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.rename(dest)
            return True
        except Exception as e:
            err = e
            time.sleep(2 * (attempt + 1))
    print("   !! %s: %s" % (url, err))
    return False

def main():
    apply = "--yes" in sys.argv
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 0
    con = sqlite3.connect(DB)
    rows = con.execute("SELECT id, data FROM products ORDER BY id").fetchall()
    todo = [(pid, raw) for pid, raw in rows if any(RX.search(u or "") for u in json.loads(raw).get("photos", []))]
    total = sum(sum(1 for u in json.loads(raw).get("photos", []) if RX.search(u or "")) for _, raw in todo)
    print("Карток з фото на OLX: %d, фото: %d" % (len(todo), total))
    if not apply:
        print("Попередній перегляд. Щоб завантажити, додайте --yes"); return
    done = 0
    for pid, raw in todo[:limit or None]:
        p = json.loads(raw)
        folder = MEDIA / pid
        folder.mkdir(parents=True, exist_ok=True)
        new, ok = [], True
        for u in p.get("photos", []):
            m = RX.search(u or "")
            if not m:
                new.append(u); continue
            fid = re.sub(r"[^0-9A-Za-z_-]", "", m.group(1))
            base = "https://ireland.apollo.olxcdn.com/v1/files/%s/image" % m.group(1)
            big, small = folder / (fid + ".jpg"), folder / (fid + "_400.jpg")
            if fetch(base + ";s=1600x1200;q=85", big) and fetch(base + ";s=400x300;q=80", small):
                new.append("/media/%s/%s.jpg" % (pid, fid))
            else:
                ok = False; break
        if not ok:
            print("%s: пропущено (не всі фото завантажились), лишаються посилання OLX" % pid); continue
        con.execute("INSERT INTO history (id,data,ts,ip) VALUES (?,?,?,?)", (pid, raw, int(time.time()), "mirror_photos"))
        p["photos"] = new
        con.execute("UPDATE products SET data=?, updated=? WHERE id=?", (json.dumps(p, ensure_ascii=False), int(time.time()), pid))
        con.commit(); done += 1
        print("%s: %d фото" % (pid, len(new)))
    if done:
        Path(Path(DB).parent / "publish").touch()
    print("Оновлено карток: %d" % done)

main()
