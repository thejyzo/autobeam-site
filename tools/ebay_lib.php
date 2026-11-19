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
      // Скільки реально списано: AmountPaid враховує купони/знижки eBay; Total — ні. Якщо AmountPaid немає — Total.
      $paid = (float) $o->AmountPaid;
      $payments = 0.0;
      foreach ($o->MonetaryDetails->Payments->Payment ?? [] as $pm) $payments += (float) $pm->PaymentAmount;
      $charged = $paid > 0 ? $paid : ($payments > 0 ? $payments : (float) $o->Total);
      $totalC = (int) round($charged * 100);
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
            'order_total' => (float) $o->Total,
            'order_paid' => $paid,
            'order_payments' => round($payments, 2),
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

// Photo URLs of lots (for the owner's private Google Drive folder per lot; not stored on the server, not used on the site).
// Returns [itemId => [url, ...]] in the largest size eBay serves (s-l1600).
function ebay_pictures($cfg, $ids) {
  $out = [];
  foreach (array_slice(array_unique($ids), 0, 10) as $id) {
    if (!preg_match('/^\d{6,20}$/', $id)) continue;
    $x = ebay_call($cfg, 'GetItem', "<ItemID>$id</ItemID><OutputSelector>PictureDetails</OutputSelector>");
    $urls = [];
    if ($x && (string) $x->Ack !== 'Failure') {
      foreach ($x->Item->PictureDetails->PictureURL ?? [] as $u) {
        $u = (string) $u;
        if (preg_match('#/z/([A-Za-z0-9~_-]+)/\$_\d+\.#', $u, $m)) $u = 'https://i.ebayimg.com/images/g/' . $m[1] . '/s-l1600.jpg';
        $u = preg_replace('#/s-l\d+\.(jpg|jpeg|png|webp)#i', '/s-l1600.$1', $u);
        if (preg_match('#^https://i\.ebayimg\.com/#', $u)) $urls[] = $u;
      }
    }
    $out[$id] = array_values(array_unique($urls));
  }
  return $out;
}

// ===== eBay monitor (Browse API: search of new listings) =====
// Application token (client credentials) — no user data; cached outside the web root for its lifetime (~2 h).
function ebay_app_token($cfg, $dataDir) {
  $f = "$dataDir/ebay_app_token.json";
  $c = is_file($f) ? json_decode((string) file_get_contents($f), true) : null;
  if (is_array($c) && ($c['exp'] ?? 0) > time() + 120) return $c['token'];
  $ctx = stream_context_create(['http' => ['method' => 'POST', 'timeout' => 30, 'ignore_errors' => true,
    'header' => "Content-Type: application/x-www-form-urlencoded\r\nAuthorization: Basic " . base64_encode($cfg['ebay_app_id'] . ':' . $cfg['ebay_cert_id']) . "\r\n",
    'content' => http_build_query(['grant_type' => 'client_credentials', 'scope' => 'https://api.ebay.com/oauth/api_scope'])]]);
  $r = json_decode((string) @file_get_contents('https://api.ebay.com/identity/v1/oauth2/token', false, $ctx), true);
  if (empty($r['access_token'])) return null;
  @file_put_contents($f, json_encode(['token' => $r['access_token'], 'exp' => time() + (int) ($r['expires_in'] ?? 7200)]), LOCK_EX);
  @chmod($f, 0600);
  return $r['access_token'];
}

// Newest US listings for a query, Buy It Now / Best Offer, item price ≤ $max. Shipping is quoted to $zip (US forwarder warehouse).
// Returned: lot id, title, price, shipping, condition, link, listed time, seller feedback % — no seller names.
function ebay_search($cfg, $dataDir, $q, $max, $zip = '19720', $limit = 50) {
  $tok = ebay_app_token($cfg, $dataDir);
  if (!$tok) return [null, 'eBay: не вдалося отримати токен застосунку'];
  $filter = 'buyingOptions:{FIXED_PRICE|BEST_OFFER},itemLocationCountry:US,deliveryCountry:US,priceCurrency:USD';
  if ($max > 0) $filter .= ',price:[..' . round($max, 2) . ']';
  $url = 'https://api.ebay.com/buy/browse/v1/item_summary/search?' . http_build_query([
    'q' => $q, 'filter' => $filter, 'sort' => 'newlyListed', 'limit' => max(1, min(200, (int) $limit))]);
  $ctx = stream_context_create(['http' => ['method' => 'GET', 'timeout' => 30, 'ignore_errors' => true,
    'header' => "Authorization: Bearer $tok\r\nX-EBAY-C-MARKETPLACE-ID: EBAY_US\r\n"
              . 'X-EBAY-C-ENDUSERCTX: contextualLocation=' . rawurlencode("country=US,zip=$zip") . "\r\n"]]);
  $r = json_decode((string) @file_get_contents($url, false, $ctx), true);
  if (!is_array($r)) return [null, 'eBay не відповів'];
  if (!empty($r['errors'])) return [null, 'eBay: ' . ($r['errors'][0]['message'] ?? 'помилка')];
  $out = [];
  foreach ($r['itemSummaries'] ?? [] as $it) {
    $ship = null; $shipType = '';
    foreach ($it['shippingOptions'] ?? [] as $so) {
      if (isset($so['shippingCost']['value'])) { $v = (float) $so['shippingCost']['value']; if ($ship === null || $v < $ship) $ship = $v; }
      $shipType = $so['shippingCostType'] ?? $shipType;
    }
    $out[] = [
      'id' => (string) ($it['legacyItemId'] ?? preg_replace('/^v1\|(\d+)\|.*$/', '$1', (string) ($it['itemId'] ?? ''))),
      'title' => (string) ($it['title'] ?? ''),
      'price' => (float) ($it['price']['value'] ?? 0),
      'ship' => $ship,
      'ship_type' => $shipType,
      'condition' => (string) ($it['condition'] ?? ''),
      'options' => implode('/', $it['buyingOptions'] ?? []),
      'url' => 'https://www.ebay.com/itm/' . (string) ($it['legacyItemId'] ?? ''),
      'listed' => (string) ($it['itemCreationDate'] ?? ''),
      'fb' => isset($it['seller']['feedbackPercentage']) ? (float) $it['seller']['feedbackPercentage'] : null,
      'img' => (string) ($it['image']['imageUrl'] ?? ''),
    ];
  }
  return [$out, null];
}

function tg_send($token, $chat, $text) {
  $ctx = stream_context_create(['http' => ['method' => 'POST', 'timeout' => 20, 'ignore_errors' => true,
    'header' => "Content-Type: application/json\r\n",
    'content' => json_encode(['chat_id' => $chat, 'text' => $text, 'parse_mode' => 'HTML', 'disable_web_page_preview' => false])]]);
  $r = json_decode((string) @file_get_contents("https://api.telegram.org/bot$token/sendMessage", false, $ctx), true);
  return !empty($r['ok']);
}
