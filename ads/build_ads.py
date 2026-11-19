#!/usr/bin/env python3
"""Build a Google Ads Editor import CSV for the AutoBeam search campaign from stock.tsv (in-stock cards with part numbers)."""
import csv, re, collections, sys
from pathlib import Path

HERE = Path(__file__).parent
SITE = "https://autobeam.com.ua"
CAMPAIGN = "AutoBeam"   # renamed by the owner in Google Ads (19.11)
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
            "лінза", "лінзи", "линзы", "наклейка", "плівка", "пленка", "чохол",
            "протитуманні", "противотуманные", "птф", "запітніває", "потеет", "відео", "видео", "фото", "схема",
            "lego", "gta", "игрушка", "іграшка", "кузовщина", "розборка повна",
            "туманка", "противотуманка", "протитуманка", "противотуманная", "протитуманна", 
            "ремкомплект", "кріплення фари", "крепление фары", "ушки фары", "вушка фари",
            "блок розжига", "блок розжигу", "омыватель фар", "омивач фар", "led лампы", "led лампи", "ксенон лампы",
            "реставрация", "реставрація", "чертеж", "креслення", "3d модель", "stl", "обои", "шпалери", "раскраска", "розмальовка",
            "как снять", "як зняти", "как поменять", "як поміняти", "своими силами"]


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
    years = g["years"]
    if kind in PARTS:
        P = PARTS[kind]["pl"].capitalize()
        heads = [f"{P} {m}", f"{P} {b} {m}", f"{m} {years}: {PARTS[kind]['pl']}", "Аналог, нова деталь", "Є в наявності",
                 "Доставка Новою поштою", "Відправка того ж дня", "Підберемо за VIN", "AutoBeam — оптика зі США",
                 "Пишіть у Telegram або Viber", "Фото реального товару", "Гарантія 14 днів"]
        descs = [f"{P} для {b} {m} {years} — аналог (не оригінал). Ліва та права сторона.",
                 "Є в наявності. Відправка Новою поштою по Україні того ж дня.",
                 "Підберемо за VIN або номером фари. Пишіть у Telegram, Viber чи телефонуйте.",
                 f"Також є оригінальні фари {b} зі США — підкажемо, що підходить саме вам."]
        return fit(heads, 30)[:15], fit(descs, 90)[:4]
    pl = {"Фара": "фари", "Ліхтар": "ліхтарі", "ДХВ": "ходові вогні"}[kind]
    Pl = pl.capitalize()
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



# Generation / body names people type ("камри 70", "рав 4 50", "escape mk4"). (from_year, to_year, tokens)
GENS = {
 "Camry": [(2017, 2024, ["70", "75", "xv70", "v70"]), (2025, 2026, ["80", "xv80"])],
 "RAV4": [(2019, 2025, ["50", "xa50", "5"]), (2026, 2026, ["60", "xa60", "6"])],
 "Highlander": [(2020, 2024, ["xu70", "4"])], "Corolla": [(2017, 2019, ["e170", "11"])],
 "Escape / Kuga": [(2020, 2026, ["mk4", "4", "3"])], "Edge": [(2015, 2024, ["2", "mk2"])],
 "CR-V": [(2017, 2022, ["5", "rw"]), (2023, 2025, ["6"])], "Civic": [(2022, 2025, ["11"])],
 "Accord": [(2018, 2022, ["10"]), (2023, 2025, ["11"])], "Kona": [(2023, 2025, ["2", "sx2"])],
 "Grand Cherokee": [(2017, 2021, ["wk2"]), (2021, 2025, ["wl"])], "Cherokee": [(2019, 2023, ["kl"])],
 "Compass": [(2017, 2026, ["mp", "2"])], "Sorento": [(2019, 2020, ["um", "prime", "прайм"]), (2022, 2025, ["mq4", "4"])],
 "CX-5": [(2017, 2025, ["kf", "2"])], "RX": [(2023, 2025, ["350", "350h", "500h", "al30"])],
 "C-Class": [(2022, 2026, ["w206"])], "Rogue": [(2021, 2023, ["t33", "3"])], "Sentra": [(2020, 2022, ["b18"])],
 "Murano": [(2023, 2026, ["z52"])], "A4": [(2020, 2025, ["b9", "b9.5"])], "A3": [(2025, 2026, ["8y"])],
 "Outback / Legacy": [(2020, 2025, ["bt", "6"]), (2026, 2026, ["7"])], "Forester": [(2025, 2026, ["6", "sl"])],
 "Tiguan": [(2022, 2024, ["2", "ad1"])], "QX60": [(2022, 2025, ["2"])],
}
# older generations of the same model — negatives, so we do not pay for parts that will not fit
OLD_GENS = {
 "Camry": ["40", "45", "50", "55", "xv40", "xv50", "xv55"], "RAV4": ["xa40", "xa30", "xa20", "кузов 40", "кузов 30", "40 кузов", "30 кузов"],
 "Highlander": ["xu50", "xu40"], "CR-V": ["rm", "re"], "Grand Cherokee": ["wk", "wj"], "Sorento": ["xm", "bl"],
 "Escape / Kuga": ["mk3", "mk2", "mk1"], "Accord": ["cr", "cu"], "Civic": ["fc", "fk"], "C-Class": ["w205", "w204"],
 "CX-5": ["ke"], "Rogue": ["t32"], "Outback / Legacy": ["bs", "br"], "Forester": ["sk", "sj"], "A4": ["b8", "b7"],
}

