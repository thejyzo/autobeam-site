<?php
// CSV для імпорту на OLX («Импорт объявлений»): той самий формат, що й експорт OLX.
// Рядок з id оновлює існуюче оголошення, без id — створює нове.
define('AB', 1);
require __DIR__ . '/_lib.php';
start_session();
if (empty($_SESSION['ok'])) { http_response_code(401); exit('auth'); }
$cat = preg_replace('/\D/', '', $_GET['cat'] ?? '2544');
$mode = $_GET['mode'] ?? 'active';            // active = лише картки з активним оголошенням; all = + в наявності без оголошення
$KCAT = ['Фара' => '2544', 'ДХО' => '2544', 'ДХВ' => '2544', 'Скло фари' => '2544', 'Ліхтар' => '2545', 'Повторювач' => '2545', 'Корпус фари' => '2550'];
$site = 'https://autobeam.com.ua';
$stock = stock_map();
header('Content-Type: text/csv; charset=utf-8');
header('Content-Disposition: attachment; filename="olx_' . $cat . '_' . date('Ymd_Hi') . '.csv"');
$out = fopen('php://output', 'w');
fputcsv($out, ['id','title','description','external_id','location_city','location_district','images','price_value','price_currency','state','part_num','parts_type','car_brand','part_number','compatibility_list']);
foreach (all_products() as $p) {
  if (!empty($p['archived']) || empty($p['show'])) continue;
  $pc = $p['olx_category'] ?: ($KCAT[$p['kind'] ?? ''] ?? '');
  if ($pc !== $cat) continue;
  $s = $stock[$p['key'] ?? ''] ?? null;
  $avail = $s ? ($s[0] + $s[1] + $s[2] > 0) : !empty($p['olx_active']);
  if ($mode === 'active' && !(!empty($p['olx_id']) && !empty($p['olx_active']))) continue;
  if ($mode === 'all' && !( (!empty($p['olx_id']) && !empty($p['olx_active'])) || ($avail && empty($p['olx_id'])) )) continue;
  if (empty($p['title']) || empty($p['photos'])) continue;
  $img = implode('|', array_map(function ($u) use ($site) { return strpos($u, 'http') === 0 ? $u : $site . $u; }, array_slice($p['photos'], 0, 8)));
  $pns = trim(implode(' ', array_merge([$p['pn'] ?? ''], $p['pn_alt'] ?? [])));
  fputcsv($out, [$p['olx_id'] ?? '', $p['title'], $p['description'] ?? '', $p['id'], '280', '67', $img, $p['price'], $p['currency'] ?: 'USD',
    ($p['state'] ?? '') === 'Нове' ? 'new' : 'used', $pns, ($p['original'] ?? '') === 'Аналог' ? 'analog' : 'original',
    $p['olx_brand'] ?? strtolower($p['brand'] ?? ''), $pns, $p['olx_compat'] ?? '']);
}
