<?php
// OLX Partner API: OAuth callback. OLX redirects here with ?code=...&state=... after the shop owner approves access.
// The code is exchanged for access/refresh tokens, which are stored outside the web root (~/autobeam_data/olx_tokens.json, 600).
header('Content-Type: text/html; charset=utf-8');
header('X-Robots-Tag: noindex, nofollow');
header('Referrer-Policy: no-referrer');
$home = dirname(__DIR__, 3);
$cfg = @include "$home/autobeam_secrets.php";
function page($title, $text) {
  echo '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>AutoBeam · OLX</title>'
     . '<body style="font:16px system-ui;background:#0b0b0d;color:#eee;display:flex;min-height:90vh;align-items:center;justify-content:center">'
     . '<div style="max-width:520px;padding:24px;border:1px solid #333;border-radius:14px"><h2 style="margin-top:0">' . htmlspecialchars($title) . '</h2><p>' . htmlspecialchars($text) . '</p></div>';
  exit;
}
if (!is_array($cfg) || empty($cfg['olx_client_id']) || empty($cfg['olx_client_secret'])) page('Не налаштовано', 'Спершу запустіть на сервері: php ~/autobeam_repo/tools/setup_api.php olx');
$code = $_GET['code'] ?? ''; $state = $_GET['state'] ?? '';
if ($code === '' || empty($cfg['olx_state']) || !hash_equals($cfg['olx_state'], $state)) page('Помилка', 'Неправильний або застарілий запит. Згенеруйте нове посилання командою setup_api.php olx.');

$body = json_encode(['grant_type' => 'authorization_code', 'client_id' => (int) $cfg['olx_client_id'], 'client_secret' => $cfg['olx_client_secret'],
  'code' => $code, 'scope' => 'v2 read write', 'redirect_uri' => 'https://autobeam.com.ua/admin/olx_callback.php']);
$ctx = stream_context_create(['http' => ['method' => 'POST', 'timeout' => 20, 'ignore_errors' => true, 'content' => $body,
  'header' => "Content-Type: application/json\r\nVersion: 2.0\r\n"]]);
$r = @file_get_contents('https://www.olx.ua/api/open/oauth/token', false, $ctx);
$t = $r ? json_decode($r, true) : null;
if (empty($t['access_token'])) page('OLX не видав токен', 'Відповідь: ' . substr(preg_replace('/"(access|refresh)_token"\s*:\s*"[^"]+"/', '"$1_token":"…"', (string) $r), 0, 300));

$t['obtained_at'] = time();
$f = "$home/autobeam_data/olx_tokens.json";
file_put_contents($f, json_encode($t), LOCK_EX); @chmod($f, 0600);
// one-time state: forget it so the link cannot be reused
$cfg['olx_state'] = '';
file_put_contents("$home/autobeam_secrets.php", "<?php\nreturn " . var_export($cfg, true) . ";\n", LOCK_EX); @chmod("$home/autobeam_secrets.php", 0600);

// quick check: who are we
$ctx = stream_context_create(['http' => ['method' => 'GET', 'timeout' => 20, 'ignore_errors' => true,
  'header' => "Authorization: Bearer {$t['access_token']}\r\nVersion: 2.0\r\n"]]);
$me = json_decode((string) @file_get_contents('https://www.olx.ua/api/partner/users/me', false, $ctx), true);
$name = $me['data']['name'] ?? ($me['data']['email'] ?? '');
page('OLX підключено ✅', 'Доступ до акаунта ' . ($name ?: 'OLX') . ' отримано. Можна закрити цю сторінку.');
