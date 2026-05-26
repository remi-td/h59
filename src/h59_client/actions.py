"""One-shot device actions for the H59."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from bleak import BleakClient

from h59_client.ble import PacketTransport, discover_h59, ensure_services, enumerate_services
from h59_client.protocol import (
    BATTERY_PACKET,
    BLINK_TWICE_PACKET,
    DEVICE_FW_UUID,
    DEVICE_HW_UUID,
    REBOOT_PACKET,
    CMD_BATTERY,
    CMD_SET_TIME,
    parse_battery,
    parse_capabilities,
    set_time_packet,
)


async def _connect_h59(name: str, scan_timeout: float) -> tuple[dict[str, object], BleakClient]:
    discovered = await discover_h59(name=name, timeout=scan_timeout)
    device = discovered["device"]
    client = BleakClient(device, timeout=20.0)
    await client.connect()
    try:
        await ensure_services(client)
        return discovered, client
    except Exception:
        await client.disconnect()
        raise


async def vibrate_h59(
    *,
    name: str = "H59",
    scan_timeout: float = 20.0,
    repeat: int = 1,
    interval: float = 0.75,
) -> dict[str, object]:
    if repeat < 1:
        raise ValueError("repeat must be >= 1")
    if interval < 0:
        raise ValueError("interval must be >= 0")

    discovered, client = await _connect_h59(name, scan_timeout)
    device = discovered["device"]
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
        "address": device.address,
        "name": device.name,
        "repeat": repeat,
        "packet_hex": BLINK_TWICE_PACKET.hex(),
    }


async def reboot_h59(
    *,
    name: str = "H59",
    scan_timeout: float = 20.0,
) -> dict[str, object]:
    discovered, client = await _connect_h59(name, scan_timeout)
    device = discovered["device"]
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
        "address": device.address,
        "name": device.name,
        "packet_hex": REBOOT_PACKET.hex(),
    }


async def fetch_capabilities_h59(
    *,
    name: str = "H59",
    scan_timeout: float = 20.0,
) -> dict[str, object]:
    discovered, client = await _connect_h59(name, scan_timeout)
    device = discovered["device"]
    try:
        transport = PacketTransport(client)
        await transport.start()
        try:
            await transport.send_packet(set_time_packet(datetime.now(UTC)))
            packet, _observed_at = (await transport.read_command_packets(CMD_SET_TIME))[0]
        finally:
            await transport.stop()
    finally:
        await client.disconnect()

    return {
        "address": device.address,
        "name": device.name,
        "packet_hex": packet.hex(),
        "capabilities": parse_capabilities(packet),
    }


async def fetch_device_info_h59(
    *,
    name: str = "H59",
    scan_timeout: float = 20.0,
) -> dict[str, object]:
    discovered, client = await _connect_h59(name, scan_timeout)
    device = discovered["device"]
    try:
        services = await enumerate_services(client)
        hw_version = None
        fw_version = None
        for service in services:
            for char in service.get("chars", []):
                if char.get("uuid") == DEVICE_HW_UUID:
                    hw_version = char.get("read_value_text") or None
                if char.get("uuid") == DEVICE_FW_UUID:
                    fw_version = char.get("read_value_text") or None

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
        "address": device.address,
        "name": device.name,
        "hw_version": hw_version,
        "fw_version": fw_version,
        "advertisement": discovered["advertisement"],
        "battery_level": battery.battery_level,
        "charging": battery.charging,
    }
