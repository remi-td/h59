import asyncio
from datetime import UTC, datetime
import os
import time

import pytest

from h59_client.devices import DeviceTarget
from h59_client.protocol import HealthCheckSample, NoData, RealTimeSample
from h59_client.sync import (
    INITIAL_BACKFILL_MAX_DAYS,
    determine_history_selector,
    determine_initial_backfill_dates,
    determine_sync_dates,
    realtime_h59,
    sync_h59,
    sync_one_h59,
)


def test_determine_sync_dates_without_incremental_uses_today_only():
    now = datetime(2026, 5, 26, 15, 0, tzinfo=UTC)
    dates = determine_sync_dates(now=now, last_sync_at=datetime(2026, 5, 25, 10, 0, tzinfo=UTC), incremental=False)
    assert dates == [datetime(2026, 5, 26, 0, 0, tzinfo=UTC)]


def test_determine_sync_dates_incremental_uses_last_sync_day_forward():
    now = datetime(2026, 5, 26, 15, 0, tzinfo=UTC)
    dates = determine_sync_dates(now=now, last_sync_at=datetime(2026, 5, 25, 10, 0, tzinfo=UTC), incremental=True)
    assert dates == [
        datetime(2026, 5, 25, 0, 0, tzinfo=UTC),
        datetime(2026, 5, 26, 0, 0, tzinfo=UTC),
    ]


def test_determine_sync_dates_incremental_without_previous_sync_uses_today_only():
    now = datetime(2026, 5, 26, 15, 0, tzinfo=UTC)
    dates = determine_sync_dates(now=now, last_sync_at=None, incremental=True)
    assert dates == [datetime(2026, 5, 26, 0, 0, tzinfo=UTC)]


def test_determine_initial_backfill_dates_starts_from_today_and_moves_backward():
    now = datetime(2026, 5, 26, 15, 0, tzinfo=UTC)
    dates = determine_initial_backfill_dates(now=now, max_days=3)
    assert dates == [
        datetime(2026, 5, 26, 0, 0, tzinfo=UTC),
        datetime(2026, 5, 25, 0, 0, tzinfo=UTC),
        datetime(2026, 5, 24, 0, 0, tzinfo=UTC),
    ]


def test_determine_initial_backfill_dates_uses_default_bound():
    now = datetime(2026, 5, 26, 15, 0, tzinfo=UTC)
    dates = determine_initial_backfill_dates(now=now)
    assert len(dates) == INITIAL_BACKFILL_MAX_DAYS
    assert dates[0] == datetime(2026, 5, 26, 0, 0, tzinfo=UTC)


def test_determine_history_selector_uses_utc_day_offset():
    now = datetime(2026, 5, 27, 10, 0, tzinfo=UTC)
    assert determine_history_selector(now=now, target=datetime(2026, 5, 27, 0, 0, tzinfo=UTC)) == 0
    assert determine_history_selector(now=now, target=datetime(2026, 5, 26, 0, 0, tzinfo=UTC)) == 1
    assert determine_history_selector(now=now, target=datetime(2026, 5, 24, 0, 0, tzinfo=UTC)) == 3


def test_determine_history_selector_uses_local_day_offset(monkeypatch):
    previous_tz = os.environ.get("TZ")
    try:
        monkeypatch.setenv("TZ", "Europe/Paris")
        time.tzset()
        now = datetime(2026, 6, 2, 0, 30, tzinfo=UTC)
        assert determine_history_selector(
            now=now,
            target=datetime(2026, 6, 1, 22, 0, tzinfo=UTC),
            device_clock_mode="local",
        ) == 0
    finally:
        if previous_tz is None:
            monkeypatch.delenv("TZ", raising=False)
        else:
            monkeypatch.setenv("TZ", previous_tz)
        time.tzset()


