<?php
define('AB', 1);
require __DIR__ . '/_lib.php';
start_session();
header('Cache-Control: no-store');

$cfg = cfg_admin();
$err = '';
if (empty($cfg['hash'])) {
  $err = 'Пароль адмінки ще не задано. Задайте його в консолі хостингу командою: php ~/autobeam_repo/server/admin_password.php';
} elseif ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['password'])) {
  if (!hash_equals($_SESSION['csrf'], $_POST['csrf'] ?? '')) {
    $err = 'Сесія застаріла, спробуйте ще раз.';
  } elseif (throttled()) {
    $err = 'Забагато невдалих спроб. Зачекайте 15 хвилин.';
  } elseif (password_verify($_POST['password'], $cfg['hash'])) {
    session_regenerate_id(true);
    $_SESSION['ok'] = 1; $_SESSION['csrf'] = bin2hex(random_bytes(24));
    header('Location: /admin/'); exit;
  } else {
    note_fail(); usleep(800000);
    $err = 'Невірний пароль.';
  }
}
$v = @filemtime(__DIR__ . '/admin.js');
?><!doctype html>
<html lang="uk"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>AutoBeam · Адмінка</title>
<link rel="icon" href="/assets/favicon.svg">
<link rel="stylesheet" href="/admin/admin.css?v=<?= $v ?>">
<meta name="csrf" content="<?= htmlspecialchars($_SESSION['csrf']) ?>">
</head><body>
<?php if (empty($_SESSION['ok'])): ?>
<form class="login" method="post" autocomplete="on">
  <div class="brand">Auto<b>Beam</b> <small>адмінка</small></div>
  <input type="hidden" name="csrf" value="<?= htmlspecialchars($_SESSION['csrf']) ?>">
  <input type="password" name="password" placeholder="Пароль" autofocus required autocomplete="current-password">
  <button>Увійти</button>
  <?php if ($err): ?><p class="err"><?= htmlspecialchars($err) ?></p><?php endif; ?>
</form>
<?php else: ?>
<div id="app">
  <header class="top">
    <div class="brand">Auto<b>Beam</b></div>
    <input id="q" type="search" placeholder="Пошук: марка, модель, парт-номер, AB-…">
    <select id="f-status">
      <option value="">Усі статуси</option><option>В наявності</option><option>Незабаром у наявності</option><option>Під замовлення</option>
    </select>
    <select id="f-extra">
      <option value="">Усі картки</option><option value="olx">З активним OLX</option><option value="olxoff">OLX неактивне</option>
      <option value="noolx">Без оголошення</option><option value="nophoto">Без фото</option><option value="nodesc">Без опису</option>
      <option value="note">Є примітка</option><option value="hidden">Приховані з сайту</option><option value="arch">Архів</option>
    </select>
    <button id="b-new" class="ghost">+ Нова</button>
    <select id="b-exp" title="CSV для імпорту на OLX">
      <option value="">OLX CSV…</option>
      <option value="2544:active">Фари передні — активні</option><option value="2544:all">Фари передні — активні + нові</option>
      <option value="2545:active">Ліхтарі — активні</option><option value="2545:all">Ліхтарі — активні + нові</option>
      <option value="2550:active">Корпуси — активні</option><option value="2550:all">Корпуси — активні + нові</option>
    </select>
    <button id="b-pub" title="Оновити сайт і фіди">Опублікувати</button>
    <button id="b-out" class="ghost">Вийти</button>
  </header>
  <div class="main">
    <aside><div id="count"></div><div id="list"></div></aside>
    <section id="ed"><p class="hint">Оберіть картку зліва або створіть нову.</p></section>
  </div>
</div>
<div id="toast"></div>
<script src="/admin/admin.js?v=<?= $v ?>"></script>
<?php endif; ?>
</body></html>
