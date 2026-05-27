"""Device registry and targeting helpers for H59 operations."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from bleak import BleakClient

from h59_client.ble import discover_h59, discover_h59_devices, ensure_services
from h59_client import date_utils
from h59_client.storage import H59Database


MAC_ADDRESS_RE = re.compile(r"^(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$")
UUID_ADDRESS_RE = re.compile(r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$")


@dataclass
class DeviceTarget:
    address: str
    name: str | None = None
    nickname: str | None = None
    device_id: int | None = None
    advertisement: dict[str, Any] | None = None
    score: int | None = None
    device: Any | None = None


def row_to_target(row: Any) -> DeviceTarget:
    return DeviceTarget(
        address=str(row["address"]),
        name=row["name"],
        nickname=row["nickname"],
        device_id=int(row["device_id"]),
    )


async def discover_targets(name: str | None = "H59", timeout: float = 20.0) -> list[DeviceTarget]:
    matches = await discover_h59_devices(name=name, timeout=timeout)
    return [
        DeviceTarget(
            address=entry["device"].address,
            name=entry["advertisement"].get("local_name") or entry["device"].name,
            advertisement=entry["advertisement"],
            score=entry["score"],
            device=entry["device"],
        )
        for entry in matches
    ]


async def discover_target(name: str | None = "H59", timeout: float = 20.0) -> DeviceTarget:
    entry = await discover_h59(name=name, timeout=timeout)
    return DeviceTarget(
        address=entry["device"].address,
        name=entry["advertisement"].get("local_name") or entry["device"].name,
        advertisement=entry["advertisement"],
        score=entry["score"],
        device=entry["device"],
    )


def resolve_known_target(db_path: str, selector: str) -> DeviceTarget | None:
    database = H59Database(db_path)
    try:
        row = database.get_device_by_selector(selector)
        if row is None:
            return None
        return row_to_target(row)
    finally:
        database.close()


def resolve_preferred_known_target(db_path: str, *, name: str | None) -> DeviceTarget | None:
    database = H59Database(db_path)
    try:
        row = database.get_preferred_device(name=name)
        if row is None:
            return None
        return row_to_target(row)
    finally:
        database.close()


def looks_like_device_address(selector: str) -> bool:
    return bool(MAC_ADDRESS_RE.fullmatch(selector) or UUID_ADDRESS_RE.fullmatch(selector))


async def resolve_single_target(
    *,
    db_path: str,
    selector: str | None,
    name: str = "H59",
    scan_timeout: float = 20.0,
) -> DeviceTarget:
    if selector:
        known = resolve_known_target(db_path, selector)
        if known is not None:
            return known
        if looks_like_device_address(selector):
            return DeviceTarget(address=selector, name=name)
        raise ValueError(f"unknown device selector: {selector}")
    preferred = resolve_preferred_known_target(db_path, name=name)
    if preferred is not None:
        return preferred
    return await discover_target(name=name, timeout=scan_timeout)


async def connect_target(target: DeviceTarget, *, timeout: float = 20.0) -> BleakClient:
    client = BleakClient(target.device or target.address, timeout=timeout)
    await client.connect()
    try:
        await ensure_services(client)
        return client
    except Exception:
        await client.disconnect()
        raise


async def discover_and_store_targets(
    *,
    db_path: str,
    name: str = "H59",
    scan_timeout: float = 20.0,
) -> list[DeviceTarget]:
    targets = await discover_targets(name=name, timeout=scan_timeout)
    database = H59Database(db_path)
    try:
        for target in targets:
            target.device_id = database.upsert_device(
                address=target.address,
                name=target.name,
                advertisement=target.advertisement,
                hw_version=None,
                fw_version=None,
                last_seen_at=date_utils.utc_now(),
            )
        return targets
    finally:
        database.close()
