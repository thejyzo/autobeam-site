<?php
// AutoBeam: shared eBay purchases reader (Trading API GetOrders, buyer role). Used by tools/ebay_orders.php (console)
// and admin/ebay_feed.php (Google Sheets «Входящие операции»).
// Kept: order/line ids, Kyiv date, lot title, lot id, amount actually charged, eBay status, US tracking, cabinet КАБ1-4.
// NOT kept or returned: seller ids, addresses, names (only the cabinet label is derived from the recipient's first name).

const EBAY_KAB = ['serhii' => 'КАБ1', 'anastasiia' => 'КАБ2', 'volodymyr' => 'КАБ3', 'larysa' => 'КАБ4'];

function ebay_kab($name) {
  $n = strtolower(preg_replace('/[^a-z ]/i', ' ', (string) $name));
  foreach (EBAY_KAB as $k => $v) if (preg_match('/\b' . $k . '\b/', $n)) return $v;
  return '?';
}

function ebay_call($cfg, $name, $body) {
  $xml = '<?xml version="1.0" encoding="utf-8"?><' . $name . 'Request xmlns="urn:ebay:apis:eBLBaseComponents">'
       . '<RequesterCredentials><eBayAuthToken>' . htmlspecialchars($cfg['ebay_token']) . '</eBayAuthToken></RequesterCredentials>'
       . $body . '</' . $name . 'Request>';
  $ctx = stream_context_create(['http' => ['method' => 'POST', 'timeout' => 60, 'ignore_errors' => true, 'content' => $xml,
    'header' => "Content-Type: text/xml\r\nX-EBAY-API-COMPATIBILITY-LEVEL: 1193\r\nX-EBAY-API-CALL-NAME: $name\r\nX-EBAY-API-SITEID: 0\r\n"
              . "X-EBAY-API-APP-NAME: {$cfg['ebay_app_id']}\r\nX-EBAY-API-DEV-NAME: {$cfg['ebay_dev_id']}\r\nX-EBAY-API-CERT-NAME: {$cfg['ebay_cert_id']}\r\n"]]);
  $r = @file_get_contents('https://api.ebay.com/ws/api.dll', false, $ctx);
  return $r ? @simplexml_load_string($r) : null;
}

function ebay_kyiv_date($iso) {
  // Kyiv time; the zone name differs between tz databases, so try both and fall back to EU DST rules (UTC+2 / +3).
  try { $d = new DateTime($iso); } catch (Exception $e) { return substr((string) $iso, 0, 10); }
  foreach (['Europe/Kyiv', 'Europe/Kiev'] as $z) {
    try { return $d->setTimezone(new DateTimeZone($z))->format('Y-m-d'); } catch (Exception $e) {}
  }
  $ts = $d->getTimestamp(); $y = (int) gmdate('Y', $ts);
  $dstFrom = strtotime("last sunday of march $y 01:00 UTC"); $dstTo = strtotime("last sunday of october $y 01:00 UTC");
  return gmdate('Y-m-d', $ts + (($ts >= $dstFrom && $ts < $dstTo) ? 3 : 2) * 3600);
}

// Split cents into $n parts by weights; the remainder goes to the last parts so the sum is exact.
function ebay_split($cents, $weights) {
  $sum = array_sum($weights); $out = []; $left = $cents;
  foreach ($weights as $i => $w) {
    $v = ($i === count($weights) - 1) ? $left : ($sum > 0 ? (int) floor($cents * $w / $sum) : intdiv($cents, count($weights)));
    $out[] = $v; $left -= $v;
  }
  return $out;
}

// Returns [rows, error]. One row per purchased UNIT (qty 3 => 3 rows), amount = share of what eBay actually charged
// for the order (Order Total = price + shipping + tax), split by line subtotal, then evenly per unit.
function ebay_purchases($cfg, $days = 30) {
  $days = max(1, min(90, (int) $days));
  $from = gmdate('Y-m-d\TH:i:s.000\Z', time() - $days * 86400);
  $rows = []; $page = 1;
  do {
    $x = ebay_call($cfg, 'GetOrders', "<OrderRole>Buyer</OrderRole><CreateTimeFrom>$from</CreateTimeFrom><CreateTimeTo>" . gmdate('Y-m-d\TH:i:s.000\Z') . "</CreateTimeTo>"
           . "<OrderStatus>All</OrderStatus><DetailLevel>ReturnAll</DetailLevel><Pagination><EntriesPerPage>100</EntriesPerPage><PageNumber>$page</PageNumber></Pagination>");
    if (!$x) return [[], 'eBay не відповів'];
    if ((string) $x->Ack === 'Failure') return [[], 'Помилка eBay: ' . (string) $x->Errors->LongMessage];
    foreach ($x->OrderArray->Order ?? [] as $o) {
      $lines = [];
      foreach ($o->TransactionArray->Transaction as $t) $lines[] = $t;
      $weights = [];
      foreach ($lines as $t) $weights[] = (int) round((float) $t->TransactionPrice * 100) * max(1, (int) $t->QuantityPurchased);
      $totalC = (int) round((float) $o->Total * 100);
      $lineC = ebay_split($totalC, $weights);
      $status = (string) $o->OrderStatus;
      if ((string) $o->ShippedTime) $status .= ' / відправлено ' . ebay_kyiv_date((string) $o->ShippedTime);
      foreach ($lines as $li => $t) {
        $trk = [];
        foreach ($t->ShippingDetails->ShipmentTrackingDetails ?? [] as $d) $trk[] = trim((string) $d->ShippingCarrierUsed . ' ' . (string) $d->ShipmentTrackingNumber);
        $qty = max(1, (int) $t->QuantityPurchased);
        $unitC = ebay_split($lineC[$li], array_fill(0, $qty, 1));
        $lineId = (string) $t->OrderLineItemID ?: ((string) $t->Item->ItemID . '-' . (string) $t->TransactionID);
        for ($u = 0; $u < $qty; $u++) {
          $rows[] = [
            'id' => $lineId . '#' . ($u + 1),
            'order' => (string) $o->OrderID,
            'date' => ebay_kyiv_date((string) $o->CreatedTime),
            'item' => (string) $t->Item->Title,
            'item_id' => (string) $t->Item->ItemID,
            'unit' => ($u + 1) . '/' . $qty,
            'amount' => $unitC[$u] / 100,
            'currency' => (string) $o->Total['currencyID'],
            'status' => $status,
            'cancelled' => (bool) preg_match('/cancel/i', (string) $o->OrderStatus),
            'tracking' => implode(', ', array_unique(array_filter($trk))),
            'kab' => ebay_kab((string) $o->ShippingAddress->Name),
          ];
        }
      }
    }
    $more = (string) $x->HasMoreOrders === 'true'; $page++;
  } while ($more && $page < 20);
  return [$rows, null];
}
