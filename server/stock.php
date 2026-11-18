<?php
// Наявність з обліку: опублікований CSV аркуша «Наявність (для сайту)» -> ~/autobeam_data/stock.json
// Запускається з deploy.sh (cron). Якщо дані змінились — ставить прапорець на перебудову сайту.
if (PHP_SAPI !== 'cli') exit;
$home = getenv('HOME'); $data = "$home/autobeam_data"; @mkdir($data, 0700, true);
$url = is_file("$data/stock_url.txt") ? trim(file_get_contents("$data/stock_url.txt")) : '';   // URL is kept only on the server
if (!$url) exit(0);
$ctx = stream_context_create(['http' => ['timeout' => 25, 'follow_location' => 1]]);
$csv = @file_get_contents($url, false, $ctx);
if (!$csv || strpos($csv, ',') === false) { fwrite(STDERR, "stock: download failed\n"); exit(0); }
$map = [];
$lines = array_map('str_getcsv', preg_split('/\r?\n/', trim($csv)));
foreach (array_slice($lines, 1) as $r) {
  if (count($r) < 4 || trim($r[0]) === '') continue;
  $map[trim($r[0])] = [(int) $r[1], (int) $r[2], (int) $r[3], 0];
}
if (count($map) < 50) { fwrite(STDERR, "stock: suspiciously small (" . count($map) . "), ignored\n"); exit(0); }
$new = json_encode($map, JSON_UNESCAPED_UNICODE);
$f = "$data/stock.json";
if (!is_file($f) || file_get_contents($f) !== $new) {
  file_put_contents("$f.tmp", $new); rename("$f.tmp", $f);
  touch("$data/publish");
  echo "stock updated: " . count($map) . " positions\n";
}
