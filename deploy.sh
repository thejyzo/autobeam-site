#!/bin/sh
# Runs on the hosting via cron (every few minutes):
#  1) USD rate (hourly)  2) stock from the accounting sheet  3) pull code from GitHub
#  4) rebuild the site from the admin DB when code/stock/products changed, then sync into the web root.
set -e
REPO="$HOME/autobeam_repo"
WWW="$HOME/autobeam.com.ua/www"
DATA="$HOME/autobeam_data"
BUILD="$HOME/autobeam_build"
mkdir -p "$DATA"
cd "$REPO"
if [ -z "$(find "$WWW/rate.json" -mmin -60 2>/dev/null)" ]; then /bin/sh "$REPO/update_rate.sh" || true; fi

NEED=""
git fetch -q origin main
if [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ] || [ "$1" = "force" ]; then
  git reset -q --hard origin/main
  NEED="code $(git rev-parse --short HEAD)"
fi
# first run: fill the admin DB from data/products.json
[ -f "$DATA/products.sqlite" ] || php "$REPO/server/import_products.php"
[ -f "$DATA/data_keys.json" ] || cp "$REPO/data/data_keys.json" "$DATA/"
php "$REPO/server/stock.php" || true
[ -f "$DATA/publish" ] && NEED="$NEED publish"
# rebuild when today's rate changes (prices in HTML and feeds must match what the browser shows)
RATE_NOW=$(cat "$WWW/rate.json" 2>/dev/null | sed -n 's/.*"rate":\([0-9.]*\).*/\1/p')
[ -n "$RATE_NOW" ] && [ "$RATE_NOW" != "$(cat "$DATA/built_rate" 2>/dev/null)" ] && NEED="$NEED rate"

if [ -n "$NEED" ]; then
  rm -f "$DATA/publish" "$DATA/dirty"
  AB_OUT="$BUILD" AB_DB="$DATA/products.sqlite" AB_STOCK="$DATA/stock.json" AB_RATE="$WWW/rate.json" python3 "$REPO/build.py" > "$DATA/build.log" 2>&1
  [ -n "$RATE_NOW" ] && echo "$RATE_NOW" > "$DATA/built_rate"
  rsync -a --delete --exclude '/.htaccess' --exclude '/.well-known' --exclude '/rate.json' --exclude '/media' "$BUILD/" "$WWW/"
  echo "$(date '+%F %T') built+deployed:$NEED | $(tail -1 "$DATA/build.log")" >> "$HOME/deploy.log"
fi
