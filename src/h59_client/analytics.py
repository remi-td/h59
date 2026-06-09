"""Analytic helpers and SQLite views for H59 data.

The device-facing storage layer preserves raw and minimally typed data.
This module defines the logical analytic layer that projects that device data
into stable consumer-oriented shapes.
"""

from __future__ import annotations

import datetime
import sqlite3
from typing import Any


ANALYTIC_VIEWS_SQL = """
DROP VIEW IF EXISTS health_feature_baselines;
DROP VIEW IF EXISTS health_daily_feature_store;
DROP VIEW IF EXISTS health_feature_observations;
DROP VIEW IF EXISTS health_metric_baselines;
DROP VIEW IF EXISTS health_metric_observations;
DROP VIEW IF EXISTS health_daily_features;
DROP VIEW IF EXISTS analytic_heart_rate_intervals;
DROP VIEW IF EXISTS analytic_activity_intervals;
DROP VIEW IF EXISTS analytic_sleep_stage_intervals;
DROP VIEW IF EXISTS analytic_blood_oxygen_intervals;
DROP VIEW IF EXISTS analytic_blood_pressure_intervals;
DROP VIEW IF EXISTS analytic_pressure_intervals;
DROP VIEW IF EXISTS analytic_hrv_intervals;
DROP VIEW IF EXISTS analytic_realtime_observations;
DROP VIEW IF EXISTS analytic_daily_steps;
DROP VIEW IF EXISTS analytic_daily_sleep;
DROP VIEW IF EXISTS analytic_sleep_sessions_classified;
DROP VIEW IF EXISTS analytic_sleep_sessions_canonical;

CREATE VIEW IF NOT EXISTS analytic_heart_rate_intervals AS
SELECT
    hr.heart_rate_id AS source_id,
    hr.device_id,
    hr.sync_id,
    hr.timestamp AS valid_from,
    strftime(
        '%Y-%m-%dT%H:%M:%S+00:00',
        unixepoch(hr.timestamp) + (
            COALESCE(
                (
                    SELECT hrs.interval_minutes
                    FROM heart_rate_settings AS hrs
                    WHERE hrs.device_id = hr.device_id
                    ORDER BY hrs.timestamp DESC
                    LIMIT 1
                ),
                5
            ) * 60
        ),
        'unixepoch'
    ) AS valid_to,
    hr.reading AS value,
    hr.source_command,
    hr.raw_packet_hex
FROM heart_rates AS hr;

CREATE VIEW IF NOT EXISTS analytic_activity_intervals AS
SELECT
    sd.sport_detail_id AS source_id,
    sd.device_id,
    sd.sync_id,
    sd.timestamp AS valid_from,
    strftime('%Y-%m-%dT%H:%M:%S+00:00', unixepoch(sd.timestamp) + (60 * 60), 'unixepoch') AS valid_to,
    sd.steps,
    sd.distance,
    sd.calories,
    sd.time_index,
    sd.source_command,
    sd.raw_packet_hex
FROM sport_details AS sd;

CREATE VIEW IF NOT EXISTS analytic_sleep_stage_intervals AS
SELECT
    sss.sleep_stage_sample_id AS source_id,
    sss.sleep_session_id,
    sss.device_id,
    sss.sync_id,
    sss.stage,
    sss.start_timestamp AS valid_from,
    sss.end_timestamp AS valid_to,
    sss.minutes,
    sss.is_provisional,
    sss.raw_json
FROM sleep_stage_samples AS sss;

CREATE VIEW IF NOT EXISTS analytic_sleep_sessions_classified AS
WITH sleep_quality AS (
    SELECT
        ss.sleep_session_id,
        ss.device_id,
        ss.sync_id,
        ss.start_timestamp,
        ss.end_timestamp,
        ss.total_minutes,
        ss.state,
        ss.score,
        ss.is_provisional,
        ss.source_command,
        ss.raw_json,
        date(COALESCE(ss.end_timestamp, ss.start_timestamp)) AS sleep_day,
        COALESCE(SUM(CASE WHEN sss.stage = 'no-data' THEN sss.minutes ELSE 0 END), 0) AS no_data_minutes,
        CASE
            WHEN ss.total_minutes IS NOT NULL THEN MAX(ss.total_minutes - COALESCE(SUM(CASE WHEN sss.stage = 'no-data' THEN sss.minutes ELSE 0 END), 0), 0)
            ELSE NULL
        END AS effective_minutes
    FROM sleep_sessions AS ss
    LEFT JOIN sleep_stage_samples AS sss
      ON sss.sleep_session_id = ss.sleep_session_id
    GROUP BY ss.sleep_session_id
)
SELECT
    sleep_session_id,
    device_id,
    sync_id,
    start_timestamp,
    end_timestamp,
    total_minutes,
    state,
    score,
    is_provisional,
    source_command,
    raw_json,
    sleep_day,
    no_data_minutes,
    effective_minutes,
    CASE
        WHEN total_minutes >= 180
             AND (
                date(COALESCE(start_timestamp, end_timestamp)) <> date(COALESCE(end_timestamp, start_timestamp))
                OR CAST(strftime('%H', COALESCE(start_timestamp, end_timestamp)) AS INTEGER) >= 18
                OR CAST(strftime('%H', COALESCE(end_timestamp, start_timestamp)) AS INTEGER) <= 12
             )
        THEN 'overnight'
        ELSE 'nap'
    END AS session_kind
FROM sleep_quality;

CREATE VIEW IF NOT EXISTS analytic_sleep_sessions_canonical AS
WITH ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY device_id, sleep_day
            ORDER BY
                effective_minutes DESC,
                no_data_minutes ASC,
                end_timestamp DESC,
                total_minutes DESC,
                sleep_session_id DESC
        ) AS session_rank
    FROM analytic_sleep_sessions_classified
    WHERE session_kind = 'overnight'
)
SELECT
    sleep_session_id,
    device_id,
    sync_id,
    start_timestamp,
    end_timestamp,
    total_minutes,
    state,
    score,
    is_provisional,
    source_command,
    raw_json,
    sleep_day,
    no_data_minutes,
    effective_minutes,
    session_kind
FROM ranked
WHERE session_rank = 1;

CREATE VIEW IF NOT EXISTS analytic_blood_oxygen_intervals AS
SELECT
    bos.blood_oxygen_sample_id AS source_id,
    bos.device_id,
    bos.sync_id,
    bos.timestamp AS valid_from,
    strftime('%Y-%m-%dT%H:%M:%S+00:00', unixepoch(bos.timestamp) + (bos.interval_minutes * 60), 'unixepoch') AS valid_to,
    ROUND((bos.min_percent + bos.max_percent) / 2.0, 1) AS value,
    bos.min_percent,
    bos.max_percent,
    bos.interval_minutes,
    bos.is_provisional,
    bos.source_command,
    bos.raw_packet_hex
FROM blood_oxygen_samples AS bos;

CREATE VIEW IF NOT EXISTS analytic_realtime_observations AS
SELECT
    rs.realtime_sample_id AS source_id,
    rs.device_id,
    rs.sync_id,
    rs.timestamp AS valid_from,
    rs.timestamp AS valid_to,
    mc.metric_code,
    mc.label AS metric_label,
    mc.unit,
    rs.value_numeric,
    rs.value_text,
    rs.error_code,
    rs.source_command,
    rs.raw_packet_hex
FROM realtime_samples AS rs
LEFT JOIN metric_codes AS mc
  ON mc.metric_code_id = rs.metric_code_id;

CREATE VIEW IF NOT EXISTS analytic_blood_pressure_intervals AS
WITH historical AS (
    SELECT
        'historical:' || bpr.blood_pressure_reading_id AS source_id,
        bpr.device_id,
        bpr.sync_id,
        bpr.timestamp AS valid_from,
        strftime('%Y-%m-%dT%H:%M:%S+00:00', unixepoch(bpr.timestamp) + (5 * 60), 'unixepoch') AS valid_to,
        bpr.systolic,
        bpr.diastolic,
        ROUND((bpr.systolic + (2.0 * bpr.diastolic)) / 3.0, 1) AS mean_arterial_pressure,
        bpr.source_command,
        bpr.raw_packet_hex
    FROM blood_pressure_readings AS bpr
),
realtime AS (
    SELECT
        'realtime:' || sys.source_id AS source_id,
        sys.device_id,
        sys.sync_id,
        sys.valid_from,
        strftime('%Y-%m-%dT%H:%M:%S+00:00', unixepoch(sys.valid_from) + (5 * 60), 'unixepoch') AS valid_to,
        CAST(sys.value_numeric AS INTEGER) AS systolic,
        CAST(dia.value_numeric AS INTEGER) AS diastolic,
        ROUND((CAST(sys.value_numeric AS REAL) + (2.0 * CAST(dia.value_numeric AS REAL))) / 3.0, 1) AS mean_arterial_pressure,
        sys.source_command,
        sys.raw_packet_hex
    FROM analytic_realtime_observations AS sys
    JOIN analytic_realtime_observations AS dia
      ON dia.device_id = sys.device_id
     AND dia.sync_id = sys.sync_id
     AND dia.valid_from = sys.valid_from
     AND dia.raw_packet_hex = sys.raw_packet_hex
     AND dia.metric_code = 'health-check.diastolic'
    WHERE sys.metric_code = 'health-check.systolic'
)
SELECT * FROM historical
UNION ALL
SELECT * FROM realtime;

CREATE VIEW IF NOT EXISTS analytic_pressure_intervals AS
SELECT
    ps.pressure_sample_id AS source_id,
    ps.device_id,
    ps.sync_id,
    ps.timestamp AS valid_from,
    strftime('%Y-%m-%dT%H:%M:%S+00:00', unixepoch(ps.timestamp) + (ps.interval_minutes * 60), 'unixepoch') AS valid_to,
    ps.value,
    ps.interval_minutes,
    ps.source_command,
    ps.raw_packet_hex
FROM pressure_samples AS ps;

CREATE VIEW IF NOT EXISTS analytic_hrv_intervals AS
SELECT
    hs.hrv_sample_id AS source_id,
    hs.device_id,
    hs.sync_id,
    hs.timestamp AS valid_from,
    strftime('%Y-%m-%dT%H:%M:%S+00:00', unixepoch(hs.timestamp) + (hs.interval_minutes * 60), 'unixepoch') AS valid_to,
    hs.value,
    hs.interval_minutes,
    hs.source_command,
    hs.raw_packet_hex
FROM hrv_samples AS hs;

CREATE VIEW IF NOT EXISTS analytic_daily_steps AS
SELECT
    device_id,
    date(timestamp) AS day_value,
    strftime('%Y-%m-%dT00:00:00+00:00', timestamp) AS valid_from,
    strftime('%Y-%m-%dT00:00:00+00:00', unixepoch(timestamp) + (24 * 60 * 60), 'unixepoch') AS valid_to,
    SUM(steps) AS steps_total,
    SUM(distance) AS distance_total,
    SUM(calories) AS calories_total,
    COUNT(*) AS sample_count
FROM sport_details
GROUP BY device_id, date(timestamp);

CREATE VIEW IF NOT EXISTS analytic_daily_sleep AS
SELECT
    device_id,
    sleep_day,
    strftime('%Y-%m-%dT00:00:00+00:00', end_timestamp) AS valid_from,
    strftime('%Y-%m-%dT00:00:00+00:00', unixepoch(end_timestamp) + (24 * 60 * 60), 'unixepoch') AS valid_to,
    SUM(total_minutes) AS minutes_total,
    COUNT(*) AS session_count
FROM analytic_sleep_sessions_canonical
GROUP BY device_id, sleep_day;

CREATE VIEW IF NOT EXISTS health_daily_features AS
WITH all_days AS (
    SELECT device_id, date(valid_from) AS day_value FROM analytic_heart_rate_intervals
    UNION
    SELECT device_id, date(valid_from) AS day_value FROM analytic_hrv_intervals
    UNION
    SELECT device_id, date(valid_from) AS day_value FROM analytic_pressure_intervals
    UNION
    SELECT device_id, date(valid_from) AS day_value FROM analytic_blood_oxygen_intervals
    UNION
    SELECT device_id, date(valid_from) AS day_value FROM analytic_blood_pressure_intervals
    UNION
    SELECT device_id, day_value FROM analytic_daily_steps
    UNION
    SELECT device_id, sleep_day AS day_value FROM analytic_daily_sleep
), hr AS (
    SELECT device_id, date(valid_from) AS day_value, AVG(value) AS avg_hr, MIN(value) AS min_hr, MAX(value) AS max_hr, COUNT(*) AS hr_sample_count
    FROM analytic_heart_rate_intervals
    GROUP BY device_id, date(valid_from)
), hrv AS (
    SELECT device_id, date(valid_from) AS day_value, AVG(value) AS hrv_avg, MIN(value) AS hrv_min, MAX(value) AS hrv_max, COUNT(*) AS hrv_sample_count
    FROM analytic_hrv_intervals
    GROUP BY device_id, date(valid_from)
), pressure AS (
    SELECT device_id, date(valid_from) AS day_value, AVG(value) AS pressure_avg, MAX(value) AS pressure_max, COUNT(*) AS pressure_sample_count
    FROM analytic_pressure_intervals
    GROUP BY device_id, date(valid_from)
), spo2 AS (
    SELECT device_id, date(valid_from) AS day_value, AVG(value) AS spo2_avg, MIN(min_percent) AS spo2_min, SUM(CASE WHEN min_percent < 90 THEN interval_minutes ELSE 0 END) AS minutes_spo2_below_90, COUNT(*) AS spo2_sample_count
    FROM analytic_blood_oxygen_intervals
    GROUP BY device_id, date(valid_from)
), sleep_stages AS (
    SELECT device_id, date(valid_to) AS day_value,
           SUM(CASE WHEN stage = 'deep' THEN minutes ELSE 0 END) AS deep_minutes,
           SUM(CASE WHEN stage = 'rem' THEN minutes ELSE 0 END) AS rem_minutes,
           SUM(CASE WHEN stage = 'light' THEN minutes ELSE 0 END) AS light_minutes,
           SUM(CASE WHEN stage IN ('awake', 'wake') THEN minutes ELSE 0 END) AS awake_minutes,
           SUM(CASE WHEN stage = 'no-data' THEN minutes ELSE 0 END) AS no_data_minutes
    FROM analytic_sleep_stage_intervals
    GROUP BY device_id, date(valid_to)
), bp AS (
    SELECT device_id, date(valid_from) AS day_value, systolic AS systolic_bp_latest, diastolic AS diastolic_bp_latest, mean_arterial_pressure
    FROM analytic_blood_pressure_intervals AS bpi
    WHERE valid_from = (
        SELECT MAX(valid_from)
        FROM analytic_blood_pressure_intervals AS newer
        WHERE newer.device_id = bpi.device_id AND date(newer.valid_from) = date(bpi.valid_from)
    )
), obs_values AS (
    SELECT device_id, date(valid_from) AS day_value, valid_to AS observed_at FROM analytic_heart_rate_intervals
    UNION ALL SELECT device_id, date(valid_from) AS day_value, valid_to FROM analytic_activity_intervals
    UNION ALL SELECT device_id, date(valid_from) AS day_value, valid_to FROM analytic_hrv_intervals
    UNION ALL SELECT device_id, date(valid_from) AS day_value, valid_to FROM analytic_pressure_intervals
    UNION ALL SELECT device_id, date(valid_from) AS day_value, valid_to FROM analytic_blood_oxygen_intervals
    UNION ALL SELECT device_id, date(valid_from) AS day_value, valid_to FROM analytic_blood_pressure_intervals
    UNION ALL SELECT device_id, sleep_day AS day_value, end_timestamp FROM analytic_sleep_sessions_canonical
), obs AS (
    SELECT device_id, day_value, MAX(observed_at) AS observation_as_of
    FROM obs_values
    WHERE observed_at IS NOT NULL
    GROUP BY device_id, day_value
)
SELECT
    d.device_id,
    d.day_value,
    strftime('%Y-%m-%dT00:00:00+00:00', d.day_value) AS valid_from,
    strftime('%Y-%m-%dT00:00:00+00:00', unixepoch(d.day_value || 'T00:00:00+00:00') + (24 * 60 * 60), 'unixepoch') AS valid_to,
    obs.observation_as_of,
    ROUND(
        (CASE WHEN hr.hr_sample_count IS NOT NULL THEN 20 ELSE 0 END) +
        (CASE WHEN hrv.hrv_sample_count IS NOT NULL THEN 15 ELSE 0 END) +
        (CASE WHEN s.steps_total IS NOT NULL THEN 15 ELSE 0 END) +
        (CASE WHEN ds.minutes_total IS NOT NULL THEN 25 ELSE 0 END) +
        (CASE WHEN spo2.spo2_sample_count IS NOT NULL THEN 10 ELSE 0 END) +
        (CASE WHEN pressure.pressure_sample_count IS NOT NULL THEN 10 ELSE 0 END) +
        (CASE WHEN bp.systolic_bp_latest IS NOT NULL THEN 5 ELSE 0 END),
        1
    ) AS data_quality_score,
    hr.hr_sample_count,
    hrv.hrv_sample_count,
    pressure.pressure_sample_count,
    spo2.spo2_sample_count,
    ds.minutes_total AS sleep_total_minutes,
    c.effective_minutes AS sleep_effective_minutes,
    c.start_timestamp AS sleep_start,
    c.end_timestamp AS sleep_end,
    CAST((unixepoch(c.start_timestamp) + ((unixepoch(c.end_timestamp) - unixepoch(c.start_timestamp)) / 2)) AS INTEGER) AS sleep_midpoint_epoch,
    ss.deep_minutes,
    ss.rem_minutes,
    ss.light_minutes,
    ss.awake_minutes,
    ss.no_data_minutes,
    hr.avg_hr,
    hr.min_hr,
    hr.max_hr,
    hr.min_hr AS resting_hr_bpm,
    hrv.hrv_avg,
    hrv.hrv_min,
    hrv.hrv_max,
    spo2.spo2_avg,
    spo2.spo2_min,
    spo2.minutes_spo2_below_90,
    pressure.pressure_avg,
    pressure.pressure_max,
    s.steps_total,
    s.distance_total,
    s.calories_total,
    ROUND((COALESCE(s.steps_total, 0) / 1000.0) + (COALESCE(s.calories_total, 0) / 100000.0), 2) AS activity_load,
    bp.systolic_bp_latest,
    bp.diastolic_bp_latest,
    bp.mean_arterial_pressure
FROM all_days AS d
LEFT JOIN hr ON hr.device_id = d.device_id AND hr.day_value = d.day_value
LEFT JOIN hrv ON hrv.device_id = d.device_id AND hrv.day_value = d.day_value
LEFT JOIN pressure ON pressure.device_id = d.device_id AND pressure.day_value = d.day_value
LEFT JOIN spo2 ON spo2.device_id = d.device_id AND spo2.day_value = d.day_value
LEFT JOIN analytic_daily_steps AS s ON s.device_id = d.device_id AND s.day_value = d.day_value
LEFT JOIN analytic_daily_sleep AS ds ON ds.device_id = d.device_id AND ds.sleep_day = d.day_value
LEFT JOIN analytic_sleep_sessions_canonical AS c ON c.device_id = d.device_id AND c.sleep_day = d.day_value
LEFT JOIN sleep_stages AS ss ON ss.device_id = d.device_id AND ss.day_value = d.day_value
LEFT JOIN bp ON bp.device_id = d.device_id AND bp.day_value = d.day_value
LEFT JOIN obs ON obs.device_id = d.device_id AND obs.day_value = d.day_value;

CREATE VIEW IF NOT EXISTS health_metric_observations AS
SELECT device_id, day_value, 'resting_hr_bpm' AS metric, resting_hr_bpm AS value FROM health_daily_features WHERE resting_hr_bpm IS NOT NULL
UNION ALL SELECT device_id, day_value, 'avg_hr', avg_hr FROM health_daily_features WHERE avg_hr IS NOT NULL
UNION ALL SELECT device_id, day_value, 'hrv_avg', hrv_avg FROM health_daily_features WHERE hrv_avg IS NOT NULL
UNION ALL SELECT device_id, day_value, 'sleep_total_minutes', sleep_total_minutes FROM health_daily_features WHERE sleep_total_minutes IS NOT NULL
UNION ALL SELECT device_id, day_value, 'steps_total', steps_total FROM health_daily_features WHERE steps_total IS NOT NULL
UNION ALL SELECT device_id, day_value, 'activity_load', activity_load FROM health_daily_features WHERE activity_load IS NOT NULL
UNION ALL SELECT device_id, day_value, 'pressure_avg', pressure_avg FROM health_daily_features WHERE pressure_avg IS NOT NULL
UNION ALL SELECT device_id, day_value, 'spo2_avg', spo2_avg FROM health_daily_features WHERE spo2_avg IS NOT NULL
UNION ALL SELECT device_id, day_value, 'spo2_min', spo2_min FROM health_daily_features WHERE spo2_min IS NOT NULL;

CREATE VIEW IF NOT EXISTS health_metric_baselines AS
WITH windows(window_days) AS (VALUES (7), (14), (30), (60)),
baseline_values AS (
    SELECT
        cur.device_id,
        cur.metric,
        cur.day_value AS as_of_day,
        windows.window_days,
        hist.value
    FROM health_metric_observations AS cur
    CROSS JOIN windows
    JOIN health_metric_observations AS hist
      ON hist.device_id = cur.device_id
     AND hist.metric = cur.metric
     AND hist.day_value >= date(cur.day_value, '-' || (windows.window_days - 1) || ' days')
     AND hist.day_value <= cur.day_value
), numbered AS (
    SELECT
        device_id,
        metric,
        as_of_day,
        window_days,
        value,
        ROW_NUMBER() OVER (PARTITION BY device_id, metric, as_of_day, window_days ORDER BY value) AS rn,
        COUNT(*) OVER (PARTITION BY device_id, metric, as_of_day, window_days) AS cnt
    FROM baseline_values
)
SELECT
    device_id,
    metric,
    as_of_day,
    window_days,
    COUNT(*) AS n_days,
    ROUND(AVG(value), 3) AS mean,
    MIN(value) AS min,
    MAX(value) AS max,
    ROUND(AVG(CASE WHEN rn IN ((cnt + 1) / 2, (cnt + 2) / 2) THEN value END), 3) AS median,
    ROUND(AVG(CASE WHEN rn IN (MAX(1, CAST((cnt * 0.2) AS INTEGER)), MAX(1, CAST((cnt * 0.8) AS INTEGER))) THEN value END), 3) AS band_sample,
    CASE
        WHEN COUNT(*) >= 45 THEN 'high'
        WHEN COUNT(*) >= 30 THEN 'medium'
        WHEN COUNT(*) >= 14 THEN 'low'
        ELSE 'new'
    END AS quality
FROM numbered
GROUP BY device_id, metric, as_of_day, window_days;

CREATE VIEW IF NOT EXISTS health_feature_observations AS
SELECT device_id, 'hr.daily_avg_bpm' AS feature_name, avg_hr AS feature_value, 'bpm' AS unit, valid_from, valid_to, day_value AS feature_date,
       'derived' AS source_kind, 'heart_rates' AS source_table, NULL AS source_id,
       CASE WHEN hr_sample_count >= 6 THEN 'complete' WHEN hr_sample_count > 0 THEN 'partial' ELSE 'missing' END AS data_quality_state,
       CASE WHEN hr_sample_count >= 6 THEN 0.85 ELSE 0.55 END AS confidence,
       observation_as_of, 'observed' AS approximation_label
FROM health_daily_features WHERE avg_hr IS NOT NULL
UNION ALL SELECT device_id, 'hr.resting_sleep_bpm', resting_hr_bpm, 'bpm', valid_from, valid_to, day_value,
       'derived', 'heart_rates', NULL,
       CASE WHEN sleep_total_minutes IS NOT NULL THEN 'complete' ELSE 'partial' END,
       CASE WHEN sleep_total_minutes IS NOT NULL THEN 0.75 ELSE 0.45 END,
       observation_as_of, CASE WHEN sleep_total_minutes IS NOT NULL THEN 'observed' ELSE 'heuristic' END
FROM health_daily_features WHERE resting_hr_bpm IS NOT NULL
UNION ALL SELECT device_id, 'hrv.daily_median', hrv_avg, 'ms', valid_from, valid_to, day_value,
       'derived', 'hrv_samples', NULL,
       CASE WHEN hrv_sample_count >= 3 THEN 'complete' WHEN hrv_sample_count > 0 THEN 'partial' ELSE 'missing' END,
       CASE WHEN hrv_sample_count >= 3 THEN 0.75 ELSE 0.5 END,
       observation_as_of, 'vendor_derived'
FROM health_daily_features WHERE hrv_avg IS NOT NULL
UNION ALL SELECT device_id, 'sleep.total_minutes', sleep_total_minutes, 'minutes', valid_from, valid_to, day_value,
       'derived', 'sleep_sessions', NULL,
       CASE WHEN sleep_total_minutes IS NOT NULL THEN 'complete' ELSE 'missing' END,
       0.8, observation_as_of, 'observed'
FROM health_daily_features WHERE sleep_total_minutes IS NOT NULL
UNION ALL SELECT device_id, 'sleep.effective_minutes', sleep_effective_minutes, 'minutes', valid_from, valid_to, day_value,
       'derived', 'sleep_sessions', NULL,
       CASE WHEN no_data_minutes IS NOT NULL AND no_data_minutes > 0 THEN 'partial' ELSE 'complete' END,
       CASE WHEN no_data_minutes IS NOT NULL AND no_data_minutes > 0 THEN 0.65 ELSE 0.8 END,
       observation_as_of, 'observed'
FROM health_daily_features WHERE sleep_effective_minutes IS NOT NULL
UNION ALL SELECT device_id, 'sleep.efficiency_pct', ROUND(100.0 * sleep_effective_minutes / NULLIF(sleep_total_minutes, 0), 1), 'percent', valid_from, valid_to, day_value,
       'derived', 'sleep_sessions', NULL,
       CASE WHEN no_data_minutes IS NOT NULL AND no_data_minutes > 0 THEN 'partial' ELSE 'complete' END,
       CASE WHEN no_data_minutes IS NOT NULL AND no_data_minutes > 0 THEN 0.6 ELSE 0.75 END,
       observation_as_of, 'heuristic'
FROM health_daily_features WHERE sleep_effective_minutes IS NOT NULL AND sleep_total_minutes IS NOT NULL AND sleep_total_minutes > 0
UNION ALL SELECT device_id, 'sleep.restorative_minutes', COALESCE(deep_minutes, 0) + COALESCE(rem_minutes, 0), 'minutes', valid_from, valid_to, day_value,
       'derived', 'sleep_stage_samples', NULL, 'partial', 0.6, observation_as_of, 'heuristic'
FROM health_daily_features WHERE deep_minutes IS NOT NULL OR rem_minutes IS NOT NULL
UNION ALL SELECT device_id, 'sleep.stage_deep_pct', ROUND(100.0 * deep_minutes / NULLIF(sleep_total_minutes, 0), 1), 'percent', valid_from, valid_to, day_value,
       'derived', 'sleep_stage_samples', NULL, 'partial', 0.55, observation_as_of, 'heuristic'
FROM health_daily_features WHERE deep_minutes IS NOT NULL AND sleep_total_minutes > 0
UNION ALL SELECT device_id, 'sleep.stage_rem_pct', ROUND(100.0 * rem_minutes / NULLIF(sleep_total_minutes, 0), 1), 'percent', valid_from, valid_to, day_value,
       'derived', 'sleep_stage_samples', NULL, 'partial', 0.55, observation_as_of, 'heuristic'
FROM health_daily_features WHERE rem_minutes IS NOT NULL AND sleep_total_minutes > 0
UNION ALL SELECT device_id, 'activity.steps_total', steps_total, 'steps', valid_from, valid_to, day_value,
       'raw', 'sport_details', NULL, CASE WHEN steps_total IS NOT NULL THEN 'complete' ELSE 'missing' END, 0.85, observation_as_of, 'observed'
FROM health_daily_features WHERE steps_total IS NOT NULL
UNION ALL SELECT device_id, 'activity.distance_total', distance_total, 'm', valid_from, valid_to, day_value,
       'raw', 'sport_details', NULL, 'complete', 0.8, observation_as_of, 'observed'
FROM health_daily_features WHERE distance_total IS NOT NULL
UNION ALL SELECT device_id, 'activity.calories_total', calories_total, 'kcal', valid_from, valid_to, day_value,
       'raw', 'sport_details', NULL, 'partial', 0.65, observation_as_of, 'vendor_derived'
FROM health_daily_features WHERE calories_total IS NOT NULL
UNION ALL SELECT device_id, 'strain.activity_load', activity_load, 'load', valid_from, valid_to, day_value,
       'derived', 'sport_details', NULL, 'partial', 0.55, observation_as_of, 'heuristic'
FROM health_daily_features WHERE activity_load IS NOT NULL
UNION ALL SELECT device_id, 'stress.pressure_avg', pressure_avg, 'score', valid_from, valid_to, day_value,
       'derived', 'pressure_samples', NULL, CASE WHEN pressure_sample_count >= 3 THEN 'complete' ELSE 'partial' END, 0.65, observation_as_of, 'vendor_derived'
FROM health_daily_features WHERE pressure_avg IS NOT NULL
UNION ALL SELECT device_id, 'spo2.avg', spo2_avg, 'percent', valid_from, valid_to, day_value,
       'derived', 'blood_oxygen_samples', NULL, 'partial', 0.65, observation_as_of, 'observed'
FROM health_daily_features WHERE spo2_avg IS NOT NULL
UNION ALL SELECT device_id, 'spo2.min', spo2_min, 'percent', valid_from, valid_to, day_value,
       'derived', 'blood_oxygen_samples', NULL, 'partial', 0.6, observation_as_of, 'observed'
FROM health_daily_features WHERE spo2_min IS NOT NULL
UNION ALL SELECT device_id, 'bp.latest_systolic', systolic_bp_latest, 'mmHg', valid_from, valid_to, day_value,
       'realtime', 'analytic_blood_pressure_intervals', NULL, 'partial', 0.7, observation_as_of, 'observed'
FROM health_daily_features WHERE systolic_bp_latest IS NOT NULL
UNION ALL SELECT device_id, 'bp.latest_diastolic', diastolic_bp_latest, 'mmHg', valid_from, valid_to, day_value,
       'realtime', 'analytic_blood_pressure_intervals', NULL, 'partial', 0.7, observation_as_of, 'observed'
FROM health_daily_features WHERE diastolic_bp_latest IS NOT NULL;

CREATE VIEW IF NOT EXISTS health_daily_feature_store AS
SELECT
    hdf.*,
    ROUND(100.0 * sleep_effective_minutes / NULLIF(sleep_total_minutes, 0), 1) AS sleep_efficiency_pct,
    COALESCE(deep_minutes, 0) + COALESCE(rem_minutes, 0) AS sleep_restorative_minutes,
    ROUND(100.0 * (COALESCE(deep_minutes, 0) + COALESCE(rem_minutes, 0)) / NULLIF(sleep_total_minutes, 0), 1) AS sleep_restorative_pct,
    awake_minutes AS sleep_waso_minutes,
    CASE WHEN awake_minutes IS NULL THEN NULL ELSE MAX(CAST(awake_minutes / 5 AS INTEGER), 0) END AS sleep_disturbance_count,
    ROUND((COALESCE(activity_load, 0) * 1.5) + (COALESCE(max_hr, avg_hr, resting_hr_bpm, 0) - COALESCE(resting_hr_bpm, 60)) / 10.0, 2) AS strain_score_0_21,
    CASE
        WHEN data_quality_score >= 70 THEN 'complete'
        WHEN data_quality_score >= 35 THEN 'partial'
        ELSE 'sparse'
    END AS data_quality_state
FROM health_daily_features AS hdf;

CREATE VIEW IF NOT EXISTS health_feature_baselines AS
WITH windows(window_days) AS (VALUES (7), (14), (30), (60)),
base AS (
    SELECT cur.device_id, cur.feature_name, cur.feature_date AS as_of_date, w.window_days,
           hist.feature_value, hist.observation_as_of
    FROM health_feature_observations AS cur
    CROSS JOIN windows AS w
    JOIN health_feature_observations AS hist
      ON hist.device_id = cur.device_id
     AND hist.feature_name = cur.feature_name
     AND hist.feature_date >= date(cur.feature_date, '-' || (w.window_days - 1) || ' days')
     AND hist.feature_date <= cur.feature_date
), numbered AS (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY device_id, feature_name, as_of_date, window_days ORDER BY feature_value) AS rn,
           COUNT(*) OVER (PARTITION BY device_id, feature_name, as_of_date, window_days) AS cnt,
           AVG(feature_value) OVER (PARTITION BY device_id, feature_name, as_of_date, window_days) AS avg_value
    FROM base
)
SELECT
    device_id,
    feature_name,
    as_of_date,
    window_days,
    COUNT(*) AS sample_count,
    ROUND(AVG(feature_value), 3) AS mean,
    ROUND(AVG(CASE WHEN rn IN ((cnt + 1) / 2, (cnt + 2) / 2) THEN feature_value END), 3) AS median,
    MIN(feature_value) AS min,
    MAX(feature_value) AS max,
    ROUND(AVG(ABS(feature_value - avg_value)), 3) AS mean_abs_deviation,
    MAX(observation_as_of) AS latest_observation_as_of,
    CASE
        WHEN MAX(observation_as_of) < datetime(as_of_date || 'T00:00:00+00:00', '-3 days') THEN 'stale'
        WHEN COUNT(*) >= 14 THEN 'trusted'
        WHEN COUNT(*) >= 7 THEN 'provisional'
        ELSE 'calibrating'
    END AS baseline_status
FROM numbered
GROUP BY device_id, feature_name, as_of_date, window_days;
"""


