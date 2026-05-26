"""Unix-style CLI for H59 sync operations."""

from __future__ import annotations

import argparse
import asyncio
import atexit
import json
import logging
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any

from h59_client import __version__
from h59_client.actions import fetch_capabilities_h59, fetch_device_info_h59, reboot_h59, vibrate_h59
from h59_client.sync import sync_h59


logger = logging.getLogger(__name__)


def parse_duration(value: str) -> int:
    text = value.strip().lower()
    if text.isdigit():
        return int(text)
    if len(text) < 2:
        raise argparse.ArgumentTypeError("duration must be an integer number of seconds or use s/m/h suffixes")
    number = text[:-1]
    suffix = text[-1]
    if not number.isdigit():
        raise argparse.ArgumentTypeError("duration must start with an integer")
    factor = {"s": 1, "m": 60, "h": 3600}.get(suffix)
    if factor is None:
        raise argparse.ArgumentTypeError("duration suffix must be one of s, m, or h")
    return int(number) * factor


def default_state_dir() -> Path:
    xdg_state_home = os.environ.get("XDG_STATE_HOME")
    if xdg_state_home:
        return Path(xdg_state_home).expanduser() / "h59"
    return Path.home() / ".local" / "state" / "h59"


def default_data_dir() -> Path:
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home).expanduser() / "h59"
    return Path.home() / ".local" / "share" / "h59"


def is_source_checkout(base_dir: Path | None = None) -> bool:
    root = base_dir or Path.cwd()
    return (root / "pyproject.toml").exists() and (root / "src" / "h59_client").is_dir()


def default_db_path(base_dir: Path | None = None) -> Path:
    root = base_dir or Path.cwd()
    if is_source_checkout(root):
        return root / "data" / "h59.sqlite"
    return default_data_dir() / "h59.sqlite"


def resolve_runtime_paths(args: argparse.Namespace) -> tuple[Path, Path, Path, Path]:
    state_dir = Path(args.state_dir).expanduser() if getattr(args, "state_dir", None) else default_state_dir()
    pid_file = Path(args.pid_file).expanduser() if getattr(args, "pid_file", None) else state_dir / "daemon.pid"
    log_file = Path(args.log_file).expanduser() if getattr(args, "log_file", None) else state_dir / "daemon.log"
    meta_file = state_dir / "daemon.json"
    return state_dir, pid_file, log_file, meta_file


def ensure_runtime_dirs(*paths: Path) -> None:
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)


def pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_pid(pid_file: Path) -> int | None:
    if not pid_file.exists():
        return None
    text = pid_file.read_text().strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def clear_stale_pidfile(pid_file: Path) -> None:
    pid = read_pid(pid_file)
    if pid is None:
        if pid_file.exists():
            pid_file.unlink()
        return
    if not pid_is_running(pid):
        pid_file.unlink(missing_ok=True)


def refuse_if_daemon_running(pid_file: Path) -> None:
    clear_stale_pidfile(pid_file)
    pid = read_pid(pid_file)
    if pid is not None and pid_is_running(pid):
        raise RuntimeError(f"daemon already running with pid {pid}")


def write_pidfile(pid_file: Path) -> None:
    ensure_runtime_dirs(pid_file)
    pid_file.write_text(f"{os.getpid()}\n")


def remove_pidfile(pid_file: Path) -> None:
    pid_file.unlink(missing_ok=True)


def write_metadata(meta_file: Path, data: dict[str, Any]) -> None:
    ensure_runtime_dirs(meta_file)
    meta_file.write_text(json.dumps(data, indent=2, sort_keys=True))


def read_metadata(meta_file: Path) -> dict[str, Any] | None:
    if not meta_file.exists():
        return None
    try:
        return json.loads(meta_file.read_text())
    except json.JSONDecodeError:
        return None


def configure_daemon_logging(log_file: Path) -> None:
    ensure_runtime_dirs(log_file)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_file, encoding="utf-8")],
        force=True,
    )


