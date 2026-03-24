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

// Count statistics
$total_participants = count($participants);
$paid_count = count(array_filter($participants, fn($p) => $p['paid']));
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
                    <div class="list-item <?= $p['paid'] ? 'paid' : 'unpaid' ?>">
                        <div>
                            <span class="name"><?= ($i + 1) ?>. <?= htmlspecialchars(formatName($p, true)) ?></span>
                            <?php if ($p['paid'] && $p['paid_at']): ?>
                                <span class="time"><?= date('H:i', strtotime($p['paid_at'])) ?></span>
                            <?php endif; ?>
                        </div>
                        <span class="badge <?= $p['paid'] ? 'paid' : 'unpaid' ?>">
                            <?= $p['paid'] ? 'Оплачено' : 'Не оплачено' ?>
                        </span>
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

    <div class="updated">
        Обновлено: <?= date('Y-m-d H:i:s') ?>
    </div>
</body>
</html>