def ensure_analytic_views(conn: sqlite3.Connection) -> None:
    """Create the logical analytic surface over device-owned tables."""
    conn.executescript(ANALYTIC_VIEWS_SQL)


def _to_date_str(date_value: str | datetime.date | datetime.datetime) -> str:
    if isinstance(date_value, str):
        return date_value
    if isinstance(date_value, datetime.date):
        return date_value.isoformat()
    if isinstance(date_value, datetime.datetime):
        return date_value.date().isoformat()
    raise TypeError("date must be str or datetime.date/datetime")


def _utc_day_bounds(date_value: str | datetime.date | datetime.datetime) -> tuple[str, str]:
    day = datetime.date.fromisoformat(_to_date_str(date_value))
    start = datetime.datetime.combine(day, datetime.time.min, tzinfo=datetime.UTC)
    end = start + datetime.timedelta(days=1)
    return start.isoformat(), end.isoformat()


def compute_daily_summary(conn: sqlite3.Connection, date_value: str | datetime.date | datetime.datetime) -> dict[str, Any]:
    """Compute a daily summary for a UTC day using explicit range predicates."""
    start_iso, end_iso = _utc_day_bounds(date_value)
    day_value = _to_date_str(date_value)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT COALESCE(SUM(steps), 0), COALESCE(SUM(calories), 0), COALESCE(SUM(distance), 0)
        FROM sport_details
        WHERE replace(timestamp, ' ', 'T') >= ? AND replace(timestamp, ' ', 'T') < ?
        """,
        (start_iso, end_iso),
    )
    steps, calories, distance = cur.fetchone()

    cur.execute(
        """
        SELECT
            COUNT(reading),
            COALESCE(AVG(reading), 0),
            COALESCE(MIN(reading), 0),
            COALESCE(MAX(reading), 0)
        FROM heart_rates
        WHERE replace(timestamp, ' ', 'T') >= ? AND replace(timestamp, ' ', 'T') < ?
        """,
        (start_iso, end_iso),
    )
    hr_count, hr_avg, hr_min, hr_max = cur.fetchone()

    return {
        "date": day_value,
        "steps": int(steps),
        "calories": int(calories),
        "distance_meters": float(distance),
        "hr_count": int(hr_count),
        "hr_avg": float(hr_avg) if hr_count else None,
        "hr_min": int(hr_min) if hr_count else None,
        "hr_max": int(hr_max) if hr_count else None,
    }


def heart_rate_time_series(conn: sqlite3.Connection, date_value: str | datetime.date | datetime.datetime) -> list[dict[str, Any]]:
    """Return [{timestamp, reading}] for the given UTC day ordered by time."""
    start_iso, end_iso = _utc_day_bounds(date_value)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT timestamp, reading
        FROM heart_rates
        WHERE replace(timestamp, ' ', 'T') >= ? AND replace(timestamp, ' ', 'T') < ?
        ORDER BY timestamp ASC
        """,
        (start_iso, end_iso),
    )
    rows = cur.fetchall()
    return [{"timestamp": row[0], "reading": int(row[1])} for row in rows]
