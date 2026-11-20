<?php
// AutoBeam: публікація / оновлення картки на OLX через Partner API.
// Запуск:  php ~/autobeam_repo/tools/olx_publish.php AB-0148           — лише показати, що піде на OLX (нічого не надсилає)
//          php ~/autobeam_repo/tools/olx_publish.php AB-0148 --yes     — надіслати
//          php ~/autobeam_repo/tools/olx_publish.php "Mazda 3 BP 19-23 LED RH"  — картку можна вказати позицією DATA (key)
// Є olx_id → оновлює це оголошення; немає → створює нове і записує olx_id у картку.
// Платне розміщення скрипт НЕ оплачує: якщо OLX вимагає оплату, оголошення лишається в кабінеті «очікує оплати».

require __DIR__ . '/olx_api.php';
if (PHP_SAPI !== 'cli') exit;

$arg = $argv[1] ?? '';
$yes = in_array('--yes', $argv, true);
if ($arg === '') exit("Вкажіть картку: php olx_publish.php AB-xxxx [--yes]\n");

$SITE = 'https://autobeam.com.ua';
$KCAT = ['Фара' => '2544', 'ДХО' => '2544', 'ДХВ' => '2544', 'Скло фари' => '2544', 'Ліхтар' => '2545', 'Повторювач' => '2545', 'Корпус фари' => '2550'];

$pdo = new PDO('sqlite:' . "$home/autobeam_data/products.sqlite");
$pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
$cards = [];
foreach ($pdo->query('SELECT data FROM products') as $r) { $p = json_decode($r['data'], true); if ($p) $cards[] = $p; }
$m = array_values(array_filter($cards, function ($p) use ($arg) {
  return strcasecmp($p['id'] ?? '', $arg) === 0 || trim($p['key'] ?? '') === trim($arg);
}));
if (preg_match('/^AB-/i', $arg) === 0) $m = array_values(array_filter($m, function ($p) { return !empty($p['photos']) && empty($p['archived']); }));
if (count($m) !== 1) exit(count($m) ? "Під «{$arg}» кілька карток: " . implode(', ', array_column($m, 'id')) . " — вкажіть AB-номер.\n" : "Картку «{$arg}» не знайдено.\n");
$p = $m[0];
$id = $p['id'];

// ---- перевірки картки
$err = [];
$title = trim($p['title'] ?? '');
$desc = trim($p['description'] ?? '');
$cat = $p['olx_category'] ?: ($KCAT[$p['kind'] ?? ''] ?? '');
if ($title === '' || mb_strlen($title) > 70) $err[] = 'назва порожня або довша за 70 символів (' . mb_strlen($title) . ')';
if (mb_strlen($desc) < 80) $err[] = 'опис коротший за 80 символів';
if (mb_strlen($desc) > 9000) $err[] = 'опис довший за 9000 символів';
if (empty($p['photos'])) $err[] = 'немає фото';
if (empty($p['price'])) $err[] = 'немає ціни';
if ($cat === '') $err[] = 'невідома категорія OLX';
if (!empty($p['archived'])) $err[] = 'картка в архіві';
if ($err) exit("❌ $id: " . implode('; ', $err) . "\n");

$imgs = array_map(function ($u) use ($SITE) { return ['url' => strpos($u, 'http') === 0 ? $u : $SITE . $u]; }, array_slice($p['photos'], 0, 40));
$pns = trim(implode(' ', array_unique(array_filter(array_merge([$p['pn'] ?? ''], $p['pn_alt'] ?? [])))));
$compat = array_values(array_filter(array_map('trim', preg_split('/[|,;\s]+/', (string) ($p['olx_compat'] ?? '')))));
$brand = $p['olx_brand'] ?: strtolower(str_replace([' ', '-'], '_', $p['brand'] ?? ''));

$attrs = [['code' => 'state', 'value' => ($p['state'] ?? '') === 'Нове' ? 'new' : 'used'],
          ['code' => 'parts_type', 'value' => ($p['original'] ?? '') === 'Аналог' ? 'analog' : 'original']];
if ($brand !== '') $attrs[] = ['code' => 'car_brand', 'values' => [$brand]];
if ($pns !== '') { $attrs[] = ['code' => 'part_num', 'value' => $pns]; $attrs[] = ['code' => 'part_number', 'value' => $pns]; }
if ($compat) { $attrs[] = ['code' => 'compatibility_list_source', 'value' => 'auto']; $attrs[] = ['code' => 'compatibility_list', 'values' => $compat]; }

try { $tok = olx_token(); } catch (Exception $e) { exit('❌ ' . $e->getMessage() . "\n"); }

// контакт, тип продавця і локацію беремо з наших же оголошень (як у кабінеті), щоб не вигадувати
[$c, $list] = olx_http('GET', '/api/partner/adverts?category_ids=' . $cat . '&limit=5', $tok);
$ref = null;
foreach ($list['data'] ?? [] as $a) { if (!empty($a['contact']['name'])) { $ref = $a; break; } }
if (!$ref && !empty($list['data'][0]['id'])) { [, $one] = olx_http('GET', '/api/partner/adverts/' . $list['data'][0]['id'], $tok); $ref = $one['data'] ?? null; }
if (!$ref) exit("❌ Не знайшов жодного вашого оголошення в категорії $cat як зразок контакту (HTTP $c).\n");
$loc = $ref['location'] ?? ['city_id' => 280, 'district_id' => 67];

