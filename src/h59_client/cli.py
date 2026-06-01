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
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from typing import Any

from bleak.exc import BleakError

try:
    from bleak.exc import BleakBluetoothNotAvailableError
except ImportError:  # pragma: no cover - older bleak versions do not expose this class
    BleakBluetoothNotAvailableError = None  # type: ignore[assignment]

try:
    from bleak.exc import BleakDeviceNotFoundError
except ImportError:  # pragma: no cover - older bleak versions do not expose this class
    BleakDeviceNotFoundError = None  # type: ignore[assignment]

from h59_client import __version__
from h59_client.actions import (
    fetch_capabilities_h59,
    fetch_device_info_h59,
    fetch_periodic_measurement_setting_h59,
    reboot_h59,
    set_periodic_measurement_setting_h59,
    vibrate_h59,
)
from h59_client.config import (
    DEFAULT_DEVICE_CLOCK_MODE,
    DEVICE_CLOCK_MODES,
    default_config_path,
    read_config,
    resolve_device_clock_mode,
    write_config,
)
from h59_client.devices import discover_and_store_targets
from h59_client.report import render_health_dashboard_report
from h59_client.storage import H59Database
from h59_client.sync import realtime_h59, sync_h59


logger = logging.getLogger(__name__)
DEFAULT_DISCOVERY_NAME = "H59"
REALTIME_METRIC_CHOICES = (
    "heart-rate",
    "blood-pressure",
    "spo2",
    "fatigue",
    "health-check",
    "ecg",
    "pressure",
    "blood-sugar",
    "hrv",
)
PERIODIC_SETTING_CHOICES = ("blood-pressure", "spo2", "stress", "hrv")


def format_operational_error(exc: Exception) -> str | None:
    message = str(exc)
    if message == "database does not contain any device":
        return (
            "No devices are registered in the local database.\n"
            "Use `h59 device discover` first, then run a sync before generating a report."
        )
    if message.startswith("unknown device selector: "):
        selector = message.split(": ", 1)[1]
        return (
            f"Unknown device selector: {selector}.\n"
            "Use a known device_id, nickname, or address from `h59 device list`.\n"
            "Use `h59 device discover` first if the device has not been registered yet."
        )
    if message == "No H59-like device found during scan":
        return (
            "No H59 device was discovered.\n"
            "Check that the device is nearby, charged, and advertising over Bluetooth.\n"
            "If it is currently connected to a phone or another app, disconnect or unpair it temporarily and try again."
        )
    if isinstance(exc, TimeoutError):
        return (
            "Timed out while trying to reach an H59 device over Bluetooth.\n"
            "Check that the device is nearby, awake, and advertising.\n"
            "If it is currently connected to a phone or another app, disconnect or unpair it temporarily and try again."
        )
    if BleakBluetoothNotAvailableError is not None and isinstance(exc, BleakBluetoothNotAvailableError):
        return (
            "Bluetooth is not available for H59 discovery right now.\n"
            "Check that Bluetooth is enabled and that this process has Bluetooth permission.\n"
            "If the bracelet is currently connected to a phone or another app, disconnect or unpair it temporarily and try again."
        )
    if BleakDeviceNotFoundError is not None and isinstance(exc, BleakDeviceNotFoundError):
        return (
            "The requested device address could not be reached over Bluetooth.\n"
            "Check that the device is nearby and advertising, or register it first with `h59 device discover`."
        )
    if isinstance(exc, BleakError) and (
        "Bluetooth is unsupported" in message
        or ("Bluetooth" in message and "not available" in message.lower())
        or "device with address" in message.lower()
        or "timed out" in message.lower()
        or "timeout" in message.lower()
        or "unsupported" in message.lower()
    ):
        return (
            "Bluetooth is not available for H59 discovery right now.\n"
            "Check that Bluetooth is enabled, that this process has Bluetooth permission, and that the device is reachable.\n"
            "If the bracelet is currently connected to a phone or another app, disconnect or unpair it temporarily and try again."
        )
    return None


def format_daemon_operational_notice(exc: Exception) -> str | None:
    message = format_operational_error(exc)
    if message is None:
        return None
    compact = " ".join(part.strip() for part in message.splitlines() if part.strip())
    return f"no device observed during sync cycle: {compact}"


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


def archive_db_path(db_path: Path, *, now: datetime | None = None) -> Path:
    timestamp = (now or datetime.now(UTC)).strftime("%Y%m%d-%H%M%S")
    return db_path.with_name(f"archive_{timestamp}_{db_path.name}")


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


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def update_metadata(meta_file: Path, updates: dict[str, Any]) -> dict[str, Any]:
    metadata = read_metadata(meta_file) or {}
    metadata.update(updates)
    write_metadata(meta_file, metadata)
    return metadata


