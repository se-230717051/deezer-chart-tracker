"""Six checks that prove the database behaves. Run: python src/checks.py

Everything happens in a temporary folder; the real database is never touched.
"""
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

import db
import load

NOW = "2026-01-01T00:00:00Z"
results = []


def report(name, passed, detail=""):
    results.append(passed)
    print("%-22s %s %s" % (name + ":", "PASS" if passed else "FAIL", detail))


def is_rejected(con, sql, params):
    """True if the database refuses this statement."""
    try:
        con.execute(sql, params)
        con.commit()
        return False
    except sqlite3.Error:
        con.rollback()
        return True


def add_test_rows(con):
    """Insert one genre, artist, album and track. Returns (genre_key, artist_key, track_key)."""
    con.execute("INSERT INTO genre (deezer_id, name, retrieved_at) VALUES (?, ?, ?)",
                (-1, "test genre", NOW))
    con.execute("INSERT INTO artist (deezer_id, name, retrieved_at) VALUES (?, ?, ?)",
                (-1, "test artist", NOW))
    con.execute("INSERT INTO album (deezer_id, title, retrieved_at) VALUES (?, ?, ?)",
                (-1, "test album", NOW))
    genre_key = con.execute("SELECT genre_key FROM genre WHERE deezer_id = ?", (-1,)).fetchone()[0]
    artist_key = con.execute("SELECT artist_key FROM artist WHERE deezer_id = ?", (-1,)).fetchone()[0]
    album_key = con.execute("SELECT album_key FROM album WHERE deezer_id = ?", (-1,)).fetchone()[0]
    con.execute("INSERT INTO track (deezer_id, title, artist_key, album_key, retrieved_at) "
                "VALUES (?, ?, ?, ?, ?)", (-1, "test track", artist_key, album_key, NOW))
    track_key = con.execute("SELECT track_key FROM track WHERE deezer_id = ?", (-1,)).fetchone()[0]
    con.commit()
    return genre_key, artist_key, track_key


def constraint_checks(tmp):
    # work on a copy of the real database (or a fresh one if it does not exist yet)
    copy = tmp / "copy.db"
    if db.DB_PATH.exists():
        shutil.copyfile(db.DB_PATH, copy)
    con = db.connect(copy)
    db.create_schema(con)
    genre_key, artist_key, track_key = add_test_rows(con)

    report("duplicate natural key", is_rejected(
        con, "INSERT INTO artist (deezer_id, name, retrieved_at) VALUES (?, ?, ?)",
        (-1, "same id again", NOW)))
    report("orphan event", is_rejected(
        con, "INSERT INTO chart_entry (genre_key, snapshot_date, position, track_key, retrieved_at) "
             "VALUES (?, ?, ?, ?, ?)", (-999, "2026-01-01", 1, -999, NOW)))
    report("NULL key", is_rejected(
        con, "INSERT INTO chart_entry (genre_key, snapshot_date, position, track_key, retrieved_at) "
             "VALUES (?, ?, ?, ?, ?)", (genre_key, "2026-01-01", None, track_key, NOW)))
    report("wrong type", is_rejected(
        con, "INSERT INTO artist_fans (artist_key, snapshot_date, nb_fan, retrieved_at) "
             "VALUES (?, ?, ?, ?)", (artist_key, "2026-01-01", "n/a", NOW)))
    con.close()


def idempotence_check(tmp):
    con = db.connect(tmp / "idem.db")
    db.create_schema(con)
    load.load_all(con)
    first = db.snapshot(con)
    load.load_all(con)
    second = db.snapshot(con)
    con.close()
    has_data = sum(len(rows) for rows in first.values()) > 0
    report("idempotence", has_data and first == second,
           "" if has_data else "(no raw data found: run ingest.py first)")


def atomicity_check(tmp):
    # copy the raw data and add one broken file that is read last
    raw_copy = tmp / "raw"
    if load.RAW_DIR.exists():
        shutil.copytree(load.RAW_DIR, raw_copy)
    (raw_copy / "deezer_chart").mkdir(parents=True, exist_ok=True)
    (raw_copy / "deezer_chart" / "29990101T000000Z_genre0_p1.json").write_text("{ broken json")

    con = db.connect(tmp / "atomic.db")
    db.create_schema(con)
    before = db.row_counts(con)
    failed = False
    try:
        load.load_all(con, raw_copy)
    except Exception:
        failed = True
    after = db.row_counts(con)
    con.close()
    report("atomicity", failed and before == after,
           "" if failed else "(the broken file did not make the load fail)")


def main():
    with tempfile.TemporaryDirectory() as folder:
        tmp = Path(folder)
        original_raw = load.RAW_DIR
        constraint_checks(tmp)
        idempotence_check(tmp)
        atomicity_check(tmp)
        load.RAW_DIR = original_raw
    print("\n%d of %d checks passed" % (sum(results), len(results)))
    return 0 if all(results) and len(results) == 6 else 1


if __name__ == "__main__":
    sys.exit(main())
