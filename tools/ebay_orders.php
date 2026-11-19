<?php
// AutoBeam: read-only eBay purchases (Trading API GetOrders, buyer role).
// php ~/autobeam_repo/tools/ebay_orders.php [days=30] [--json]
// One line per purchased unit; amount = what eBay charged (price + shipping + tax), split per unit.
// Seller user IDs and addresses are NOT printed or stored; from the buyer's shipping address only the cabinet (КАБ1-4) is derived.
if (PHP_SAPI !== 'cli') exit("CLI only\n");
require __DIR__ . '/ebay_lib.php';
$home = getenv('HOME') ?: dirname(__DIR__, 2);
$cfg = @include "$home/autobeam_secrets.php";
if (!is_array($cfg) || empty($cfg['ebay_token'])) exit("Немає ключів eBay. Запустіть: php ~/autobeam_repo/tools/setup_api.php ebay\n");
$days = (int) ($argv[1] ?? 30);
[$rows, $err] = ebay_purchases($cfg, $days);
if ($err) exit("$err\n");
// Перевірка одного лота: php tools/ebay_orders.php 60 --item 860125949902
$ix = array_search('--item', $argv, true);
if ($ix !== false) {
  foreach ($rows as $r) if ($r['item_id'] === ($argv[$ix + 1] ?? '')) {
    echo "{$r['date']} | {$r['item']}\n  Total (без купона): {$r['order_total']} | AmountPaid: {$r['order_paid']} | Payments: {$r['order_payments']} | беремо: {$r['amount']}\n";
  }
  exit;
}
if (in_array('--json', $argv, true)) { echo json_encode($rows, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT), "\n"; exit; }
echo "Покупок (одиниць) за $days дн.: " . count($rows) . "\n";
$byk = array_count_values(array_column($rows, 'kab')); ksort($byk);
echo "За кабінетами: " . implode(', ', array_map(function ($k, $v) { return "$k: $v"; }, array_keys($byk), $byk)) . "\n";
foreach ($rows as $r) {
  echo "{$r['kab']} | {$r['date']} | {$r['item']} | #{$r['item_id']} | {$r['unit']} | {$r['amount']} {$r['currency']} | {$r['status']}" . ($r['tracking'] ? " | трек {$r['tracking']}" : "") . "\n";
}
