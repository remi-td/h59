import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import signal
from typing import Any

from bleak.exc import BleakError
import pytest

from h59_client.cli import (
    archive_db_path,
    build_parser,
    default_db_path,
    default_state_dir,
    filter_realtime_metrics_for_capabilities,
    format_daemon_operational_notice,
    format_operational_error,
    handle_daemon_stop,
    main,
    parse_duration,
    resolve_realtime_capabilities,
    resolve_runtime_paths,
)
from h59_client.storage import H59Database


def test_parse_duration_accepts_seconds_and_suffixes():
    assert parse_duration("300") == 300
    assert parse_duration("30s") == 30
    assert parse_duration("5m") == 300
    assert parse_duration("1h") == 3600


def test_build_parser_supports_sync_daemon_shorthand_flags():
    parser = build_parser()
    args = parser.parse_args(["sync", "12", "-di", "--db", "data/test.sqlite"])
    assert args.command == "sync"
    assert args.selector == "12"
    assert args.incremental is True
    assert args.daemonize is True
    assert args.db == "data/test.sqlite"


def test_build_parser_supports_device_clock_override():
    parser = build_parser()
    args = parser.parse_args(["sync", "--device-clock", "local"])
    assert args.device_clock == "local"


def test_build_parser_supports_realtime_control_arguments():
    parser = build_parser()
    args = parser.parse_args(["realtime", "demo-band", "health-check", "-t", "30s"])
    assert args.command == "realtime"
    assert args.selector == "demo-band"
    assert args.metrics == ["health-check"]
    assert args.time == 30


def test_build_parser_supports_realtime_stdout_mode():
    parser = build_parser()
    args = parser.parse_args(["realtime", "--stdout", "demo-band", "health-check"])
    assert args.command == "realtime"
    assert args.selector == "demo-band"
    assert args.stdout is True
    assert args.metrics == ["health-check"]


def test_build_parser_supports_config_commands():
    parser = build_parser()
    show_args = parser.parse_args(["config", "show"])
    set_args = parser.parse_args(["config", "set-device-clock", "local"])
    assert show_args.command == "config"
    assert show_args.config_command == "show"
    assert set_args.command == "config"
    assert set_args.config_command == "set-device-clock"
    assert set_args.mode == "local"


def test_default_runtime_paths_use_state_dir_override(tmp_path):
    parser = build_parser()
    args = parser.parse_args(["sync", "--state-dir", str(tmp_path / "state")])
    state_dir, pid_file, log_file, meta_file = resolve_runtime_paths(args)
    assert state_dir == tmp_path / "state"
    assert pid_file == state_dir / "daemon.pid"
    assert log_file == state_dir / "daemon.log"
    assert meta_file == state_dir / "daemon.json"


def test_default_state_dir_is_h59_specific():
    path = default_state_dir()
    assert path.name == "h59"
    assert isinstance(path, Path)