def test_realtime_h59_stdout_mode_skips_database_persistence(monkeypatch, tmp_path):
    import h59_client.sync as sync_module

    class FailDatabase:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("stdout mode should not open the database writer")

    class FakeClient:
        def __init__(self) -> None:
            self.disconnected = False

        async def disconnect(self) -> None:
            self.disconnected = True

    class FakeTransport:
        def __init__(self, _client, packet_callback=None) -> None:
            self.packet_callback = packet_callback

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

    async def fake_resolve_single_target(**_kwargs):
        return DeviceTarget(address="00000000-0000-0000-0000-000000000001", name="Demo Band", nickname="demo")

    async def fake_connect_target(_target, *, timeout=20.0):
        assert timeout == 20.0
        return FakeClient()

    async def fail_read_device_versions(_client):
        raise AssertionError("stdout mode should not request versions for persistence")

    async def fake_query_realtime_controlled(_transport, metric_name, *, on_sample=None, **_kwargs):
        sample = RealTimeSample(metric="heart_rate", value=77, error_code=0)
        observed_at = "2026-05-31T10:00:00+00:00"
        if on_sample is not None:
            on_sample(
                metric_name,
                {
                    "timestamp": observed_at,
                    "value": 77,
                    "error_code": 0,
                    "raw_packet_hex": "6901004d000000000000000000000000",
                },
            )
        return [(sample, "6901004d000000000000000000000000", observed_at)]

    monkeypatch.setattr(sync_module, "H59Database", FailDatabase)
    monkeypatch.setattr(sync_module, "resolve_single_target", fake_resolve_single_target)
    monkeypatch.setattr(sync_module, "connect_target", fake_connect_target)
    monkeypatch.setattr(sync_module, "PacketTransport", FakeTransport)
    monkeypatch.setattr(sync_module, "read_device_versions", fail_read_device_versions)
    monkeypatch.setattr(sync_module, "_query_realtime_controlled", fake_query_realtime_controlled)

    observed_samples: list[tuple[str, dict[str, object]]] = []
    result = asyncio.run(
        realtime_h59(
            db_path=tmp_path / "stdout.sqlite",
            selector="00000000-0000-0000-0000-000000000001",
            metric_names=["heart-rate"],
            persist=False,
            on_sample=lambda metric_name, sample: observed_samples.append((metric_name, sample)),
        )
    )

    assert result["persisted"] is False
    assert result["sync_id"] is None
    assert result["address"] == "00000000-0000-0000-0000-000000000001"
    assert result["realtime_results"]["heart-rate"]["samples"] == 1
    assert observed_samples == [
        (
            "heart-rate",
            {
                "timestamp": "2026-05-31T10:00:00+00:00",
                "value": 77,
                "error_code": 0,
                "raw_packet_hex": "6901004d000000000000000000000000",
            },
        )
    ]


def test_realtime_h59_health_check_runs_as_one_shot(monkeypatch, tmp_path):
    import h59_client.sync as sync_module

    class FakeClient:
        def __init__(self) -> None:
            self.disconnected = False

        async def disconnect(self) -> None:
            self.disconnected = True

    class FakeTransport:
        def __init__(self, _client, packet_callback=None) -> None:
            self.packet_callback = packet_callback

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

    async def fake_resolve_single_target(**_kwargs):
        return DeviceTarget(address="00000000-0000-0000-0000-000000000001", name="Demo Band", nickname="demo")

    async def fake_connect_target(_target, *, timeout=20.0):
        assert timeout == 20.0
        return FakeClient()

    async def fake_read_device_versions(_client):
        return ("HW", "FW")

    captured: dict[str, object] = {}

    async def fake_query_health_check(_transport, **kwargs):
        captured.update(kwargs)
        return ([], None)

    monkeypatch.setattr(sync_module, "resolve_single_target", fake_resolve_single_target)
    monkeypatch.setattr(sync_module, "connect_target", fake_connect_target)
    monkeypatch.setattr(sync_module, "PacketTransport", FakeTransport)
    monkeypatch.setattr(sync_module, "read_device_versions", fake_read_device_versions)
    monkeypatch.setattr(sync_module, "_query_health_check", fake_query_health_check)

    result = asyncio.run(
        realtime_h59(
            db_path=tmp_path / "persist.sqlite",
            selector="demo-band",
            metric_names=["health-check"],
            duration_seconds=30,
            should_stop=lambda: True,
            metric_start_hook=lambda _name: (lambda: True),
        )
    )

    assert result["realtime_results"]["health-check"]["packets"] == 0
    assert captured["hard_timeout"] == 40.0
    assert captured["stop_on_idle"] is True
    assert captured["should_stop"] is None


