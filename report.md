# H59 Health Dashboard Data Audit

- Generated at: 2026-05-28 08:47 UTC
- Database: `/Users/remi.turpaud/Code/h59/data/h59.sqlite`
- Device: `H59_7407` (`86B9D8D4-6CB2-E24D-815D-A141786F427B`)
- Device ID: `1`
- Selected day: `2026-05-28`
- Time basis: UTC day boundaries from the stored timestamps

## Daily Overview

- Steps: `1026`
- Distance: `692`
- Calories-like field: `29910`
- Heart-rate samples: `105`
- Latest heart rate: `78 bpm`
- Last successful sync: `2026-05-28 08:43 UTC`
- Battery: `80%`

## Coverage Matrix

| Requirement | Data in DB | Current extraction/rule coverage | Remaining gap |
|---|---|---|---|
| Steps | Available | Partial: Daily totals and hourly buckets from stored activity summaries | No raw accelerometer history, no goal logic, calories unit still unvalidated |
| Heart rate | Available | Available: Latest/min/max/avg from historical 5-minute samples | No night-time segmentation or confidence scoring yet |
| Sleep | Available | Available: Sleep sessions and staged periods available | Stage semantics still provisional for some values; local-day presentation rules are still missing |
| Blood oxygen / SpO2 | Available | Partial: Historical min/max samples available (41 for selected day) | Sample timing and header semantics are still provisional; no night-time minimum rule yet |
| HRV | Available | Partial: Historical samples available (11 for selected day) | No baseline logic yet; vendor formula and physiological meaning still need validation |
| Stress | Available | Partial: Historical pressure/stress-like samples available (22 for selected day) | Need mapping from device metric to stress score and label |
| Blood pressure estimate | Partial | Missing: Device advertises support, but no stored observations exist | No historical sync path, no systolic/diastolic presentation rules, must remain labelled as estimated |
| Sport / activity record | Available | Partial: Sessions inferred from contiguous activity bins | No explicit sport type, no vendor session boundaries, no dedicated exercise table yet |
| One key measurement | Partial | Missing: Device advertises support, but no decoded observation exists | Need composite score extraction and component breakdown rules |
| Device status and sync quality | Available | Partial: Battery, last sync, sync completion counts, raw packet counts | No live connected/disconnected state persisted, no sync SLA rules yet |

## Daily Steps

- Activity bins on selected day: `2`
- First activity bin: `2026-05-28 07:00 UTC`
- Last activity bin: `2026-05-28 08:00 UTC`
- Notes: current stored activity summaries are hourly in this dataset; steps and distance are usable, and the calories-like field still needs unit validation against the app.

| Hour bucket | Steps |
|---|---|
| 07:00 | 256 |
| 08:00 | 770 |

## Heart Rate

- Sample window: `2026-05-28 00:00 UTC` to `2026-05-28 08:40 UTC`
- Latest: `78 bpm` at `2026-05-28 08:40 UTC`
- Min / avg / max: `50 / 62.7 / 107 bpm`

## Sleep

- Sleep sessions stored: `5` total, `2` on selected day
- Latest session: `2026-05-27 23:40 UTC` to `2026-05-28 08:49 UTC`
- Latest duration: `09 h 09 min`

## Health Metrics

### Blood Oxygen / SpO2
- Historical samples: `87` total, `41` on selected day
- Latest historical sample: `min=98%`, `max=98%` at `2026-05-28 23:30 UTC`

### HRV
- Historical samples: `83` total, `11` on selected day
- Latest historical sample: `48` at `2026-05-28 05:00 UTC`

### Stress / Pressure-like
- Historical samples: `168` total, `22` on selected day
- Latest historical sample: `41` at `2026-05-28 10:30 UTC`

### Blood Pressure
- Not available in the current database.

### One Key Measurement
- Not available in the current database.

- No realtime metric samples are stored in this database.
- Device-advertised capability flags: `support_blood_pressure, support_hrv, support_menstruation, support_one_key_check, support_pressure, support_spo2, support_wechat`

## Data Quality and Completeness

- Window basis: last 24 hours for each fixed-interval series, ending at that series' latest stored measurement
### Heart rate
- Latest measurement: `2026-05-28 08:40 UTC` (interval `5 min`, samples in window `214`)
- Gaps detected in the last 24 hours:
  - `2026-05-27 10:35 UTC` to `2026-05-27 10:55 UTC` (`5` missing intervals)
  - `2026-05-27 11:45 UTC` to `2026-05-27 11:55 UTC` (`3` missing intervals)
  - `2026-05-27 13:20 UTC` to `2026-05-27 13:40 UTC` (`5` missing intervals)
  - `2026-05-27 14:00 UTC` to `2026-05-27 14:15 UTC` (`4` missing intervals)
  - `2026-05-27 14:25 UTC` to `2026-05-27 15:15 UTC` (`11` missing intervals)
  - `2026-05-27 18:30 UTC` to `2026-05-27 19:05 UTC` (`8` missing intervals)
  - `2026-05-27 19:15 UTC` to `2026-05-27 20:25 UTC` (`15` missing intervals)
  - `2026-05-27 21:10 UTC` to `2026-05-27 23:05 UTC` (`24` missing intervals)