def build_sync_child_command(args: argparse.Namespace) -> list[str]:
    cmd = [sys.executable, "-m", "h59_client.cli", "sync", "--daemon-child"]
    if args.selector:
        cmd.append(args.selector)
    cmd.extend(["--db", args.db, "--scan-timeout", str(args.scan_timeout)])
    cmd.extend(["--period", str(args.period_seconds)])
    if args.incremental:
        cmd.append("--incremental")
    if getattr(args, "device_clock", None):
        cmd.extend(["--device-clock", args.device_clock])
    if getattr(args, "config", None):
        cmd.extend(["--config", args.config])
    if args.capture_gatt:
        cmd.append("--capture-gatt")
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
    if getattr(args, "realtime_duration", None) is not None:
        cmd.extend(["--realtime-duration", str(args.realtime_duration)])
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
            "selector": args.selector,
            "incremental": bool(args.incremental),
            "period_seconds": args.period_seconds,
            "log_file": str(log_file),
            "pid_file": str(pid_file),
            "state_dir": str(state_dir),
            "started_at": time.time(),
            "started_at_iso": _utc_now_iso(),
            "last_activity_at": _utc_now_iso(),
            "last_cycle_state": "starting",
        },
    )
    return proc.pid


def print_sync_results(results: list[dict[str, Any]]) -> None:
    for result in results:
        label = result.get("nickname") or result.get("name") or result["address"]
        print(
            "Synced {label} ({address}) into {db_path} (sync_id={sync_id}, incremental={incremental}, queried_days={queried_days}, captured_gatt={captured_gatt})".format(
                label=label,
                **result,
            )
        )
        realtime_results = result.get("realtime_results") or {}
        health_check = realtime_results.get("health-check")
        if health_check is not None:
            final_result = health_check.get("final_result")
            if final_result:
                print(
                    "  Health check result: {systolic}/{diastolic} mmHg, HR {heart_rate} bpm at {timestamp}".format(
                        systolic=final_result.get("systolic"),
                        diastolic=final_result.get("diastolic"),
                        heart_rate=final_result.get("heart_rate"),
                        timestamp=final_result.get("timestamp"),
                    )
                )
            else:
                print(f"  Health check packets captured: {health_check.get('packets', 0)}")
        for metric_name, metric_result in sorted(realtime_results.items()):
            if metric_name == "health-check":
                continue
            print(
                "  Realtime {metric}: {samples} samples (last at {last_timestamp})".format(
                    metric=metric_name,
                    samples=metric_result.get("samples", 0),
                    last_timestamp=metric_result.get("last_timestamp", "n/a"),
                )
            )
    if len(results) > 1:
        print(f"Completed sync for {len(results)} devices")


def print_realtime_results(results: list[dict[str, Any]]) -> None:
    for result in results:
        label = result.get("nickname") or result.get("name") or result["address"]
        if result.get("persisted", True):
            print(
                "Captured realtime measurements for {label} ({address}) into {db_path} (sync_id={sync_id})".format(
                    label=label,
                    **result,
                )
            )
        else:
            print(f"Captured realtime measurements for {label} ({result['address']}) to terminal output only")
        realtime_results = result.get("realtime_results") or {}
        for metric_name, realtime_result in realtime_results.items():
            final_result = realtime_result.get("final_result")
            if final_result:
                print(
                    "  {metric}: {systolic}/{diastolic} mmHg, HR {heart_rate} bpm at {timestamp}".format(
                        metric=metric_name,
                        systolic=final_result.get("systolic"),
                        diastolic=final_result.get("diastolic"),
                        heart_rate=final_result.get("heart_rate"),
                        timestamp=final_result.get("timestamp"),
                    )
                )
            elif "samples" in realtime_result:
                print(
                    "  {metric}: {samples} samples (last at {last_timestamp})".format(
                        metric=metric_name,
                        samples=realtime_result.get("samples", 0),
                        last_timestamp=realtime_result.get("last_timestamp", "n/a"),
                    )
                )
            else:
                print(f"  {metric_name}: {realtime_result.get('packets', 0)} packets")


