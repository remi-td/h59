from datetime import UTC, datetime
from pathlib import Path

from bleak.exc import BleakError

from h59_client.cli import (
    archive_db_path,
    build_parser,
    default_db_path,
    default_state_dir,
    format_operational_error,
    main,
    parse_duration,
    resolve_runtime_paths,
)


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
    args = parser.parse_args(["device", "capabilities", "bracelet", "--name", "H59_TEST"])
    assert args.command == "device"
    assert args.device_command == "capabilities"
    assert args.selector == "bracelet"
    assert args.name == "H59_TEST"


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


def test_archive_db_path_formats_expected_name(tmp_path):
    db_path = tmp_path / "h59.sqlite"
    archived = archive_db_path(db_path, now=datetime(2026, 5, 27, 10, 11, 12, tzinfo=UTC))
    assert archived.name == "archive_20260527-101112_h59.sqlite"


def test_format_operational_error_for_missing_device_scan():
    message = format_operational_error(RuntimeError("No H59-like device found during scan"))
    assert message is not None
    assert "No H59 device was discovered." in message
    assert "disconnect or unpair it temporarily" in message


def test_format_operational_error_for_bluetooth_unavailable():
    message = format_operational_error(BleakError("Bluetooth is unsupported"))
    assert message is not None
    assert "Bluetooth is not available" in message
    assert "Bluetooth permission" in message


def test_main_returns_clean_error_for_known_runtime_failure(monkeypatch, capsys):
    monkeypatch.setattr("h59_client.cli.handle_device_info", lambda args: (_ for _ in ()).throw(RuntimeError("No H59-like device found during scan")))
    exit_code = main(["device", "info"])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "No H59 device was discovered." in captured.err
