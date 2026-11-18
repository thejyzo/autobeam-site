#!/usr/bin/env python3
"""AutoBeam static site generator.
Reads data/olx_raw.json (exported from OLX shop) and writes the site into ./site
Run:  python3 build.py
"""
import json, re, html, os, shutil, datetime
from pathlib import Path

ROOT = Path(__file__).parent
SRC = ROOT / "src"
OUT = ROOT / "site"
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))

BRANDS = ["Land Rover", "Mercedes", "Volkswagen", "Chevrolet", "Infiniti", "Hyundai", "Toyota", "Nissan",
          "Subaru", "Lexus", "Mazda", "Honda", "Acura", "Audi", "Jeep", "Ford", "Kia"]

def esc(s): return html.escape(str(s), quote=True)

def img(pid, size="800x600"):
    return f"https://ireland.apollo.olxcdn.com/v1/files/{pid}/image;s={size};q=80"

def price_fmt(p):
    return f"{round(p):,}".replace(",", " ") + " грн"

def parse(row):
    oid, title, price, pn, state, ptype, olx_slug, photos = row
    t = title.lower()
    brand = next((b for b in BRANDS if b.lower() in t), "Інше")
    if t.startswith("скло"): kind = "Скло фари"
    elif "корпус" in t: kind = "Корпус фари"
    elif "ліхтар" in t: kind = "Ліхтар"
    elif t.startswith("дхо") : kind = "ДХО"
    else: kind = "Фара"
    left, right = ("ліва" in t or "ліве" in t or "лів" in t.split()), ("права" in t or "праве" in t or "правий" in t)
    side = "Ліва + права" if left and right else "Ліва" if left else "Права" if right else ""
    if "full led" in t: light = "Full LED"
    elif "bi-led" in t: light = "Bi-LED"
    elif "ксенон" in t or "xenon" in t: light = "Ксенон"
    elif "галоген" in t: light = "Галоген"
    elif "led" in t: light = "LED"
    else: light = ""
    years = re.search(r"(20\d\d)\s*[–-]\s*(20\d\d)|(20\d\d)\+|(20\d\d)", title)
    yrs = ""
    if years:
        yrs = f"{years.group(1)}–{years.group(2)}" if years.group(1) else (years.group(3) + "+" if years.group(3) else years.group(4))
    slug = re.sub(r"-ID[0-9A-Za-z]+\.html$", "", olx_slug)
    clean = re.sub(r"\s+", " ", title.replace("ОРИГІНАЛ", "").replace("оригінал", "")).strip(" ,")
    pns = [x for x in re.split(r"[,\s]+(?=[A-Z0-9P])", pn.strip()) if x] if pn else []
    return dict(id=oid, title=title, name=clean, price=round(price), price_txt=price_fmt(price),
                pn=pn, state=state, type=ptype or "Оригінал", brand=brand, kind=kind, side=side,
                light=light, years=yrs, slug=slug, olx=f"https://www.olx.ua/d/uk/obyavlenie/{olx_slug}",
                photos=photos.split(","))

def contact_buttons(ctx, cls=""):
    c = CFG
    return f'''<div class="cta-row {cls}">
  <a class="btn btn-tg" href="{c['telegram']}" target="_blank" rel="noopener" data-track="telegram" data-ctx="{ctx}"><svg><use href="#i-tg"/></svg>Telegram</a>
  <a class="btn btn-viber" href="{c['viber']}" data-track="viber" data-ctx="{ctx}"><svg><use href="#i-viber"/></svg>Viber</a>
  <a class="btn btn-call" href="tel:{c['phone_intl']}" data-track="call" data-ctx="{ctx}"><svg><use href="#i-phone"/></svg>{c['phone_display']}</a>
</div>'''

def page(tpl_name, **kw):
    tpl = (SRC / tpl_name).read_text(encoding="utf-8")
    shell = (SRC / "_shell.html").read_text(encoding="utf-8")
    body = tpl
    for k, v in kw.items():
        body = body.replace("{{" + k + "}}", str(v))
    out = shell.replace("{{body}}", body)
    for k, v in {**CFG, **kw}.items():
        out = out.replace("{{" + k + "}}", str(v))
    return out

