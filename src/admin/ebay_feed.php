<?php
// AutoBeam: eBay purchases for the Google Sheet «Входящие операции» (read by Apps Script once a day / on demand).
// Auth: header X-AB-Key must equal sheets_key in ~/autobeam_secrets.php (set by: php ~/autobeam_repo/tools/setup_api.php sheets).
// Returns only accounting fields (see tools/ebay_lib.php) — no seller data, no addresses.
header('Content-Type: application/json; charset=utf-8');
header('X-Robots-Tag: noindex, nofollow');
header('Cache-Control: no-store');
$home = dirname(__DIR__, 3);
$cfg = @include "$home/autobeam_secrets.php";
$key = (string) ($_SERVER['HTTP_X_AB_KEY'] ?? '');
if (!is_array($cfg) || empty($cfg['sheets_key']) || strlen($key) < 32 || !hash_equals((string) $cfg['sheets_key'], $key)) {
  http_response_code(403); echo '{"error":"forbidden"}'; exit;
}
if (empty($cfg['ebay_token'])) { http_response_code(500); echo '{"error":"no eBay token on server"}'; exit; }
require "$home/autobeam_repo/tools/ebay_lib.php";
[$rows, $err] = ebay_purchases($cfg, (int) ($_GET['days'] ?? 30));
if ($err) { http_response_code(502); echo json_encode(['error' => $err], JSON_UNESCAPED_UNICODE); exit; }
echo json_encode(['rows' => $rows], JSON_UNESCAPED_UNICODE);
