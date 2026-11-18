<?php
// Задати / змінити пароль адмінки. Запуск у консолі хостингу:
//   php ~/autobeam_repo/server/admin_password.php
// Пароль не відображається на екрані і не зберігається у відкритому вигляді (лише хеш).
if (PHP_SAPI !== 'cli') exit;
$home = getenv('HOME') ?: dirname(__DIR__, 2);
function ask($q) { echo $q; system('stty -echo 2>/dev/null'); $v = rtrim(fgets(STDIN), "\r\n"); system('stty echo 2>/dev/null'); echo "\n"; return $v; }
$p1 = ask('Новий пароль адмінки (мін. 10 символів): ');
if (mb_strlen($p1) < 10) { echo "Закороткий пароль.\n"; exit(1); }
$p2 = ask('Ще раз: ');
if ($p1 !== $p2) { echo "Паролі не збігаються.\n"; exit(1); }
$f = "$home/autobeam_admin.php";
file_put_contents($f, "<?php return " . var_export(['hash' => password_hash($p1, PASSWORD_DEFAULT), 'set' => date('c')], true) . ";\n");
chmod($f, 0600);
// розлогінити всі старі сесії
foreach (glob("$home/autobeam_data/sessions/sess_*") ?: [] as $s) @unlink($s);
echo "Готово. Пароль збережено (хеш) у $f\n";