### Activity steps
- Latest measurement: `2026-05-28 08:00 UTC` (interval `60 min`, samples in window `13`)
- Gaps detected in the last 24 hours:
  - `2026-05-27 13:00 UTC` to `2026-05-27 14:00 UTC` (`2` missing intervals)
  - `2026-05-27 21:00 UTC` to `2026-05-28 06:00 UTC` (`10` missing intervals)
### Activity distance
- Latest measurement: `2026-05-28 08:00 UTC` (interval `60 min`, samples in window `13`)
- Gaps detected in the last 24 hours:
  - `2026-05-27 13:00 UTC` to `2026-05-27 14:00 UTC` (`2` missing intervals)
  - `2026-05-27 21:00 UTC` to `2026-05-28 06:00 UTC` (`10` missing intervals)
### Activity calories-like
- Latest measurement: `2026-05-28 08:00 UTC` (interval `60 min`, samples in window `13`)
- Gaps detected in the last 24 hours:
  - `2026-05-27 13:00 UTC` to `2026-05-27 14:00 UTC` (`2` missing intervals)
  - `2026-05-27 21:00 UTC` to `2026-05-28 06:00 UTC` (`10` missing intervals)
### Blood oxygen min
- Latest measurement: `2026-05-28 23:30 UTC` (interval `30 min`, samples in window `41`)
- Gaps detected in the last 24 hours:
  - `2026-05-28 11:00 UTC` to `2026-05-28 11:30 UTC` (`2` missing intervals)
  - `2026-05-28 17:00 UTC` to `2026-05-28 17:30 UTC` (`2` missing intervals)
  - `2026-05-28 18:30 UTC` to `2026-05-28 19:30 UTC` (`3` missing intervals)
### Blood oxygen max
- Latest measurement: `2026-05-28 23:30 UTC` (interval `30 min`, samples in window `41`)
- Gaps detected in the last 24 hours:
  - `2026-05-28 11:00 UTC` to `2026-05-28 11:30 UTC` (`2` missing intervals)
  - `2026-05-28 17:00 UTC` to `2026-05-28 17:30 UTC` (`2` missing intervals)
  - `2026-05-28 18:30 UTC` to `2026-05-28 19:30 UTC` (`3` missing intervals)
### Stress / pressure-like
- Latest measurement: `2026-05-28 10:30 UTC` (interval `30 min`, samples in window `44`)
- Gaps detected in the last 24 hours:
  - `2026-05-27 13:30 UTC` to `2026-05-27 15:00 UTC` (`4` missing intervals)
  - `2026-05-27 23:00 UTC` to `2026-05-27 23:00 UTC` (`1` missing interval)
### HRV
- Latest measurement: `2026-05-28 05:00 UTC` (interval `30 min`, samples in window `22`)
- Gaps detected in the last 24 hours:
  - `2026-05-27 07:00 UTC` to `2026-05-27 07:30 UTC` (`2` missing intervals)
  - `2026-05-27 11:30 UTC` to `2026-05-27 23:30 UTC` (`25` missing intervals)

## Statistical Analysis

Window basis: last 24 hours for each fixed-interval series, ending at that series' latest stored measurement.

| Measurement | Samples | Median | P5 | P95 | Min | Max |
|---|---|---|---|---|---|---|
| Heart rate | 214 | 70 | 56 | 90 | 50 | 112 |
| Activity steps | 13 | 207 | 30 | 871.2 | 24 | 1023 |
| Activity distance | 13 | 138 | 17.2 | 591.8 | 13 | 716 |
| Activity calories-like | 13 | 5950 | 762 | 25586.0 | 570 | 30980 |
| Blood oxygen min | 41 | 98 | 96 | 99 | 1 | 99 |
| Blood oxygen max | 41 | 98 | 96 | 99 | 96 | 99 |
| Stress / pressure-like | 44 | 43.5 | 33 | 61.9 | 25 | 65 |
| HRV | 22 | 43.5 | 34.0 | 49.0 | 31 | 49 |

## Sport / Activity Sessions

| Session start | Session end | Duration | Steps | Distance | Calories-like | Avg HR |
|---|---|---|---|---|---|---|
| 2026-05-28 07:00 UTC | 2026-05-28 07:15 UTC | 15 min | 256 | 183 | 7920 | 58.3 |
| 2026-05-28 08:00 UTC | 2026-05-28 08:15 UTC | 15 min | 770 | 509 | 21990 | 78.0 |
- These sessions are inferred from contiguous stored activity summaries, not explicit device sport records.

## Device and Sync Status

- Battery sample: `80%`, charging=`False` at `2026-05-28 08:43 UTC`
- Sync runs: `18` total, `18` completed, `0` incomplete
- Last sync start: `2026-05-28 08:43 UTC`
- Last successful sync: `2026-05-28 08:43 UTC`
- Raw packets captured: `1214` from `2026-05-27 11:37 UTC` to `2026-05-28 08:43 UTC`

