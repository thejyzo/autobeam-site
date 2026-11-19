<?php
// AutoBeam: збереження ключів eBay і OLX на сервері (приховане введення, нічого не потрапляє в історію команд).
// Запуск:  php ~/autobeam_repo/tools/setup_api.php olx     — OLX Partner API (client_id + client_secret) і посилання для авторизації
//          php ~/autobeam_repo/tools/setup_api.php ebay    — eBay Trading API (App ID, Dev ID, Cert ID, User token) + перевірка
// Ключі зберігаються в ~/autobeam_secrets.php (права 600), поза сайтом.

if (PHP_SAPI !== 'cli') exit("Тільки з консолі\n");
$home = getenv('HOME') ?: dirname(__DIR__, 2);
$file = "$home/autobeam_secrets.php";
$cfg = is_file($file) ? (include $file) : [];
if (!is_array($cfg)) $cfg = [];

function ask($label, $hidden = true) {
  echo $label . ($hidden ? " (не відображається): " : ": ");
  if ($hidden) system('stty -echo');
  $v = trim((string) fgets(STDIN));
  if ($hidden) { system('stty echo'); echo "\n"; }
  return $v;
}
function save($file, $cfg) {
  file_put_contents($file, "<?php\nreturn " . var_export($cfg, true) . ";\n", LOCK_EX);
  chmod($file, 0600);
}

$what = $argv[1] ?? '';

if ($what === 'olx') {
  $id = ask('OLX client_id', false);
  $secret = ask('OLX client_secret');
  if (!preg_match('/^\d+$/', $id) || strlen($secret) < 10) exit("Не схоже на client_id / client_secret. Нічого не змінено.\n");
  $cfg['olx_client_id'] = $id;
  $cfg['olx_client_secret'] = $secret;
  $cfg['olx_state'] = bin2hex(random_bytes(16));
  save($file, $cfg);
  $url = 'https://www.olx.ua/oauth/authorize/?' . http_build_query([
    'client_id' => $id, 'response_type' => 'code', 'state' => $cfg['olx_state'], 'scope' => 'read write v2',
    'redirect_uri' => 'https://autobeam.com.ua/admin/olx_callback.php']);
  echo "Збережено. Тепер відкрийте в браузері (увійдіть в OLX-акаунт магазину і підтвердіть доступ):\n\n$url\n\n";
  exit;
}

if ($what === 'ebay') {
  $cfg['ebay_app_id'] = ask('eBay App ID (Client ID)', false);
  $cfg['ebay_dev_id'] = ask('eBay Dev ID', false);
  $cfg['ebay_cert_id'] = ask('eBay Cert ID (Client Secret)');
  // The token is ~800–2000 chars; when copied from the eBay page it often contains line breaks.
  // Read lines until an empty line and glue them together. Alternative: put the token into ~/ebay_token.txt and type: file
  echo "eBay User Token: вставте токен і натисніть Enter ДВІЧІ (порожній рядок = кінець).\n"
     . "Або збережіть токен у файл ~/ebay_token.txt (файловий менеджер хостингу) і введіть слово file.\n";
  system('stty -echo');
  $tok = '';
  while (($line = fgets(STDIN)) !== false) {
    $line = trim($line);
    if ($line === '' && $tok !== '') break;
    if ($line === 'file' && $tok === '') {
      $f = "$GLOBALS[home]/ebay_token.txt";
      $tok = is_file($f) ? (string) file_get_contents($f) : '';
      if (is_file($f)) { @unlink($f); }
      break;
    }
    $tok .= $line;
  }
  system('stty echo');
  $tok = preg_replace('/\s+/', '', $tok);
  echo "Отримано символів: " . strlen($tok) . "\n";
  $cfg['ebay_token'] = $tok;
  // Two valid formats: new compact Auth'n'Auth "v^1.1#i^1#...#t^..." (~100 chars, ends with "=" or "==") and legacy "AgAAAA**..." (~800+).
  $ok = (strpos($tok, 'v^1.1#') === 0 && strpos($tok, '#t^') !== false && strlen($tok) >= 60) || (strpos($tok, 'AgAAAA') === 0 && strlen($tok) >= 300);
  if (!$ok) exit("Не схоже на токен eBay (має починатися з v^1.1# або AgAAAA). Нічого не змінено.\n");
  save($file, $cfg);
  $xml = '<?xml version="1.0" encoding="utf-8"?><GetUserRequest xmlns="urn:ebay:apis:eBLBaseComponents">'
       . '<RequesterCredentials><eBayAuthToken>' . htmlspecialchars($cfg['ebay_token']) . '</eBayAuthToken></RequesterCredentials></GetUserRequest>';
  $ctx = stream_context_create(['http' => ['method' => 'POST', 'timeout' => 30, 'ignore_errors' => true, 'content' => $xml,
    'header' => "Content-Type: text/xml\r\nX-EBAY-API-COMPATIBILITY-LEVEL: 1193\r\nX-EBAY-API-CALL-NAME: GetUser\r\nX-EBAY-API-SITEID: 0\r\n"
              . "X-EBAY-API-APP-NAME: {$cfg['ebay_app_id']}\r\nX-EBAY-API-DEV-NAME: {$cfg['ebay_dev_id']}\r\nX-EBAY-API-CERT-NAME: {$cfg['ebay_cert_id']}\r\n"]]);
  $r = @file_get_contents('https://api.ebay.com/ws/api.dll', false, $ctx);
  if ($r && preg_match('#<Ack>(Success|Warning)</Ack>#', $r) && preg_match('#<UserID>([^<]+)</UserID>#', $r, $m)) {
    echo "Збережено. eBay відповів: акаунт {$m[1]}. Підключення працює.\n";
  } else {
    preg_match('#<LongMessage>([^<]+)</LongMessage>#', (string) $r, $e);
    echo "Ключі збережено, але eBay не прийняв запит: " . ($e[1] ?? 'немає відповіді') . "\nНапишіть мені цей текст (без ключів).\n";
  }
  exit;
}

echo "Вкажіть: olx або ebay\n";
