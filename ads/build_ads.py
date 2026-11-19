#!/usr/bin/env python3
"""Build a Google Ads Editor import CSV for the AutoBeam search campaign from stock.tsv (in-stock cards with part numbers)."""
import csv, re, collections, sys
from pathlib import Path

HERE = Path(__file__).parent
SITE = "https://autobeam.com.ua"
CAMPAIGN = "Пошук — Фари за номером і моделлю"
BUDGET = "300"

CYR = {  # how people type the model in Cyrillic (UA / RU)
 "A4": ["ауді а4", "ауди а4"], "A3": ["ауді а3", "ауди а3"],
 "Escape / Kuga": ["ескейп", "эскейп", "куга"], "Edge": ["едж", "эдж"], "Mustang Mach-E": ["мах е", "мустанг мах"],
 "CR-V": ["срв", "црв"], "Civic": ["сівік", "цивик"], "Accord": ["акорд", "аккорд"], "Kona": ["кона"],
 "QX60": ["qx60 інфініті", "инфинити qx60"], "QX50 / QX55": ["инфинити qx50", "інфініті qx50"],
 "Grand Cherokee": ["гранд черокі", "гранд чероки"], "Cherokee": ["черокі", "чероки"], "Compass": ["компас"],
 "Grand Wagoneer": ["вагонір", "вагонир"], "Sorento": ["соренто"], "RX": ["лексус рх", "лексус rx"],
 "CX-5": ["сх5", "сх 5"], "CX-50": ["сх50", "сх 50"], "CX-70 / CX-90": ["сх90", "сх 90", "сх70"],
 "C-Class": ["мерседес с клас", "мерседес с класс", "w206"], "Kicks": ["кікс", "кикс"], "Murano": ["мурано"],
 "Rogue": ["рог", "рога"], "Sentra": ["сентра"], "Outback / Legacy": ["аутбек", "легасі", "легаси"],
 "Forester": ["форестер"], "Grand Highlander": ["гранд хайлендер"], "Highlander": ["хайлендер", "хайландер"],
 "RAV4": ["рав4", "рав 4"], "Camry": ["камрі", "камри"], "Corolla": ["королла", "корола"],
 "Atlas Cross Sport": ["атлас крос спорт", "атлас кросс спорт"], "Tiguan": ["тігуан", "тигуан"],
}
LAT_EXTRA = {"Escape / Kuga": ["escape", "kuga"], "CX-70 / CX-90": ["cx-90", "cx-70", "cx90"], "QX50 / QX55": ["qx50", "qx55"],
             "Outback / Legacy": ["outback", "legacy"], "RAV4": ["rav4", "rav 4"], "CX-5": ["cx-5", "cx5"], "CX-50": ["cx-50", "cx50"],
             "CR-V": ["cr-v", "crv"], "Mustang Mach-E": ["mach-e", "mach e"], "C-Class": ["c-class", "c class", "w206"],
             "Atlas Cross Sport": ["atlas cross sport"]}
import json
AL = json.loads((HERE.parent / "data" / "aliases.json").read_text(encoding="utf-8")) if (HERE.parent / "data" / "aliases.json").exists() else None
if AL:  # single source of truth for model spellings (site search uses the same file)
    for key, v in AL["models"].items():
        b, m = key.split("|", 1)
        short = [x for x in v if len(x.replace(" ", "")) < 3]
        v = [x for x in v if len(x.replace(" ", "")) >= 3]  # "kl", "wl", "рх" are too ambiguous alone — only with the brand
        lat = [x for x in v if re.match(r"^[a-z0-9 .-]+$", x)]
        cyr = [x for x in v if not re.match(r"^[a-z0-9 .-]+$", x)]
        LAT_EXTRA[m] = list(dict.fromkeys([m.lower()] + LAT_EXTRA.get(m, []) + lat))
        bc = AL["brands"].get(b, [""])[0]
        CYR[m] = list(dict.fromkeys(cyr + ([f"{bc} {cyr[0]}"] if bc and cyr and not cyr[0].startswith(bc) else []) +
                                    [f"{bc} {x}" for x in short if bc and not re.match(r"^[a-z0-9]+$", x)] + ([f"{bc} {m.lower()}"] if bc else [])))
KOITO = re.compile(r"^10[01]008a")

NEGATIVE = ["ремонт", "полірування", "полировка", "лампа", "лампи", "лампы", "лампочка", "заміна", "замена",
            "регулювання", "регулировка", "своїми руками", "своими руками", "як ", "как ", "тюнінг", "тюнинг",
            "лінза", "лінзи", "линзы", "скло фари", "стекло фары", "наклейка", "плівка", "пленка", "чохол",
            "протитуманні", "противотуманные", "птф", "запітніває", "потеет", "відео", "видео", "фото", "схема",
            "lego", "gta", "игрушка", "іграшка", "кузовщина", "розборка повна"]


