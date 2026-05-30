"""Local-first tools for H59 BLE sync, storage, and analytics."""

__all__ = ["__version__", "summary_from_db"]

__version__ = "0.0.1"

def summary_from_db(conn):
    """Return a short summary dict from an open sqlite3.Connection.

    The function is intentionally small: it reads table counts for quick
    inspection during development and tests.
    """
    cur = conn.cursor()
    out = {}
    for t in (
        "database_metadata",
        "devices",
        "syncs",
        "heart_rates",
        "sport_details",
        "battery_samples",
        "heart_rate_settings",
        "capability_snapshots",
        "realtime_samples",
        "raw_packets",
        "sleep_sessions",
        "sleep_stage_samples",
        "blood_oxygen_samples",
        "blood_pressure_readings",
        "pressure_samples",
        "hrv_samples",
    ):
        try:
            cur.execute(f"SELECT COUNT(*) FROM \"{t}\"")
            out[t] = cur.fetchone()[0]
        except Exception:
            out[t] = None
    return out
