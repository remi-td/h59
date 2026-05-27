# H59 Health Dashboard Data Audit

- Generated at: 2026-05-27 21:05 UTC
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
| Steps | Available | Partial: Daily totals and hourly buckets from 15-minute activity bins | No raw accelerometer history, no goal logic, calories unit still unvalidated |
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
- Notes: steps and distance are usable; the calories-like field still needs unit validation against the app.

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

## Blood Oxygen, HRV, Stress, Blood Pressure, One Key

- No realtime metric samples are stored in this database.
- Device-advertised capability flags: `support_blood_pressure, support_hrv, support_menstruation, support_one_key_check, support_pressure, support_spo2, support_wechat`

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
- These sessions are inferred from contiguous 15-minute activity bins, not explicit device sport records.

## Device and Sync Status

- Battery sample: `82%`, charging=`False` at `2026-05-27 20:53 UTC`
- Sync runs: `17` total, `17` completed, `0` incomplete
- Last sync start: `2026-05-27 20:53 UTC`
- Last successful sync: `2026-05-27 20:53 UTC`
- Raw packets captured: `1112` from `2026-05-27 11:37 UTC` to `2026-05-27 20:53 UTC`

## What Is Still Missing

- No raw accelerometer history is stored. Current activity data is already aggregated into 15-minute bins.
- Historical samples are now stored for SpO2=`46`, HRV=`72`, pressure/stress-like=`145`.
- No rule layer exists yet for daily goals, night-time windows, baseline HRV, stress labels, or blood-pressure presentation.
- Timestamps are still reported against UTC storage days; local-day normalization for dashboard display is not implemented.

## Suggested Next Rules To Implement

1. Normalize report dates into the user timezone before building daily cards.
2. Normalize UTC storage days into the user timezone before building daily cards.
3. Validate sleep stage semantics, SpO2 sample timing, and pressure/stress naming against more captures.
4. Validate the calories field against the vendor app before exposing it as kcal.
5. Investigate historical blood-pressure extraction and decide whether inferred activity sessions are sufficient for the first sport card.
