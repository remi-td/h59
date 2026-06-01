"""Live sync primitives for the H59 bracelet."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from h59_client import date_utils
from h59_client.ble import BigDataTransport, PacketTransport, enumerate_services, read_device_versions
from h59_client.devices import DeviceTarget, connect_target, discover_targets, resolve_single_target
from h59_client.protocol import (
    BATTERY_PACKET,
    BIGDATA_BLOOD_OXYGEN_ID,
    BIGDATA_MAGIC,
    BIGDATA_SERVICE_UUID,
    BIGDATA_SLEEP_ID,
    CMD_BATTERY,
    CMD_GET_STEP_SOMEDAY,
    CMD_HEART_RATE_LOG_SETTINGS,
    CMD_HRV_HISTORY,
    CMD_PRESSURE_HISTORY,
    CMD_READ_HEART_RATE,
    CMD_SET_TIME,
    CMD_START_REAL_TIME,
    READ_HEART_RATE_LOG_SETTINGS_PACKET,
    ActivityBlockParser,
    HeartRateDayParser,
    HealthCheckSample,
    HrvHistoryParser,
    NoData,
    PressureHistoryParser,
    REALTIME_NAME_MAP,
    RealTimeMetric,
    bigdata_request_packet,
    parse_battery,
    parse_bigdata_blood_oxygen,
    parse_bigdata_sleep,
    parse_capabilities,
    parse_health_check_packet,
    parse_heart_rate_log_settings,
    parse_realtime_packet,
    read_heart_rate_packet,
    read_hrv_history_packet,
    read_pressure_history_packet,
    read_steps_packet,
    set_time_packet,
    start_realtime_packet,
    stop_realtime_packet,
)
from h59_client.storage import H59Database
from h59_client.storage import RealtimeObservation

INITIAL_BACKFILL_MAX_DAYS = 60
INITIAL_BACKFILL_STOP_AFTER_EMPTY_DAYS = 2
ONE_SHOT_REALTIME_METRICS = frozenset({"health-check", "spo2"})


def device_clock_now(mode: str) -> datetime:
    if mode == "local":
        return date_utils.local_now()
    if mode == "utc":
        return date_utils.utc_now()
    raise ValueError(f"unsupported device clock mode: {mode}")


def determine_history_selector(*, now: datetime, target: datetime) -> int:
    day_offset = (date_utils.start_of_day(now).date() - date_utils.start_of_day(target).date()).days
    if day_offset < 0:
        raise ValueError("target cannot be in the future")
    return day_offset


async def _query_battery(transport: PacketTransport):
    await transport.send_packet(BATTERY_PACKET)
    packet, observed_at = (await transport.read_command_packets(CMD_BATTERY))[0]
    return parse_battery(packet), packet.hex(), observed_at


async def _query_hr_settings(transport: PacketTransport):
    await transport.send_packet(READ_HEART_RATE_LOG_SETTINGS_PACKET)
    packet, observed_at = (await transport.read_command_packets(CMD_HEART_RATE_LOG_SETTINGS))[0]
    return parse_heart_rate_log_settings(packet), packet.hex(), observed_at


async def _query_steps(transport: PacketTransport, *, day_offset: int):
    parser = ActivityBlockParser()
    await transport.send_packet(read_steps_packet(day_offset))
    packets: list[str] = []
    observed_at = date_utils.utc_now().isoformat()
    while True:
        packet, observed_at = (await transport.read_command_packets(CMD_GET_STEP_SOMEDAY))[0]
        packets.append(packet.hex())
        parsed = parser.parse(packet)
        if parsed is None:
            continue
        return parsed, packets, observed_at


async def _query_heart_rate_day(transport: PacketTransport, *, target: datetime):
    parser = HeartRateDayParser()
    await transport.send_packet(read_heart_rate_packet(target))
    packets: list[str] = []
    observed_at = date_utils.utc_now().isoformat()
    while True:
        packet, observed_at = (await transport.read_command_packets(CMD_READ_HEART_RATE))[0]
        packets.append(packet.hex())
        parsed = parser.parse(packet)
        if parsed is None:
            continue
        return parsed, packets, observed_at


async def _query_capabilities(transport: PacketTransport, *, device_clock_mode: str):
    await transport.send_packet(set_time_packet(device_clock_now(device_clock_mode)))
    packet, observed_at = (await transport.read_command_packets(CMD_SET_TIME))[0]
    return parse_capabilities(packet), packet.hex(), observed_at


async def _query_pressure_history(transport: PacketTransport, *, now: datetime, target: datetime):
    parser = PressureHistoryParser()
    await transport.send_packet(read_pressure_history_packet(determine_history_selector(now=now, target=target)))
    packets: list[str] = []
    observed_at = date_utils.utc_now().isoformat()
    while True:
        packet, observed_at = (await transport.read_command_packets(CMD_PRESSURE_HISTORY))[0]
        packets.append(packet.hex())
        parsed = parser.parse(packet)
        if parsed is None:
            continue
        return parsed, packets, observed_at, target


async def _query_hrv_history(transport: PacketTransport, *, now: datetime, target: datetime):
    parser = HrvHistoryParser()
    await transport.send_packet(read_hrv_history_packet(determine_history_selector(now=now, target=target)))
    packets: list[str] = []
    observed_at = date_utils.utc_now().isoformat()
    while True:
        packet, observed_at = (await transport.read_command_packets(CMD_HRV_HISTORY))[0]
        packets.append(packet.hex())
        parsed = parser.parse(packet)
        if parsed is None:
            continue
        return parsed, packets, observed_at, target


async def _query_bigdata_sleep(transport: BigDataTransport):
    await transport.send_packet(bigdata_request_packet(BIGDATA_SLEEP_ID))
    payload, observed_at = await transport.read_data_payload(BIGDATA_SLEEP_ID)
    return parse_bigdata_sleep(payload), payload.hex(), observed_at


async def _query_bigdata_blood_oxygen(transport: BigDataTransport, *, target: datetime):
    await transport.send_packet(bigdata_request_packet(BIGDATA_BLOOD_OXYGEN_ID))
    payload, observed_at = await transport.read_data_payload(BIGDATA_BLOOD_OXYGEN_ID)
    return parse_bigdata_blood_oxygen(payload), payload.hex(), observed_at, target


async def _query_realtime(transport: PacketTransport, metric_name: str, *, samples: int):
    metric = REALTIME_NAME_MAP[metric_name]
    await transport.send_packet(start_realtime_packet(metric))
    out = []
    for _ in range(samples):
        packet, observed_at = (await transport.read_command_packets(CMD_START_REAL_TIME))[0]
        out.append((parse_realtime_packet(packet), packet.hex(), observed_at))
    await transport.send_packet(stop_realtime_packet(metric))
    return out


async def _query_realtime_controlled(
    transport: PacketTransport,
    metric_name: str,
    *,
    samples: int,
    duration_seconds: float | None = None,
    hard_timeout: float | None = None,
    stop_on_idle: bool = False,
    should_stop: Callable[[], bool] | None = None,
    idle_timeout: float = 5.0,
    poll_timeout: float = 1.0,
    on_sample: Callable[[str, dict[str, Any]], None] | None = None,
):
    if duration_seconds is None and should_stop is None and hard_timeout is None and not stop_on_idle:
        return await _query_realtime(transport, metric_name, samples=samples)

    metric = REALTIME_NAME_MAP[metric_name]
    await transport.send_packet(start_realtime_packet(metric))
    out = []
    started = asyncio.get_running_loop().time()
    last_packet_at = started
    try:
        while True:
            if should_stop is not None and should_stop():
                break
            if duration_seconds is not None and (asyncio.get_running_loop().time() - started) >= duration_seconds:
                break
            if hard_timeout is not None and (asyncio.get_running_loop().time() - started) >= hard_timeout:
                break
            remaining = poll_timeout
            if duration_seconds is not None:
                remaining = min(remaining, max(0.1, duration_seconds - (asyncio.get_running_loop().time() - started)))
            if hard_timeout is not None:
                remaining = min(remaining, max(0.1, hard_timeout - (asyncio.get_running_loop().time() - started)))
            try:
                packet, observed_at = (await transport.read_command_packets(CMD_START_REAL_TIME, expected=1, timeout=remaining))[0]
            except TimeoutError:
                if stop_on_idle and out and asyncio.get_running_loop().time() - last_packet_at >= idle_timeout:
                    break
                continue
            parsed = parse_realtime_packet(packet)
            raw_packet_hex = packet.hex()
            out.append((parsed, raw_packet_hex, observed_at))
            last_packet_at = asyncio.get_running_loop().time()
            if on_sample is not None:
                on_sample(
                    metric_name,
                    {
                        "timestamp": observed_at,
                        "value": parsed.value,
                        "error_code": parsed.error_code,
                        "raw_packet_hex": raw_packet_hex,
                    },
                )
        return out
    finally:
        await transport.send_packet(stop_realtime_packet(metric))


async def _query_health_check(
    transport: PacketTransport,
    *,
    hard_timeout: float | None = 40.0,
    stop_on_idle: bool = True,
    should_stop: Callable[[], bool] | None = None,
    idle_timeout: float = 5.0,
    on_sample: Callable[[str, dict[str, Any]], None] | None = None,
) -> tuple[list[tuple[HealthCheckSample, str, str]], tuple[HealthCheckSample, str, str] | None]:
    metric = RealTimeMetric.HEALTH_CHECK
    await transport.send_packet(start_realtime_packet(metric))
    out: list[tuple[HealthCheckSample, str, str]] = []
    final_reading: tuple[HealthCheckSample, str, str] | None = None
    started = asyncio.get_running_loop().time()
    last_packet_at = started
    try:
        while True:
            if should_stop is not None and should_stop():
                break
            if hard_timeout is not None and (asyncio.get_running_loop().time() - started) >= hard_timeout:
                break
            remaining = idle_timeout
            if hard_timeout is not None:
                remaining = min(remaining, max(0.1, hard_timeout - (asyncio.get_running_loop().time() - started)))
            try:
                packet, observed_at = (await transport.read_command_packets(CMD_START_REAL_TIME, expected=1, timeout=remaining))[0]
            except TimeoutError:
                if stop_on_idle and out and asyncio.get_running_loop().time() - last_packet_at >= idle_timeout:
                    break
                continue
            parsed = parse_health_check_packet(packet)
            raw_packet_hex = packet.hex()
            captured = (parsed, raw_packet_hex, observed_at)
            out.append(captured)
            last_packet_at = asyncio.get_running_loop().time()
            if on_sample is not None:
                on_sample(
                    "health-check",
                    {
                        "timestamp": observed_at,
                        "cuff_pressure_tenths": parsed.cuff_pressure_tenths,
                        "diastolic": parsed.diastolic,
                        "systolic": parsed.systolic,
                        "heart_rate": parsed.heart_rate,
                        "error_code": parsed.error_code,
                        "raw_packet_hex": raw_packet_hex,
                    },
                )
            if parsed.has_blood_pressure_result:
                final_reading = captured
        return out, final_reading
    finally:
        await transport.send_packet(stop_realtime_packet(metric))


def _health_check_observations(
    samples: list[tuple[HealthCheckSample, str, str]],
    final_reading: tuple[HealthCheckSample, str, str] | None,
) -> tuple[list[RealtimeObservation], dict[str, Any]]:
    observations: list[RealtimeObservation] = []
    for sample, raw_packet_hex, observed_at in samples:
        observations.append(
            RealtimeObservation(
                metric_code="health-check.cuff-pressure-tenths",
                timestamp=observed_at,
                value_numeric=int(sample.cuff_pressure_tenths),
                error_code=int(sample.error_code),
                raw_packet_hex=raw_packet_hex,
                source_command=CMD_START_REAL_TIME,
            )
        )
    result_summary = None
    if final_reading is not None:
        sample, raw_packet_hex, observed_at = final_reading
        if sample.diastolic is not None:
            observations.append(
                RealtimeObservation(
                    metric_code="health-check.diastolic",
                    timestamp=observed_at,
                    value_numeric=int(sample.diastolic),
                    error_code=int(sample.error_code),
                    raw_packet_hex=raw_packet_hex,
                    source_command=CMD_START_REAL_TIME,
                )
            )
        if sample.systolic is not None:
            observations.append(
                RealtimeObservation(
                    metric_code="health-check.systolic",
                    timestamp=observed_at,
                    value_numeric=int(sample.systolic),
                    error_code=int(sample.error_code),
                    raw_packet_hex=raw_packet_hex,
                    source_command=CMD_START_REAL_TIME,
                )
            )
        if sample.heart_rate is not None:
            observations.append(
                RealtimeObservation(
                    metric_code="health-check.heart-rate",
                    timestamp=observed_at,
                    value_numeric=int(sample.heart_rate),
                    error_code=int(sample.error_code),
                    raw_packet_hex=raw_packet_hex,
                    source_command=CMD_START_REAL_TIME,
                )
            )
        result_summary = {
            "diastolic": int(sample.diastolic) if sample.diastolic is not None else None,
            "systolic": int(sample.systolic) if sample.systolic is not None else None,
            "heart_rate": int(sample.heart_rate) if sample.heart_rate is not None else None,
            "timestamp": observed_at,
        }
    return observations, {"packets": len(samples), "final_result": result_summary}


def determine_sync_dates(
    *,
    now: datetime,
    last_sync_at: datetime | None,
    incremental: bool,
) -> list[datetime]:
    if incremental and last_sync_at is not None:
        start = date_utils.start_of_day(last_sync_at)
    else:
        start = date_utils.start_of_day(now)
    return list(date_utils.dates_between(start, now))


def determine_initial_backfill_dates(
    *,
    now: datetime,
    max_days: int = INITIAL_BACKFILL_MAX_DAYS,
) -> list[datetime]:
    if max_days < 1:
        raise ValueError("max_days must be >= 1")
    today = date_utils.start_of_day(now)
    return [today - timedelta(days=day_offset) for day_offset in range(max_days)]


async def sync_one_h59(
    *,
    db_path: str | Path,
    target: DeviceTarget,
    incremental: bool = False,
    device_clock_mode: str = "utc",
    capture_gatt: bool | None = None,
    realtime_metrics: list[str] | None = None,
    realtime_samples: int = 3,
    realtime_duration_seconds: int | None = None,
    realtime_should_stop: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    database = H59Database(db_path)

    try:
        client = await connect_target(target, timeout=20.0)
        try:
            now = date_utils.utc_now()
            hw_version, fw_version = await read_device_versions(client)
            services = None

            device_id = database.upsert_device(
                address=target.address,
                name=target.name,
                advertisement=target.advertisement,
                hw_version=hw_version,
                fw_version=fw_version,
                last_seen_at=now,
            )
            last_sync_at = database.get_latest_sync_timestamp(device_id) if incremental else None
            sync_id = database.create_sync(
                device_id,
                started_at=now,
                source="h59_client.sync",
            )

            should_capture_gatt = capture_gatt if capture_gatt is not None else not database.has_gatt_snapshot(device_id)
            if should_capture_gatt:
                services = await enumerate_services(client)
                database.record_gatt_snapshot(device_id, sync_id, observed_at=now, services=services)

            def record_packet(direction: str, channel_uuid: str, payload: bytearray, observed_at: str) -> None:
                command_id = None
                if payload:
                    if payload[0] == BIGDATA_MAGIC and len(payload) > 1:
                        command_id = payload[1]
                    else:
                        command_id = payload[0] & 127
                database.record_raw_packet(
                    device_id,
                    sync_id,
                    timestamp=observed_at,
                    direction=direction,
                    channel_uuid=channel_uuid,
                    packet_hex=payload.hex(),
                    command_id=command_id,
                )

            transport = PacketTransport(client, packet_callback=record_packet)
            bigdata_transport: BigDataTransport | None = None
            await transport.start()
            if client.services.get_service(BIGDATA_SERVICE_UUID) is not None:
                bigdata_transport = BigDataTransport(client, packet_callback=record_packet)
                await bigdata_transport.start()
            realtime_results: dict[str, Any] = {}
            try:
                battery_sample, battery_packet_hex, battery_ts = await _query_battery(transport)
                database.record_battery(device_id, sync_id, timestamp=battery_ts, sample=battery_sample, raw_packet_hex=battery_packet_hex)

                hr_settings, hr_settings_packet_hex, hr_settings_ts = await _query_hr_settings(transport)
                database.record_heart_rate_settings(
                    device_id,
                    sync_id,
                    timestamp=hr_settings_ts,
                    settings=hr_settings,
                    raw_packet_hex=hr_settings_packet_hex,
                )

                capabilities, capability_packet_hex, capability_ts = await _query_capabilities(
                    transport,
                    device_clock_mode=device_clock_mode,
                )
                database.record_capabilities(
                    device_id,
                    sync_id,
                    timestamp=capability_ts,
                    capabilities=capabilities,
                    raw_packet_hex=capability_packet_hex,
                )

                if bigdata_transport is not None:
                    sleep_sessions, sleep_payload_hex, _sleep_ts = await _query_bigdata_sleep(bigdata_transport)
                    if sleep_sessions:
                        database.record_sleep_sessions(
                            device_id,
                            sync_id,
                            reference=now,
                            sessions=sleep_sessions,
                            raw_packet_hex=sleep_payload_hex,
                            source_command=BIGDATA_SLEEP_ID,
                        )

                    blood_oxygen_history, blood_oxygen_payload_hex, _bo_ts, blood_oxygen_target = await _query_bigdata_blood_oxygen(
                        bigdata_transport,
                        target=now,
                    )
                    if blood_oxygen_history.samples:
                        database.record_blood_oxygen_history(
                            device_id,
                            sync_id,
                            target=blood_oxygen_target,
                            history=blood_oxygen_history,
                            raw_packet_hex=blood_oxygen_payload_hex,
                            source_command=BIGDATA_BLOOD_OXYGEN_ID,
                        )

                if incremental and last_sync_at is None:
                    targets = determine_initial_backfill_dates(now=now)
                    empty_history_streak = 0
                else:
                    targets = determine_sync_dates(now=now, last_sync_at=last_sync_at, incremental=incremental)
                    empty_history_streak = None

                attempted_days = 0
                pressure_history_exhausted = False
                hrv_history_exhausted = False
                for target_day in targets:
                    attempted_days += 1
                    day_offset = determine_history_selector(now=now, target=target_day)

                    if not pressure_history_exhausted:
                        pressure_history, pressure_packets, _pressure_ts, pressure_target = await _query_pressure_history(
                            transport,
                            now=now,
                            target=target_day,
                        )
                        if isinstance(pressure_history, NoData):
                            pressure_history_exhausted = day_offset > 0
                        else:
                            database.record_pressure_history(
                                device_id,
                                sync_id,
                                target=pressure_target,
                                history=pressure_history,
                                raw_packet_hex=",".join(pressure_packets),
                                source_command=CMD_PRESSURE_HISTORY,
                            )

                    if not hrv_history_exhausted:
                        hrv_history, hrv_packets, _hrv_ts, hrv_target = await _query_hrv_history(
                            transport,
                            now=now,
                            target=target_day,
                        )
                        if isinstance(hrv_history, NoData):
                            hrv_history_exhausted = day_offset > 0
                        else:
                            database.record_hrv_history(
                                device_id,
                                sync_id,
                                target=hrv_target,
                                history=hrv_history,
                                raw_packet_hex=",".join(hrv_packets),
                                source_command=CMD_HRV_HISTORY,
                            )

                    hr_day, hr_packets, _ = await _query_heart_rate_day(transport, target=target_day)
                    hr_has_data = not isinstance(hr_day, NoData)
                    if not isinstance(hr_day, NoData):
                        database.record_heart_rate_day(
                            device_id,
                            sync_id,
                            day=hr_day,
                            raw_packet_hex=",".join(hr_packets),
                        )

                    blocks, block_packets, _ = await _query_steps(transport, day_offset=day_offset)
                    steps_has_data = not isinstance(blocks, NoData)
                    if not isinstance(blocks, NoData):
                        database.record_activity_blocks(
                            device_id,
                            sync_id,
                            blocks=blocks,
                            raw_packet_hex=",".join(block_packets),
                        )

                    if empty_history_streak is not None:
                        if hr_has_data or steps_has_data:
                            empty_history_streak = 0
                        else:
                            empty_history_streak += 1
                            if empty_history_streak >= INITIAL_BACKFILL_STOP_AFTER_EMPTY_DAYS:
                                break

                if realtime_metrics:
                    for metric_name in realtime_metrics:
                        if metric_name == "health-check":
                            samples, final_reading = await _query_health_check(
                                transport,
                                hard_timeout=40.0,
                                stop_on_idle=True,
                                should_stop=None,
                            )
                            observations, realtime_results["health-check"] = _health_check_observations(samples, final_reading)
                            if observations:
                                database.record_realtime_observations(
                                    device_id,
                                    sync_id,
                                    observations=observations,
                                )
                            continue
                        if metric_name == "spo2":
                            samples = await _query_realtime_controlled(
                                transport,
                                metric_name,
                                samples=3,
                                hard_timeout=40.0,
                                stop_on_idle=True,
                            )
                            if samples:
                                observed_at = samples[-1][2]
                                database.record_realtime_samples(
                                    device_id,
                                    sync_id,
                                    observed_at=observed_at,
                                    samples=[(sample, raw_packet_hex) for sample, raw_packet_hex, _ in samples],
                                )
                                realtime_results[metric_name] = {
                                    "samples": len(samples),
                                    "last_timestamp": observed_at,
                                }
                            continue
                        samples = await _query_realtime_controlled(
                            transport,
                            metric_name,
                            samples=realtime_samples,
                            duration_seconds=float(realtime_duration_seconds) if realtime_duration_seconds is not None else None,
                            should_stop=realtime_should_stop,
                        )
                        if samples:
                            observed_at = samples[-1][2]
                            database.record_realtime_samples(
                                device_id,
                                sync_id,
                                observed_at=observed_at,
                                samples=[(sample, raw_packet_hex) for sample, raw_packet_hex, _ in samples],
                            )
                            realtime_results[metric_name] = {
                                "samples": len(samples),
                                "last_timestamp": observed_at,
                            }
            finally:
                if bigdata_transport is not None:
                    await bigdata_transport.stop()
                await transport.stop()
                database.finish_sync(sync_id, finished_at=date_utils.utc_now())
        finally:
            await client.disconnect()

        return {
            "device_id": device_id,
            "sync_id": sync_id,
            "address": target.address,
            "name": target.name,
            "nickname": target.nickname,
            "db_path": str(db_path),
            "queried_days": attempted_days,
            "incremental": incremental,
            "last_sync_at": last_sync_at.isoformat() if last_sync_at is not None else None,
            "captured_gatt": bool(should_capture_gatt),
            "realtime_results": realtime_results,
        }
    finally:
        database.close()


async def sync_h59(
    *,
    db_path: str | Path,
    selector: str | None = None,
    name: str = "H59",
    scan_timeout: float = 20.0,
    incremental: bool = False,
    device_clock_mode: str = "utc",
    capture_gatt: bool | None = None,
    realtime_metrics: list[str] | None = None,
    realtime_samples: int = 3,
    realtime_duration_seconds: int | None = None,
    realtime_should_stop: Callable[[], bool] | None = None,
) -> list[dict[str, Any]]:
    if selector:
        target = await resolve_single_target(
            db_path=str(db_path),
            selector=selector,
            name=name,
            scan_timeout=scan_timeout,
        )
        return [
            await sync_one_h59(
                db_path=db_path,
                target=target,
                incremental=incremental,
                device_clock_mode=device_clock_mode,
                capture_gatt=capture_gatt,
                realtime_metrics=realtime_metrics,
                realtime_samples=realtime_samples,
                realtime_duration_seconds=realtime_duration_seconds,
                realtime_should_stop=realtime_should_stop,
            )
        ]

    discovered_targets = await discover_targets(name=name, timeout=scan_timeout)
    if not discovered_targets:
        raise RuntimeError("No H59-like device found during scan")

    results = []
    for target in discovered_targets:
        result = await sync_one_h59(
            db_path=db_path,
            target=target,
            incremental=incremental,
            device_clock_mode=device_clock_mode,
            capture_gatt=capture_gatt,
            realtime_metrics=realtime_metrics,
            realtime_samples=realtime_samples,
            realtime_duration_seconds=realtime_duration_seconds,
            realtime_should_stop=realtime_should_stop,
        )
        results.append(result)
    return results


async def realtime_h59(
    *,
    db_path: str | Path,
    selector: str,
    metric_names: list[str],
    name: str = "H59",
    scan_timeout: float = 20.0,
    duration_seconds: int | None = None,
    should_stop: Callable[[], bool] | None = None,
    metric_start_hook: Callable[[str], Callable[[], bool] | None] | None = None,
    persist: bool = True,
    on_sample: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    database = H59Database(db_path) if persist else None
    try:
        target = await resolve_single_target(
            db_path=str(db_path),
            selector=selector,
            name=name,
            scan_timeout=scan_timeout,
        )
        client = await connect_target(target, timeout=20.0)
        try:
            now = date_utils.utc_now()
            hw_version = None
            fw_version = None
            device_id = None
            sync_id = None
            packet_callback = None
            if database is not None:
                hw_version, fw_version = await read_device_versions(client)
                device_id = database.upsert_device(
                    address=target.address,
                    name=target.name,
                    advertisement=target.advertisement,
                    hw_version=hw_version,
                    fw_version=fw_version,
                    last_seen_at=now,
                )
                sync_id = database.create_sync(
                    device_id,
                    started_at=now,
                    source="h59_client.realtime",
                )

                def record_packet(direction: str, channel_uuid: str, payload: bytearray, observed_at: str) -> None:
                    command_id = None
                    if payload:
                        if payload[0] == BIGDATA_MAGIC and len(payload) > 1:
                            command_id = payload[1]
                        else:
                            command_id = payload[0] & 127
                    database.record_raw_packet(
                        device_id,
                        sync_id,
                        timestamp=observed_at,
                        direction=direction,
                        channel_uuid=channel_uuid,
                        packet_hex=payload.hex(),
                        command_id=command_id,
                    )

                packet_callback = record_packet

            transport = PacketTransport(client, packet_callback=packet_callback)
            await transport.start()
            try:
                realtime_results: dict[str, Any] = {}
                for metric_name in metric_names:
                    if metric_name == "health-check":
                        samples, final_reading = await _query_health_check(
                            transport,
                            hard_timeout=40.0,
                            stop_on_idle=True,
                            should_stop=None,
                            on_sample=on_sample,
                        )
                        observations, realtime_results[metric_name] = _health_check_observations(samples, final_reading)
                        if database is not None and observations:
                            database.record_realtime_observations(device_id, sync_id, observations=observations)
                        continue
                    if metric_name == "spo2":
                        samples = await _query_realtime_controlled(
                            transport,
                            metric_name,
                            samples=3,
                            hard_timeout=40.0,
                            stop_on_idle=True,
                            should_stop=None,
                            on_sample=on_sample,
                        )
                        if database is not None and samples:
                            database.record_realtime_samples(
                                device_id,
                                sync_id,
                                observed_at=samples[-1][2],
                                samples=[(sample, raw_packet_hex) for sample, raw_packet_hex, _ in samples],
                            )
                        realtime_results[metric_name] = {
                            "samples": len(samples),
                            "last_timestamp": samples[-1][2] if samples else None,
                        }
                        continue
                    per_metric_should_stop = metric_start_hook(metric_name) if metric_start_hook is not None else should_stop
                    samples = await _query_realtime_controlled(
                        transport,
                        metric_name,
                        samples=3,
                        duration_seconds=float(duration_seconds) if duration_seconds is not None else None,
                        should_stop=per_metric_should_stop,
                        on_sample=on_sample,
                    )
                    if database is not None and samples:
                        database.record_realtime_samples(
                            device_id,
                            sync_id,
                            observed_at=samples[-1][2],
                            samples=[(sample, raw_packet_hex) for sample, raw_packet_hex, _ in samples],
                        )
                    realtime_results[metric_name] = {
                        "samples": len(samples),
                        "last_timestamp": samples[-1][2] if samples else None,
                    }
            finally:
                await transport.stop()
                if database is not None and sync_id is not None:
                    database.finish_sync(sync_id, finished_at=date_utils.utc_now())
        finally:
            await client.disconnect()
        return {
            "address": target.address,
            "name": target.name,
            "nickname": target.nickname,
            "db_path": str(db_path),
            "sync_id": sync_id,
            "persisted": persist,
            "realtime_results": realtime_results,
        }
    finally:
        if database is not None:
            database.close()


def main() -> None:
    from h59_client.cli import legacy_sync_main

    raise SystemExit(legacy_sync_main())


if __name__ == "__main__":
    main()
