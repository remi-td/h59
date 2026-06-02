"""Local protocol helpers and parsers for the H59 bracelet."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timezone, timedelta
import json
import logging
import struct
from enum import IntEnum
from typing import Any

from h59_client import date_utils

logger = logging.getLogger(__name__)

UART_SERVICE_UUID = "6e40fff0-b5a3-f393-e0a9-e50e24dcca9e"
UART_RX_CHAR_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
UART_TX_CHAR_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
BIGDATA_SERVICE_UUID = "de5bf728-d711-4e47-af26-65e3012a5dc7"
BIGDATA_RX_CHAR_UUID = "de5bf72a-d711-4e47-af26-65e3012a5dc7"
BIGDATA_TX_CHAR_UUID = "de5bf729-d711-4e47-af26-65e3012a5dc7"

DEVICE_INFO_UUID = "0000180a-0000-1000-8000-00805f9b34fb"
DEVICE_HW_UUID = "00002a27-0000-1000-8000-00805f9b34fb"
DEVICE_FW_UUID = "00002a26-0000-1000-8000-00805f9b34fb"

CMD_SET_TIME = 1
CMD_BATTERY = 3
CMD_BLOOD_PRESSURE_SETTINGS = 12
CMD_REBOOT = 8
CMD_BLINK_TWICE = 16
CMD_READ_HEART_RATE = 21
CMD_BLOOD_OXYGEN_SETTINGS = 44
CMD_PRESSURE_SETTINGS = 54
CMD_HRV_SETTINGS = 56
CMD_HEART_RATE_LOG_SETTINGS = 22
CMD_PRESSURE_HISTORY = 55
CMD_HRV_HISTORY = 57
CMD_GET_STEP_SOMEDAY = 67
CMD_START_REAL_TIME = 105
CMD_STOP_REAL_TIME = 106

BIGDATA_MAGIC = 188
BIGDATA_SLEEP_ID = 39
BIGDATA_BLOOD_OXYGEN_ID = 42

BATTERY_PACKET = None
READ_HEART_RATE_LOG_SETTINGS_PACKET = None
BLINK_TWICE_PACKET = None
REBOOT_PACKET = None


def checksum(packet: bytearray) -> int:
    return sum(packet) & 255


def make_packet(command: int, sub_data: bytearray | None = None) -> bytearray:
    if not 0 <= command <= 255:
        raise ValueError("command must be between 0 and 255")
    packet = bytearray(16)
    packet[0] = command
    if sub_data:
        if len(sub_data) > 14:
            raise ValueError("sub_data must be at most 14 bytes")
        packet[1 : 1 + len(sub_data)] = sub_data
    packet[-1] = checksum(packet)
    return packet


def byte_to_bcd(value: int) -> int:
    if not 0 <= value < 100:
        raise ValueError("value must be between 0 and 99")
    return ((value // 10) << 4) | (value % 10)


def bcd_to_decimal(value: int) -> int:
    return (((value >> 4) & 15) * 10) + (value & 15)


@dataclass
class BatteryStatus:
    battery_level: int
    charging: bool


def parse_battery(packet: bytearray) -> BatteryStatus:
    return BatteryStatus(battery_level=packet[1], charging=bool(packet[2]))


@dataclass
class HeartRateLogSettings:
    enabled: bool
    interval: int


def parse_heart_rate_log_settings(packet: bytearray) -> HeartRateLogSettings:
    raw_enabled = packet[2]
    enabled = raw_enabled == 1
    if raw_enabled not in (1, 2):
        logger.warning("Unexpected heart rate logging enabled byte %s", raw_enabled)
    return HeartRateLogSettings(enabled=enabled, interval=packet[3])


def heart_rate_log_settings_packet(enabled: bool, interval: int) -> bytearray:
    if not 0 < interval < 256:
        raise ValueError("interval must be between 1 and 255")
    state = 1 if enabled else 2
    return make_packet(CMD_HEART_RATE_LOG_SETTINGS, bytearray([2, state, interval]))


PERIODIC_MEASUREMENT_SETTINGS = {
    "blood-pressure": CMD_BLOOD_PRESSURE_SETTINGS,
    "spo2": CMD_BLOOD_OXYGEN_SETTINGS,
    "stress": CMD_PRESSURE_SETTINGS,
    "hrv": CMD_HRV_SETTINGS,
}


@dataclass
class PeriodicMeasurementSetting:
    metric: str
    enabled: bool
    command_id: int
    action: int
    payload_hex: str


def periodic_measurement_settings_read_packet(command_id: int) -> bytearray:
    return make_packet(command_id, bytearray([1]))


def periodic_measurement_settings_write_packet(command_id: int, enabled: bool) -> bytearray:
    return make_packet(command_id, bytearray([2, 1 if enabled else 0]))


def parse_periodic_measurement_setting(packet: bytearray) -> PeriodicMeasurementSetting:
    if len(packet) != 16:
        raise ValueError("invalid periodic setting packet")
    command_id = packet[0] & 127
    metric = next((name for name, value in PERIODIC_MEASUREMENT_SETTINGS.items() if value == command_id), None)
    if metric is None:
        raise ValueError(f"unsupported periodic setting command: {command_id}")
    return PeriodicMeasurementSetting(
        metric=metric,
        enabled=packet[2] == 1,
        command_id=command_id,
        action=packet[1],
        payload_hex=packet.hex(),
    )


@dataclass
class ActivityBlock:
    year: int
    month: int
    day: int
    time_index: int
    calories: int
    steps: int
    distance: int

    @property
    def timestamp(self) -> datetime:
        return datetime(
            year=self.year,
            month=self.month,
            day=self.day,
            hour=self.time_index // 4,
            minute=(self.time_index % 4) * 15,
            tzinfo=UTC,
        )


class NoData:
    """Marker for protocol replies that explicitly report no data."""


class ActivityBlockParser:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.new_calorie_protocol = False
        self.index = 0
        self.blocks: list[ActivityBlock] = []

    def parse(self, packet: bytearray) -> list[ActivityBlock] | NoData | None:
        if len(packet) != 16 or packet[0] != CMD_GET_STEP_SOMEDAY:
            raise ValueError("invalid activity packet")

        if self.index == 0 and packet[1] == 255:
            self.reset()
            return NoData()

        if self.index == 0 and packet[1] == 240:
            if packet[3] == 1:
                self.new_calorie_protocol = True
            self.index += 1
            return None

        calories = packet[7] | (packet[8] << 8)
        if self.new_calorie_protocol:
            calories *= 10

        block = ActivityBlock(
            year=bcd_to_decimal(packet[1]) + 2000,
            month=bcd_to_decimal(packet[2]),
            day=bcd_to_decimal(packet[3]),
            time_index=packet[4],
            calories=calories,
            steps=packet[9] | (packet[10] << 8),
            distance=packet[11] | (packet[12] << 8),
        )
        self.blocks.append(block)

        if packet[5] == packet[6] - 1:
            result = self.blocks
            self.reset()
            return result

        self.index += 1
        return None


def read_steps_packet(day_offset: int = 0) -> bytearray:
    sub_data = bytearray(b"\x00\x0f\x00\x5f\x01")
    sub_data[0] = day_offset
    return make_packet(CMD_GET_STEP_SOMEDAY, sub_data)


@dataclass
class HeartRateDay:
    heart_rates: list[int]
    timestamp: datetime
    size: int
    index: int
    range: int

    def readings_with_times(self) -> list[tuple[int, datetime]]:
        points = self.heart_rates[:288]
        if len(points) < 288:
            points = points + [0] * (288 - len(points))

        out = []
        ts = datetime(self.timestamp.year, self.timestamp.month, self.timestamp.day, tzinfo=UTC)
        interval = timedelta(minutes=5)
        for reading in points:
            out.append((reading, ts))
            ts += interval
        return out


class HeartRateDayParser:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._raw_heart_rates: list[int] = []
        self.timestamp: datetime | None = None
        self.size = 0
        self.index = 0
        self.range = 5

    def parse(self, packet: bytearray) -> HeartRateDay | NoData | None:
        if len(packet) != 16 or packet[0] != CMD_READ_HEART_RATE:
            raise ValueError("invalid heart rate packet")

        sub_type = packet[1]
        if sub_type == 255:
            self.reset()
            return NoData()

        if self._is_today() and sub_type == 23:
            result = HeartRateDay(
                heart_rates=self.heart_rates,
                timestamp=self.timestamp or date_utils.start_of_day(date_utils.utc_now()),
                size=self.size,
                index=self.index,
                range=self.range,
            )
            self.reset()
            return result

        if sub_type == 0:
            self.size = packet[2]
            self.range = packet[3]
            self._raw_heart_rates = [-1] * (self.size * 13)
            return None

        if sub_type == 1:
            ts = struct.unpack_from("<l", packet, offset=2)[0]
            self.timestamp = datetime.fromtimestamp(ts, timezone.utc)
            self._raw_heart_rates[0:9] = list(packet[6:-1])
            self.index += 9
            return None

        self._raw_heart_rates[self.index : self.index + 13] = list(packet[2:15])
        self.index += 13
        if sub_type == self.size - 1:
            result = HeartRateDay(
                heart_rates=self.heart_rates,
                timestamp=self.timestamp or date_utils.start_of_day(date_utils.utc_now()),
                size=self.size,
                index=self.index,
                range=self.range,
            )
            self.reset()
            return result
        return None

    @property
    def heart_rates(self) -> list[int]:
        heart_rates = self._raw_heart_rates.copy()
        if len(heart_rates) > 288:
            heart_rates = heart_rates[:288]
        elif len(heart_rates) < 288:
            heart_rates.extend([0] * (288 - len(heart_rates)))

        if self._is_today():
            cutoff = date_utils.minutes_so_far(date_utils.utc_now()) // 5
            heart_rates[cutoff:] = [0] * len(heart_rates[cutoff:])
        return heart_rates

    def _is_today(self) -> bool:
        return self.timestamp is not None and date_utils.is_today(self.timestamp)


def read_heart_rate_packet(target: datetime) -> bytearray:
    ts = int(date_utils.start_of_day(target).timestamp())
    return make_packet(CMD_READ_HEART_RATE, bytearray(struct.pack("<L", ts)))


def set_time_packet(target: datetime) -> bytearray:
    dt = target if target.tzinfo is not None else target.astimezone()
    data = bytearray(7)
    data[0] = byte_to_bcd(dt.year % 2000)
    data[1] = byte_to_bcd(dt.month)
    data[2] = byte_to_bcd(dt.day)
    data[3] = byte_to_bcd(dt.hour)
    data[4] = byte_to_bcd(dt.minute)
    data[5] = byte_to_bcd(dt.second)
    data[6] = 1
    return make_packet(CMD_SET_TIME, data)


def parse_capabilities(packet: bytearray) -> dict[str, bool | int]:
    if len(packet) != 16 or packet[0] != CMD_SET_TIME:
        raise ValueError("invalid capability packet")

    data = packet[1:]
    out: dict[str, bool | int] = {}
    out["support_temperature"] = data[0] == 1
    out["support_plate"] = data[1] == 1
    out["support_menstruation"] = True
    out["support_custom_wallpaper"] = (data[3] & 1) != 0
    out["support_spo2"] = (data[3] & 2) != 0
    out["support_blood_pressure"] = (data[3] & 4) != 0
    out["support_feature"] = (data[3] & 8) != 0
    out["support_one_key_check"] = (data[3] & 16) != 0
    out["support_weather"] = (data[3] & 32) != 0
    out["support_wechat"] = (data[3] & 64) == 0
    out["support_avatar"] = (data[3] & 128) != 0
    out["new_sleep_protocol"] = data[8] == 1
    out["max_watch_face"] = data[9]
    out["support_contact"] = (data[10] & 1) != 0
    out["support_lyrics"] = (data[10] & 2) != 0
    out["support_album"] = (data[10] & 4) != 0
    out["support_gps"] = (data[10] & 8) != 0
    out["support_jieli_music"] = (data[10] & 16) != 0
    out["support_manual_heart"] = (data[11] & 1) != 0
    out["support_ecard"] = (data[11] & 2) != 0
    out["support_location"] = (data[11] & 4) != 0
    out["support_music"] = (data[11] & 16) != 0
    out["support_rtk_mcu"] = (data[11] & 32) != 0
    out["support_ebook"] = (data[11] & 64) != 0
    out["support_blood_sugar"] = (data[11] & 128) != 0
    out["max_contacts"] = 20 if data[12] == 0 else data[12] * 10
    out["support_bp_settings"] = (data[13] & 2) != 0
    out["support_4g"] = (data[13] & 4) != 0
    out["support_nav_picture"] = (data[13] & 8) != 0
    out["support_pressure"] = (data[13] & 16) != 0
    out["support_hrv"] = (data[13] & 32) != 0
    return out


@dataclass
class PressureHistory:
    values: list[int]
    range_minutes: int

    def readings_with_times(self, target: datetime, *, clock_mode: str = "utc") -> list[tuple[int, datetime]]:
        start = date_utils.start_of_clock_day(target, clock_mode)
        out = []
        for index, reading in enumerate(self.values):
            out.append((reading, start + timedelta(minutes=index * self.range_minutes)))
        return out


class PressureHistoryParser:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.size = 0
        self.range_minutes = 0
        self._values: list[int] = []

    def parse(self, packet: bytearray) -> PressureHistory | NoData | None:
        command_id = packet[0] & 127
        if len(packet) != 16 or command_id != CMD_PRESSURE_HISTORY:
            raise ValueError("invalid pressure history packet")
        if packet[0] & 128:
            self.reset()
            return NoData()

        index = packet[1]
        if index == 255:
            self.reset()
            return NoData()
        if index == 0:
            self.size = packet[2]
            self.range_minutes = packet[3]
            self._values = []
            return None

        if index == 1:
            self._values.extend(list(packet[3:15]))
        else:
            # Empirically, streaming bytes from offset 2 preserves the fullest
            # current-day series for this bracelet.
            self._values.extend(list(packet[2:15]))

        if self.size and index == self.size - 1:
            slots_per_day = max(1, (24 * 60) // max(1, self.range_minutes))
            result = PressureHistory(values=self._values[:slots_per_day], range_minutes=self.range_minutes)
            self.reset()
            return result
        return None


@dataclass
class HrvHistory:
    values: list[int]
    range_minutes: int

    def readings_with_times(self, target: datetime, *, clock_mode: str = "utc") -> list[tuple[int, datetime]]:
        start = date_utils.start_of_clock_day(target, clock_mode)
        out = []
        for index, reading in enumerate(self.values):
            out.append((reading, start + timedelta(minutes=index * self.range_minutes)))
        return out


class HrvHistoryParser:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.size = 0
        self.range_minutes = 0
        self._raw_values: list[int] = []

    def parse(self, packet: bytearray) -> HrvHistory | NoData | None:
        command_id = packet[0] & 127
        if len(packet) != 16 or command_id != CMD_HRV_HISTORY:
            raise ValueError("invalid HRV history packet")
        if packet[0] & 128:
            self.reset()
            return NoData()

        index = packet[1]
        if index == 255:
            self.reset()
            return NoData()
        if index == 0:
            self.size = packet[2]
            # The protocol header reports `30` here, but live reconciliation
            # against the vendor app's historical HRV screen shows these slots
            # are displayed hourly on-device/app.
            self.range_minutes = 60
            self._raw_values = []
            return None

        if index == 1:
            self._raw_values.extend(list(packet[3:15]))
        else:
            self._raw_values.extend(list(packet[2:15]))

        if self.size and index == self.size - 1:
            values = []
            for offset in range(0, len(self._raw_values) - 1, 2):
                values.append(self._raw_values[offset] | (self._raw_values[offset + 1] << 8))
            result = HrvHistory(values=values, range_minutes=self.range_minutes)
            self.reset()
            return result
        return None


def read_pressure_history_packet(selector: int = 0) -> bytearray:
    if not 0 <= selector <= 255:
        raise ValueError("selector must be between 0 and 255")
    return make_packet(CMD_PRESSURE_HISTORY, bytearray([selector]))


def read_hrv_history_packet(selector: int = 0) -> bytearray:
    if not 0 <= selector <= 255:
        raise ValueError("selector must be between 0 and 255")
    return make_packet(CMD_HRV_HISTORY, bytearray([selector]))


class Action(IntEnum):
    START = 1
    PAUSE = 2
    CONTINUE = 3
    STOP = 4


class RealTimeMetric(IntEnum):
    HEART_RATE = 1
    BLOOD_PRESSURE = 2
    SPO2 = 3
    FATIGUE = 4
    HEALTH_CHECK = 5
    ECG = 7
    PRESSURE = 8
    BLOOD_SUGAR = 9
    HRV = 10


REALTIME_NAME_MAP = {
    "heart-rate": RealTimeMetric.HEART_RATE,
    "blood-pressure": RealTimeMetric.BLOOD_PRESSURE,
    "spo2": RealTimeMetric.SPO2,
    "fatigue": RealTimeMetric.FATIGUE,
    "health-check": RealTimeMetric.HEALTH_CHECK,
    "ecg": RealTimeMetric.ECG,
    "pressure": RealTimeMetric.PRESSURE,
    "blood-sugar": RealTimeMetric.BLOOD_SUGAR,
    "hrv": RealTimeMetric.HRV,
}


@dataclass
class RealTimeSample:
    metric: str
    value: int
    error_code: int = 0


@dataclass
class HealthCheckSample:
    diastolic: int | None
    systolic: int | None
    heart_rate: int | None
    cuff_pressure_tenths: int
    error_code: int = 0

    @property
    def has_blood_pressure_result(self) -> bool:
        return (self.diastolic or 0) > 0 and (self.systolic or 0) > 0


def start_realtime_packet(metric: RealTimeMetric) -> bytearray:
    return make_packet(CMD_START_REAL_TIME, bytearray([metric, Action.START]))


def stop_realtime_packet(metric: RealTimeMetric) -> bytearray:
    return make_packet(CMD_STOP_REAL_TIME, bytearray([metric, 0, 0]))


def parse_realtime_packet(packet: bytearray) -> RealTimeSample:
    if len(packet) != 16 or packet[0] != CMD_START_REAL_TIME:
        raise ValueError("invalid realtime packet")
    metric = RealTimeMetric(packet[1])
    error_code = packet[2]
    return RealTimeSample(metric=metric.name.lower(), value=packet[3], error_code=error_code)


def parse_health_check_packet(packet: bytearray) -> HealthCheckSample:
    if len(packet) != 16 or packet[0] != CMD_START_REAL_TIME or packet[1] != RealTimeMetric.HEALTH_CHECK:
        raise ValueError("invalid health-check packet")
    error_code = packet[2]
    diastolic = packet[3] or None
    systolic = packet[4] or None
    heart_rate = packet[5] or None
    cuff_pressure_tenths = packet[6] | (packet[7] << 8)
    return HealthCheckSample(
        diastolic=diastolic,
        systolic=systolic,
        heart_rate=heart_rate,
        cuff_pressure_tenths=cuff_pressure_tenths,
        error_code=error_code,
    )


def bigdata_request_packet(data_id: int) -> bytes:
    if not 0 <= data_id <= 255:
        raise ValueError("data_id must be between 0 and 255")
    return bytes((BIGDATA_MAGIC, data_id, 0, 0, 255, 255))


@dataclass
class SleepPeriod:
    stage: str
    minutes: int


@dataclass
class SleepSession:
    days_ago: int
    bytes_used: int
    sleep_start_minutes: int
    sleep_end_minutes: int
    periods: list[SleepPeriod]

    def resolved_bounds(self, reference: datetime) -> tuple[datetime, datetime]:
        end_day = date_utils.start_of_day(reference) - timedelta(days=max(0, self.days_ago - 1))
        end_timestamp = end_day + timedelta(minutes=self.sleep_end_minutes)
        start_timestamp = end_day + timedelta(minutes=self.sleep_start_minutes)
        if self.sleep_start_minutes > self.sleep_end_minutes:
            start_timestamp -= timedelta(days=1)
        return start_timestamp, end_timestamp

    def has_valid_bounds(self) -> bool:
        if self.bytes_used < 4:
            return False
        if not self.periods:
            return False
        if not 0 <= self.sleep_start_minutes <= 48 * 60:
            return False
        if not 0 <= self.sleep_end_minutes <= 48 * 60:
            return False
        return True


def parse_bigdata_sleep(payload: bytes) -> list[SleepSession]:
    if len(payload) < 7 or payload[0] != BIGDATA_MAGIC or payload[1] != BIGDATA_SLEEP_ID:
        raise ValueError("invalid bigdata sleep payload")
    data_len = int.from_bytes(payload[2:4], "little")
    body = payload[6 : 6 + data_len]
    if not body:
        return []

    stage_names = {
        0: "no-data",
        1: "error",
        2: "light",
        3: "deep",
        5: "awake",
    }
    sleep_days = body[0]
    offset = 1
    sessions: list[SleepSession] = []
    for _ in range(sleep_days):
        if offset + 6 > len(body):
            break
        days_ago = body[offset]
        bytes_used = body[offset + 1]
        if bytes_used < 4:
            break
        sleep_start = struct.unpack_from("<h", body, offset + 2)[0]
        sleep_end = struct.unpack_from("<h", body, offset + 4)[0]
        offset += 6

        periods: list[SleepPeriod] = []
        period_bytes = max(0, bytes_used - 4)
        consumed = 0
        while consumed + 2 <= period_bytes and offset + 1 < len(body):
            stage_code = body[offset]
            duration = body[offset + 1]
            periods.append(SleepPeriod(stage=stage_names.get(stage_code, f"unknown-{stage_code}"), minutes=duration))
            offset += 2
            consumed += 2

        sessions.append(
            SleepSession(
                days_ago=days_ago,
                bytes_used=bytes_used,
                sleep_start_minutes=sleep_start,
                sleep_end_minutes=sleep_end,
                periods=periods,
            )
        )
    return sessions


@dataclass
class BloodOxygenSample:
    min_percent: int
    max_percent: int


@dataclass
class BloodOxygenHistory:
    unknown_flag: int
    samples: list[BloodOxygenSample]
    slots_per_day: int = 48
    interval_minutes: int = 30
    start_index: int = 0

    def samples_with_times(self, target: datetime, *, clock_mode: str = "utc") -> list[tuple[BloodOxygenSample, datetime]]:
        start = date_utils.start_of_clock_day(target, clock_mode) + timedelta(minutes=self.start_index * self.interval_minutes)
        out = []
        for index, sample in enumerate(self.samples[: self.slots_per_day]):
            out.append((sample, start + timedelta(minutes=index * self.interval_minutes)))
        return out


def parse_bigdata_blood_oxygen(payload: bytes) -> BloodOxygenHistory:
    if len(payload) < 7 or payload[0] != BIGDATA_MAGIC or payload[1] != BIGDATA_BLOOD_OXYGEN_ID:
        raise ValueError("invalid bigdata blood oxygen payload")
    data_len = int.from_bytes(payload[2:4], "little")
    body = payload[6 : 6 + data_len]
    if not body:
        return BloodOxygenHistory(unknown_flag=0, samples=[])

    unknown_flag = body[0]
    sample_bytes = body[1:]
    if unknown_flag == 2 and len(sample_bytes) >= 34:
        # In local-clock mode, the vendor app's visible hourly SpO2 rows map
        # to the final 17 duplicated byte-pairs in the payload.
        tail = sample_bytes[-34:]
        samples = []
        for index in range(0, len(tail) - 1, 2):
            samples.append(BloodOxygenSample(min_percent=tail[index], max_percent=tail[index + 1]))
        return BloodOxygenHistory(
            unknown_flag=unknown_flag,
            samples=samples,
            slots_per_day=len(samples),
            interval_minutes=60,
            start_index=7,
        )

    samples = []
    for index in range(0, len(sample_bytes) - 1, 2):
        samples.append(BloodOxygenSample(min_percent=sample_bytes[index], max_percent=sample_bytes[index + 1]))
    return BloodOxygenHistory(unknown_flag=unknown_flag, samples=samples)


@dataclass
class BloodPressureReading:
    timestamp: datetime
    diastolic: int
    systolic: int


def parse_blood_pressure_packet(packet: bytearray) -> BloodPressureReading:
    command_id = packet[0] & 127
    if len(packet) != 16 or command_id != 20:
        raise ValueError("invalid blood pressure packet")
    ts = struct.unpack_from("<I", packet, offset=1)[0]
    return BloodPressureReading(
        timestamp=datetime.fromtimestamp(ts, timezone.utc),
        diastolic=packet[5],
        systolic=packet[6],
    )


def to_json(value: Any) -> str:
    def _default(item: Any) -> Any:
        if isinstance(item, datetime):
            return item.isoformat()
        if hasattr(item, "__dict__"):
            return item.__dict__
        raise TypeError(f"Object of type {type(item)!r} is not JSON serializable")

    return json.dumps(value, default=_default, sort_keys=True)


BATTERY_PACKET = make_packet(CMD_BATTERY)
READ_HEART_RATE_LOG_SETTINGS_PACKET = make_packet(CMD_HEART_RATE_LOG_SETTINGS, bytearray(b"\x01"))
BLINK_TWICE_PACKET = make_packet(CMD_BLINK_TWICE)
REBOOT_PACKET = make_packet(CMD_REBOOT, bytearray(b"\x01"))
