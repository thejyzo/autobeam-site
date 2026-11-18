<?php
// Перше наповнення бази з data/products.json (тільки якщо база порожня, або з --force).
//   php ~/autobeam_repo/server/import_products.php
if (PHP_SAPI !== 'cli') exit;
define('AB', 1);
$_SERVER['REQUEST_METHOD'] = 'CLI';
$home = getenv('HOME');
define('HOME_OVERRIDE', $home);
$data = "$home/autobeam_data"; @mkdir($data, 0700, true);
$pdo = new PDO("sqlite:$data/products.sqlite");
$pdo->exec('CREATE TABLE IF NOT EXISTS products (id TEXT PRIMARY KEY, data TEXT NOT NULL, updated INTEGER NOT NULL)');
$pdo->exec('CREATE TABLE IF NOT EXISTS history (n INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT, data TEXT, ts INTEGER, ip TEXT)');
$n = (int) $pdo->query('SELECT COUNT(*) FROM products')->fetchColumn();
if ($n && !in_array('--force', $argv)) { echo "База вже має $n карток — нічого не роблю (додайте --force, щоб перезаписати).\n"; exit; }
$repo = dirname(__DIR__);
$rows = json_decode(file_get_contents("$repo/data/products.json"), true);
$pdo->beginTransaction();
$pdo->exec('DELETE FROM products');
$st = $pdo->prepare('INSERT INTO products (id,data,updated) VALUES (?,?,?)');
foreach ($rows as $p) { $p['updated'] = date('c'); $st->execute([$p['id'], json_encode($p, JSON_UNESCAPED_UNICODE), time()]); }
$pdo->commit();
copy("$repo/data/data_keys.json", "$data/data_keys.json");
chmod("$data/products.sqlite", 0600);
echo "Імпортовано " . count($rows) . " карток.\n";