def ukside(s):
    return {"Ліва": "ліва", "Права": "права", "Пара (ліва + права)": "пара", "Центральна": "центральна"}.get(s, "")


def load():
    rows = []
    for line in (HERE / "stock.tsv").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        f = line.split("\t")
        rows.append(dict(id=f[0], mk=f[1], mn=f[2], b=f[3], side=f[4], y=f[5], kind=f[6], typ=f[7], slug=f[8], pn=f[9], pns=f[10].split()))
    return rows


def fit(xs, n):
    out = []
    for x in xs:
        x = x.strip()
        if x and len(x) <= n and x not in out:
            out.append(x)
    return out


def ad_texts(g):
    m, b, kind, analog = g["mn"], g["b"], g["kind"], g["analog"]
    pl = {"Фара": "фари", "Ліхтар": "ліхтарі", "ДХВ": "ходові вогні"}[kind]
    Pl = pl.capitalize()
    years = g["years"]
    if analog:
        heads = [f"{Pl} {m} аналог DEPO", f"Аналог DEPO для {m}", f"{b} {m}: аналог DEPO", "Не оригінал — чесна ціна",
                 "Гарантія 14 днів", "Доставка Новою поштою", "Відправка в день замовлення", "Підбір за парт-номером",
                 "Фото реального товару", "AutoBeam — оптика зі США", "Пишіть у Telegram або Viber", f"{m} {years}"]
        descs = [f"Аналог DEPO (не оригінал) для {b} {m}, ринок США. Перевірено перед продажем.",
                 "Підберемо за парт-номером або VIN. Відправка Новою поштою в день замовлення.",
                 "Гарантія 14 днів. Реальні фото товару на сайті. Пишіть у Telegram, Viber або дзвоніть.",
                 "Потрібен оригінал? Підкажемо, що є в наявності, і підберемо за номером."]
    else:
        heads = [f"{Pl} {m} з США", f"{Pl} {b} {m}", f"{m}: оригінал зі США", f"{Pl} {m} {years}",
                 "Оригінальна оптика зі США", "Гарантія 14 днів", "Доставка Новою поштою", "Відправка в день замовлення",
                 "Підбір за парт-номером", "Ліва або права сторона", "Перевірено перед продажем", "AutoBeam — оптика зі США",
                 "Пишіть у Telegram або Viber", "Фото реального товару", "Вживані оригінали"]
        descs = [f"Оригінальні {pl} для {b} {m} з ринку США. Перевірені перед продажем, гарантія 14 днів.",
                 "Підберемо за парт-номером або VIN. Відправка Новою поштою в день замовлення.",
                 "Ліва чи права — ціна за 1 шт. Уточніть наявність у Telegram, Viber чи за телефоном.",
                 f"Вживані оригінальні {pl} {b}. Реальні фото кожного товару на сайті AutoBeam."]
    heads = fit(heads, 30)[:15]
    descs = fit(descs, 90)[:4]
    if len(heads) < 3 or len(descs) < 2:
        sys.exit(f"Too few ad texts for {g['name']}: {heads} {descs}")
    return heads, descs


def model_names(g):
    """All the ways people name this model: Latin / Cyrillic, with or without the brand, mixed (форд escape)."""
    m, b = g["mn"], g["b"]
    lat = [x for x in LAT_EXTRA.get(m, [m.lower()]) if "/" not in x]
    if "/" in m.lower() and not lat:
        lat = [x.strip() for x in m.lower().split("/")]
    cyr = [x for x in CYR.get(m, []) if "/" not in x]
    bl = b.lower()
    bc = (AL["brands"].get(b, []) if AL else [])[:2]
    names = []
    for x in lat:
        names += [x, f"{bl} {x}"] + [f"{c} {x}" for c in bc]
    for x in cyr:
        if any(x.startswith(c) for c in bc):
            names.append(x); continue
        names += [x] + [f"{c} {x}" for c in bc] + [f"{bl} {x}"]
    out = []
    for n in names:
        n = re.sub(r"\s+", " ", n).strip()
        if n and n not in out:
            out.append(n)
    return out


def model_keywords(g):
    kind, analog = g["kind"], g["analog"]
    names = model_names(g)
    kw = []
    if analog:
        for x in names[:4]:
            kw += [f"фара {x} аналог", f"фара {x} depo", f"depo {x}"]
    else:
        nouns = {"Фара": ["фара", "фари", "фары"], "Ліхтар": ["ліхтар", "фонарь", "задній ліхтар", "стоп"],
                 "ДХВ": ["ходові вогні", "дхв", "led смуга"]}[kind]
        en = {"Фара": "headlight", "Ліхтар": "tail light", "ДХВ": "drl"}[kind]
        for x in names:
            for n in nouns:
                kw += [f"{n} {x}", f"{x} {n}"]        # phrase match keeps word order, so both orders
            if re.match(r"^[a-z0-9 .-]+$", x):
                kw += [f"{x} {en}"]
    out = []
    for k in kw:
        k = re.sub(r"\s+", " ", k).strip()
        if k not in out:
            out.append(k)
    return out


