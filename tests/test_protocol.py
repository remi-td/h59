from datetime import UTC, datetime

from h59_client.protocol import (
    ActivityBlockParser,
    HrvHistoryParser,
    HeartRateDayParser,
    PressureHistoryParser,
    parse_bigdata_blood_oxygen,
    parse_bigdata_sleep,
    parse_battery,
    parse_capabilities,
    parse_heart_rate_log_settings,
    parse_realtime_packet,
    read_hrv_history_packet,
    read_pressure_history_packet,
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


def test_pressure_history_packet_uses_selector_byte():
    packet = read_pressure_history_packet(3)
    assert packet.hex() == "3703000000000000000000000000003a"


def test_hrv_history_packet_uses_selector_byte():
    packet = read_hrv_history_packet(2)
    assert packet.hex() == "3902000000000000000000000000003b"


def test_parse_pressure_history_packets():
    parser = PressureHistoryParser()
    packets = [
        "3700051e00000000000000000000005a",
        "3701002b29412e2f302d28303c331b69",
        "3702252d3d25232d311f29302f2a1e5d",
        "37032531301f2f27312f2527292b275c",
        "370440222c2c000000000000000000f5",
    ]

    result = None
    for packet in packets:
        result = parser.parse(bytearray.fromhex(packet))

    assert result is not None
    assert result.range_minutes == 30
    assert result.values[:5] == [43, 41, 65, 46, 47]
    assert len([value for value in result.values if value]) == 42


def test_parse_hrv_history_packets():
    parser = HrvHistoryParser()
    packets = [
        "3900051e00000000000000000000005c",
        "3901002f002c002d002b003200240043",
        "39022b002d002d00290030002e002d74",
        "3903001e002a001e002c001e002f001b",
        "39043100260000000000000000000094",
    ]

    result = None
    for packet in packets:
        result = parser.parse(bytearray.fromhex(packet))

    assert result is not None
    assert result.range_minutes == 30
    assert result.values[:5] == [47, 44, 45, 43, 50]
    assert [value for value in result.values if value][-1] == 38


def test_parse_bigdata_sleep_payload():
    payload = bytes.fromhex(
        "bc275b005cf502012c8305ce01022603140212041102160412022003100224040e031204160209033a041b0233040c020d050a0228002a9a059d010219040f0318022204120210041203140412032d0233041a021e041b02120418020105030206"
    )

    sessions = parse_bigdata_sleep(payload)

    assert len(sessions) == 2
    assert sessions[0].days_ago == 1
    assert sessions[0].periods[0].stage == "light"
    assert sessions[0].periods[0].minutes == 38
    assert sessions[0].has_valid_bounds() is True
    assert sum(period.minutes for period in sessions[0].periods) == 491
    start_ts, end_ts = sessions[0].resolved_bounds(datetime(2026, 5, 26, 20, 58, 20, tzinfo=UTC))
    assert start_ts == datetime(2026, 5, 25, 23, 31, tzinfo=UTC)
    assert end_ts == datetime(2026, 5, 26, 7, 42, tzinfo=UTC)
    assert sessions[1].days_ago == 0
    assert sessions[1].has_valid_bounds() is True


def test_parse_bigdata_sleep_payload_with_three_blocks():
    payload = bytes.fromhex(
        "bc279900fef203022c8305ce01022603140212041102160412022003100224040e031204160209033a041b0233040c020d050a0228012a9a059d010219040f0318022204120210041203140412032d0233041a021e041b02120418020105030206003c8c0511020223030b040d0214031a0410021c04110221040f022a040a021c0339020a0416022304080509020a0503021f0505020405060217041c0204"
    )

    sessions = parse_bigdata_sleep(payload)

    assert len(sessions) == 3
    assert sessions[0].days_ago == 2
    assert sessions[1].days_ago == 1
    assert sessions[2].days_ago == 0
    assert sessions[1].sleep_start_minutes == 1434
    assert sessions[1].sleep_end_minutes == 413
    assert sessions[2].sleep_start_minutes == 1420
    assert sessions[2].sleep_end_minutes == 529


def test_parse_bigdata_blood_oxygen_payload():
    payload = bytes.fromhex(
        "bc2a6200933e0161616161636361616262626262626161636363636161626260606363636360606060606061616262626200006262636300636363636363616161616363636361616060636361616363636363636161636360606363636362626161000000000000"
    )

    history = parse_bigdata_blood_oxygen(payload)

    assert history.unknown_flag == 1
    assert len(history.samples) > 40
    assert history.samples[0].min_percent == 97
    assert history.samples[0].max_percent == 97
    samples = history.samples_with_times(datetime(2026, 5, 26, 12, 0, tzinfo=UTC))
    assert len(samples) == 48
    assert samples[-1][1] == datetime(2026, 5, 26, 23, 30, tzinfo=UTC)
