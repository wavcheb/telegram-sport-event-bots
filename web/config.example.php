<?php
/**
 * Configuration for the payments page.
 * Copy this file to config.php and fill in your credentials.
 */

define('DB_HOST', 'localhost');
define('DB_NAME', 'futsal_bot');
define('DB_USER', 'futsal_bot');
define('DB_PASS', 'your_password_here');

/**
 * Shared signing key for event links. Set the SAME value as PAYMENTS_SECRET
 * in each bot's .env and the page will only open links the bots produced —
 * without it, anyone could read other events by editing ?event=.
 * Leave empty to keep the page open to anyone with the link (old behaviour).
 */
define('PAYMENTS_SECRET', '');

/** Sign shown next to the kitty balance. Match BANK_CURRENCY in the bots' .env. */
define('BANK_CURRENCY', '₽');

/** Default window, in weeks, for the duty table. */
define('DUTY_WEEKS_DEFAULT', 4);