def test_realtime_h59_spo2_runs_as_one_shot(monkeypatch, tmp_path):
    import h59_client.sync as sync_module

    class FakeClient:
        def __init__(self) -> None:
            self.disconnected = False

        async def disconnect(self) -> None:
            self.disconnected = True

    class FakeTransport:
        def __init__(self, _client, packet_callback=None) -> None:
            self.packet_callback = packet_callback

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

    async def fake_resolve_single_target(**_kwargs):
        return DeviceTarget(address="00000000-0000-0000-0000-000000000001", name="Demo Band", nickname="demo")

    async def fake_connect_target(_target, *, timeout=20.0):
        assert timeout == 20.0
        return FakeClient()

    async def fake_read_device_versions(_client):
        return ("HW", "FW")

    captured: dict[str, object] = {}

    async def fake_query_realtime_controlled(_transport, metric_name, **kwargs):
        captured["metric_name"] = metric_name
        captured.update(kwargs)
        return []

    monkeypatch.setattr(sync_module, "resolve_single_target", fake_resolve_single_target)
    monkeypatch.setattr(sync_module, "connect_target", fake_connect_target)
    monkeypatch.setattr(sync_module, "PacketTransport", FakeTransport)
    monkeypatch.setattr(sync_module, "read_device_versions", fake_read_device_versions)
    monkeypatch.setattr(sync_module, "_query_realtime_controlled", fake_query_realtime_controlled)

    result = asyncio.run(
        realtime_h59(
            db_path=tmp_path / "persist.sqlite",
            selector="demo-band",
            metric_names=["spo2"],
            duration_seconds=30,
            should_stop=lambda: True,
            metric_start_hook=lambda _name: (lambda: True),
        )
    )

    assert result["realtime_results"]["spo2"]["samples"] == 0
    assert captured["metric_name"] == "spo2"
    assert captured["hard_timeout"] == 40.0
    assert captured["stop_on_idle"] is True
    assert captured["should_stop"] is None


class FakeServices:
    def get_service(self, _uuid):
        return None


class FakeClient:
    def __init__(self):
        self.services = FakeServices()
        self.disconnected = False

    async def disconnect(self):
        self.disconnected = True


class FakeTransport:
    def __init__(self, client, packet_callback=None):
        self.client = client
        self.packet_callback = packet_callback
        self.started = False
        self.stopped = False

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True


class FakeDatabase:
    def __init__(self, db_path):
        self.db_path = db_path
        self.realtime_observations = []
        self.finished_sync = None
        self.closed = False

    def close(self):
        self.closed = True

    def upsert_device(self, **_kwargs):
        return 1

    def get_latest_sync_timestamp(self, _device_id):
        return None

    def create_sync(self, _device_id, **_kwargs):
        return 7

    def has_gatt_snapshot(self, _device_id):
        return True

    def record_battery(self, *args, **kwargs):
        return None

    def record_heart_rate_settings(self, *args, **kwargs):
        return None

    def record_capabilities(self, *args, **kwargs):
        return None

    def record_raw_packet(self, *args, **kwargs):
        return None

    def record_sleep_sessions(self, *args, **kwargs):
        return None

    def record_blood_oxygen_history(self, *args, **kwargs):
        return None

    def record_pressure_history(self, *args, **kwargs):
        return None

    def record_hrv_history(self, *args, **kwargs):
        return None

    def record_heart_rate_day(self, *args, **kwargs):
        return None

    def record_activity_blocks(self, *args, **kwargs):
        return None

    def record_realtime_observations(self, device_id, sync_id, observations):
        self.realtime_observations.append((device_id, sync_id, observations))

    def finish_sync(self, sync_id, finished_at):
        self.finished_sync = (sync_id, finished_at)


