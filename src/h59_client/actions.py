"""One-shot device actions for the H59."""

from __future__ import annotations

import asyncio

from h59_client.ble import PacketTransport, read_device_versions
from h59_client import date_utils
from h59_client.devices import connect_target, resolve_single_target
from h59_client.protocol import (
    BATTERY_PACKET,
    BLINK_TWICE_PACKET,
    REBOOT_PACKET,
    CMD_BATTERY,
    CMD_SET_TIME,
    parse_battery,
    parse_capabilities,
    set_time_packet,
)


async def vibrate_h59(
    *,
    db_path: str,
    selector: str | None = None,
    name: str = "H59",
    scan_timeout: float = 20.0,
    repeat: int = 1,
    interval: float = 0.75,
) -> dict[str, object]:
    if repeat < 1:
        raise ValueError("repeat must be >= 1")
    if interval < 0:
        raise ValueError("interval must be >= 0")

    target = await resolve_single_target(db_path=db_path, selector=selector, name=name, scan_timeout=scan_timeout)
    client = await connect_target(target)
    try:
        transport = PacketTransport(client)
        await transport.start()
        try:
            for index in range(repeat):
                await transport.send_packet(BLINK_TWICE_PACKET)
                if index + 1 < repeat:
                    await asyncio.sleep(interval)
        finally:
            await transport.stop()
    finally:
        await client.disconnect()

    return {
        "address": target.address,
        "name": target.name,
        "nickname": target.nickname,
        "repeat": repeat,
        "packet_hex": BLINK_TWICE_PACKET.hex(),
    }


async def reboot_h59(
    *,
    db_path: str,
    selector: str | None = None,
    name: str = "H59",
    scan_timeout: float = 20.0,
) -> dict[str, object]:
    target = await resolve_single_target(db_path=db_path, selector=selector, name=name, scan_timeout=scan_timeout)
    client = await connect_target(target)
    try:
        transport = PacketTransport(client)
        await transport.start()
        try:
            await transport.send_packet(REBOOT_PACKET)
        finally:
            await transport.stop()
    finally:
        await client.disconnect()

    return {
        "address": target.address,
        "name": target.name,
        "nickname": target.nickname,
        "packet_hex": REBOOT_PACKET.hex(),
    }


async def fetch_capabilities_h59(
    *,
    db_path: str,
    selector: str | None = None,
    name: str = "H59",
    scan_timeout: float = 20.0,
    device_clock_mode: str = "utc",
) -> dict[str, object]:
    target = await resolve_single_target(db_path=db_path, selector=selector, name=name, scan_timeout=scan_timeout)
    client = await connect_target(target)
    try:
        transport = PacketTransport(client)
        await transport.start()
        try:
            target_time = date_utils.local_now() if device_clock_mode == "local" else date_utils.utc_now()
            await transport.send_packet(set_time_packet(target_time))
            packet, _observed_at = (await transport.read_command_packets(CMD_SET_TIME))[0]
        finally:
            await transport.stop()
    finally:
        await client.disconnect()

    return {
        "address": target.address,
        "name": target.name,
        "nickname": target.nickname,
        "packet_hex": packet.hex(),
        "capabilities": parse_capabilities(packet),
    }


async def fetch_device_info_h59(
    *,
    db_path: str,
    selector: str | None = None,
    name: str = "H59",
    scan_timeout: float = 20.0,
) -> dict[str, object]:
    target = await resolve_single_target(db_path=db_path, selector=selector, name=name, scan_timeout=scan_timeout)
    client = await connect_target(target)
    try:
        hw_version, fw_version = await read_device_versions(client)

        transport = PacketTransport(client)
        await transport.start()
        try:
            await transport.send_packet(BATTERY_PACKET)
            packet, _observed_at = (await transport.read_command_packets(CMD_BATTERY))[0]
            battery = parse_battery(packet)
        finally:
            await transport.stop()
    finally:
        await client.disconnect()

    return {
        "address": target.address,
        "name": target.name,
        "nickname": target.nickname,
        "hw_version": hw_version,
        "fw_version": fw_version,
        "advertisement": target.advertisement,
        "battery_level": battery.battery_level,
        "charging": battery.charging,
    }
