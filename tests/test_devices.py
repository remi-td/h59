import asyncio
from types import SimpleNamespace

from h59_client.ble import discover_h59_devices
from h59_client.devices import looks_like_device_address, resolve_single_target
from h59_client.storage import H59Database


def test_resolve_single_target_prefers_known_device_without_discovery(tmp_path, monkeypatch):
    db_path = tmp_path / "h59.sqlite"
    db = H59Database(db_path)
    db.upsert_device(
        address="AA-BB",
        name="H59_7407",
        advertisement=None,
        hw_version=None,
        fw_version=None,
        last_seen_at="2026-05-27T12:00:00+00:00",
    )
    db.close()

    async def fail_discovery(*args, **kwargs):  # pragma: no cover - should not be called
        raise AssertionError("discovery should not be used for a known default target")

    monkeypatch.setattr("h59_client.devices.discover_target", fail_discovery)

    target = asyncio.run(resolve_single_target(db_path=str(db_path), selector=None, name="H59", scan_timeout=1.0))
    assert target.address == "AA-BB"
    assert target.name == "H59_7407"


def test_resolve_single_target_with_explicit_wrong_name_does_not_use_unrelated_known_device(tmp_path, monkeypatch):
    db_path = tmp_path / "h59.sqlite"
    db = H59Database(db_path)
    db.upsert_device(
        address="AA-BB",
        name="H59_7407",
        advertisement=None,
        hw_version=None,
        fw_version=None,
        last_seen_at="2026-05-27T12:00:00+00:00",
    )
    db.close()

    async def fail_discovery(*args, **kwargs):
        raise RuntimeError("No H59-like device found during scan")

    monkeypatch.setattr("h59_client.devices.discover_target", fail_discovery)

    try:
        asyncio.run(resolve_single_target(db_path=str(db_path), selector=None, name="NOT_A_REAL_BAND", scan_timeout=1.0))
    except RuntimeError as exc:
        assert str(exc) == "No H59-like device found during scan"
    else:  # pragma: no cover
        raise AssertionError("expected wrong explicit name to fail")


def test_discover_h59_devices_respects_non_generic_name_filter(monkeypatch):
    async def fake_discover(*args, **kwargs):
        return {
            "one": (
                SimpleNamespace(address="AA-BB", name="H59_7407"),
                SimpleNamespace(
                    local_name="H59_7407",
                    service_uuids=["0000fe00-0000-1000-8000-00805f9b34fb"],
                    manufacturer_data={0x004C: bytes.fromhex("fee73031")},
                    service_data={},
                    rssi=-50,
                ),
            )
        }

    monkeypatch.setattr("h59_client.ble.BleakScanner.discover", fake_discover)

    strict_matches = asyncio.run(discover_h59_devices(name="NOT_A_REAL_BAND", timeout=0.1))
    generic_matches = asyncio.run(discover_h59_devices(name="H59", timeout=0.1))

    assert strict_matches == []
    assert len(generic_matches) == 1


def test_looks_like_device_address_supports_mac_and_uuid():
    assert looks_like_device_address("AA:BB:CC:DD:EE:FF") is True
    assert looks_like_device_address("AA-BB-CC-DD-EE-FF") is True
    assert looks_like_device_address("86B9D8D4-6CB2-E24D-815D-A141786F427B") is True
    assert looks_like_device_address("wristband") is False
    assert looks_like_device_address("2") is False


def test_resolve_single_target_rejects_unknown_non_address_selector(tmp_path):
    db_path = tmp_path / "h59.sqlite"
    db = H59Database(db_path)
    db.close()

    try:
        asyncio.run(resolve_single_target(db_path=str(db_path), selector="wristband", name="H59", scan_timeout=1.0))
    except ValueError as exc:
        assert str(exc) == "unknown device selector: wristband"
    else:  # pragma: no cover
        raise AssertionError("expected unknown non-address selector to fail")


def test_resolve_single_target_allows_direct_address_selector(tmp_path):
    db_path = tmp_path / "h59.sqlite"
    db = H59Database(db_path)
    db.close()

    target = asyncio.run(
        resolve_single_target(
            db_path=str(db_path),
            selector="86B9D8D4-6CB2-E24D-815D-A141786F427B",
            name="H59",
            scan_timeout=1.0,
        )
    )
    assert target.address == "86B9D8D4-6CB2-E24D-815D-A141786F427B"
