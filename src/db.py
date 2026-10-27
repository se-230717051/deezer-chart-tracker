"""Shared database helpers. Every script connects through connect()."""
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("DB_PATH") or ROOT / "data" / "deezer.db")
SCHEMA_PATH = ROOT / "sql" / "schema.sql"

# One fixed query per table (used to count rows and compare contents).
TABLE_QUERIES = {
    "genre": "SELECT * FROM genre",
    "artist": "SELECT * FROM artist",
    "album": "SELECT * FROM album",
    "track": "SELECT * FROM track",
    "recording": "SELECT * FROM recording",
    "track_detail": "SELECT * FROM track_detail",
    "album_detail": "SELECT * FROM album_detail",
    "chart_entry": "SELECT * FROM chart_entry",
    "artist_fans": "SELECT * FROM artist_fans",
    "track_recording": "SELECT * FROM track_recording",
    "quarantine": "SELECT * FROM quarantine",
}


def connect(path=None):
    """Open the database and switch foreign key checking ON (it is OFF by default)."""
    con = sqlite3.connect(path or DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    return con


def create_schema(con):
    if sqlite3.sqlite_version_info < (3, 37, 0):
        raise SystemExit("SQLite %s is too old: STRICT tables need 3.37 or newer. "
                         "Install a newer Python." % sqlite3.sqlite_version)
    con.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def snapshot(con):
    """Return {table: sorted rows} for every table."""
    return {table: sorted(con.execute(query).fetchall(), key=repr)
            for table, query in TABLE_QUERIES.items()}


def row_counts(con):
    return {table: len(rows) for table, rows in snapshot(con).items()}
