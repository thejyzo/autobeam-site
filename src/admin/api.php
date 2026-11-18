<?php
define('AB', 1);
require __DIR__ . '/_lib.php';
start_session();

if (empty($_SESSION['ok'])) json_out(['ok' => false, 'error' => 'auth'], 401);
if ($_SERVER['REQUEST_METHOD'] !== 'POST' || !hash_equals($_SESSION['csrf'], $_SERVER['HTTP_X_CSRF'] ?? '')) json_out(['ok' => false, 'error' => 'csrf'], 403);

$act = $_GET['a'] ?? '';
$in = json_decode(file_get_contents('php://input'), true) ?: [];

// fields that the editor may write (everything else is ignored)
const FIELDS = ['key','kind','brand','model','body','years','side','trim','pn','pn_alt','title','description','short','price','currency',
  'state','original','photos','olx_id','olx_active','olx_dupes','olx_category','olx_brand','olx_compat','avto_maker','avto_code','show','status_manual','note'];

function clean($p) {
  $o = [];
  foreach (FIELDS as $f) {
    if (!array_key_exists($f, $p)) continue;
    $v = $p[$f];
    if (in_array($f, ['pn_alt', 'photos', 'olx_dupes'])) {
      $v = array_values(array_filter(array_map(function ($x) { return trim((string) $x); }, (array) $v), 'strlen'));
    } elseif (in_array($f, ['show', 'olx_active'])) {
      $v = (bool) $v;
    } elseif ($f === 'price') {
      $v = ($v === '' || $v === null) ? '' : (int) round((float) $v);
    } else {
      $v = mb_substr(trim((string) $v), 0, $f === 'description' ? 9000 : 2000);
    }
    $o[$f] = $v;
  }
  return $o;
}

