import asyncio
from datetime import UTC, datetime

from h59_client.devices import DeviceTarget
from h59_client.protocol import RealTimeSample
from h59_client.sync import (
    INITIAL_BACKFILL_MAX_DAYS,
    determine_initial_backfill_dates,
    determine_history_selector,
    determine_sync_dates,
    realtime_h59,
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
