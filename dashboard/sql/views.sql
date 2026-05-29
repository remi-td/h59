-- Optional helper views for ad hoc dashboard analysis.
-- These views are not required by the provisioned dashboards.

CREATE VIEW IF NOT EXISTS dashboard_device_directory AS
SELECT
    device_id,
    COALESCE(nickname, name, 'device-' || device_id) AS device_label,
    address,
    name,
    nickname,
    hw_version,
    fw_version,
    last_seen_at
FROM devices;

CREATE VIEW IF NOT EXISTS dashboard_latest_sync AS
SELECT
    s.device_id,
    MAX(s.finished_at) AS last_successful_sync_at
FROM syncs s
WHERE s.finished_at IS NOT NULL
GROUP BY s.device_id;

CREATE VIEW IF NOT EXISTS dashboard_metric_freshness AS
SELECT device_id, 'heart_rate' AS metric, MAX(timestamp) AS latest_timestamp
FROM heart_rates
GROUP BY device_id
UNION ALL
SELECT device_id, 'activity', MAX(timestamp) AS latest_timestamp
FROM sport_details
GROUP BY device_id
UNION ALL
SELECT device_id, 'sleep', MAX(end_timestamp) AS latest_timestamp
FROM sleep_sessions
GROUP BY device_id
UNION ALL
SELECT device_id, 'blood_oxygen', MAX(timestamp) AS latest_timestamp
FROM blood_oxygen_samples
GROUP BY device_id
UNION ALL
SELECT device_id, 'pressure', MAX(timestamp) AS latest_timestamp
FROM pressure_samples
GROUP BY device_id
UNION ALL
SELECT device_id, 'hrv', MAX(timestamp) AS latest_timestamp
FROM hrv_samples
GROUP BY device_id;

CREATE VIEW IF NOT EXISTS dashboard_daily_sample_counts AS
SELECT device_id, date(timestamp) AS day_utc, 'heart_rate' AS metric, COUNT(*) AS sample_count
FROM heart_rates
GROUP BY device_id, date(timestamp)
UNION ALL
SELECT device_id, date(timestamp) AS day_utc, 'activity' AS metric, COUNT(*) AS sample_count
FROM sport_details
GROUP BY device_id, date(timestamp)
UNION ALL
SELECT device_id, date(timestamp) AS day_utc, 'blood_oxygen' AS metric, COUNT(*) AS sample_count
FROM blood_oxygen_samples
GROUP BY device_id, date(timestamp)
UNION ALL
SELECT device_id, date(timestamp) AS day_utc, 'pressure' AS metric, COUNT(*) AS sample_count
FROM pressure_samples
GROUP BY device_id, date(timestamp)
UNION ALL
SELECT device_id, date(timestamp) AS day_utc, 'hrv' AS metric, COUNT(*) AS sample_count
FROM hrv_samples
GROUP BY device_id, date(timestamp);

CREATE VIEW IF NOT EXISTS dashboard_sleep_daily AS
SELECT
    device_id,
    date(start_timestamp) AS sleep_day_utc,
    total_minutes,
    start_timestamp,
    end_timestamp,
    is_provisional
FROM sleep_sessions;
