"""Live sync primitives for the H59 bracelet."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

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
    HrvHistoryParser,
    NoData,
    PressureHistoryParser,
    REALTIME_NAME_MAP,
    bigdata_request_packet,
    parse_battery,
    parse_bigdata_blood_oxygen,
    parse_bigdata_sleep,
    parse_capabilities,
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

INITIAL_BACKFILL_MAX_DAYS = 60
INITIAL_BACKFILL_STOP_AFTER_EMPTY_DAYS = 2


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
                        samples = await _query_realtime(transport, metric_name, samples=realtime_samples)
                        if samples:
                            observed_at = samples[-1][2]
                            database.record_realtime_samples(
                                device_id,
                                sync_id,
                                observed_at=observed_at,
                                samples=[(sample, raw_packet_hex) for sample, raw_packet_hex, _ in samples],
                            )
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
        )
        results.append(result)
    return results


def main() -> None:
    from h59_client.cli import legacy_sync_main

    raise SystemExit(legacy_sync_main())


if __name__ == "__main__":
    main()