def test_sync_one_h59_runs_post_sync_health_check_once_and_persists_observations(monkeypatch):
    client = FakeClient()
    target = DeviceTarget(address="AA:BB:CC:DD:EE:FF", name="H59", advertisement=None, nickname="remi")
    fake_db = FakeDatabase("data/h59.sqlite")
    battery = object()
    hr_settings = object()
    capabilities = object()
    hc_sample = HealthCheckSample(diastolic=81, systolic=122, heart_rate=67, cuff_pressure_tenths=1012, error_code=0)

    monkeypatch.setattr("h59_client.sync.H59Database", lambda db_path: fake_db)

    async def fake_connect_target(target, timeout=20.0):
        return client

    async def fake_read_device_versions(client):
        return ("1.0", "2.0")

    async def fake_query_battery(transport):
        return (battery, "aa", "2026-05-26T15:00:00+00:00")

    async def fake_query_hr_settings(transport):
        return (hr_settings, "bb", "2026-05-26T15:00:00+00:00")

    async def fake_query_capabilities(transport, device_clock_mode):
        return (capabilities, "cc", "2026-05-26T15:00:00+00:00")

    async def fake_query_health_check(transport):
        return ([(hc_sample, "deadbeef", "2026-05-26T15:00:01+00:00")], (hc_sample, "deadbeef", "2026-05-26T15:00:01+00:00"))

    monkeypatch.setattr("h59_client.sync.connect_target", fake_connect_target)
    monkeypatch.setattr("h59_client.sync.read_device_versions", fake_read_device_versions)
    monkeypatch.setattr("h59_client.sync.PacketTransport", FakeTransport)
    monkeypatch.setattr("h59_client.sync.date_utils.utc_now", lambda: datetime(2026, 5, 26, 15, 0, tzinfo=UTC))
    monkeypatch.setattr("h59_client.sync.determine_sync_dates", lambda **kwargs: [])
    monkeypatch.setattr("h59_client.sync._query_battery", fake_query_battery)
    monkeypatch.setattr("h59_client.sync._query_hr_settings", fake_query_hr_settings)
    monkeypatch.setattr("h59_client.sync._query_capabilities", fake_query_capabilities)
    monkeypatch.setattr("h59_client.sync._query_health_check", fake_query_health_check)

    health_calls = []

    def fake_health_check_observations(samples, final_reading):
        health_calls.append((samples, final_reading))
        return (["obs-1", "obs-2"], {"diastolic": 81, "systolic": 122, "heart_rate": 67})

    monkeypatch.setattr("h59_client.sync._health_check_observations", fake_health_check_observations)

    result = asyncio.run(
        sync_one_h59(
            db_path="data/h59.sqlite",
            target=target,
            post_sync_health_check=True,
            realtime_metrics=["health-check"],
        )
    )

    assert len(health_calls) == 1
    assert result["realtime_results"]["health-check"]["diastolic"] == 81
    assert fake_db.realtime_observations == [(1, 7, ["obs-1", "obs-2"])]
    assert fake_db.finished_sync is not None
    assert fake_db.finished_sync[0] == 7
    assert client.disconnected is True


def test_sync_h59_forwards_post_sync_health_check_to_sync_one(monkeypatch):
    captured = {}

    async def fake_sync_one_h59(**kwargs):
        captured.update(kwargs)
        return [{"sync_id": 11}]

    target = DeviceTarget(address="AA:BB:CC:DD:EE:FF", name="H59", advertisement=None, nickname="remi")

    async def fake_resolve_single_target(**kwargs):
        return target

    monkeypatch.setattr("h59_client.sync.resolve_single_target", fake_resolve_single_target)
    monkeypatch.setattr("h59_client.sync.sync_one_h59", fake_sync_one_h59)

    result = asyncio.run(
        sync_h59(
            db_path="data/h59.sqlite",
            selector="remi",
            post_sync_health_check=True,
            realtime_metrics=["health-check"],
        )
    )

    assert result == [[{"sync_id": 11}]]
    assert captured["post_sync_health_check"] is True
    assert captured["realtime_metrics"] == ["health-check"]