def build_sync_child_command(args: argparse.Namespace) -> list[str]:
    cmd = [sys.executable, "-m", "h59_client.cli", "sync", "--daemon-child"]
    cmd.extend(["--db", args.db, "--name", args.name, "--scan-timeout", str(args.scan_timeout)])
    cmd.extend(["--period", str(args.period_seconds)])
    if args.incremental:
        cmd.append("--incremental")
    if args.skip_capabilities:
        cmd.append("--skip-capabilities")
    if args.state_dir:
        cmd.extend(["--state-dir", args.state_dir])
    if args.pid_file:
        cmd.extend(["--pid-file", args.pid_file])
    if args.log_file:
        cmd.extend(["--log-file", args.log_file])
    if args.realtime:
        cmd.append("--realtime")
        cmd.extend(args.realtime)
    if args.realtime_samples != 3:
        cmd.extend(["--realtime-samples", str(args.realtime_samples)])
    return cmd


def spawn_daemon(args: argparse.Namespace) -> int:
    state_dir, pid_file, log_file, meta_file = resolve_runtime_paths(args)
    state_dir.mkdir(parents=True, exist_ok=True)
    refuse_if_daemon_running(pid_file)

    cmd = build_sync_child_command(args)
    with log_file.open("a", encoding="utf-8") as log_handle:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=log_handle,
            start_new_session=True,
            close_fds=True,
            cwd=os.getcwd(),
            env=os.environ.copy(),
        )

    write_metadata(
        meta_file,
        {
            "pid": proc.pid,
            "db": args.db,
            "name": args.name,
            "incremental": bool(args.incremental),
            "period_seconds": args.period_seconds,
            "log_file": str(log_file),
            "pid_file": str(pid_file),
            "state_dir": str(state_dir),
            "started_at": time.time(),
        },
    )
    return proc.pid


def run_foreground_sync(args: argparse.Namespace) -> int:
    result = asyncio.run(
        sync_h59(
            db_path=args.db,
            name=args.name,
            scan_timeout=args.scan_timeout,
            incremental=args.incremental,
            capture_capabilities=not args.skip_capabilities,
            realtime_metrics=args.realtime,
            realtime_samples=args.realtime_samples,
        )
    )
    print(
        "Synced device {address} into {db_path} (sync_id={sync_id}, incremental={incremental}, queried_days={queried_days})".format(
            **result
        )
    )
    return 0


def run_daemon_loop(args: argparse.Namespace) -> int:
    state_dir, pid_file, log_file, meta_file = resolve_runtime_paths(args)
    state_dir.mkdir(parents=True, exist_ok=True)
    clear_stale_pidfile(pid_file)
    write_pidfile(pid_file)
    atexit.register(remove_pidfile, pid_file)

    configure_daemon_logging(log_file)
    stop_requested = False

    def _handle_signal(signum: int, _frame: Any) -> None:
        nonlocal stop_requested
        logger.info("received signal %s, stopping daemon", signum)
        stop_requested = True

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    metadata = read_metadata(meta_file) or {}
    metadata.update(
        {
            "pid": os.getpid(),
            "db": args.db,
            "name": args.name,
            "incremental": bool(args.incremental),
            "period_seconds": args.period_seconds,
            "log_file": str(log_file),
            "pid_file": str(pid_file),
            "state_dir": str(state_dir),
        }
    )
    write_metadata(meta_file, metadata)

    logger.info("starting h59 daemon loop db=%s incremental=%s period=%ss", args.db, args.incremental, args.period_seconds)

    while not stop_requested:
        cycle_started = time.time()
        try:
            result = asyncio.run(
                sync_h59(
                    db_path=args.db,
                    name=args.name,
                    scan_timeout=args.scan_timeout,
                    incremental=args.incremental,
                    capture_capabilities=not args.skip_capabilities,
                    realtime_metrics=args.realtime,
                    realtime_samples=args.realtime_samples,
                )
            )
            logger.info(
                "sync successful device=%s sync_id=%s incremental=%s queried_days=%s",
                result["address"],
                result["sync_id"],
                result["incremental"],
                result["queried_days"],
            )
        except Exception:
            logger.exception("sync cycle failed")

        sleep_seconds = max(0, args.period_seconds - (time.time() - cycle_started))
        deadline = time.time() + sleep_seconds
        while not stop_requested and time.time() < deadline:
            time.sleep(min(1.0, max(0, deadline - time.time())))

    logger.info("daemon exiting")
    return 0


