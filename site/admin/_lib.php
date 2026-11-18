<?php
// AutoBeam admin — shared code. Not callable directly.
defined('AB') or exit;

define('HOME', dirname(__DIR__, 3));                 // /home/autobeam
define('DATA', HOME . '/autobeam_data');             // outside the web root
define('WWW', dirname(__DIR__));                     // .../www
define('MEDIA', WWW . '/media');

header('X-Frame-Options: DENY');
header('X-Content-Type-Options: nosniff');
header('X-Robots-Tag: noindex, nofollow');
header('Referrer-Policy: same-origin');
header("Content-Security-Policy: default-src 'self'; img-src 'self' https: data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'");

if (!is_dir(DATA)) { @mkdir(DATA, 0700, true); }
if (!is_dir(DATA . '/sessions')) { @mkdir(DATA . '/sessions', 0700, true); }

function cfg_admin() {
  $f = HOME . '/autobeam_admin.php';
  return is_file($f) ? (include $f) : [];
}

function start_session() {
  session_save_path(DATA . '/sessions');
  session_name('ab_admin');
  ini_set('session.gc_maxlifetime', 14 * 86400);
  session_set_cookie_params(['lifetime' => 14 * 86400, 'path' => '/admin/', 'secure' => !preg_match('/^(localhost|127\.0\.0\.1)(:\d+)?$/', $_SERVER['HTTP_HOST'] ?? ''), 'httponly' => true, 'samesite' => 'Strict']);
  session_start();
  if (!empty($_SESSION['ok']) && (time() - ($_SESSION['seen'] ?? 0) > 14 * 86400)) { $_SESSION = []; }
  $_SESSION['seen'] = time();
  if (empty($_SESSION['csrf'])) $_SESSION['csrf'] = bin2hex(random_bytes(24));
}

function client_ip() { return $_SERVER['HTTP_X_REAL_IP'] ?? $_SERVER['HTTP_X_FORWARDED_FOR'] ?? $_SERVER['REMOTE_ADDR'] ?? '?'; }

// login throttling: 5 failures / 15 min per IP, 20 / hour overall
function throttled() {
  $f = DATA . '/login_fail.json';
  $d = is_file($f) ? (json_decode(file_get_contents($f), true) ?: []) : [];
  $now = time(); $ip = client_ip();
  $d = array_values(array_filter($d, function ($x) use ($now) { return $x['t'] > $now - 3600; }));
  $mine = array_filter($d, function ($x) use ($now, $ip) { return $x['ip'] === $ip && $x['t'] > $now - 900; });
  return count($mine) >= 5 || count($d) >= 20;
}
function note_fail() {
  $f = DATA . '/login_fail.json';
  $d = is_file($f) ? (json_decode(file_get_contents($f), true) ?: []) : [];
  $d[] = ['ip' => client_ip(), 't' => time()];
  file_put_contents($f, json_encode(array_slice($d, -200)), LOCK_EX);
}

function db() {
  static $pdo;
  if ($pdo) return $pdo;
  $pdo = new PDO('sqlite:' . DATA . '/products.sqlite');
  $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
  $pdo->exec('PRAGMA journal_mode=WAL');
  $pdo->exec('CREATE TABLE IF NOT EXISTS products (id TEXT PRIMARY KEY, data TEXT NOT NULL, updated INTEGER NOT NULL)');
  $pdo->exec('CREATE TABLE IF NOT EXISTS history (n INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT, data TEXT, ts INTEGER, ip TEXT)');
  return $pdo;
}

function all_products() {
  $out = [];
  foreach (db()->query('SELECT data FROM products ORDER BY id') as $r) $out[] = json_decode($r['data'], true);
  return $out;
}
function get_product($id) {
  $s = db()->prepare('SELECT data FROM products WHERE id=?'); $s->execute([$id]);
  $r = $s->fetchColumn();
  return $r ? json_decode($r, true) : null;
}
function put_product($p) {
  $old = get_product($p['id']);
  if ($old) db()->prepare('INSERT INTO history (id,data,ts,ip) VALUES (?,?,?,?)')->execute([$p['id'], json_encode($old, JSON_UNESCAPED_UNICODE), time(), client_ip()]);
  $p['updated'] = date('c');
  db()->prepare('INSERT OR REPLACE INTO products (id,data,updated) VALUES (?,?,?)')->execute([$p['id'], json_encode($p, JSON_UNESCAPED_UNICODE), time()]);
  @touch(DATA . '/dirty');                       // site rebuild is pending
  return $p;
}
function next_id() {
  $max = 0;
  foreach (db()->query('SELECT id FROM products') as $r) { $n = (int) substr($r['id'], 3); if ($n > $max) $max = $n; }
  return sprintf('AB-%04d', $max + 1);
}

function stock_map() {               // name in accounting -> [sklad, remont, road, sold, total]
  $f = DATA . '/stock.json';
  return is_file($f) ? (json_decode(file_get_contents($f), true) ?: []) : [];
}

function json_out($x, $code = 200) {
  http_response_code($code);
  header('Content-Type: application/json; charset=utf-8');
  header('Cache-Control: no-store');
  echo json_encode($x, JSON_UNESCAPED_UNICODE);
  exit;
}