def main():
    rows = load()
    groups = collections.OrderedDict()
    for r in rows:
        analog = r["typ"] == "Аналог"
        key = (r["mk"], r["kind"], analog)
        if key not in groups:
            nm = f"{r['b']} {r['mn']}" + ("" if r["kind"] == "Фара" else f" — {r['kind'].lower()}") + (" — аналог DEPO" if analog else "")
            groups[key] = dict(name=nm, mk=r["mk"], mn=r["mn"], b=r["b"], kind=r["kind"], analog=analog, items=[])
        groups[key]["items"].append(r)

    # part numbers: one keyword → one card (primary pn wins over alternates)
    owner = {}
    for r in rows:
        for p in [re.sub(r"[^0-9a-z]", "", r["pn"].lower())] + r["pns"]:
            p = re.sub(r"^p(?=\d{8})", "", p)
            if KOITO.match(p) or len(p) < 6:
                continue
            if p not in owner or p == re.sub(r"[^0-9a-z]", "", r["pn"].lower()):
                owner[p] = r

    hdr = ["Campaign", "Campaign Type", "Networks", "Budget", "Budget type", "Bid Strategy Type", "Campaign Status", "Languages",
           "Location", "Ad Group", "Ad Group Status", "Keyword", "Criterion Type", "Final URL", "Ad type"] + \
          [f"Headline {i}" for i in range(1, 16)] + [f"Description {i}" for i in range(1, 5)] + ["Path 1", "Path 2", "Status"]
    out = []
    def row(**kw):
        out.append({h: kw.get(h.replace(" ", "_"), "") for h in hdr})

    row(Campaign=CAMPAIGN, Campaign_Type="Search", Networks="Google search", Budget=BUDGET, Budget_type="Daily",
        Bid_Strategy_Type="Maximize clicks", Campaign_Status="Paused", Languages="uk;ru")
    row(Campaign=CAMPAIGN, Location="Ukraine")
    for n in NEGATIVE:
        row(Campaign=CAMPAIGN, Keyword=n.strip(), Criterion_Type="Negative Phrase")

    summary = []
    for g in groups.values():
        years = sorted({y for it in g["items"] for y in re.findall(r"\d{4}", it["y"])})
        g["years"] = f"{years[0]}–{years[-1]}" if len(years) > 1 else (years[0] + "+" if years else "")
        if len(g["items"]) == 1:
            gurl = f"{SITE}/fary/{g['items'][0]['slug']}.html"
        else:
            gurl = f"{SITE}/?model={g['mk']}"
        row(Campaign=CAMPAIGN, Ad_Group=g["name"], Ad_Group_Status="Enabled")
        heads, descs = ad_texts(g)
        ad = dict(Campaign=CAMPAIGN, Ad_Group=g["name"], Ad_type="Responsive search ad", Final_URL=gurl,
                  Path_1="fary", Path_2=re.sub(r"[^a-z0-9-]", "", g["mk"].split("-", 1)[-1])[:15], Status="Enabled")
        for i, h in enumerate(heads, 1):
            ad[f"Headline_{i}"] = h
        for i, d in enumerate(descs, 1):
            ad[f"Description_{i}"] = d
        row(**ad)
        mk = model_keywords(g)
        for k in mk:
            row(Campaign=CAMPAIGN, Ad_Group=g["name"], Keyword=k, Criterion_Type="Phrase", Final_URL=gurl)
        nums = 0
        for it in g["items"]:
            url = f"{SITE}/fary/{it['slug']}.html"
            for p, r in owner.items():
                if r is not it:
                    continue
                kws = [p]
                disp = re.sub(r"^p(?=\d{8})", "", it["pn"].lower()) if re.sub(r"^p(?=\d{8})", "", re.sub(r"[^0-9a-z]", "", it["pn"].lower())) == p else ""
                if disp and disp != p:
                    kws.append(disp)
                for k in kws:
                    row(Campaign=CAMPAIGN, Ad_Group=g["name"], Keyword=k, Criterion_Type="Phrase", Final_URL=url)
                    nums += 1
        summary.append((g["name"], len(g["items"]), len(mk), nums, gurl))

    with open(HERE / "autobeam_search_campaign.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=hdr)
        w.writeheader()
        w.writerows(out)
    with open(HERE / "summary.tsv", "w", encoding="utf-8") as fh:
        for s in summary:
            fh.write("\t".join(map(str, s)) + "\n")
    print(f"groups={len(groups)} rows={len(out)} kw_model={sum(s[2] for s in summary)} kw_numbers={sum(s[3] for s in summary)}")


if __name__ == "__main__":
    main()
