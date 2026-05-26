from datetime import UTC, datetime

from h59_client.sync import determine_sync_dates


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
