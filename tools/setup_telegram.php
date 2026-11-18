<?php
// AutoBeam: підключення Telegram-бота для заявок з сайту.
// Запуск на сервері:  php ~/autobeam_repo/tools/setup_telegram.php
// Токен вводиться приховано (не видно на екрані, не потрапляє в історію команд).
// Результат: ~/autobeam_secrets.php (права 600) з tg_token і tg_chat + тестове повідомлення.

if (PHP_SAPI !== 'cli') { exit("Тільки з консолі\n"); }
$home = getenv('HOME') ?: dirname(__DIR__, 2);
$file = "$home/autobeam_secrets.php";

function tg($token, $method, $params = []) {
  $ctx = stream_context_create(['http' => ['method' => 'POST', 'timeout' => 15,
    'header' => "Content-Type: application/x-www-form-urlencoded\r\n",
    'content' => http_build_query($params), 'ignore_errors' => true]]);
  $r = @file_get_contents("https://api.telegram.org/bot$token/$method", false, $ctx);
  return $r ? json_decode($r, true) : null;
}

echo "Вставте токен бота від @BotFather і натисніть Enter (символи не відображаються): ";
system('stty -echo');
$token = trim(fgets(STDIN));
system('stty echo');
echo "\n";
if (!preg_match('/^\d+:[A-Za-z0-9_-]{30,}$/', $token)) { exit("Це не схоже на токен бота. Нічого не змінено.\n"); }

$me = tg($token, 'getMe');
if (empty($me['ok'])) { exit("Telegram не прийняв токен. Перевірте і запустіть ще раз.\n"); }
echo "Бот: @{$me['result']['username']}\n";

$up = tg($token, 'getUpdates', ['limit' => 100]);
$chats = [];
foreach (($up['result'] ?? []) as $u) {
  $m = $u['message'] ?? $u['my_chat_member'] ?? $u['channel_post'] ?? null;
  if (!$m || empty($m['chat']['id'])) continue;
  $c = $m['chat'];
  $chats[$c['id']] = ($c['type'] === 'private') ? trim(($c['first_name'] ?? '') . ' ' . ($c['last_name'] ?? '')) . ' (особистий чат)'
                                                : (($c['title'] ?? 'група') . ' (група)');
}
if (!$chats) { exit("Бот ще не бачить жодного чату. Відкрийте бота в Telegram, натисніть «Почати» і надішліть будь-яке повідомлення, потім запустіть скрипт ще раз.\n"); }

$ids = array_keys($chats);
foreach ($ids as $i => $id) echo ($i + 1) . ") {$chats[$id]}\n";
$pick = 0;
if (count($ids) > 1) {
  echo "Куди надсилати заявки? Номер: ";
  $pick = max(0, min(count($ids) - 1, (int) trim(fgets(STDIN)) - 1));
}
$chat = $ids[$pick];

$cfg = is_file($file) ? (@include $file) : [];
if (!is_array($cfg)) $cfg = [];
$cfg['tg_token'] = $token;
$cfg['tg_chat'] = (string) $chat;
file_put_contents($file, "<?php\nreturn " . var_export($cfg, true) . ";\n", LOCK_EX);
chmod($file, 0600);

$t = tg($token, 'sendMessage', ['chat_id' => $chat, 'text' => "✅ AutoBeam: бот підключено. Сюди приходитимуть заявки з сайту."]);
echo !empty($t['ok']) ? "Готово. Тестове повідомлення надіслано у «{$chats[$chat]}».\n" : "Збережено, але тестове повідомлення не пройшло — напишіть мені.\n";