def main():
    items = [parse(r) for r in json.loads((ROOT / "data" / "olx_raw.json").read_text(encoding="utf-8"))]
    seen = set()
    for it in items:
        if it["slug"] in seen: it["slug"] += f"-{it['id']}"
        seen.add(it["slug"])

    if OUT.exists(): shutil.rmtree(OUT)
    (OUT / "fary").mkdir(parents=True)
    shutil.copytree(SRC / "assets", OUT / "assets")

    # catalog for client-side filtering
    slim = [{k: it[k] for k in ("id", "name", "price", "pn", "brand", "kind", "side", "light", "years", "type", "slug")}
            | {"img": img(it["photos"][0], "400x300")} for it in items]
    (OUT / "assets" / "catalog.js").write_text("window.CATALOG=" + json.dumps(slim, ensure_ascii=False) + ";", encoding="utf-8")
    (OUT / "assets" / "config.js").write_text("window.AB_CONFIG=" + json.dumps(CFG, ensure_ascii=False) + ";", encoding="utf-8")

    brands = sorted({i["brand"] for i in items}, key=lambda b: (b == "Інше", -sum(x["brand"] == b for x in items)))
    brand_chips = "".join(f'<button class="chip" data-brand="{esc(b)}">{esc(b)} <span>{sum(x["brand"]==b for x in items)}</span></button>' for b in brands)

    # SSR cards (SEO + no-JS), JS re-renders on filter
    def card(it, base=""):
        meta = " · ".join(x for x in (it["side"], it["light"], it["years"]) if x)
        return f'''<a class="card" href="{base}fary/{it['slug']}.html">
  <div class="card-img"><img loading="lazy" src="{img(it['photos'][0], '400x300')}" alt="{esc(it['name'])}"></div>
  <div class="card-body"><div class="card-brand">{esc(it['brand'])} · {esc(it['kind'])}</div>
  <h3>{esc(it['name'])}</h3><div class="card-meta">{esc(meta)}</div>
  {f'<div class="card-pn">{esc(it["pn"])}</div>' if it['pn'] else ''}
  <div class="card-price">{it['price_txt']}</div></div></a>'''

    ld_org = json.dumps({"@context": "https://schema.org", "@type": "AutoPartsStore", "name": "AutoBeam",
        "url": CFG["site_url"], "telephone": CFG["phone_intl"], "areaServed": "UA",
        "sameAs": [CFG["telegram"], CFG["olx"]]}, ensure_ascii=False)

    idx = page("index.html", base="", title="AutoBeam — оригінальні фари зі США в наявності та під замовлення",
               description=f"Оригінальні фари, ліхтарі та ДХО зі США для Toyota, Mazda, Ford, Jeep, Nissan, VW та інших. Великий вибір в наявності, підбір за VIN і привезення під замовлення. Пошук за парт-номером, доставка по Україні.",
               canonical=CFG["site_url"] + "/", og_image=CFG["banner"], jsonld=ld_org,
               count=len(items), brand_chips=brand_chips, cards="\n".join(card(i) for i in items),
               cta_hero=contact_buttons("hero"), cta_request=contact_buttons("request", "center"), cta_contacts=contact_buttons("contacts"))
    (OUT / "index.html").write_text(idx, encoding="utf-8")

    for it in items:
        rel = [x for x in items if x["brand"] == it["brand"] and x["id"] != it["id"]][:4]
        thumbs = "".join(f'<button class="thumb{" active" if n==0 else ""}" data-src="{img(p, "1200x900")}"><img src="{img(p, "200x150")}" alt=""></button>' for n, p in enumerate(it["photos"]))
        specs = [("Парт-номер", it["pn"]), ("Марка", it["brand"]), ("Тип", it["kind"]), ("Сторона", it["side"]),
                 ("Світло", it["light"]), ("Роки", it["years"]), ("Стан", it["state"]), ("Походження", it["type"] + ", США")]
        spec_html = "".join(f"<tr><th>{k}</th><td>{esc(v)}</td></tr>" for k, v in specs if v)
        ld = json.dumps({"@context": "https://schema.org", "@type": "Product", "name": it["name"], "sku": it["pn"] or str(it["id"]),
            "mpn": it["pn"] or None, "brand": {"@type": "Brand", "name": it["brand"]}, "image": [img(p, "1200x900") for p in it["photos"]],
            "offers": {"@type": "Offer", "priceCurrency": "UAH", "price": it["price"], "availability": "https://schema.org/InStock",
                       "itemCondition": "https://schema.org/UsedCondition" if it["state"] == "Вживане" else "https://schema.org/NewCondition",
                       "url": f"{CFG['site_url']}/fary/{it['slug']}.html"}}, ensure_ascii=False)
        p = page("product.html", base="../", title=f"{it['name']} — купити | AutoBeam",
                 description=f"{it['name']}. {('Парт-номер ' + it['pn'] + '. ') if it['pn'] else ''}Ціна {it['price_txt']}. Оригінал зі США, перевірена перед продажем. Доставка по Україні.",
                 canonical=f"{CFG['site_url']}/fary/{it['slug']}.html", og_image=img(it["photos"][0], "1200x900"), jsonld=ld,
                 name=esc(it["name"]), brand=esc(it["brand"]), kind=esc(it["kind"]), price_txt=it["price_txt"], pn=esc(it["pn"] or "—"),
                 main_img=img(it["photos"][0], "1200x900"), thumbs=thumbs, specs=spec_html, olx_url=it["olx"],
                 cta=contact_buttons("product"), related="\n".join(card(r, "../") for r in rel), pn_raw=esc(it["pn"]), pid=it["id"])
        (OUT / "fary" / f"{it['slug']}.html").write_text(p, encoding="utf-8")

    today = datetime.date.today().isoformat()
    urls = [CFG["site_url"] + "/"] + [f"{CFG['site_url']}/fary/{i['slug']}.html" for i in items]
    (OUT / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
        "\n".join(f"<url><loc>{u}</loc><lastmod>{today}</lastmod></url>" for u in urls) + "\n</urlset>\n", encoding="utf-8")
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {CFG['site_url']}/sitemap.xml\n", encoding="utf-8")
    print(f"Built {len(items)} products -> {OUT}")

if __name__ == "__main__":
    main()
