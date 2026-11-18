# AutoBeam — сайт autobeam.com.ua

Статичний сайт з продажу оригінальних фар зі США.

- `data/olx_raw.json` — каталог (вивантаження з магазину OLX)
- `src/` — шаблони, стилі, скрипти
- `config.json` — домен, контакти, ID Google Ads / GA4
- `python3 build.py` — збирає готовий сайт у `site/`

Хостинг (adm.tools) кожні 10 хвилин забирає `site/` з гілки `main` (cron: `deploy.sh`).
