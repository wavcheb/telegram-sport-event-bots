<?php
/**
 * Payment log page for Sport Event Bot
 * Usage: payments.php?event=123 or payments.php?chat=456
 *
 * Parameters:
 *   event - event_id to show payments for specific event
 *   chat  - chat_id to show payments for latest open event in chat
 */

// Load configuration
$config_file = __DIR__ . '/config.php';
if (!file_exists($config_file)) {
    die('Configuration file not found. Copy config.example.php to config.php');
}
require_once $config_file;

// Database connection
try {
    $pdo = new PDO(
        "mysql:host=" . DB_HOST . ";dbname=" . DB_NAME . ";charset=utf8mb4",
        DB_USER,
        DB_PASS,
        [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]
    );
} catch (PDOException $e) {
    die('Database connection failed');
}

// Get event_id from parameters
$event_id = null;
$chat_id = null;

if (isset($_GET['event']) && is_numeric($_GET['event'])) {
    $event_id = (int)$_GET['event'];
} elseif (isset($_GET['chat']) && is_numeric($_GET['chat'])) {
    $chat_id = (int)$_GET['chat'];
    // Get latest open event for this chat
    $stmt = $pdo->prepare('SELECT event_id, description FROM Events WHERE chat_id = ? AND status = "Open" ORDER BY event_id DESC LIMIT 1');
    $stmt->execute([$chat_id]);
    $row = $stmt->fetch(PDO::FETCH_ASSOC);
    if ($row) {
        $event_id = $row['event_id'];
    }
}

if (!$event_id) {
    die('Event not found. Use ?event=ID or ?chat=CHAT_ID');
}

