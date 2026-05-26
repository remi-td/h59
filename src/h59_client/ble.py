"""BLE discovery and packet transport for the H59."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any, Callable

from bleak import BleakClient, BleakScanner

from h59_client.protocol import (
    BIGDATA_MAGIC,
    BIGDATA_RX_CHAR_UUID,
    BIGDATA_SERVICE_UUID,
    BIGDATA_TX_CHAR_UUID,
    UART_RX_CHAR_UUID,
    UART_SERVICE_UUID,
    UART_TX_CHAR_UUID,
)


def utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


async def discover_h59(name: str | None = None, timeout: float = 20.0) -> dict[str, Any]:
    devices = await BleakScanner.discover(timeout=timeout, return_adv=True)
    matches: list[tuple[int, Any, Any, dict[str, str]]] = []
    for device, adv in devices.values():
        local_name = adv.local_name or device.name or ""
        service_uuids = [value.lower() for value in (adv.service_uuids or [])]
        manufacturer = {f"0x{key:04x}": bytes(value).hex() for key, value in (adv.manufacturer_data or {}).items()}
        score = 0
        if name and local_name == name:
            score += 100
        elif name and name in local_name:
            score += 80
        if local_name.startswith("H59"):
            score += 60
        if "0000fe00-0000-1000-8000-00805f9b34fb" in service_uuids:
            score += 40
        if any(value.startswith("fee73031") for value in manufacturer.values()):
            score += 20
        if score:
            matches.append((score, device, adv, manufacturer))

    if not matches:
        raise RuntimeError("No H59-like device found during scan")

    matches.sort(key=lambda item: item[0], reverse=True)
    score, device, adv, manufacturer = matches[0]
    return {
        "score": score,
        "device": device,
        "advertisement": {
            "local_name": adv.local_name or device.name,
            "service_uuids": adv.service_uuids or [],
            "manufacturer_data": manufacturer,
            "service_data": {key: bytes(value).hex() for key, value in (adv.service_data or {}).items()},
            "rssi": getattr(adv, "rssi", None),
        },
    }


async def ensure_services(client: BleakClient) -> None:
    try:
        client.services
        return
    except Exception:
        pass

    try:
        await client.get_services()
    except Exception:
        pass


async def enumerate_services(client: BleakClient) -> list[dict[str, Any]]:
    services: list[dict[str, Any]] = []
    for service in client.services:
        entry = {"uuid": str(service.uuid), "description": getattr(service, "description", None), "chars": []}
        for char in service.characteristics:
            char_entry = {
                "uuid": str(char.uuid),
                "handle": getattr(char, "handle", None),
                "properties": list(char.properties),
            }
            if "read" in char.properties:
                try:
                    value = await client.read_gatt_char(char.uuid)
                    char_entry["read_value_hex"] = bytes(value).hex()
                    char_entry["read_value_text"] = bytes(value).decode("utf-8", errors="ignore")
                except Exception as exc:
                    char_entry["read_error"] = str(exc)
            entry["chars"].append(char_entry)
        services.append(entry)
    return services


class PacketTransport:
    def __init__(
        self,
        client: BleakClient,
        *,
        packet_callback: Callable[[str, str, bytearray, str], None] | None = None,
    ):
        self.client = client
        self.packet_callback = packet_callback
        self.queues: dict[int, asyncio.Queue[tuple[bytearray, str]]] = {}
        self.rx_char = None

    async def start(self) -> None:
        service = self.client.services.get_service(UART_SERVICE_UUID)
        if service is None:
            raise RuntimeError(f"UART service {UART_SERVICE_UUID} not found")
        self.rx_char = service.get_characteristic(UART_RX_CHAR_UUID)
        if self.rx_char is None:
            raise RuntimeError(f"UART RX characteristic {UART_RX_CHAR_UUID} not found")
        await self.client.start_notify(UART_TX_CHAR_UUID, self._handle_uart_notify)

    async def stop(self) -> None:
        try:
            await self.client.stop_notify(UART_TX_CHAR_UUID)
        except Exception:
            pass

    def _handle_uart_notify(self, _sender: Any, data: bytearray) -> None:
        payload = bytearray(data)
        observed_at = utc_now_iso()
        if self.packet_callback is not None:
            self.packet_callback("rx", UART_TX_CHAR_UUID, payload, observed_at)
        if payload:
            queue = self.queues.setdefault(payload[0] & 127, asyncio.Queue())
            queue.put_nowait((payload, observed_at))

    async def send_packet(self, payload: bytearray) -> str:
        if self.rx_char is None:
            raise RuntimeError("transport not started")
        observed_at = utc_now_iso()
        if self.packet_callback is not None:
            self.packet_callback("tx", UART_RX_CHAR_UUID, payload, observed_at)
        await self.client.write_gatt_char(self.rx_char, payload, response=False)
        return observed_at

    async def read_command_packets(
        self,
        command_id: int,
        *,
        expected: int = 1,
        timeout: float = 3.0,
    ) -> list[tuple[bytearray, str]]:
        queue = self.queues.setdefault(command_id, asyncio.Queue())
        packets = []
        for _ in range(expected):
            packets.append(await asyncio.wait_for(queue.get(), timeout=timeout))
        return packets


class BigDataTransport:
    def __init__(
        self,
        client: BleakClient,
        *,
        packet_callback: Callable[[str, str, bytearray, str], None] | None = None,
    ):
        self.client = client
        self.packet_callback = packet_callback
        self.queues: dict[int, asyncio.Queue[tuple[bytearray, str]]] = {}
        self.rx_char = None

    async def start(self) -> None:
        service = self.client.services.get_service(BIGDATA_SERVICE_UUID)
        if service is None:
            raise RuntimeError(f"Big Data service {BIGDATA_SERVICE_UUID} not found")
        self.rx_char = service.get_characteristic(BIGDATA_RX_CHAR_UUID)
        if self.rx_char is None:
            raise RuntimeError(f"Big Data RX characteristic {BIGDATA_RX_CHAR_UUID} not found")
        await self.client.start_notify(BIGDATA_TX_CHAR_UUID, self._handle_bigdata_notify)

    async def stop(self) -> None:
        try:
            await self.client.stop_notify(BIGDATA_TX_CHAR_UUID)
        except Exception:
            pass

    def _handle_bigdata_notify(self, _sender: Any, data: bytearray) -> None:
        payload = bytearray(data)
        observed_at = utc_now_iso()
        if self.packet_callback is not None:
            self.packet_callback("rx", BIGDATA_TX_CHAR_UUID, payload, observed_at)
        if len(payload) >= 2 and payload[0] == BIGDATA_MAGIC:
            queue = self.queues.setdefault(payload[1], asyncio.Queue())
            queue.put_nowait((payload, observed_at))

    async def send_packet(self, payload: bytes | bytearray) -> str:
        if self.rx_char is None:
            raise RuntimeError("big data transport not started")
        data = bytearray(payload)
        observed_at = utc_now_iso()
        if self.packet_callback is not None:
            self.packet_callback("tx", BIGDATA_RX_CHAR_UUID, data, observed_at)
        await self.client.write_gatt_char(self.rx_char, data, response=False)
        return observed_at

    async def read_data_packets(
        self,
        data_id: int,
        *,
        expected: int = 1,
        timeout: float = 3.0,
    ) -> list[tuple[bytearray, str]]:
        queue = self.queues.setdefault(data_id, asyncio.Queue())
        packets = []
        for _ in range(expected):
            packets.append(await asyncio.wait_for(queue.get(), timeout=timeout))
        return packets

    async def read_data_payload(
        self,
        data_id: int,
        *,
        timeout: float = 3.0,
    ) -> tuple[bytes, str]:
        queue = self.queues.setdefault(data_id, asyncio.Queue())
        first, observed_at = await asyncio.wait_for(queue.get(), timeout=timeout)
        payload = bytearray(first)
        if len(payload) < 6 or payload[0] != BIGDATA_MAGIC:
            return bytes(payload), observed_at

        data_len = int.from_bytes(payload[2:4], "little")
        while len(payload) < 6 + data_len:
            chunk, _chunk_observed_at = await asyncio.wait_for(queue.get(), timeout=timeout)
            payload.extend(chunk)
        return bytes(payload), observed_at