switch ($act) {
  case 'list':
    $stock = stock_map();
    $rows = [];
    foreach (all_products() as $p) {
      $s = $stock[$p['key'] ?? ''] ?? null;
      $rows[] = [
        'id' => $p['id'], 'key' => $p['key'] ?? '', 'kind' => $p['kind'] ?? '', 'brand' => $p['brand'] ?? '', 'model' => $p['model'] ?? '',
        'years' => $p['years'] ?? '', 'side' => $p['side'] ?? '', 'trim' => $p['trim'] ?? '', 'title' => $p['title'] ?? '',
        'pn' => $p['pn'] ?? '', 'pns' => implode(' ', array_merge($p['pn_alt'] ?? [], [$p['avto_code'] ?? ''])), 'price' => $p['price'] ?? '', 'currency' => $p['currency'] ?? 'USD',
        'photo' => ($p['photos'][0] ?? ''), 'nphotos' => count($p['photos'] ?? []), 'hasdesc' => !empty($p['description']),
        'show' => !empty($p['show']), 'olx' => $p['olx_id'] ?? '', 'olx_active' => !empty($p['olx_active']), 'note' => $p['note'] ?? '',
        'status_manual' => $p['status_manual'] ?? '', 'archived' => !empty($p['archived']), 'stock' => $s,
      ];
    }
    json_out(['ok' => true, 'rows' => $rows, 'stock_updated' => is_file(DATA . '/stock.json') ? date('d.m H:i', filemtime(DATA . '/stock.json')) : null,
              'dirty' => is_file(DATA . '/dirty')]);

  case 'get':
    $p = get_product($in['id'] ?? '');
    $p ? json_out(['ok' => true, 'p' => $p, 'stock' => stock_map()[$p['key'] ?? ''] ?? null]) : json_out(['ok' => false, 'error' => 'not found'], 404);

  case 'save':
    $id = $in['p']['id'] ?? '';
    $p = get_product($id);
    if (!$p) json_out(['ok' => false, 'error' => 'not found'], 404);
    $p = array_merge($p, clean($in['p']));
    json_out(['ok' => true, 'p' => put_product($p)]);

  case 'create':
    $src = !empty($in['copy']) ? get_product($in['copy']) : null;
    $p = $src ? $src : ['kind' => 'Фара', 'currency' => 'USD', 'state' => 'Вживане', 'original' => 'Оригінал', 'photos' => [], 'pn_alt' => [], 'show' => true];
    if (!$src && !empty($in['p']) && is_array($in['p'])) $p = array_merge($p, clean($in['p']));   // a draft saved for the first time
    $p['id'] = next_id();
    if ($src) { $p['olx_id'] = ''; $p['olx_active'] = false; $p['olx_dupes'] = []; $p['note'] = 'копія ' . $src['id']; }
    json_out(['ok' => true, 'p' => put_product($p)]);

  case 'archive':
    $p = get_product($in['id'] ?? '');
    if (!$p) json_out(['ok' => false], 404);
    $p['archived'] = !empty($in['on']); if ($p['archived']) $p['show'] = false;
    json_out(['ok' => true, 'p' => put_product($p)]);

  case 'keys':                        // positions (DATA names) for the picker
    $f = DATA . '/data_keys.json';
    json_out(['ok' => true, 'keys' => is_file($f) ? json_decode(file_get_contents($f), true) : []]);

  case 'upload':                      // multipart: id + files[]
    $id = preg_replace('/[^A-Z0-9-]/', '', $_POST['id'] ?? '');
    if (!$id || !get_product($id)) json_out(['ok' => false, 'error' => 'id'], 400);
    $dir = MEDIA . '/' . $id; if (!is_dir($dir)) mkdir($dir, 0755, true);
    $urls = [];
    foreach ($_FILES['files']['tmp_name'] ?? [] as $i => $tmp) {
      if (!is_uploaded_file($tmp) || $_FILES['files']['size'][$i] > 25 * 1024 * 1024) continue;
      $info = @getimagesize($tmp);
      if (!$info || !in_array($info[2], [IMAGETYPE_JPEG, IMAGETYPE_PNG, IMAGETYPE_WEBP])) continue;
      $im = $info[2] === IMAGETYPE_PNG ? imagecreatefrompng($tmp) : ($info[2] === IMAGETYPE_WEBP ? imagecreatefromwebp($tmp) : imagecreatefromjpeg($tmp));
      if (!$im) continue;
      if ($info[2] === IMAGETYPE_JPEG && function_exists('exif_read_data')) {          // phone photos: respect orientation
        $o = @exif_read_data($tmp)['Orientation'] ?? 1;
        if ($o == 3) $im = imagerotate($im, 180, 0); elseif ($o == 6) $im = imagerotate($im, -90, 0); elseif ($o == 8) $im = imagerotate($im, 90, 0);
      }
      $w = imagesx($im); $h = imagesy($im); $k = min(1, 1600 / max($w, $h));
      $out = imagecreatetruecolor((int) ($w * $k), (int) ($h * $k));
      imagecopyresampled($out, $im, 0, 0, 0, 0, (int) ($w * $k), (int) ($h * $k), $w, $h);
      $name = bin2hex(random_bytes(6)) . '.jpg';
      imagejpeg($out, "$dir/$name", 84);
      $urls[] = "/media/$id/$name";
    }
    json_out(['ok' => true, 'urls' => $urls]);

  case 'history':
    $s = db()->prepare('SELECT ts, ip FROM history WHERE id=? ORDER BY n DESC LIMIT 20'); $s->execute([$in['id'] ?? '']);
    json_out(['ok' => true, 'h' => array_map(function ($r) { return ['ts' => date('d.m.Y H:i', $r['ts']), 'ip' => $r['ip']]; }, $s->fetchAll(PDO::FETCH_ASSOC))]);

  case 'publish':
    @touch(DATA . '/publish');
    json_out(['ok' => true]);

  case 'logout':
    $_SESSION = []; session_destroy();
    json_out(['ok' => true]);
}
json_out(['ok' => false, 'error' => 'unknown action'], 400);
