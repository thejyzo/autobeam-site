<?php
// AutoBeam: заявка "Замовити запчастину зі США".
// Секрети (email, Telegram-бот) лежать ПОЗА папкою сайту: ~/autobeam_secrets.php
//   <?php return ['email' => 'you@example.com', 'tg_token' => '123:ABC', 'tg_chat' => '123456'];
// Кожна заявка також пишеться в ~/requests.log (резервна копія).
header('Content-Type: application/json; charset=utf-8');
if ($_SERVER['REQUEST_METHOD'] !== 'POST') { http_response_code(405); echo '{"ok":false}'; exit; }

$in = json_decode(file_get_contents('php://input'), true) ?: $_POST;
$f = function ($k, $max = 500) use ($in) { return mb_substr(trim(strip_tags($in[$k] ?? '')), 0, $max); };
if ($f('website') !== '') { echo '{"ok":true}'; exit; } // honeypot

$d = [
  'time'    => date('Y-m-d H:i:s'),
  'part'    => $f('part', 1000),
  'car'     => $f('car', 300),
  'name'    => $f('name', 100),
  'phone'   => $f('phone', 40),
  'contact' => $f('contact', 20),
  'page'    => $f('page', 300),
  'ip'      => $_SERVER['REMOTE_ADDR'] ?? '',
];
$digits = preg_replace('/\D/', '', $d['phone']);
if ($d['part'] === '' || strlen($digits) < 9) { http_response_code(422); echo '{"ok":false,"error":"Вкажіть запчастину і телефон"}'; exit; }

$home = dirname(__DIR__, 3); // /home/<user>  (www -> autobeam.com.ua -> home)
@file_put_contents("$home/requests.log", json_encode($d, JSON_UNESCAPED_UNICODE) . "\n", FILE_APPEND | LOCK_EX);

// простий захист від флуду: не більше 5 заявок з IP за 10 хв
$rl = "$home/.req_rl_" . md5($d['ip']);
$hits = array_filter(explode(',', @file_get_contents($rl) ?: ''), function ($t) { return $t && $t > time() - 600; });
if (count($hits) >= 5) { echo '{"ok":true}'; exit; }
$hits[] = time(); @file_put_contents($rl, implode(',', $hits));

$text = "🔦 Заявка з сайту AutoBeam\n"
      . "Запчастина: {$d['part']}\n"
      . ($d['car'] ? "Авто / VIN: {$d['car']}\n" : '')
      . ($d['name'] ? "Імʼя: {$d['name']}\n" : '')
      . "Телефон: {$d['phone']}\n"
      . ($d['contact'] ? "Звʼязок: {$d['contact']}\n" : '')
      . ($d['page'] ? "Сторінка: {$d['page']}\n" : '')
      . "Час: {$d['time']}";

$cfg = @include "$home/autobeam_secrets.php";
$sent = false;
if (is_array($cfg)) {
  if (!empty($cfg['tg_token']) && !empty($cfg['tg_chat'])) {
    $ctx = stream_context_create(['http' => ['method' => 'POST', 'header' => "Content-Type: application/x-www-form-urlencoded\r\n",
      'content' => http_build_query(['chat_id' => $cfg['tg_chat'], 'text' => $text]), 'timeout' => 8]]);
    $sent = (bool) @file_get_contents("https://api.telegram.org/bot{$cfg['tg_token']}/sendMessage", false, $ctx) || $sent;
  }
  if (!empty($cfg['email'])) {
    $subj = '=?UTF-8?B?' . base64_encode('Заявка AutoBeam: ' . mb_substr($d['part'], 0, 60)) . '?=';
    $sent = @mail($cfg['email'], $subj, $text, "From: AutoBeam <noreply@autobeam.com.ua>\r\nContent-Type: text/plain; charset=utf-8") || $sent;
  }
}
echo json_encode(['ok' => true, 'delivered' => $sent]);