def print_realtime_sample(metric_name: str, sample: dict[str, Any]) -> None:
    timestamp = sample.get("timestamp", "n/a")
    if metric_name == "health-check":
        systolic = sample.get("systolic")
        diastolic = sample.get("diastolic")
        heart_rate = sample.get("heart_rate")
        if systolic is not None and diastolic is not None:
            hr_suffix = f", HR {heart_rate} bpm" if heart_rate is not None else ""
            print(f"{timestamp} health-check {systolic}/{diastolic} mmHg{hr_suffix}")
            return
        cuff_pressure_tenths = sample.get("cuff_pressure_tenths")
        if cuff_pressure_tenths is not None:
            print(f"{timestamp} health-check cuff={cuff_pressure_tenths}")
            return
    value = sample.get("value")
    if value is not None:
        print(f"{timestamp} {metric_name} {value}")
        return
    print(f"{timestamp} {metric_name} {sample}")


def _wait_for_enter_to_stop(stop_event: threading.Event) -> None:
    try:
        input()
    except EOFError:
        pass
    finally:
        stop_event.set()


def _keypress_stop_factory(metric_name: str) -> Callable[[], bool]:
    stop_event = threading.Event()
    print(f"Realtime {metric_name} running. Press Enter to stop.")
    threading.Thread(target=_wait_for_enter_to_stop, args=(stop_event,), daemon=True).start()
    return stop_event.is_set


def validate_realtime_metrics(metrics: list[str]) -> list[str]:
    invalid = [metric for metric in metrics if metric not in REALTIME_METRIC_CHOICES]
    if invalid:
        allowed = ", ".join(REALTIME_METRIC_CHOICES)
        raise SystemExit(f"unsupported realtime metric(s): {', '.join(invalid)}. Choose from: {allowed}")
    return metrics


def run_foreground_sync(args: argparse.Namespace) -> int:
    device_clock_mode = resolve_device_clock_mode(cli_value=args.device_clock, config_path=args.config)
    realtime_should_stop = None
    if args.realtime and args.realtime_until_keypress:
        stop_event = threading.Event()
        print("Realtime measurement running. Press Enter to stop.")
        threading.Thread(target=_wait_for_enter_to_stop, args=(stop_event,), daemon=True).start()
        realtime_should_stop = stop_event.is_set
    elif args.realtime and args.realtime_duration is not None:
        print(f"Realtime measurement running for {args.realtime_duration} seconds.")
    results = asyncio.run(
        sync_h59(
            db_path=args.db,
            selector=args.selector,
            name=DEFAULT_DISCOVERY_NAME,
            scan_timeout=args.scan_timeout,
            incremental=args.incremental,
            device_clock_mode=device_clock_mode,
            capture_gatt=args.capture_gatt,
            realtime_metrics=args.realtime,
            realtime_samples=args.realtime_samples,
            realtime_duration_seconds=args.realtime_duration,
            realtime_should_stop=realtime_should_stop,
        )
    )
    print_sync_results(results)
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

    metadata = update_metadata(
        meta_file,
        {
            "pid": os.getpid(),
            "db": args.db,
            "selector": args.selector,
            "incremental": bool(args.incremental),
            "period_seconds": args.period_seconds,
            "log_file": str(log_file),
            "pid_file": str(pid_file),
            "state_dir": str(state_dir),
            "started_at_iso": (read_metadata(meta_file) or {}).get("started_at_iso", _utc_now_iso()),
            "last_activity_at": _utc_now_iso(),
            "last_cycle_state": "starting",
        },
    )

    logger.info(
        "starting h59 daemon loop db=%s selector=%s incremental=%s period=%ss device_clock=%s",
        args.db,
        args.selector,
        args.incremental,
        args.period_seconds,
        resolve_device_clock_mode(cli_value=args.device_clock, config_path=args.config),
    )

    while not stop_requested:
        cycle_started = time.time()
        update_metadata(
            meta_file,
            {
                "last_activity_at": _utc_now_iso(),
                "last_cycle_started_at": _utc_now_iso(),
                "last_cycle_state": "running",
            },
        )
        try:
            device_clock_mode = resolve_device_clock_mode(cli_value=args.device_clock, config_path=args.config)
            results = asyncio.run(
                sync_h59(
                    db_path=args.db,
                    selector=args.selector,
                    name=DEFAULT_DISCOVERY_NAME,
                    scan_timeout=args.scan_timeout,
                    incremental=args.incremental,
                    device_clock_mode=device_clock_mode,
                    capture_gatt=args.capture_gatt,
                    realtime_metrics=args.realtime,
                    realtime_samples=args.realtime_samples,
                    realtime_duration_seconds=args.realtime_duration,
                )
            )
            logger.info("sync successful devices=%s", len(results))
            for result in results:
                logger.info(
                    "sync successful device=%s sync_id=%s incremental=%s queried_days=%s captured_gatt=%s",
                    result["address"],
                    result["sync_id"],
                    result["incremental"],
                    result["queried_days"],
                    result["captured_gatt"],
                )
            update_metadata(
                meta_file,
                {
                    "last_activity_at": _utc_now_iso(),
                    "last_cycle_finished_at": _utc_now_iso(),
                    "last_cycle_state": "idle",
                    "last_cycle_result": f"ok:{len(results)}",
                },
            )
        except Exception as exc:
            notice = format_daemon_operational_notice(exc)
            if notice is not None:
                logger.info(notice)
                update_metadata(
                    meta_file,
                    {
                        "last_activity_at": _utc_now_iso(),
                        "last_cycle_finished_at": _utc_now_iso(),
                        "last_cycle_state": "idle",
                        "last_cycle_result": notice,
                    },
                )
            else:
                logger.exception("sync cycle failed")
                update_metadata(
                    meta_file,
                    {
                        "last_activity_at": _utc_now_iso(),
                        "last_cycle_finished_at": _utc_now_iso(),
                        "last_cycle_state": "idle",
                        "last_cycle_result": f"error:{type(exc).__name__}",
                    },
                )

        sleep_seconds = max(0, args.period_seconds - (time.time() - cycle_started))
        update_metadata(
            meta_file,
            {
                "last_activity_at": _utc_now_iso(),
                "last_cycle_state": "sleeping",
                "next_cycle_due_at": datetime.now(UTC).timestamp() + sleep_seconds,
                "next_cycle_due_at_iso": datetime.fromtimestamp(datetime.now(UTC).timestamp() + sleep_seconds, UTC).isoformat(),
            },
        )
        deadline = time.time() + sleep_seconds
        while not stop_requested and time.time() < deadline:
            time.sleep(min(1.0, max(0, deadline - time.time())))

    logger.info("daemon exiting")
    return 0


