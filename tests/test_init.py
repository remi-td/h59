import sqlite3
import os
from h59_client import __version__, summary_from_db


def test_version():
    assert isinstance(__version__, str)


def test_summary_on_existing_db():
    db_path = os.path.join(os.getcwd(), "data", "h59.sqlite")
    if not os.path.exists(db_path):
        # If the user hasn't created a DB, create a transient one for the test
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE devices(device_id INTEGER);")
        conn.commit()
    else:
        conn = sqlite3.connect(db_path)

    s = summary_from_db(conn)
    assert isinstance(s, dict)
