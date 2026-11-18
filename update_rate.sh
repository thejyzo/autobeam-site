#!/bin/sh
# Runs on the hosting via cron (hourly): USD sell rate of monobank + markup -> www/rate.json
OUT="$HOME/autobeam.com.ua/www/rate.json"
MARKUP=1
J=$(curl -s --max-time 20 https://api.monobank.ua/bank/currency) || exit 0
php -r '
$a = json_decode($argv[1], true); if (!is_array($a)) exit(1);
foreach ($a as $r) if (($r["currencyCodeA"] ?? 0) == 840 && ($r["currencyCodeB"] ?? 0) == 980 && !empty($r["rateSell"])) {
  echo json_encode(["source" => "monobank", "usd_sell" => $r["rateSell"], "markup" => (float)$argv[2],
    "rate" => round($r["rateSell"] + $argv[2], 2), "updated" => date("c")]); exit(0); }
exit(1);' "$J" "$MARKUP" > "$OUT.tmp" && mv "$OUT.tmp" "$OUT" || rm -f "$OUT.tmp"
