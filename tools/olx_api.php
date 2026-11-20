<?php
// AutoBeam: OLX Partner API — спільні функції + перевірка (лише читання).
// Запуск:  php ~/autobeam_repo/tools/olx_api.php check [olx_id]
//   — оновлює токен, показує акаунт, поля категорії «Фари» (2544) і одне наше оголошення як зразок.
//   Звіт також пишеться в ~/autobeam_data/olx_check.json. Токени не друкуються.

$home = getenv('HOME') ?: dirname(__DIR__, 2);
const OLX = 'https://www.olx.ua';

function olx_cfg() { global $home; $c = @include "$home/autobeam_secrets.php"; return is_array($c) ? $c : []; }

function olx_http($method, $path, $token = null, $body = null) {
  $h = "Version: 2.0\r\nAccept: application/json\r\nUser-Agent: AutoBeamSync/1.0 (+https://autobeam.com.ua)\r\n";
  if ($token) $h .= "Authorization: Bearer $token\r\n";
  if ($body !== null) $h .= "Content-Type: application/json\r\n";
  $ctx = stream_context_create(['http' => ['method' => $method, 'timeout' => 30, 'ignore_errors' => true, 'header' => $h,
    'content' => $body === null ? '' : json_encode($body, JSON_UNESCAPED_UNICODE)]]);
  $r = @file_get_contents(OLX . $path, false, $ctx);
  $code = 0;
  foreach ($http_response_header ?? [] as $l) if (preg_match('#^HTTP/\S+ (\d+)#', $l, $m)) $code = (int) $m[1];
  return [$code, $r === false ? null : json_decode($r, true), (string) $r];
}

// Повертає дійсний access_token (оновлює за refresh_token, якщо залишилось < 5 хв).
function olx_token() {
  global $home;
  $f = "$home/autobeam_data/olx_tokens.json";
  $t = is_file($f) ? json_decode((string) file_get_contents($f), true) : null;
  if (empty($t['access_token'])) throw new Exception('Немає токенів OLX. Запустіть: php ~/autobeam_repo/tools/setup_api.php olx');
  $exp = ($t['obtained_at'] ?? 0) + ($t['expires_in'] ?? 0);
  if ($exp - time() > 300) return $t['access_token'];
  $cfg = olx_cfg();
  [$code, $j, $raw] = olx_http('POST', '/api/open/oauth/token', null, ['grant_type' => 'refresh_token',
    'client_id' => (int) ($cfg['olx_client_id'] ?? 0), 'client_secret' => $cfg['olx_client_secret'] ?? '',
    'refresh_token' => $t['refresh_token'] ?? '']);
  if (empty($j['access_token'])) {
    throw new Exception("OLX не оновив токен (HTTP $code): " . substr(preg_replace('/"(access|refresh)_token"\s*:\s*"[^"]+"/', '"$1_token":"…"', $raw), 0, 300)
      . "\nПотрібна повторна авторизація: php ~/autobeam_repo/tools/setup_api.php olx");
  }
  $j['obtained_at'] = time();
  if (empty($j['refresh_token'])) $j['refresh_token'] = $t['refresh_token'];
  file_put_contents($f, json_encode($j), LOCK_EX); @chmod($f, 0600);
  return $j['access_token'];
}

if (PHP_SAPI !== 'cli' || realpath($argv[0] ?? '') !== __FILE__) return;   // підключено як бібліотеку

if (($argv[1] ?? '') !== 'check') exit("Використання: php olx_api.php check [olx_id]\n");
try { $tok = olx_token(); } catch (Exception $e) { exit('❌ ' . $e->getMessage() . "\n"); }
echo "✅ Токен OLX дійсний\n";
$rep = [];

[$c, $me] = olx_http('GET', '/api/partner/users/me', $tok);
$rep['me'] = ['http' => $c, 'id' => $me['data']['id'] ?? null, 'name' => $me['data']['name'] ?? null];
echo "Акаунт: " . ($me['data']['name'] ?? '?') . " (HTTP $c)\n";

[$c, $attr] = olx_http('GET', '/api/partner/categories/2544/attributes', $tok);
$rep['attributes_2544'] = $attr['data'] ?? $attr;
echo "\nПоля категорії 2544 (HTTP $c):\n";
foreach ($attr['data'] ?? [] as $a) {
  $v = $a['validation'] ?? [];
  $vals = array_slice(array_map(function ($x) { return $x['code'] ?? ''; }, $a['values'] ?? []), 0, 8);
  echo sprintf("  %-22s %-28s %s%s\n", $a['code'] ?? '', $a['label'] ?? '', !empty($v['required']) ? 'ОБОВʼЯЗКОВЕ ' : '',
    $vals ? '[' . implode(', ', $vals) . (count($a['values']) > 8 ? ', …' : '') . ']' : '');
}

[$c, $lim] = olx_http('GET', '/api/partner/users/me/account-balance', $tok);
$rep['balance'] = $lim['data'] ?? $lim;
[$c, $pk] = olx_http('GET', '/api/partner/users/me/packets', $tok);
$rep['packets'] = $pk['data'] ?? $pk;
echo "\nПакети/баланс записано у звіт (HTTP $c)\n";

$id = $argv[2] ?? '';
if ($id === '') {
  [$c, $ads] = olx_http('GET', '/api/partner/adverts?category_ids=2544&limit=1', $tok);
  $id = $ads['data'][0]['id'] ?? '';
}
if ($id !== '') {
  [$c, $ad] = olx_http('GET', '/api/partner/adverts/' . rawurlencode($id), $tok);
  $d = $ad['data'] ?? [];
  unset($d['contact']);   // без телефону/імені у звіті
  $rep['sample_advert'] = $d;
  echo "Зразок оголошення $id (HTTP $c): " . ($d['title'] ?? '?') . "\n  location: " . json_encode($d['location'] ?? null)
    . "\n  attributes: " . json_encode($d['attributes'] ?? null, JSON_UNESCAPED_UNICODE) . "\n";
}

$out = "$home/autobeam_data/olx_check.json";
file_put_contents($out, json_encode($rep, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT));
echo "\nПовний звіт: $out\n";