def handle_sync(args: argparse.Namespace) -> int:
    if args.realtime_until_keypress and not args.realtime:
        raise SystemExit("--realtime-until-keypress requires at least one --realtime metric")
    if args.realtime_duration is not None and not args.realtime:
        raise SystemExit("--realtime-duration requires at least one --realtime metric")
    if args.realtime_until_keypress and args.realtime_duration is not None:
        raise SystemExit("--realtime-until-keypress cannot be combined with --realtime-duration")
    if args.realtime_until_keypress and args.daemonize:
        raise SystemExit("--realtime-until-keypress cannot be used with --daemonize")
    if args.daemon_child:
        return run_daemon_loop(args)
    if args.daemonize:
        pid = spawn_daemon(args)
        print(f"Started h59 daemon (pid={pid})")
        return 0
    return run_foreground_sync(args)


def handle_realtime(args: argparse.Namespace) -> int:
    metrics = validate_realtime_metrics(args.metrics or list(REALTIME_METRIC_CHOICES))
    interactive = args.time is None
    if interactive and len(metrics) > 1:
        print("Realtime metrics will run sequentially over a single BLE session. Press Enter to stop each metric and continue to the next.")
        metric_start_hook = _keypress_stop_factory
        stop_callback = None
    elif interactive:
        metric_start_hook = _keypress_stop_factory
        stop_callback = None
    else:
        metric_start_hook = None
        stop_callback = None
        print(f"Realtime measurement running for {args.time} seconds per metric.")

    sample_callback = print_realtime_sample if args.stdout else None
    result = asyncio.run(
        realtime_h59(
            db_path=args.db,
            selector=args.selector,
            metric_names=metrics,
            name=DEFAULT_DISCOVERY_NAME,
            scan_timeout=args.scan_timeout,
            duration_seconds=args.time,
            should_stop=stop_callback,
            metric_start_hook=metric_start_hook,
            persist=not args.stdout,
            on_sample=sample_callback,
        )
    )
    print_realtime_results([result])
    return 0


