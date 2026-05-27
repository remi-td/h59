# H59 Health Dashboard Data Audit

- Generated at: 2026-05-27 21:28 UTC
- Database: `/Users/remi.turpaud/Code/h59/data/h59.sqlite`
- Device: `H59_7407` (`86B9D8D4-6CB2-E24D-815D-A141786F427B`)
- Device ID: `1`
- Selected day: `2026-05-27`
- Time basis: UTC day boundaries from the stored timestamps

## Daily Overview

- Steps: `3063`
- Distance: `1994`
- Calories-like field: `86080`
- Heart-rate samples: `199`
- Latest heart rate: `67 bpm`
- Last successful sync: `2026-05-27 20:53 UTC`
- Battery: `82%`

## Coverage Matrix

| Requirement | Data in DB | Current extraction/rule coverage | Remaining gap |
|---|---|---|---|
| Steps | Available | Partial: Daily totals and hourly buckets from stored activity summaries | No raw accelerometer history, no goal logic, calories unit still unvalidated |
| Heart rate | Available | Available: Latest/min/max/avg from historical 5-minute samples | No night-time segmentation or confidence scoring yet |
| Sleep | Available | Available: Sleep sessions and staged periods available | Stage semantics still provisional for some values; local-day presentation rules are still missing |
| Blood oxygen / SpO2 | Available | Partial: Historical min/max samples available (46 for selected day) | Sample timing and header semantics are still provisional; no night-time minimum rule yet |
| HRV | Available | Partial: Historical samples available (21 for selected day) | No baseline logic yet; vendor formula and physiological meaning still need validation |
| Stress | Available | Partial: Historical pressure/stress-like samples available (42 for selected day) | Need mapping from device metric to stress score and label |
| Blood pressure estimate | Partial | Missing: Device advertises support, but no stored observations exist | No historical sync path, no systolic/diastolic presentation rules, must remain labelled as estimated |
| Sport / activity record | Available | Partial: Sessions inferred from contiguous activity bins | No explicit sport type, no vendor session boundaries, no dedicated exercise table yet |
| One key measurement | Partial | Missing: Device advertises support, but no decoded observation exists | Need composite score extraction and component breakdown rules |
| Device status and sync quality | Available | Partial: Battery, last sync, sync completion counts, raw packet counts | No live connected/disconnected state persisted, no sync SLA rules yet |

## Daily Steps

- Activity bins on selected day: `12`
- First activity bin: `2026-05-27 07:00 UTC`
- Last activity bin: `2026-05-27 20:00 UTC`
- Notes: current stored activity summaries are hourly in this dataset; steps and distance are usable, and the calories-like field still needs unit validation against the app.

| Hour bucket | Steps |
|---|---|
| 07:00 | 169 |
| 08:00 | 24 |
| 09:00 | 97 |
| 10:00 | 204 |
| 11:00 | 34 |
| 12:00 | 207 |
| 15:00 | 132 |
| 16:00 | 293 |
| 17:00 | 351 |
| 18:00 | 187 |
| 19:00 | 1023 |
| 20:00 | 342 |

## Heart Rate

- Sample window: `2026-05-27 00:00 UTC` to `2026-05-27 20:45 UTC`
- Latest: `67 bpm` at `2026-05-27 20:45 UTC`
- Min / avg / max: `48 / 69.4 / 112 bpm`

## Sleep

- Sleep sessions stored: `3` total, `2` on selected day
- Latest session: `2026-05-26 23:40 UTC` to `2026-05-27 08:49 UTC`
- Latest duration: `09 h 09 min`

## Health Metrics

### Blood Oxygen / SpO2
- Historical samples: `46` total, `46` on selected day
- Latest historical sample: `min=97%`, `max=97%` at `2026-05-27 22:30 UTC`

### HRV
- Historical samples: `72` total, `21` on selected day
- Latest historical sample: `42` at `2026-05-27 11:00 UTC`

### Stress / Pressure-like
- Historical samples: `145` total, `42` on selected day
- Latest historical sample: `48` at `2026-05-27 22:30 UTC`

### Blood Pressure
- Not available in the current database.

### One Key Measurement
- Not available in the current database.

- No realtime metric samples are stored in this database.
- Device-advertised capability flags: `support_blood_pressure, support_hrv, support_menstruation, support_one_key_check, support_pressure, support_spo2, support_wechat`

## Data Quality and Completeness

- Window basis: last 24 hours for each fixed-interval series, ending at that series' latest stored measurement
### Heart rate
- Latest measurement: `2026-05-27 20:45 UTC` (interval `5 min`, samples in window `214`)
- Gaps detected in the last 24 hours:
  - `2026-05-26 20:50 UTC` to `2026-05-26 20:55 UTC` (`2` missing intervals)
  - `2026-05-26 21:10 UTC` to `2026-05-26 21:25 UTC` (`4` missing intervals)
  - `2026-05-26 21:40 UTC` to `2026-05-26 22:45 UTC` (`14` missing intervals)
  - `2026-05-26 23:00 UTC` to `2026-05-26 23:05 UTC` (`2` missing intervals)
  - `2026-05-26 23:30 UTC` to `2026-05-26 23:35 UTC` (`2` missing intervals)
  - `2026-05-27 10:35 UTC` to `2026-05-27 10:55 UTC` (`5` missing intervals)
  - `2026-05-27 11:45 UTC` to `2026-05-27 11:55 UTC` (`3` missing intervals)
  - `2026-05-27 13:20 UTC` to `2026-05-27 13:40 UTC` (`5` missing intervals)
  - `2026-05-27 14:00 UTC` to `2026-05-27 14:15 UTC` (`4` missing intervals)
  - `2026-05-27 14:25 UTC` to `2026-05-27 15:15 UTC` (`11` missing intervals)
  - `2026-05-27 18:30 UTC` to `2026-05-27 19:05 UTC` (`8` missing intervals)
  - `2026-05-27 19:15 UTC` to `2026-05-27 20:25 UTC` (`15` missing intervals)
