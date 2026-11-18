#!/bin/sh
# Runs on the hosting via cron: pull latest and sync site/ into the web root.
set -e
REPO="$HOME/autobeam_repo"
WWW="$HOME/autobeam.com.ua/www"
cd "$REPO"
# refresh USD rate at most once an hour (same cron job)
if [ -z "$(find "$WWW/rate.json" -mmin -60 2>/dev/null)" ]; then /bin/sh "$REPO/update_rate.sh"; fi
git fetch -q origin main
if [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ] || [ "$1" = "force" ]; then
  git reset -q --hard origin/main
  rsync -a --delete --exclude '.htaccess' --exclude '.well-known' --exclude 'rate.json' "$REPO/site/" "$WWW/"
  echo "$(date '+%F %T') deployed $(git rev-parse --short HEAD)" >> "$HOME/deploy.log"
fi
