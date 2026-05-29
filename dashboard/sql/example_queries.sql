-- Example direct queries against the H59 SQLite database.

-- Latest devices
SELECT
    device_id,
    COALESCE(nickname, name, 'device-' || device_id) AS device_label,
    address,
    last_seen_at
FROM devices
ORDER BY last_seen_at DESC;

-- Heart rate trend over the last 24 hours
SELECT
    timestamp AS time,
    reading AS heart_rate_bpm
FROM heart_rates
WHERE device_id = 1
  AND timestamp >= strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now', '-24 hours')
ORDER BY timestamp;

-- Daily steps totals for the last 30 days
SELECT
    date(timestamp) AS day_utc,
    SUM(steps) AS steps_total
FROM sport_details
WHERE device_id = 1
  AND timestamp >= strftime('%Y-%m-%dT00:00:00+00:00', 'now', '-29 days')
GROUP BY date(timestamp)
ORDER BY day_utc;

-- Sleep sessions
SELECT
    start_timestamp,
    end_timestamp,
    total_minutes,
    is_provisional
FROM sleep_sessions
WHERE device_id = 1
ORDER BY start_timestamp DESC;
