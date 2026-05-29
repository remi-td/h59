-- Example overview summary query for manual inspection.
-- Replace the value in selected_device as needed.

WITH selected_device AS (
    SELECT 1 AS device_id
)
SELECT
    d.device_id,
    COALESCE(d.nickname, d.name, 'device-' || d.device_id) AS device_label,
    (
        SELECT MAX(finished_at)
        FROM syncs s
        WHERE s.device_id = d.device_id
          AND s.finished_at IS NOT NULL
    ) AS last_successful_sync_at,
    (
        SELECT reading
        FROM heart_rates hr
        WHERE hr.device_id = d.device_id
        ORDER BY hr.timestamp DESC
        LIMIT 1
    ) AS latest_heart_rate_bpm,
    (
        SELECT SUM(sd.steps)
        FROM sport_details sd
        WHERE sd.device_id = d.device_id
          AND sd.timestamp >= strftime('%Y-%m-%dT00:00:00+00:00', 'now')
          AND sd.timestamp < strftime('%Y-%m-%dT00:00:00+00:00', 'now', '+1 day')
    ) AS steps_today,
    (
        SELECT total_minutes
        FROM sleep_sessions ss
        WHERE ss.device_id = d.device_id
        ORDER BY ss.end_timestamp DESC
        LIMIT 1
    ) AS latest_sleep_minutes,
    (
        SELECT battery_level
        FROM battery_samples bs
        WHERE bs.device_id = d.device_id
        ORDER BY bs.timestamp DESC
        LIMIT 1
    ) AS latest_battery_percent
FROM devices d
JOIN selected_device sel ON sel.device_id = d.device_id;
