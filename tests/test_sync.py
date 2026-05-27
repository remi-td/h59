from datetime import UTC, datetime

from h59_client.sync import (
    INITIAL_BACKFILL_MAX_DAYS,
    determine_initial_backfill_dates,
    determine_history_selector,
    determine_sync_dates,
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