$body = [
  'title' => $title,
  'description' => $desc,
  'category_id' => (int) $cat,
  'advertiser_type' => $ref['advertiser_type'] ?? 'business',
  'external_id' => $id,
  'contact' => array_filter(['name' => $ref['contact']['name'] ?? 'AutoBeam', 'phone' => $ref['contact']['phone'] ?? null]),
  'location' => array_filter(['city_id' => $loc['city_id'] ?? 280, 'district_id' => $loc['district_id'] ?? null]),
  'images' => $imgs,
  'price' => ['value' => (float) $p['price'], 'currency' => $p['currency'] ?: 'USD', 'negotiable' => false, 'trade' => false],
  'attributes' => $attrs,
];

$olx = trim((string) ($p['olx_id'] ?? ''));
if ($olx !== '') {
  [$c, $cur] = olx_http('GET', '/api/partner/adverts/' . rawurlencode($olx), $tok);
  if ($c === 404) { echo "⚠️ Оголошення $olx на OLX не знайдено — буде створено нове.\n"; $olx = ''; }
  elseif ($c !== 200) exit("❌ Не вдалося прочитати оголошення $olx (HTTP $c).\n");
}

echo ($olx ? "ОНОВИТИ оголошення $olx" : 'СТВОРИТИ нове оголошення') . " для $id ({$p['key']})\n"
   . "  Назва: $title\n  Ціна: {$p['price']} " . ($p['currency'] ?: 'USD') . " · категорія $cat · фото " . count($imgs)
   . " · опис " . mb_strlen($desc) . " симв.\n  Поля: " . json_encode($attrs, JSON_UNESCAPED_UNICODE) . "\n"
   . "  Контакт/локація — як у оголошенні {$ref['id']}\n";
if (!$yes) exit("\nНічого не надіслано. Щоб опублікувати, додайте --yes\n");

// наше оголошення з цим external_id вже є на OLX (напр. попередня спроба створила його, хоч і повернула помилку)?
function find_ours($tok, $cat, $id) {
  for ($off = 0; $off < 2000; $off += 100) {
    [$c, $l] = olx_http('GET', "/api/partner/adverts?category_ids=$cat&limit=100&offset=$off", $tok);
    foreach ($l['data'] ?? [] as $a) if (($a['external_id'] ?? '') === $id) return $a;
    if (count($l['data'] ?? []) < 100) break;
  }
  return null;
}
function short_err($raw) {
  $j = json_decode($raw, true);
  if ($j) return json_encode($j['error'] ?? $j, JSON_UNESCAPED_UNICODE);
  return preg_match('#<title>(.*?)</title>#s', $raw, $m) ? 'сторінка «' . trim($m[1]) . '»' : mb_substr(trim(strip_tags($raw)), 0, 300);
}
@file_put_contents("$home/autobeam_data/olx_last_request.json", json_encode($body, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT));

if ($olx === '' && ($ex = find_ours($tok, $cat, $id))) {
  $olx = (string) $ex['id'];
  echo "ℹ️ На OLX уже є оголошення $olx для $id — оновлюю його, а не створюю дубль.\n";
}
$send = function ($body) use ($olx, $tok) {
  return $olx ? olx_http('PUT', '/api/partner/adverts/' . rawurlencode($olx), $tok, $body)
              : olx_http('POST', '/api/partner/adverts', $tok, $body);
};
[$c, $res, $raw] = $send($body);
if (($c < 200 || $c >= 300) && $olx === '' && ($ex = find_ours($tok, $cat, $id))) {   // помилка, але оголошення створилось
  $c = 200; $res = ['data' => $ex];
}
if ($c >= 500 && count($body['images']) > 8) {
  echo "⚠️ OLX: помилка HTTP $c з " . count($body['images']) . " фото. Пробую з 8 фото…\n";
  $body['images'] = array_slice($body['images'], 0, 8);
  [$c, $res, $raw] = $send($body);
  if ($c >= 200 && $c < 300) echo "✅ З 8 фото пройшло — отже API приймає максимум 8 (решту можна додати в кабінеті OLX).\n";
}
if ($c < 200 || $c >= 300 || empty($res['data']['id'])) {
  exit("❌ OLX відхилив (HTTP $c): " . short_err((string) $raw) . "\nЗапит збережено: ~/autobeam_data/olx_last_request.json\n");
}

$d = $res['data'];
$status = $d['status'] ?? '?';
$p['olx_id'] = (string) $d['id'];
$p['olx_active'] = $status === 'active';
$p['olx_category'] = $cat;
$p['updated'] = date('c');
$old = $pdo->prepare('SELECT data FROM products WHERE id=?'); $old->execute([$id]);
$pdo->prepare('INSERT INTO history (id,data,ts,ip) VALUES (?,?,?,?)')->execute([$id, $old->fetchColumn(), time(), 'olx_publish']);
$pdo->prepare('INSERT OR REPLACE INTO products (id,data,updated) VALUES (?,?,?)')->execute([$id, json_encode($p, JSON_UNESCAPED_UNICODE), time()]);
@touch("$home/autobeam_data/dirty");

$st = ['active' => 'активне ✅', 'new' => 'на модерації ⏳', 'unpaid' => 'ОЧІКУЄ ОПЛАТИ 💳 (оплатіть у кабінеті OLX)', 'need_pay' => 'ОЧІКУЄ ОПЛАТИ 💳 (оплатіть у кабінеті OLX)',
       'limited' => 'ліміт вичерпано 💳 (оплатіть у кабінеті OLX)', 'blocked' => 'заблоковане ❌', 'disabled' => 'неактивне', 'removed_by_user' => 'видалене'][$status] ?? $status;
echo "\n" . ($olx ? 'Оновлено' : 'Створено') . ": OLX {$d['id']} — статус: $st\n" . (!empty($d['url']) ? "  {$d['url']}\n" : '')
   . "OLX ID записано в картку $id.\n";