PARTS = {  # separate products sold on their own (owner, 19.11): only for models where we have them
 "Скло фари": {"nouns": ["скло фари", "стекло фары", "скло фар", "стекла фар", "скло на фару", "стекло на фару", "скло фари ліве", "скло фари праве",
                         "стекло фары левое", "стекло фары правое"], "pl": "скло фари"},
 "Корпус фари": {"nouns": ["корпус фари", "корпус фары", "корпус фар", "маска фари", "маска фары", "маска фар", "корпус на фару",
                           "маска на фару", "декоративна маска фари", "внутрішня маска фари"], "pl": "корпус і маска фари"},
}
PART_NEG = ["скло фари", "стекло фары", "скло фар", "стекло фар", "стекла фар", "скло на фару", "стекло на фару",
            "корпус фари", "корпус фары", "корпус фар", "корпус на фару"]


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
    yrs = [int(y) for it in g["items"] for y in re.findall(r"\d{4}", it["y"])]
    lo, hi = (min(yrs), max(yrs + [min(yrs)])) if yrs else (0, 0)
    if any(it["y"].endswith("+") for it in g["items"]): hi = max(hi, 2026)
    toks = [t for (a, z, ts) in GENS.get(m, []) if a <= hi and z >= lo for t in ts]
    if toks:
        base = (lat[:2] + cyr[:2]) or [m.lower()]
        for x in base:
            for t in toks:
                names += [f"{x} {t}"] + ([f"{bl} {x} {t}"] if not x.startswith(bl) else [])
    out = []
    for n in names:
        n = re.sub(r"\s+", " ", n).strip()
        if n and n not in out:
            out.append(n)
    return out


def group_negatives(g):
    """Ad-group negatives: years of older generations (2+ years before what we have) and older body codes."""
    m = g["mn"]
    yrs = [int(y) for it in g["items"] for y in re.findall(r"\d{4}", it["y"])]
    neg = [str(y) for y in range(2005, min(yrs) - 1)] if yrs else []
    names = (LAT_EXTRA.get(m, [m.lower()])[:2] + CYR.get(m, [])[:2])
    for t in OLD_GENS.get(m, []):
        neg += [t] if (" " in t or len(t) > 2 and not t.isdigit()) else [f"{x} {t}" for x in names if "/" not in x]
    return list(dict.fromkeys(neg))


def model_keywords(g):
    kind, analog = g["kind"], g["analog"]
    names = model_names(g)
    kw = []
    if kind in PARTS:
        for x in names:
            for n in PARTS[kind]["nouns"]:
                kw += [f"{n} {x}", f"{x} {n}"]
                if not n.endswith(" на фару"):
                    kw += [f"{n} на {x}"]
    elif analog:
        for x in names[:4]:
            kw += [f"фара {x} аналог", f"фара {x} depo", f"depo {x}"]
    else:
        nouns = {"Фара": ["фара", "фари", "фары", "фару"], "Ліхтар": ["ліхтар", "фонарь", "задній ліхтар", "стоп"],
                 "ДХВ": ["ходові вогні", "дхв", "led смуга"]}[kind]
        en = {"Фара": "headlight", "Ліхтар": "tail light", "ДХВ": "drl"}[kind]
        sides = {it["side"] for it in g["items"]}
        side_words = []
        if kind == "Фара":
            if "Ліва" in sides: side_words += ["ліва", "левая"]
            if "Права" in sides: side_words += ["права", "правая"]
            extra = ["передня", "передняя", "led", "лед", "оригінал", "оригинал", "бу", "б/у"]
        elif kind == "Ліхтар":
            if "Ліва" in sides: side_words += ["лівий", "левый"]
            if "Права" in sides: side_words += ["правий", "правый"]
            extra = ["задній", "задний", "led", "оригінал", "оригинал", "бу"]
        else:
            extra = []
        base = nouns[0]
        for x in names:
            for n in nouns:
                kw += [f"{n} {x}", f"{x} {n}"]        # phrase match keeps word order, so both orders
            # phrase match does not allow words INSIDE the phrase: "фара ліва rav4" needs its own keyword
            for sw in side_words + extra:
                kw += [f"{base} {sw} {x}", f"{sw} {base} {x}", f"{x} {base} {sw}"]
            kw += [f"{n} на {x}" for n in nouns[:3]] + ([f"оптика {x}", f"оптика на {x}"] if kind == "Фара" else [])
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
            kind_name = PARTS[r["kind"]]["pl"] if r["kind"] in PARTS else r["kind"].lower()
            nm = f"{r['b']} {r['mn']}" + ("" if r["kind"] == "Фара" else f" — {kind_name}") + (" — аналог" if r["kind"] in PARTS else (" — аналог DEPO" if analog else ""))
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
        for n in group_negatives(g) + (PART_NEG if g["kind"] == "Фара" else []):
            row(Campaign=CAMPAIGN, Ad_Group=g["name"], Keyword=n, Criterion_Type="Negative Phrase")
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