### Activity steps
- Latest measurement: `2026-05-27 20:00 UTC` (interval `60 min`, samples in window `13`)
- Gaps detected in the last 24 hours:
  - `2026-05-26 21:00 UTC` to `2026-05-27 06:00 UTC` (`10` missing intervals)
  - `2026-05-27 13:00 UTC` to `2026-05-27 14:00 UTC` (`2` missing intervals)
### Activity distance
- Latest measurement: `2026-05-27 20:00 UTC` (interval `60 min`, samples in window `13`)
- Gaps detected in the last 24 hours:
  - `2026-05-26 21:00 UTC` to `2026-05-27 06:00 UTC` (`10` missing intervals)
  - `2026-05-27 13:00 UTC` to `2026-05-27 14:00 UTC` (`2` missing intervals)
### Activity calories-like
- Latest measurement: `2026-05-27 20:00 UTC` (interval `60 min`, samples in window `13`)
- Gaps detected in the last 24 hours:
  - `2026-05-26 21:00 UTC` to `2026-05-27 06:00 UTC` (`10` missing intervals)
  - `2026-05-27 13:00 UTC` to `2026-05-27 14:00 UTC` (`2` missing intervals)
### Blood oxygen min
- Latest measurement: `2026-05-27 22:30 UTC` (interval `30 min`, samples in window `46`)
- No gaps detected in the last 24 hours.
### Blood oxygen max
- Latest measurement: `2026-05-27 22:30 UTC` (interval `30 min`, samples in window `46`)
- No gaps detected in the last 24 hours.
### Stress / pressure-like
- Latest measurement: `2026-05-27 22:30 UTC` (interval `30 min`, samples in window `42`)
- Gaps detected in the last 24 hours:
  - `2026-05-27 13:30 UTC` to `2026-05-27 15:00 UTC` (`4` missing intervals)
### HRV
- Latest measurement: `2026-05-27 11:00 UTC` (interval `30 min`, samples in window `21`)
- Gaps detected in the last 24 hours:
  - `2026-05-27 07:00 UTC` to `2026-05-27 07:30 UTC` (`2` missing intervals)

## Statistical Analysis

Window basis: last 24 hours for each fixed-interval series, ending at that series' latest stored measurement.

| Measurement | Samples | Median | P5 | P95 | Min | Max |
|---|---|---|---|---|---|---|
| Heart rate | 214 | 68 | 56.6 | 88 | 48 | 112 |
| Activity steps | 13 | 204 | 30 | 701.4 | 24 | 1023 |
| Activity distance | 13 | 125 | 17.2 | 460.4 | 13 | 716 |
| Activity calories-like | 13 | 5390 | 762 | 19880.0 | 570 | 30980 |
| Blood oxygen min | 46 | 98.5 | 96 | 99 | 1 | 99 |
| Blood oxygen max | 46 | 99 | 96.2 | 99 | 96 | 99 |
| Stress / pressure-like | 42 | 40 | 30 | 61 | 25 | 65 |
| HRV | 21 | 43 | 34 | 49 | 33 | 50 |

## Sport / Activity Sessions

| Session start | Session end | Duration | Steps | Distance | Calories-like | Avg HR |
|---|---|---|---|---|---|---|
| 2026-05-27 07:00 UTC | 2026-05-27 07:15 UTC | 15 min | 169 | 121 | 5230 | 62.7 |
| 2026-05-27 08:00 UTC | 2026-05-27 08:15 UTC | 15 min | 24 | 13 | 570 | 69.3 |
| 2026-05-27 09:00 UTC | 2026-05-27 09:15 UTC | 15 min | 97 | 61 | 2640 | 74.7 |
| 2026-05-27 10:00 UTC | 2026-05-27 10:15 UTC | 15 min | 204 | 125 | 5390 | 72.0 |
| 2026-05-27 11:00 UTC | 2026-05-27 11:15 UTC | 15 min | 34 | 20 | 890 | 75.7 |
| 2026-05-27 12:00 UTC | 2026-05-27 12:15 UTC | 15 min | 207 | 138 | 5950 | 72.3 |
| 2026-05-27 15:00 UTC | 2026-05-27 15:15 UTC | 15 min | 132 | 80 | 3450 | n/a |
| 2026-05-27 16:00 UTC | 2026-05-27 16:15 UTC | 15 min | 293 | 188 | 8120 | 75.0 |
| 2026-05-27 17:00 UTC | 2026-05-27 17:15 UTC | 15 min | 351 | 205 | 8780 | 74.7 |
| 2026-05-27 18:00 UTC | 2026-05-27 18:15 UTC | 15 min | 187 | 118 | 5080 | 87.3 |
| 2026-05-27 19:00 UTC | 2026-05-27 19:15 UTC | 15 min | 1023 | 716 | 30980 | 77.0 |
| 2026-05-27 20:00 UTC | 2026-05-27 20:15 UTC | 15 min | 342 | 209 | 9000 | n/a |
- These sessions are inferred from contiguous stored activity summaries, not explicit device sport records.

## Device and Sync Status

- Battery sample: `82%`, charging=`False` at `2026-05-27 20:53 UTC`
- Sync runs: `17` total, `17` completed, `0` incomplete
- Last sync start: `2026-05-27 20:53 UTC`
- Last successful sync: `2026-05-27 20:53 UTC`
- Raw packets captured: `1112` from `2026-05-27 11:37 UTC` to `2026-05-27 20:53 UTC`