def handle_vibrate(args: argparse.Namespace) -> int:
    result = asyncio.run(
        vibrate_h59(
            db_path=args.db,
            selector=args.selector,
            name=DEFAULT_DISCOVERY_NAME,
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
    result = asyncio.run(
        fetch_device_info_h59(
            db_path=args.db,
            selector=args.selector,
            name=DEFAULT_DISCOVERY_NAME,
            scan_timeout=args.scan_timeout,
        )
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def handle_device_capabilities(args: argparse.Namespace) -> int:
    device_clock_mode = resolve_device_clock_mode(cli_value=args.device_clock, config_path=args.config)
    result = asyncio.run(
        fetch_capabilities_h59(
            db_path=args.db,
            selector=args.selector,
            name=DEFAULT_DISCOVERY_NAME,
            scan_timeout=args.scan_timeout,
            device_clock_mode=device_clock_mode,
        )
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def handle_config_show(args: argparse.Namespace) -> int:
    config_path = Path(args.config).expanduser() if args.config else default_config_path()
    payload = read_config(config_path)
    effective_clock = resolve_device_clock_mode(config_path=config_path)
    print(
        json.dumps(
            {
                "config_path": str(config_path),
                "device_clock": payload.get("device_clock", DEFAULT_DEVICE_CLOCK_MODE),
                "effective_device_clock": effective_clock,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def handle_config_set_device_clock(args: argparse.Namespace) -> int:
    config_path = Path(args.config).expanduser() if args.config else default_config_path()
    payload = read_config(config_path)
    payload["device_clock"] = args.mode
    write_config(payload, config_path)
    print(f"Configured device clock mode: {args.mode}")
    print(f"Config file: {config_path}")
    return 0


def handle_device_vibrate(args: argparse.Namespace) -> int:
    return handle_vibrate(args)


def handle_device_reboot(args: argparse.Namespace) -> int:
    result = asyncio.run(
        reboot_h59(
            db_path=args.db,
            selector=args.selector,
            name=DEFAULT_DISCOVERY_NAME,
            scan_timeout=args.scan_timeout,
        )
    )
    print("Sent reboot command to device {address} (packet={packet_hex})".format(**result))
    return 0


def handle_device_discover(args: argparse.Namespace) -> int:
    targets = asyncio.run(
        discover_and_store_targets(
            db_path=args.db,
            name=args.name,
            scan_timeout=args.scan_timeout,
        )
    )
    serialized = [
        {
            "address": target.address,
            "name": target.name,
            "device_id": target.device_id,
            "score": target.score,
        }
        for target in targets
    ]
    print(json.dumps(serialized, indent=2, sort_keys=True))
    return 0


def handle_device_setting_get(args: argparse.Namespace) -> int:
    result = asyncio.run(
        fetch_periodic_measurement_setting_h59(
            db_path=args.db,
            selector=args.selector,
            setting_name=args.metric,
            name=DEFAULT_DISCOVERY_NAME,
            scan_timeout=args.scan_timeout,
        )
    )
    setting = result["setting"]
    label = result.get("nickname") or result.get("name") or result["address"]
    print(
        "{metric} is {state} on {label} ({address})".format(
            metric=setting.metric,
            state="on" if setting.enabled else "off",
            label=label,
            address=result["address"],
        )
    )
    return 0


def handle_device_setting_set(args: argparse.Namespace) -> int:
    result = asyncio.run(
        set_periodic_measurement_setting_h59(
            db_path=args.db,
            selector=args.selector,
            setting_name=args.metric,
            enabled=args.state == "on",
            name=DEFAULT_DISCOVERY_NAME,
            scan_timeout=args.scan_timeout,
        )
    )
    confirmed = result["confirmed"]
    label = result.get("nickname") or result.get("name") or result["address"]
    print(
        "Set {metric} {requested} on {label} ({address}); confirmed {confirmed_state}".format(
            metric=confirmed.metric,
            requested=args.state,
            label=label,
            address=result["address"],
            confirmed_state="on" if confirmed.enabled else "off",
        )
    )
    return 0


def _print_device_rows(rows: list[sqlite3.Row]) -> None:
    if not rows:
        print("No devices are registered")
        return
    print("device_id\tnickname\tname\taddress\tlast_seen_at")
    for row in rows:
        print(
            "{device_id}\t{nickname}\t{name}\t{address}\t{last_seen_at}".format(
                device_id=row["device_id"],
                nickname=row["nickname"] or "",
                name=row["name"] or "",
                address=row["address"],
                last_seen_at=row["last_seen_at"] or "",
            )
        )


def handle_device_list(args: argparse.Namespace) -> int:
    database = H59Database(args.db)
    try:
        _print_device_rows(database.list_devices())
    finally:
        database.close()
    return 0


def handle_device_nickname_set(args: argparse.Namespace) -> int:
    database = H59Database(args.db)
    try:
        try:
            row = database.set_device_nickname(args.selector, args.nickname)
        except sqlite3.IntegrityError as exc:
            raise SystemExit(f"nickname must be unique: {args.nickname}") from exc
    finally:
        database.close()
    print(
        "Set nickname for device {device_id} ({address}) to {nickname}".format(
            device_id=row["device_id"],
            address=row["address"],
            nickname=row["nickname"] or "",
        )
    )
    return 0


def _resolve_report_device_id(db_path: str, selector: str | None) -> int | None:
    database = H59Database(db_path)
    try:
        if selector:
            row = database.get_device_by_selector(selector)
            if row is None:
                raise ValueError(f"unknown device selector: {selector}")
            return int(row["device_id"])
        row = database.get_preferred_device()
        if row is None:
            raise ValueError("database does not contain any device")
        return int(row["device_id"])
    finally:
        database.close()


def handle_report(args: argparse.Namespace) -> int:
    device_id = _resolve_report_device_id(args.db, args.selector)
    markdown = render_health_dashboard_report(
        args.db,
        report_date=args.date,
        device_id=device_id,
    )
    if args.output:
        output_path = Path(args.output).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown + "\n", encoding="utf-8")
        print(f"Wrote report to {output_path}")
    else:
        sys.stdout.write(markdown)
        if not markdown.endswith("\n"):
            sys.stdout.write("\n")
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
    stale = False
    last_activity_raw = metadata.get("last_activity_at")
    period_seconds = metadata.get("period_seconds")
    if isinstance(last_activity_raw, str) and isinstance(period_seconds, (int, float)):
        try:
            last_activity = datetime.fromisoformat(last_activity_raw)
        except ValueError:
            last_activity = None
        if last_activity is not None:
            age_seconds = (datetime.now(UTC) - last_activity).total_seconds()
            stale = age_seconds > (float(period_seconds) * 2 + 60)
    if metadata:
        if "db" in metadata:
            print(f"db: {metadata['db']}")
        if "selector" in metadata:
            print(f"selector: {metadata['selector']}")
        if "incremental" in metadata:
            print(f"incremental: {metadata['incremental']}")
        if "period_seconds" in metadata:
            print(f"period_seconds: {metadata['period_seconds']}")
        if "last_cycle_state" in metadata:
            print(f"last_cycle_state: {metadata['last_cycle_state']}")
        if "last_activity_at" in metadata:
            print(f"last_activity_at: {metadata['last_activity_at']}")
        if "last_cycle_started_at" in metadata:
            print(f"last_cycle_started_at: {metadata['last_cycle_started_at']}")
        if "last_cycle_finished_at" in metadata:
            print(f"last_cycle_finished_at: {metadata['last_cycle_finished_at']}")
        if "next_cycle_due_at_iso" in metadata:
            print(f"next_cycle_due_at: {metadata['next_cycle_due_at_iso']}")
        if "last_cycle_result" in metadata:
            print(f"last_cycle_result: {metadata['last_cycle_result']}")
    if stale:
        print("warning: daemon heartbeat is stale; the process may be wedged and should be restarted")
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
    forced = False
    if pid_is_running(pid):
        os.kill(pid, signal.SIGKILL)
        forced = True
        for _ in range(50):
            if not pid_is_running(pid):
                break
            time.sleep(0.1)
        clear_stale_pidfile(pid_file)
    if pid_is_running(pid):
        print(f"failed to stop h59 daemon (pid={pid})")
        return 1

    pid_file.unlink(missing_ok=True)
    meta_file.unlink(missing_ok=True)
    if forced:
        print(f"Stopped h59 daemon (pid={pid}) with SIGKILL after graceful shutdown timed out")
    else:
        print(f"Stopped h59 daemon (pid={pid})")
    return 0


def handle_db_reset(args: argparse.Namespace) -> int:
    db_path = Path(args.db).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    archived_path = None
    if db_path.exists():
        archived_path = archive_db_path(db_path)
        db_path.rename(archived_path)

    database = H59Database(db_path)
    database.close()

    if archived_path is not None:
        print(f"Archived existing database to {archived_path}")
        print("The archived database was not deleted. Remove it manually if you are sure it is no longer needed.")
    else:
        print("No existing database was found; created a fresh database.")
    print(f"Initialized new database at {db_path}")
    return 0


def handle_db_path(args: argparse.Namespace) -> int:
    print(Path(args.db).expanduser().resolve())
    return 0


def handle_db_merge_history(args: argparse.Namespace) -> int:
    target_database = H59Database(args.db)
    try:
        summary = target_database.merge_history_from(args.from_db)
    finally:
        target_database.close()

    print(f"Merged history from {summary['source_db']} into {summary['target_db']}")
    print(f"Migration source code: {summary['migration_source']}")
    print(f"Imported rows: {summary['imported_rows']}")
    if not summary["devices"]:
        print("No historic measurement rows were eligible for import.")
        return 0

    for device in summary["devices"]:
        print(
            "Device {target_device_id} ({address}) -> sync_id={sync_id}, imported_rows={imported_rows}".format(
                target_device_id=device["target_device_id"],
                address=device["address"],
                sync_id=device["sync_id"],
                imported_rows=device["imported_rows"],
            )
        )
        for entity_name, count in sorted(device["entities"].items()):
            if count:
                print(f"  {entity_name}: {count}")
    return 0


def add_db_argument(parser: argparse.ArgumentParser) -> None:
    db_default = str(default_db_path())
    parser.add_argument(
        "--db",
        default=db_default,
        help="SQLite database path (default: ./data/h59.sqlite in a source checkout, otherwise an XDG data path)",
    )


def add_target_arguments(parser: argparse.ArgumentParser, *, selector_required: bool = False) -> None:
    parser.add_argument(
        "selector",
        nargs=None if selector_required else "?",
        help="device selector: device_id, nickname, or address",
    )
    add_db_argument(parser)
    parser.add_argument("--scan-timeout", type=float, default=20.0, help="BLE discovery timeout in seconds")


def add_device_clock_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--device-clock",
        choices=DEVICE_CLOCK_MODES,
        help="device clock mode override for this command: utc or local",
    )
    parser.add_argument(
        "--config",
        help=f"config file path (default: {default_config_path()})",
    )


def add_common_sync_arguments(parser: argparse.ArgumentParser) -> None:
    add_target_arguments(parser)
    add_device_clock_arguments(parser)
    parser.add_argument("-i", "--incremental", action="store_true", help="sync from the latest recorded sync timestamp for each device")
    parser.add_argument("-d", "--daemonize", action="store_true", help="detach into the background and sync periodically")
    parser.add_argument("--period", default="5m", help="period for detached syncs, in seconds or with s/m/h suffixes")
    parser.add_argument("--capture-gatt", action="store_true", help="force a full GATT inventory capture during sync")
    parser.add_argument("--realtime", nargs="*", default=[], choices=sorted(REALTIME_METRIC_CHOICES), help=argparse.SUPPRESS)
    parser.add_argument("--realtime-samples", type=int, default=3, help=argparse.SUPPRESS)
    parser.add_argument("--realtime-duration", type=parse_duration, help=argparse.SUPPRESS)
    parser.add_argument("--realtime-until-keypress", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--state-dir", help="state directory for daemon files")
    parser.add_argument("--pid-file", help="PID file path for daemon mode")
    parser.add_argument("--log-file", help="log file path for daemon mode")
    parser.add_argument("--daemon-child", action="store_true", help=argparse.SUPPRESS)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="h59", description="Local-first H59 sync, reporting, and daemon CLI")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    sync_parser = subparsers.add_parser("sync", help="run a one-shot sync or start a detached sync worker")
    add_common_sync_arguments(sync_parser)
    sync_parser.set_defaults(handler=handle_sync)

    realtime_parser = subparsers.add_parser("realtime", help="run active live measurements without performing a history sync")
    add_target_arguments(realtime_parser, selector_required=True)
    realtime_parser.add_argument("metrics", nargs="*", help="realtime metrics to run; defaults to all known metrics")
    realtime_parser.add_argument("-t", "--time", type=parse_duration, help="run each realtime metric for a fixed duration; defaults to interactive mode until Enter")
    realtime_parser.add_argument("--stdout", action="store_true", help="print live samples to the terminal and do not persist them to SQLite")
    realtime_parser.set_defaults(handler=handle_realtime)

    vibrate_parser = subparsers.add_parser("vibrate", help="trigger the bracelet attention/vibration signal")
    add_target_arguments(vibrate_parser)
    vibrate_parser.add_argument("--repeat", type=int, default=1, help="number of vibration commands to send")
    vibrate_parser.add_argument("--interval", type=float, default=0.75, help="seconds between repeated vibration commands")
    vibrate_parser.set_defaults(handler=handle_vibrate)

    report_parser = subparsers.add_parser("report", help="render a markdown health data report from the local database")
    report_parser.add_argument(
        "selector",
        nargs="?",
        help="device selector: device_id, nickname, or address",
    )
    add_db_argument(report_parser)
    report_parser.add_argument("--date", help="report day in YYYY-MM-DD format; defaults to the latest day found in the database")
    report_parser.add_argument("--output", help="write the markdown report to this file instead of stdout")
    report_parser.set_defaults(handler=handle_report)

    device_parser = subparsers.add_parser("device", help="device discovery, registry, and one-shot control commands")
    device_subparsers = device_parser.add_subparsers(dest="device_command", required=True)

    device_discover = device_subparsers.add_parser("discover", help="scan nearby H59 devices and register them in the database")
    add_db_argument(device_discover)
    device_discover.add_argument("--name", default=DEFAULT_DISCOVERY_NAME, help="preferred advertised device name for discovery")
    device_discover.add_argument("--scan-timeout", type=float, default=20.0, help="BLE discovery timeout in seconds")
    device_discover.set_defaults(handler=handle_device_discover)

    device_list = device_subparsers.add_parser("list", help="list devices registered in the database")
    add_db_argument(device_list)
    device_list.set_defaults(handler=handle_device_list)

    device_nickname = device_subparsers.add_parser("nickname", help="manage device nicknames")
    device_nickname_subparsers = device_nickname.add_subparsers(dest="device_nickname_command", required=True)
    device_nickname_set = device_nickname_subparsers.add_parser("set", help="set or replace a unique nickname for a device")
    add_db_argument(device_nickname_set)
    device_nickname_set.add_argument("selector", help="device selector: device_id, nickname, or address")
    device_nickname_set.add_argument("nickname", help="new unique nickname")
    device_nickname_set.set_defaults(handler=handle_device_nickname_set)

    device_info = device_subparsers.add_parser("info", help="show basic device information and battery status")
    add_target_arguments(device_info)
    device_info.set_defaults(handler=handle_device_info)

    device_capabilities = device_subparsers.add_parser("capabilities", help="query and print parsed device capability flags")
    add_target_arguments(device_capabilities)
    add_device_clock_arguments(device_capabilities)
    device_capabilities.set_defaults(handler=handle_device_capabilities)

    device_get = device_subparsers.add_parser("get", help="read a periodic measurement setting from the device")
    device_get.add_argument("metric", choices=PERIODIC_SETTING_CHOICES, help="measurement setting to read")
    device_get.add_argument("selector", nargs="?", help="device selector: device_id, nickname, or address")
    add_db_argument(device_get)
    device_get.add_argument("--scan-timeout", type=float, default=20.0, help="BLE discovery timeout in seconds")
    device_get.set_defaults(handler=handle_device_setting_get)

    device_set = device_subparsers.add_parser("set", help="set a periodic measurement on or off on the device")
    device_set.add_argument("metric", choices=PERIODIC_SETTING_CHOICES, help="measurement setting to update")
    device_set.add_argument("state", choices=("on", "off"), help="desired setting state")
    device_set.add_argument("selector", nargs="?", help="device selector: device_id, nickname, or address")
    add_db_argument(device_set)
    device_set.add_argument("--scan-timeout", type=float, default=20.0, help="BLE discovery timeout in seconds")
    device_set.set_defaults(handler=handle_device_setting_set)

    device_vibrate = device_subparsers.add_parser("vibrate", help="trigger the bracelet attention/vibration signal")
    add_target_arguments(device_vibrate)
    device_vibrate.add_argument("--repeat", type=int, default=1, help="number of vibration commands to send")
    device_vibrate.add_argument("--interval", type=float, default=0.75, help="seconds between repeated vibration commands")
    device_vibrate.set_defaults(handler=handle_device_vibrate)

    device_reboot = device_subparsers.add_parser("reboot", help="reboot the device")
    add_target_arguments(device_reboot)
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

    db_parser = subparsers.add_parser("db", help="database lifecycle commands")
    db_subparsers = db_parser.add_subparsers(dest="db_command", required=True)

    db_reset = db_subparsers.add_parser("reset", help="archive the current database and initialize a fresh one")
    add_db_argument(db_reset)
    db_reset.set_defaults(handler=handle_db_reset)

    db_path_parser = db_subparsers.add_parser("path", help="print the effective SQLite database path")
    add_db_argument(db_path_parser)
    db_path_parser.set_defaults(handler=handle_db_path)

    db_merge_history = db_subparsers.add_parser("merge-history", help="load older measurement history from another SQLite database")
    add_db_argument(db_merge_history)
    db_merge_history.add_argument("from_db", help="source SQLite database path to merge historic measurements from")
    db_merge_history.set_defaults(handler=handle_db_merge_history)

    config_parser = subparsers.add_parser("config", help="inspect or modify CLI configuration")
    config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)

    config_show = config_subparsers.add_parser("show", help="show effective configuration")
    config_show.add_argument("--config", help=f"config file path (default: {default_config_path()})")
    config_show.set_defaults(handler=handle_config_show)

    config_set = config_subparsers.add_parser("set-device-clock", help="set the default bracelet clock mode")
    config_set.add_argument("mode", choices=DEVICE_CLOCK_MODES, help="default device clock mode")
    config_set.add_argument("--config", help=f"config file path (default: {default_config_path()})")
    config_set.set_defaults(handler=handle_config_set_device_clock)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if hasattr(args, "period"):
        args.period_seconds = parse_duration(args.period)
    try:
        return args.handler(args)
    except SystemExit:
        raise
    except Exception as exc:
        message = format_operational_error(exc)
        if message is None:
            raise
        print(message, file=sys.stderr)
        return 1


def legacy_sync_main() -> int:
    return main(["sync", *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