def handle_sync(args: argparse.Namespace) -> int:
    if args.daemon_child:
        return run_daemon_loop(args)
    if args.daemonize:
        pid = spawn_daemon(args)
        print(f"Started h59 daemon (pid={pid})")
        return 0
    return run_foreground_sync(args)


def handle_vibrate(args: argparse.Namespace) -> int:
    result = asyncio.run(
        vibrate_h59(
            name=args.name,
            scan_timeout=args.scan_timeout,
            repeat=args.repeat,
            interval=args.interval,
        )
    )
    print(
        "Sent vibrate command to device {address} (repeat={repeat}, packet={packet_hex})".format(
            **result
        )
    )
    return 0


def handle_device_info(args: argparse.Namespace) -> int:
    result = asyncio.run(fetch_device_info_h59(name=args.name, scan_timeout=args.scan_timeout))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def handle_device_capabilities(args: argparse.Namespace) -> int:
    result = asyncio.run(fetch_capabilities_h59(name=args.name, scan_timeout=args.scan_timeout))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def handle_device_vibrate(args: argparse.Namespace) -> int:
    return handle_vibrate(args)


def handle_device_reboot(args: argparse.Namespace) -> int:
    result = asyncio.run(reboot_h59(name=args.name, scan_timeout=args.scan_timeout))
    print("Sent reboot command to device {address} (packet={packet_hex})".format(**result))
    return 0


def handle_daemon_status(args: argparse.Namespace) -> int:
    _state_dir, pid_file, log_file, meta_file = resolve_runtime_paths(args)
    clear_stale_pidfile(pid_file)
    pid = read_pid(pid_file)
    metadata = read_metadata(meta_file) or {}
    if pid is None or not pid_is_running(pid):
        print("h59 daemon is not running")
        print(f"pid file: {pid_file}")
        print(f"log file: {log_file}")
        return 1

    print(f"h59 daemon is running (pid={pid})")
    print(f"pid file: {pid_file}")
    print(f"log file: {log_file}")
    if metadata:
        if "db" in metadata:
            print(f"db: {metadata['db']}")
        if "incremental" in metadata:
            print(f"incremental: {metadata['incremental']}")
        if "period_seconds" in metadata:
            print(f"period_seconds: {metadata['period_seconds']}")
    return 0


def handle_daemon_stop(args: argparse.Namespace) -> int:
    _state_dir, pid_file, _log_file, meta_file = resolve_runtime_paths(args)
    clear_stale_pidfile(pid_file)
    pid = read_pid(pid_file)
    if pid is None or not pid_is_running(pid):
        print("h59 daemon is not running")
        pid_file.unlink(missing_ok=True)
        return 1

    os.kill(pid, signal.SIGTERM)
    for _ in range(150):
        if not pid_is_running(pid):
            break
        time.sleep(0.1)
    clear_stale_pidfile(pid_file)
    if pid_is_running(pid):
        print(f"failed to stop h59 daemon (pid={pid})")
        return 1

    pid_file.unlink(missing_ok=True)
    meta_file.unlink(missing_ok=True)
    print(f"Stopped h59 daemon (pid={pid})")
    return 0


