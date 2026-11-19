<?php
// AutoBeam: read-only eBay purchases (Trading API GetOrders, buyer role).
// php ~/autobeam_repo/tools/ebay_orders.php [days=30] [--json]
// Prints only what we need for accounting: order id, date, item, item id, qty, price, shipping, total, status, tracking.
// Seller user IDs / addresses are NOT printed or stored (eBay exemption: "I do not persist eBay data").
if (PHP_SAPI !== 'cli') exit("CLI only\n");
$home = getenv('HOME') ?: dirname(__DIR__, 2);
$cfg = @include "$home/autobeam_secrets.php";
if (!is_array($cfg) || empty($cfg['ebay_token'])) exit("Немає ключів eBay. Запустіть: php ~/autobeam_repo/tools/setup_api.php ebay\n");
$days = (int) ($argv[1] ?? 30); if ($days < 1 || $days > 90) $days = 30;   // GetOrders: up to 90 days back
$json = in_array('--json', $argv, true);

function call($cfg, $name, $body) {
  $xml = '<?xml version="1.0" encoding="utf-8"?><' . $name . 'Request xmlns="urn:ebay:apis:eBLBaseComponents">'
       . '<RequesterCredentials><eBayAuthToken>' . htmlspecialchars($cfg['ebay_token']) . '</eBayAuthToken></RequesterCredentials>'
       . $body . '</' . $name . 'Request>';
  $ctx = stream_context_create(['http' => ['method' => 'POST', 'timeout' => 60, 'ignore_errors' => true, 'content' => $xml,
    'header' => "Content-Type: text/xml\r\nX-EBAY-API-COMPATIBILITY-LEVEL: 1193\r\nX-EBAY-API-CALL-NAME: $name\r\nX-EBAY-API-SITEID: 0\r\n"
              . "X-EBAY-API-APP-NAME: {$cfg['ebay_app_id']}\r\nX-EBAY-API-DEV-NAME: {$cfg['ebay_dev_id']}\r\nX-EBAY-API-CERT-NAME: {$cfg['ebay_cert_id']}\r\n"]]);
  $r = @file_get_contents('https://api.ebay.com/ws/api.dll', false, $ctx);
  return $r ? @simplexml_load_string($r) : null;
}

$from = gmdate('Y-m-d\TH:i:s.000\Z', time() - $days * 86400);
$rows = []; $page = 1;
do {
  $x = call($cfg, 'GetOrders', "<OrderRole>Buyer</OrderRole><CreateTimeFrom>$from</CreateTimeFrom><CreateTimeTo>" . gmdate('Y-m-d\TH:i:s.000\Z') . "</CreateTimeTo>"
         . "<OrderStatus>All</OrderStatus><DetailLevel>ReturnAll</DetailLevel><Pagination><EntriesPerPage>100</EntriesPerPage><PageNumber>$page</PageNumber></Pagination>");
  if (!$x) exit("eBay не відповів.\n");
  if ((string) $x->Ack === 'Failure') exit("Помилка eBay: " . (string) $x->Errors->LongMessage . "\n");
  foreach ($x->OrderArray->Order ?? [] as $o) {
    foreach ($o->TransactionArray->Transaction as $t) {
      $trk = [];
      foreach ($t->ShippingDetails->ShipmentTrackingDetails ?? [] as $d) $trk[] = trim((string) $d->ShippingCarrierUsed . ' ' . (string) $d->ShipmentTrackingNumber);
      $rows[] = [
        'order' => (string) $o->OrderID,
        'date' => substr((string) $o->CreatedTime, 0, 10),
        'item' => (string) $t->Item->Title,
        'item_id' => (string) $t->Item->ItemID,
        'qty' => (int) $t->QuantityPurchased,
        'price' => (float) $t->TransactionPrice . ' ' . (string) $t->TransactionPrice['currencyID'],
        'shipping' => (float) $o->ShippingServiceSelected->ShippingServiceCost,
        'tax' => (float) ($o->ShippingDetails->SalesTax->SalesTaxAmount ?? 0),
        'total' => (float) $o->Total . ' ' . (string) $o->Total['currencyID'],
        'status' => (string) $o->OrderStatus . ((string) $o->ShippedTime ? ' / відправлено ' . substr((string) $o->ShippedTime, 0, 10) : ''),
        'tracking' => implode(', ', array_filter($trk)),
      ];
    }
  }
  $more = (string) $x->HasMoreOrders === 'true'; $page++;
} while ($more && $page < 20);

if ($json) { echo json_encode($rows, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT), "\n"; exit; }
echo "Покупок за $days дн.: " . count($rows) . "\n";
foreach ($rows as $r) {
  echo "{$r['date']} | {$r['item']} | #{$r['item_id']} | {$r['qty']} шт | {$r['price']} + дост. {$r['shipping']} | разом {$r['total']} | {$r['status']}" . ($r['tracking'] ? " | трек {$r['tracking']}" : "") . "\n";
}