// Signed links. Each chat has its own signing key, so a link given to one
// group cannot be edited into another group's event — the signature would have
// to come from a key that group never sees. A chat without a key yet (nothing
// generated a link since the upgrade) stays open, as before.
$event_chat_ids = [];
$stmt = $pdo->prepare('
    SELECT DISTINCT chat_id FROM Events
    WHERE event_id = ?
       OR event_id IN (SELECT event_id_2 FROM EventLinks WHERE event_id_1 = ?)
       OR event_id IN (SELECT event_id_1 FROM EventLinks WHERE event_id_2 = ?)
');
$stmt->execute([$event_id, $event_id, $event_id]);
while ($r = $stmt->fetch(PDO::FETCH_ASSOC)) {
    if ($r['chat_id'] !== null) {
        $event_chat_ids[] = (int)$r['chat_id'];
    }
}

$page_secrets = [];
if ($event_chat_ids) {
    try {
        $ph = implode(',', array_fill(0, count($event_chat_ids), '?'));
        $stmt = $pdo->prepare("SELECT page_secret FROM Chats
                               WHERE chat_id IN ($ph) AND page_secret IS NOT NULL AND page_secret <> ''");
        $stmt->execute($event_chat_ids);
        while ($r = $stmt->fetch(PDO::FETCH_ASSOC)) {
            $page_secrets[] = $r['page_secret'];
        }
    } catch (PDOException $e) {
        // page_secret column may not exist yet on older deployments
    }
}

if ($page_secrets) {
    $given = isset($_GET['t']) ? (string)$_GET['t'] : '';
    $accepted = false;
    foreach ($page_secrets as $secret) {
        $expected = substr(hash_hmac('sha256', (string)$event_id, $secret), 0, 16);
        if (hash_equals($expected, $given)) {
            $accepted = true;
            break;
        }
    }
    if (!$accepted) {
        http_response_code(403);
        die('Link is invalid. Ask your bot for a fresh one with /info or /payments.');
    }
}

// Get event info
$stmt = $pdo->prepare('SELECT event_id, chat_id, description, datetime, status FROM Events WHERE event_id = ?');
$stmt->execute([$event_id]);
$event = $stmt->fetch(PDO::FETCH_ASSOC);

if (!$event) {
    die('Event not found');
}

// Find all linked event IDs (including this one)
$all_event_ids = [$event_id];
$stmt = $pdo->prepare('SELECT event_id_2 FROM EventLinks WHERE event_id_1 = ?');
$stmt->execute([$event_id]);
while ($row = $stmt->fetch(PDO::FETCH_ASSOC)) {
    $all_event_ids[] = (int)$row['event_id_2'];
}
$stmt = $pdo->prepare('SELECT event_id_1 FROM EventLinks WHERE event_id_2 = ?');
$stmt->execute([$event_id]);
while ($row = $stmt->fetch(PDO::FETCH_ASSOC)) {
    $all_event_ids[] = (int)$row['event_id_1'];
}
$all_event_ids = array_unique($all_event_ids);
$placeholders = implode(',', array_fill(0, count($all_event_ids), '?'));

// Get payment log from all linked events
$stmt = $pdo->prepare("
    SELECT u.first_name, u.last_name, u.username, pl.paid_at, pl.for_friend
    FROM PaymentLog pl
    LEFT JOIN Users u ON pl.payer_user_id = u.user_id
    WHERE pl.event_id IN ($placeholders)
    ORDER BY pl.paid_at ASC
");
$stmt->execute($all_event_ids);
$payments = $stmt->fetchAll(PDO::FETCH_ASSOC);

// Get participants with payment status from all linked events
$stmt = $pdo->prepare("
    SELECT p.event_id, u.user_id, u.first_name, u.last_name, u.username, p.paid, p.paid_at, e.platform
    FROM Participants p
    LEFT JOIN Events e ON p.event_id = e.event_id
    LEFT JOIN Users u ON p.user_id = u.user_id AND u.platform = e.platform
    WHERE p.event_id IN ($placeholders)
    ORDER BY p.operation_datetime ASC
");
$stmt->execute($all_event_ids);
$participants = $stmt->fetchAll(PDO::FETCH_ASSOC);

// Duty player (plays for free). Stored once per event
// chain, so look it up across all linked event ids.
$duty_keys = [];
try {
    $stmt = $pdo->prepare("SELECT user_id, platform FROM Duty WHERE event_id IN ($placeholders)");
    $stmt->execute($all_event_ids);
    while ($row = $stmt->fetch(PDO::FETCH_ASSOC)) {
        $duty_keys[$row['user_id'] . '@' . $row['platform']] = true;
    }
} catch (PDOException $e) {
    // Duty table may not exist yet on older deployments — just skip the badge
}

// Duty history over a configurable window (default 4 weeks)
$duty_weeks = isset($_GET['weeks']) && is_numeric($_GET['weeks'])
    ? max(1, min(104, (int)$_GET['weeks']))
    : (defined('DUTY_WEEKS_DEFAULT') ? (int)DUTY_WEEKS_DEFAULT : 4);

$duty_history = [];
$chat_scope = [];
try {
    // The duty table is per chat; include the linked chat so both messengers
    // show the same history.
    $stmt = $pdo->prepare('SELECT chat_id, platform FROM Events WHERE event_id IN (' . $placeholders . ')');
    $stmt->execute($all_event_ids);
    while ($r = $stmt->fetch(PDO::FETCH_ASSOC)) {
        if ($r['chat_id'] !== null) {
            $chat_scope[] = (int)$r['chat_id'];
        }
    }
    if ($chat_scope) {
        $chat_ph = implode(',', array_fill(0, count($chat_scope), '?'));
        $stmt = $pdo->prepare("
            SELECT d.user_id, d.platform, d.duty_date, u.first_name, u.last_name, u.username
            FROM Duty d
            LEFT JOIN Users u ON d.user_id = u.user_id AND u.platform = d.platform
            WHERE d.chat_id IN ($chat_ph)
              AND d.duty_date >= DATE_SUB(NOW(), INTERVAL ? WEEK)
            ORDER BY d.duty_date DESC
        ");
        $stmt->execute(array_merge($chat_scope, [$duty_weeks]));
        $duty_history = $stmt->fetchAll(PDO::FETCH_ASSOC);
    }
} catch (PDOException $e) {
    // Duty table may not exist yet on older deployments
}

// Duty tally per person over that window
$duty_tally = [];
foreach ($duty_history as $d) {
    $name = formatName($d, true);
    if (!isset($duty_tally[$name])) {
        $duty_tally[$name] = ['count' => 0, 'last' => $d['duty_date']];
    }
    $duty_tally[$name]['count']++;
    if ($d['duty_date'] > $duty_tally[$name]['last']) {
        $duty_tally[$name]['last'] = $d['duty_date'];
    }
}
uasort($duty_tally, fn($a, $b) => $b['count'] <=> $a['count']);

// What the treasurer last recorded
$bank = null;
try {
    if ($chat_scope) {
        $chat_ph = implode(',', array_fill(0, count($chat_scope), '?'));
        $stmt = $pdo->prepare("
            SELECT amount, comment, updated_at, currency FROM Bank
            WHERE chat_id IN ($chat_ph)
            ORDER BY updated_at DESC, bank_id DESC LIMIT 1
        ");
        $stmt->execute($chat_scope);
        $bank = $stmt->fetch(PDO::FETCH_ASSOC) ?: null;
    }
} catch (PDOException $e) {
    // Bank table may not exist yet on older deployments
}

function formatMoney($amount, $currency = '') {
    // The chat records its own currency with the amount; BANK_CURRENCY is only
    // the fallback for a kitty entered before currencies were per chat.
    $sign = $currency !== '' && $currency !== null
        ? $currency
        : (defined('BANK_CURRENCY') ? BANK_CURRENCY : '');
    $value = (float)$amount;
    $body = (abs($value - round($value)) < 0.005)
        ? number_format($value, 0, ',', ' ')
        : number_format($value, 2, ',', ' ');
    return trim($body . ' ' . $sign);
}

function isOnDuty($row, $duty_keys) {
    if (empty($row['user_id'])) {
        return false;
    }
    $platform = $row['platform'] ?? 'telegram';
    return isset($duty_keys[$row['user_id'] . '@' . $platform]);
}

// Helper function to format name
function formatName($row, $showPlatform = false) {
    $name = trim(($row['first_name'] ?? '') . ' ' . ($row['last_name'] ?? ''));
    $username = $row['username'] ?? '';
    if ($name && $username) {
        $result = "$name ($username)";
    } else {
        $result = $name ?: $username ?: 'Unknown';
    }
    if ($showPlatform && !empty($row['platform'])) {
        $platform = $row['platform'];
        if ($platform !== 'telegram') {
            $result .= " [$platform]";
        }
    }
    return $result;
}

// Count statistics — a duty player counts as settled up
$total_participants = count($participants);
$paid_count = count(array_filter(
    $participants,
    fn($p) => $p['paid'] || isOnDuty($p, $duty_keys)
));
$unpaid_count = $total_participants - $paid_count;

?>
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Оплаты: <?= htmlspecialchars($event['description'] ?? 'Событие') ?></title>
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
            color: #333;
        }
        h1 {
            font-size: 1.4em;
            color: #1a1a1a;
            border-bottom: 2px solid #007bff;
            padding-bottom: 10px;
        }
        .event-info {
            background: #fff;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        .stats {
            display: flex;
            gap: 15px;
            margin: 15px 0;
        }
        .stat-box {
            flex: 1;
            padding: 10px;
            border-radius: 6px;
            text-align: center;
        }
        .stat-box.paid { background: #d4edda; color: #155724; }
        .stat-box.unpaid { background: #f8d7da; color: #721c24; }
        .stat-box.total { background: #e2e3e5; color: #383d41; }
        .stat-number { font-size: 1.8em; font-weight: bold; }
        .stat-label { font-size: 0.85em; }

        .section { margin-top: 20px; }
        .section h2 {
            font-size: 1.1em;
            color: #555;
            margin-bottom: 10px;
        }

        .list {
            background: #fff;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        .list-item {
            padding: 12px 15px;
            border-bottom: 1px solid #eee;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .list-item:last-child { border-bottom: none; }
        .list-item.paid { background: #f8fff8; }
        .list-item.unpaid { background: #fff8f8; }

        .name { font-weight: 500; }
        .time { color: #888; font-size: 0.9em; }
        .badge {
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 0.8em;
            font-weight: 500;
        }
        .badge.paid { background: #28a745; color: #fff; }
        .badge.unpaid { background: #dc3545; color: #fff; }
        .badge.friend { background: #17a2b8; color: #fff; }
        .badge.duty { background: #1e7e34; color: #fff; }

        .updated {
            text-align: center;
            color: #888;
            font-size: 0.85em;
            margin-top: 20px;
        }

        .empty {
            padding: 20px;
            text-align: center;
            color: #888;
        }

        .bank {
            background: #fff8e1;
            border: 1px solid #ffe082;
            border-radius: 8px;
            padding: 12px 15px;
            margin-bottom: 20px;
        }
        .bank-amount { font-size: 1.3em; font-weight: bold; color: #7a5c00; }
        .bank-note { color: #8d7b4a; font-size: 0.9em; margin-top: 4px; }

        table.duty {
            width: 100%;
            border-collapse: collapse;
            background: #fff;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        table.duty th, table.duty td {
            padding: 10px 12px;
            text-align: left;
            border-bottom: 1px solid #eee;
            font-size: 0.95em;
        }
        table.duty th { background: #f1f3f5; font-weight: 600; color: #555; }
        table.duty td.num { text-align: right; width: 4em; }
        table.duty tr:last-child td { border-bottom: none; }

        .period { margin: 8px 0 12px; font-size: 0.9em; color: #666; }
        .period a {
            display: inline-block;
            padding: 3px 9px;
            margin-right: 5px;
            border-radius: 12px;
            background: #e9ecef;
            color: #495057;
            text-decoration: none;
        }
        .period a.active { background: #007bff; color: #fff; }
    </style>
</head>
<body>
    <h1><?= htmlspecialchars($event['description'] ?? 'Событие #' . $event_id) ?></h1>

    <div class="event-info">
        <?php if ($event['datetime']): ?>
            <div><strong>Дата:</strong> <?= htmlspecialchars($event['datetime']) ?></div>
        <?php endif; ?>
        <div><strong>Статус:</strong> <?= $event['status'] === 'Open' ? 'Открыто' : 'Закрыто' ?></div>
    </div>

    <?php if ($bank): ?>
        <div class="bank">
            <div>Касса сообщества</div>
            <div class="bank-amount"><?= htmlspecialchars(formatMoney($bank['amount'], $bank['currency'] ?? '')) ?></div>
            <?php if (!empty($bank['comment'])): ?>
                <div class="bank-note"><?= htmlspecialchars($bank['comment']) ?></div>
            <?php endif; ?>
            <div class="bank-note">обновлено <?= date('d.m.Y H:i', strtotime($bank['updated_at'])) ?></div>
        </div>
    <?php endif; ?>

    <div class="stats">
        <div class="stat-box paid">
            <div class="stat-number"><?= $paid_count ?></div>
            <div class="stat-label">Оплатили</div>
        </div>
        <div class="stat-box unpaid">
            <div class="stat-number"><?= $unpaid_count ?></div>
            <div class="stat-label">Не оплатили</div>
        </div>
        <div class="stat-box total">
            <div class="stat-number"><?= $total_participants ?></div>
            <div class="stat-label">Всего</div>
        </div>
    </div>

    <div class="section">
        <h2>Участники</h2>
        <div class="list">
            <?php if (empty($participants)): ?>
                <div class="empty">Нет участников</div>
            <?php else: ?>
                <?php foreach ($participants as $i => $p): ?>
                    <?php
                        $on_duty = isOnDuty($p, $duty_keys);
                        $settled = $on_duty || $p['paid'];
                    ?>
                    <div class="list-item <?= $settled ? 'paid' : 'unpaid' ?>">
                        <div>
                            <span class="name"><?= ($i + 1) ?>. <?= htmlspecialchars(formatName($p, true)) ?></span>
                            <?php if (!$on_duty && $p['paid'] && $p['paid_at']): ?>
                                <span class="time"><?= date('H:i', strtotime($p['paid_at'])) ?></span>
                            <?php endif; ?>
                        </div>
                        <?php if ($on_duty): ?>
                            <span class="badge duty">🧹 Дежурный</span>
                        <?php else: ?>
                            <span class="badge <?= $p['paid'] ? 'paid' : 'unpaid' ?>">
                                <?= $p['paid'] ? 'Оплачено' : 'Не оплачено' ?>
                            </span>
                        <?php endif; ?>
                    </div>
                <?php endforeach; ?>
            <?php endif; ?>
        </div>
    </div>

    <?php if (!empty($payments)): ?>
    <div class="section">
        <h2>Лог оплат</h2>
        <div class="list">
            <?php foreach ($payments as $payment): ?>
                <div class="list-item">
                    <div>
                        <span class="name"><?= htmlspecialchars(formatName($payment)) ?></span>
                        <span class="time"><?= date('H:i', strtotime($payment['paid_at'])) ?></span>
                    </div>
                    <span class="badge <?= $payment['for_friend'] ? 'friend' : 'paid' ?>">
                        <?= $payment['for_friend'] ? 'За друга' : 'За себя' ?>
                    </span>
                </div>
            <?php endforeach; ?>
        </div>
    </div>
    <?php endif; ?>

    <div class="section">
        <h2>🧹 Дежурства</h2>
        <?php
            $link_base = 'payments.php?event=' . (int)$event_id
                . (isset($_GET['t']) ? '&t=' . urlencode((string)$_GET['t']) : '');
        ?>
        <div class="period">
            Период:
            <?php foreach ([2, 4, 8, 12] as $w): ?>
                <a class="<?= $w === $duty_weeks ? 'active' : '' ?>"
                   href="<?= htmlspecialchars($link_base . '&weeks=' . $w) ?>"><?= $w ?> нед.</a>
            <?php endforeach; ?>
        </div>
        <?php if (empty($duty_tally)): ?>
            <div class="list"><div class="empty">За этот период дежурств не было</div></div>
        <?php else: ?>
            <table class="duty">
                <tr><th>Игрок</th><th class="num">Дежурств</th><th>Последнее</th></tr>
                <?php foreach ($duty_tally as $name => $info): ?>
                    <tr>
                        <td><?= htmlspecialchars($name) ?></td>
                        <td class="num"><?= (int)$info['count'] ?></td>
                        <td><?= date('d.m.Y', strtotime($info['last'])) ?></td>
                    </tr>
                <?php endforeach; ?>
            </table>
        <?php endif; ?>
    </div>

    <div class="updated">
        Обновлено: <?= date('Y-m-d H:i:s') ?>
    </div>
</body>
</html>