def add_common_sync_arguments(parser: argparse.ArgumentParser) -> None:
    db_default = str(default_db_path())
    parser.add_argument("-i", "--incremental", action="store_true", help="sync from the latest recorded sync timestamp for this device")
    parser.add_argument("-d", "--daemonize", action="store_true", help="detach into the background and sync periodically")
    parser.add_argument("--period", default="5m", help="period for detached syncs, in seconds or with s/m/h suffixes")
    parser.add_argument(
        "--db",
        default=db_default,
        help="SQLite database path (default: ./data/h59.sqlite in a source checkout, otherwise an XDG data path)",
    )
    parser.add_argument("--name", default="H59", help="preferred advertised device name")
    parser.add_argument("--scan-timeout", type=float, default=20.0, help="BLE discovery timeout in seconds")
    parser.add_argument("--skip-capabilities", action="store_true", help="skip the capability snapshot probe")
    parser.add_argument("--realtime", nargs="*", default=[], choices=sorted({
        "heart-rate",
        "blood-pressure",
        "spo2",
        "fatigue",
        "health-check",
        "ecg",
        "pressure",
        "blood-sugar",
        "hrv",
    }), help="optional realtime metrics to query")
    parser.add_argument("--realtime-samples", type=int, default=3, help="sample count per realtime metric")
    parser.add_argument("--state-dir", help="state directory for daemon files")
    parser.add_argument("--pid-file", help="PID file path for daemon mode")
    parser.add_argument("--log-file", help="log file path for daemon mode")
    parser.add_argument("--daemon-child", action="store_true", help=argparse.SUPPRESS)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="h59", description="Local-first H59 sync and daemon CLI")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    sync_parser = subparsers.add_parser("sync", help="run a one-shot sync or start a detached sync worker")
    add_common_sync_arguments(sync_parser)
    sync_parser.set_defaults(handler=handle_sync)

    vibrate_parser = subparsers.add_parser("vibrate", help="trigger the bracelet attention/vibration signal")
    vibrate_parser.add_argument("--name", default="H59", help="preferred advertised device name")
    vibrate_parser.add_argument("--scan-timeout", type=float, default=20.0, help="BLE discovery timeout in seconds")
    vibrate_parser.add_argument("--repeat", type=int, default=1, help="number of vibration commands to send")
    vibrate_parser.add_argument("--interval", type=float, default=0.75, help="seconds between repeated vibration commands")
    vibrate_parser.set_defaults(handler=handle_vibrate)

    device_parser = subparsers.add_parser("device", help="device discovery and one-shot control commands")
    device_subparsers = device_parser.add_subparsers(dest="device_command", required=True)

    device_info = device_subparsers.add_parser("info", help="show basic device information and battery status")
    device_info.add_argument("--name", default="H59", help="preferred advertised device name")
    device_info.add_argument("--scan-timeout", type=float, default=20.0, help="BLE discovery timeout in seconds")
    device_info.set_defaults(handler=handle_device_info)

    device_capabilities = device_subparsers.add_parser("capabilities", help="query and print parsed device capability flags")
    device_capabilities.add_argument("--name", default="H59", help="preferred advertised device name")
    device_capabilities.add_argument("--scan-timeout", type=float, default=20.0, help="BLE discovery timeout in seconds")
    device_capabilities.set_defaults(handler=handle_device_capabilities)

    device_vibrate = device_subparsers.add_parser("vibrate", help="trigger the bracelet attention/vibration signal")
    device_vibrate.add_argument("--name", default="H59", help="preferred advertised device name")
    device_vibrate.add_argument("--scan-timeout", type=float, default=20.0, help="BLE discovery timeout in seconds")
    device_vibrate.add_argument("--repeat", type=int, default=1, help="number of vibration commands to send")
    device_vibrate.add_argument("--interval", type=float, default=0.75, help="seconds between repeated vibration commands")
    device_vibrate.set_defaults(handler=handle_device_vibrate)

    device_reboot = device_subparsers.add_parser("reboot", help="reboot the device")
    device_reboot.add_argument("--name", default="H59", help="preferred advertised device name")
    device_reboot.add_argument("--scan-timeout", type=float, default=20.0, help="BLE discovery timeout in seconds")
    device_reboot.set_defaults(handler=handle_device_reboot)

    daemon_parser = subparsers.add_parser("daemon", help="daemon lifecycle commands")
    daemon_subparsers = daemon_parser.add_subparsers(dest="daemon_command", required=True)

    daemon_status = daemon_subparsers.add_parser("status", help="show daemon status")
    daemon_status.add_argument("--state-dir", help="state directory for daemon files")
    daemon_status.add_argument("--pid-file", help="PID file path for daemon mode")
    daemon_status.add_argument("--log-file", help="log file path for daemon mode")
    daemon_status.set_defaults(handler=handle_daemon_status)

    daemon_stop = daemon_subparsers.add_parser("stop", help="stop the detached daemon")
    daemon_stop.add_argument("--state-dir", help="state directory for daemon files")
    daemon_stop.add_argument("--pid-file", help="PID file path for daemon mode")
    daemon_stop.add_argument("--log-file", help="log file path for daemon mode")
    daemon_stop.set_defaults(handler=handle_daemon_stop)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if hasattr(args, "period"):
        args.period_seconds = parse_duration(args.period)
    return args.handler(args)


def legacy_sync_main() -> int:
    return main(["sync", *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