def test_default_db_path_uses_source_checkout_data_dir(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    (tmp_path / "src" / "h59_client").mkdir(parents=True)
    assert default_db_path(tmp_path) == tmp_path / "data" / "h59.sqlite"


def test_default_db_path_uses_xdg_data_dir_outside_source_checkout(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    path = default_db_path(tmp_path / "outside")
    assert path == tmp_path / "xdg-data" / "h59" / "h59.sqlite"


def test_build_parser_uses_dynamic_default_db_in_source_checkout(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    (tmp_path / "src" / "h59_client").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    parser = build_parser()
    args = parser.parse_args(["sync"])
    assert args.db == str(tmp_path / "data" / "h59.sqlite")


def test_build_parser_supports_vibrate_command():
    parser = build_parser()
    args = parser.parse_args(["vibrate", "left-wrist", "--repeat", "2", "--interval", "1.5"])
    assert args.command == "vibrate"
    assert args.selector == "left-wrist"
    assert args.repeat == 2
    assert args.interval == 1.5


def test_build_parser_supports_device_info_command():
    parser = build_parser()
    args = parser.parse_args(["device", "info", "42", "--scan-timeout", "10"])
    assert args.command == "device"
    assert args.device_command == "info"
    assert args.selector == "42"
    assert args.scan_timeout == 10


def test_build_parser_supports_device_capabilities_command():
    parser = build_parser()
    args = parser.parse_args(["device", "capabilities", "bracelet"])
    assert args.command == "device"
    assert args.device_command == "capabilities"
    assert args.selector == "bracelet"


def test_build_parser_supports_device_get_setting_command():
    parser = build_parser()
    args = parser.parse_args(["device", "get", "stress", "bracelet"])
    assert args.command == "device"
    assert args.device_command == "get"
    assert args.metric == "stress"
    assert args.selector == "bracelet"


def test_build_parser_supports_device_set_setting_command():
    parser = build_parser()
    args = parser.parse_args(["device", "set", "hrv", "on", "bracelet"])
    assert args.command == "device"
    assert args.device_command == "set"
    assert args.metric == "hrv"
    assert args.state == "on"
    assert args.selector == "bracelet"


def test_build_parser_supports_device_vibrate_command():
    parser = build_parser()
    args = parser.parse_args(["device", "vibrate", "AA-BB", "--repeat", "2", "--interval", "1.5"])
    assert args.command == "device"
    assert args.device_command == "vibrate"
    assert args.selector == "AA-BB"
    assert args.repeat == 2
    assert args.interval == 1.5


def test_build_parser_supports_device_reboot_command():
    parser = build_parser()
    args = parser.parse_args(["device", "reboot", "42"])
    assert args.command == "device"
    assert args.device_command == "reboot"
    assert args.selector == "42"


def test_build_parser_supports_device_discover_and_list_commands():
    parser = build_parser()
    discover_args = parser.parse_args(["device", "discover", "--db", "data/test.sqlite"])
    list_args = parser.parse_args(["device", "list", "--db", "data/test.sqlite"])
    assert discover_args.device_command == "discover"
    assert list_args.device_command == "list"


def test_build_parser_supports_device_nickname_set_command():
    parser = build_parser()
    args = parser.parse_args(["device", "nickname", "set", "--db", "data/test.sqlite", "12", "left-wrist"])
    assert args.command == "device"
    assert args.device_command == "nickname"
    assert args.device_nickname_command == "set"
    assert args.selector == "12"
    assert args.nickname == "left-wrist"


def test_build_parser_supports_db_reset_command():
    parser = build_parser()
    args = parser.parse_args(["db", "reset", "--db", "data/test.sqlite"])
    assert args.command == "db"
    assert args.db_command == "reset"
    assert args.db == "data/test.sqlite"


def test_build_parser_supports_db_path_command():
    parser = build_parser()
    args = parser.parse_args(["db", "path", "--db", "data/test.sqlite"])
    assert args.command == "db"
    assert args.db_command == "path"
    assert args.db == "data/test.sqlite"


def test_build_parser_supports_db_merge_history_command():
    parser = build_parser()
    args = parser.parse_args(["db", "merge-history", "--db", "data/target.sqlite", "data/source.sqlite"])
    assert args.command == "db"
    assert args.db_command == "merge-history"
    assert args.db == "data/target.sqlite"
    assert args.from_db == "data/source.sqlite"


def test_build_parser_supports_report_command():
    parser = build_parser()
    args = parser.parse_args(["report", "left-wrist", "--db", "data/test.sqlite", "--date", "2026-05-27", "--output", "report.md"])
    assert args.command == "report"
    assert args.selector == "left-wrist"
    assert args.db == "data/test.sqlite"
    assert args.date == "2026-05-27"
    assert args.output == "report.md"


def test_build_parser_supports_realtime_command_without_metrics():
    parser = build_parser()
    args = parser.parse_args(["realtime", "left-wrist"])
    assert args.command == "realtime"
    assert args.selector == "left-wrist"
    assert args.metrics == []
    assert args.time is None


def test_realtime_help_lists_supported_metrics_and_health_check_behavior():
    parser = build_parser()
    realtime_parser = next(
        action.choices["realtime"]
        for action in parser._actions
        if getattr(action, "choices", None) and "realtime" in action.choices
    )
    help_text = " ".join(realtime_parser.format_help().split())
    assert "spo2, fatigue, health-check, ecg, pressure" in help_text
    assert "one-shot measurements" in help_text
    assert "`health-check` and `spo2`" in help_text


def test_filter_realtime_metrics_for_capabilities_rejects_explicitly_unsupported_metrics():
    supported, unsupported = filter_realtime_metrics_for_capabilities(
        ["pressure", "health-check", "spo2"],
        {
            "support_pressure": False,
            "support_one_key_check": True,
            "support_spo2": True,
        },
    )
    assert supported == ["health-check", "spo2"]
    assert unsupported == ["pressure"]


def test_resolve_realtime_capabilities_uses_latest_snapshot_for_selected_device(tmp_path):
    db = H59Database(tmp_path / "h59.sqlite")
    device_id = db.upsert_device(
        address="AA-BB",
        name="H59_DEMO",
        advertisement=None,
        hw_version=None,
        fw_version=None,
        last_seen_at="2026-06-01T08:00:00+00:00",
    )
    sync_id = db.create_sync(device_id, started_at="2026-06-01T08:00:00+00:00", source="test")
    db.record_capabilities(
        device_id,
        sync_id,
        timestamp="2026-06-01T08:00:01+00:00",
        capabilities={"support_pressure": False, "support_spo2": True},
        raw_packet_hex="01",
    )
    db.close()

    capabilities = resolve_realtime_capabilities(str(tmp_path / "h59.sqlite"), "AA-BB")
    assert capabilities == {"support_pressure": False, "support_spo2": True}


def test_handle_realtime_health_check_ignores_time_and_interactive_control(monkeypatch, capsys):
    import h59_client.cli as cli_module

    captured: dict[str, Any] = {}

    async def fake_realtime_h59(**kwargs):
        captured.update(kwargs)
        return {
            "address": "00000000-0000-0000-0000-000000000001",
            "name": "Demo Band",
            "nickname": "demo",
            "db_path": kwargs["db_path"],
            "sync_id": 1,
            "persisted": True,
            "realtime_results": {"health-check": {"packets": 1, "final_result": None}},
        }

    monkeypatch.setattr(cli_module, "realtime_h59", fake_realtime_h59)
    parser = build_parser()
    args = parser.parse_args(["realtime", "demo-band", "health-check", "--time", "30s"])

    assert cli_module.handle_realtime(args) == 0
    assert captured["metric_names"] == ["health-check"]
    assert captured["duration_seconds"] == 30
    assert captured["metric_start_hook"] is None
    assert captured["should_stop"] is None

    output = capsys.readouterr().out
    assert "30 seconds per metric" not in output


def test_handle_realtime_spo2_ignores_time_and_interactive_control(monkeypatch, capsys):
    import h59_client.cli as cli_module

    captured: dict[str, Any] = {}

    async def fake_realtime_h59(**kwargs):
        captured.update(kwargs)
        return {
            "address": "00000000-0000-0000-0000-000000000001",
            "name": "Demo Band",
            "nickname": "demo",
            "db_path": kwargs["db_path"],
            "sync_id": 1,
            "persisted": True,
            "realtime_results": {"spo2": {"samples": 0, "last_timestamp": None}},
        }

    monkeypatch.setattr(cli_module, "realtime_h59", fake_realtime_h59)
    parser = build_parser()
    args = parser.parse_args(["realtime", "demo-band", "spo2", "--time", "30s"])

    assert cli_module.handle_realtime(args) == 0
    assert captured["metric_names"] == ["spo2"]
    assert captured["duration_seconds"] == 30
    assert captured["metric_start_hook"] is None
    assert captured["should_stop"] is None

    output = capsys.readouterr().out
    assert "30 seconds per metric" not in output


def test_handle_realtime_rejects_explicit_unsupported_metric_from_capabilities(monkeypatch, tmp_path):
    import h59_client.cli as cli_module

    db = H59Database(tmp_path / "h59.sqlite")
    device_id = db.upsert_device(
        address="AA-BB",
        name="H59_DEMO",
        advertisement=None,
        hw_version=None,
        fw_version=None,
        last_seen_at="2026-06-01T08:00:00+00:00",
    )
    sync_id = db.create_sync(device_id, started_at="2026-06-01T08:00:00+00:00", source="test")
    db.record_capabilities(
        device_id,
        sync_id,
        timestamp="2026-06-01T08:00:01+00:00",
        capabilities={"support_pressure": False},
        raw_packet_hex="01",
    )
    db.close()

    async def fail_realtime_h59(**_kwargs):
        raise AssertionError("unsupported metrics should be rejected before realtime_h59 is called")

    monkeypatch.setattr(cli_module, "realtime_h59", fail_realtime_h59)
    parser = build_parser()
    args = parser.parse_args(["realtime", "--db", str(tmp_path / "h59.sqlite"), "AA-BB", "pressure"])

    with pytest.raises(SystemExit, match="not supported by this band"):
        cli_module.handle_realtime(args)


def test_archive_db_path_formats_expected_name(tmp_path):
    db_path = tmp_path / "h59.sqlite"
    archived = archive_db_path(db_path, now=datetime(2026, 5, 27, 10, 11, 12, tzinfo=UTC))
    assert archived.name == "archive_20260527-101112_h59.sqlite"


def test_format_operational_error_for_missing_device_scan():
    message = format_operational_error(RuntimeError("No H59-like device found during scan"))
    assert message is not None
    assert "No H59 device was discovered." in message
    assert "disconnect or unpair it temporarily" in message


def test_format_operational_error_for_missing_registered_devices():
    message = format_operational_error(ValueError("database does not contain any device"))
    assert message is not None
    assert "No devices are registered in the local database." in message
    assert "`h59 device discover`" in message


def test_format_operational_error_for_unknown_device_selector():
    message = format_operational_error(ValueError("unknown device selector: wristband"))
    assert message is not None
    assert "Unknown device selector: wristband." in message
    assert "`h59 device list`" in message


def test_format_operational_error_for_bluetooth_unavailable():
    message = format_operational_error(BleakError("Bluetooth is unsupported"))
    assert message is not None
    assert "Bluetooth is not available" in message
    assert "Bluetooth permission" in message


def test_format_operational_error_for_timeout():
    message = format_operational_error(TimeoutError())
    assert message is not None
    assert "Timed out while trying to reach an H59 device over Bluetooth." in message
    assert "disconnect or unpair it temporarily" in message


def test_format_daemon_operational_notice_for_missing_device_scan():
    message = format_daemon_operational_notice(RuntimeError("No H59-like device found during scan"))
    assert message is not None
    assert message.startswith("no device observed during sync cycle:")
    assert "No H59 device was discovered." in message
    assert "\n" not in message


def test_format_daemon_operational_notice_for_timeout():
    message = format_daemon_operational_notice(TimeoutError())
    assert message is not None
    assert message.startswith("no device observed during sync cycle:")
    assert "Timed out while trying to reach an H59 device over Bluetooth." in message


def test_handle_daemon_stop_graceful(monkeypatch, tmp_path, capsys):
    pid_file = tmp_path / "daemon.pid"
    meta_file = tmp_path / "daemon.json"
    pid_file.write_text("123\n")
    meta_file.write_text("{}")
    args = argparse.Namespace(state_dir=str(tmp_path), pid_file=str(pid_file), log_file=str(tmp_path / "daemon.log"))

    kill_calls: list[tuple[int, int]] = []
    running_states = [True, True, False, False]

    def fake_pid_is_running(_pid: int) -> bool:
        if running_states:
            return running_states.pop(0)
        return False

    monkeypatch.setattr("h59_client.cli.os.kill", lambda pid, sig: kill_calls.append((pid, sig)))
    monkeypatch.setattr("h59_client.cli.pid_is_running", fake_pid_is_running)
    monkeypatch.setattr("h59_client.cli.time.sleep", lambda _seconds: None)

    assert handle_daemon_stop(args) == 0
    out = capsys.readouterr().out
    assert "Stopped h59 daemon (pid=123)" in out
    assert "SIGKILL" not in out
    assert kill_calls == [(123, signal.SIGTERM)]


def test_handle_daemon_stop_forces_kill_after_timeout(monkeypatch, tmp_path, capsys):
    pid_file = tmp_path / "daemon.pid"
    meta_file = tmp_path / "daemon.json"
    pid_file.write_text("123\n")
    meta_file.write_text("{}")
    args = argparse.Namespace(state_dir=str(tmp_path), pid_file=str(pid_file), log_file=str(tmp_path / "daemon.log"))

    kill_calls: list[tuple[int, int]] = []
    running_states = [True] + ([True] * 151) + [True, True, False, False]

    def fake_pid_is_running(_pid: int) -> bool:
        if running_states:
            return running_states.pop(0)
        return False

    monkeypatch.setattr("h59_client.cli.os.kill", lambda pid, sig: kill_calls.append((pid, sig)))
    monkeypatch.setattr("h59_client.cli.pid_is_running", fake_pid_is_running)
    monkeypatch.setattr("h59_client.cli.time.sleep", lambda _seconds: None)

    assert handle_daemon_stop(args) == 0
    out = capsys.readouterr().out
    assert "with SIGKILL after graceful shutdown timed out" in out
    assert kill_calls == [(123, signal.SIGTERM), (123, signal.SIGKILL)]


def test_main_returns_clean_error_for_known_runtime_failure(monkeypatch, capsys):
    monkeypatch.setattr("h59_client.cli.handle_device_info", lambda args: (_ for _ in ()).throw(RuntimeError("No H59-like device found during scan")))
    exit_code = main(["device", "info"])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "No H59 device was discovered." in captured.err


def test_main_rejects_realtime_until_keypress_with_daemonize(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["sync", "--daemonize", "--realtime", "health-check", "--realtime-until-keypress"])
    assert "--realtime-until-keypress cannot be used with --daemonize" in str(excinfo.value)


def test_main_rejects_realtime_duration_without_metric(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["sync", "--realtime-duration", "30s"])
    assert "--realtime-duration requires at least one --realtime metric" in str(excinfo.value)


def test_daemon_status_warns_for_stale_heartbeat(tmp_path, monkeypatch, capsys):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "daemon.pid").write_text("12345\n")
    (state_dir / "daemon.json").write_text(
        json.dumps(
            {
                "db": "data/h59.sqlite",
                "incremental": True,
                "last_activity_at": "2026-05-28T00:00:00+00:00",
                "last_cycle_state": "sleeping",
                "period_seconds": 300,
            }
        )
    )
    monkeypatch.setattr("h59_client.cli.pid_is_running", lambda pid: True)
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 5, 29, 12, 0, tzinfo=UTC)
    monkeypatch.setattr("h59_client.cli.datetime", FrozenDateTime)
    exit_code = main(["daemon", "status", "--state-dir", str(state_dir)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "warning: daemon heartbeat is stale" in captured.out
