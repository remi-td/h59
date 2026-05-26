"""Live sync primitives for the H59 bracelet."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

from bleak import BleakClient

from h59_client import date_utils
from h59_client.ble import PacketTransport, discover_h59, ensure_services, enumerate_services
from h59_client.protocol import (
    BATTERY_PACKET,
    CMD_BATTERY,
    CMD_HEART_RATE_LOG_SETTINGS,
    CMD_READ_HEART_RATE,
    CMD_START_REAL_TIME,
    CMD_GET_STEP_SOMEDAY,
    READ_HEART_RATE_LOG_SETTINGS_PACKET,
    ActivityBlockParser,
    HeartRateDayParser,
    NoData,
    REALTIME_NAME_MAP,
    parse_battery,
    parse_capabilities,
    parse_heart_rate_log_settings,
    parse_realtime_packet,
    read_heart_rate_packet,
    read_steps_packet,
    set_time_packet,
    start_realtime_packet,
    stop_realtime_packet,
    DEVICE_FW_UUID,
    DEVICE_HW_UUID,
    CMD_SET_TIME,
)
from h59_client.storage import H59Database


def _extract_device_info(services: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    hw_version = None
    fw_version = None
    for service in services:
        for char in service.get("chars", []):
            if char.get("uuid") == DEVICE_HW_UUID:
                hw_version = char.get("read_value_text") or None
            if char.get("uuid") == DEVICE_FW_UUID:
                fw_version = char.get("read_value_text") or None
    return hw_version, fw_version


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


async def _query_capabilities(transport: PacketTransport):
    await transport.send_packet(set_time_packet(date_utils.utc_now()))
    packet, observed_at = (await transport.read_command_packets(CMD_SET_TIME))[0]
    return parse_capabilities(packet), packet.hex(), observed_at


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


async def sync_h59(
    *,
    db_path: str | Path,
    name: str = "H59",
    scan_timeout: float = 20.0,
    incremental: bool = False,
    capture_capabilities: bool = True,
    realtime_metrics: list[str] | None = None,
    realtime_samples: int = 3,
) -> dict[str, Any]:
    discovered = await discover_h59(name=name, timeout=scan_timeout)
    device = discovered["device"]
    advertisement = discovered["advertisement"]
    database = H59Database(db_path)

    try:
        async with BleakClient(device, timeout=20.0) as client:
            await ensure_services(client)
            services = await enumerate_services(client)
            hw_version, fw_version = _extract_device_info(services)
            now = date_utils.utc_now()

            device_id = database.upsert_device(
                address=device.address,
                name=advertisement.get("local_name") or device.name,
                advertisement=advertisement,
                hw_version=hw_version,
                fw_version=fw_version,
                last_seen_at=now.isoformat(),
            )
            last_sync_at = database.get_latest_sync_timestamp(device_id) if incremental else None
            sync_id = database.create_sync(
                device_id,
                started_at=now.isoformat(),
                source="h59_client.sync",
            )

            database.record_gatt_snapshot(device_id, sync_id, observed_at=now.isoformat(), services=services)

            def record_packet(direction: str, channel_uuid: str, payload: bytearray, observed_at: str) -> None:
                command_id = payload[0] if payload else None
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
            await transport.start()
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

                if capture_capabilities:
                    capabilities, capability_packet_hex, capability_ts = await _query_capabilities(transport)
                    database.record_capabilities(
                        device_id,
                        sync_id,
                        timestamp=capability_ts,
                        capabilities=capabilities,
                        raw_packet_hex=capability_packet_hex,
                    )

                targets = determine_sync_dates(now=now, last_sync_at=last_sync_at, incremental=incremental)
                for target in targets:
                    hr_day, hr_packets, _ = await _query_heart_rate_day(transport, target=target)
                    if not isinstance(hr_day, NoData):
                        database.record_heart_rate_day(
                            device_id,
                            sync_id,
                            day=hr_day,
                            raw_packet_hex=",".join(hr_packets),
                        )

                    day_offset = (date_utils.start_of_day(now).date() - date_utils.start_of_day(target).date()).days
                    blocks, block_packets, _ = await _query_steps(transport, day_offset=day_offset)
                    if not isinstance(blocks, NoData):
                        database.record_activity_blocks(
                            device_id,
                            sync_id,
                            blocks=blocks,
                            raw_packet_hex=",".join(block_packets),
                        )

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
                await transport.stop()
                database.finish_sync(sync_id, finished_at=date_utils.utc_now().isoformat())

        return {
            "device_id": device_id,
            "sync_id": sync_id,
            "address": device.address,
            "db_path": str(db_path),
            "queried_days": len(targets),
            "incremental": incremental,
            "last_sync_at": last_sync_at.isoformat() if last_sync_at is not None else None,
        }
    finally:
        database.close()


def main() -> None:
    from h59_client.cli import legacy_sync_main
    raise SystemExit(legacy_sync_main())


if __name__ == "__main__":
    main()
