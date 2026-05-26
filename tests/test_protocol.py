from datetime import UTC, datetime

from h59_client.protocol import (
    ActivityBlockParser,
    HeartRateDayParser,
    parse_battery,
    parse_capabilities,
    parse_heart_rate_log_settings,
    parse_realtime_packet,
)


def test_parse_battery_packet():
    sample = bytearray.fromhex("0357000000000000000000000000005a")
    parsed = parse_battery(sample)
    assert parsed.battery_level == 87
    assert parsed.charging is False


def test_parse_heart_rate_log_settings_packet():
    sample = bytearray.fromhex("16010105050000000000000000000022")
    parsed = parse_heart_rate_log_settings(sample)
    assert parsed.enabled is True
    assert parsed.interval == 5


def test_parse_capability_packet():
    sample = bytearray.fromhex("01000001160000000001002000003069")
    parsed = parse_capabilities(sample)
    assert parsed["support_spo2"] is True
    assert parsed["support_blood_pressure"] is True
    assert parsed["new_sleep_protocol"] is True
    assert parsed["support_pressure"] is True
    assert parsed["support_hrv"] is True


def test_parse_activity_block_sequence():
    parser = ActivityBlockParser()
    packets = [
        "43f00c01000000000000000000000040",
        "432605251c000c7702ed0092000000b3",
        "4326052520010c8e0514024b010000b5",
        "4326052524020c5d0dcc04190300001b",
        "4326052528030c1e0b0b049402000098",
        "432605252c040c4608f402ec01000000",
        "4326052530050cb9053402550100001e",
        "4326052534060c8604b2010d01000024",
        "432605253c070c9b0977033a0200003c",
        "4326052540080ca1098b033c0200005d",
        "4326052544090ce50861031202000051",
        "43260525480a0c630939032c020000c7",
        "432605254c0b0c9204b5010f01000052",
    ]

    result = None
    for packet in packets:
        result = parser.parse(bytearray.fromhex(packet))

    assert result is not None
    assert len(result) == 12
    assert result[0].timestamp == datetime(2026, 5, 25, 7, 0, tzinfo=UTC)
    assert result[-1].steps == 437


def test_parse_heart_rate_day_sequence():
    parser = HeartRateDayParser()
    packets = [
        "15001805000000000000000000000032",
        "15010091136a3e3f403f3e3f3d3f4861",
        "15023f3c46414340453e41393d3c4052",
        "1503383c3d38383d3f3c3f3f3c3c3e25",
        "15043c3c3f3b3e3e3e3e433f46473f51",
        "1505413e3d3d3e3e3f3e413c41494457",
        "1506444040403e403e3d3b3e3e3f3f4d",
        "15073f3d35413f433e51473f5f3a3977",
        "15083b3b3c3d3b3c4359476e5d4547bd",
        "15094b552e4a4a4d47404b7145696422",
        "150a5045604f4e6959554645504f4436",
        "150b6075565f60614d45494c476a4f92",
        "150c66596e566b4e57656a61484d49c2",
        "150d4d566d4e4a58674947584c57596d",
        "150e6f47424d494446424445414449d4",
        "150f484b324472536e405e5560585b66",
        "1510586560676051505350645d595fc6",
        "1511695f64575e4765566762665c52e6",
        "151255686962756876505b5c516a4b0f",
        "15134a4d59445159494d595559726d82",
        "1514494c573c507a4b5f525048646a7d",
        "15154900000000000000000000000073",
        "1516000000000000000000000000002b",
        "1517000000000000000000000000002c",
    ]

    result = None
    for packet in packets:
        result = parser.parse(bytearray.fromhex(packet))

    assert result is not None
    assert result.timestamp == datetime(2026, 5, 25, 0, 0, tzinfo=UTC)
    assert result.heart_rates[0] == 62
    assert result.heart_rates[10] == 60


def test_parse_realtime_packet():
    parsed = parse_realtime_packet(bytearray.fromhex("6903000000000000000000000000006c"))
    assert parsed.metric == "spo2"
    assert parsed.value == 0
