"""Builds the cleaned layer from the M2 tables. Run: python src/clean.py

Reads only the M2 tables (never raw files, never the API) and writes only the *_clean tables
and identity_map. The M2 tables are not changed; the script checks that itself.

Order of the rules (first rule that applies wins):
  text:    1 missing_not_reported  2 unicode_normalised  3 whitespace_fixed  4 ok
  numbers: 1 missing_not_reported  2 invalid_range  3 unusual_high / unusual_low  4 ok
"""
import csv
import hashlib
import math
import statistics
import sys
import traceback
import unicodedata
from collections import Counter

import clean_config as cfg
import db

CLEAN_SCHEMA = db.ROOT / "sql" / "clean_schema.sql"

# ---------- SQL (values always go in through ? placeholders) ----------
ARTIST_KEY = "SELECT artist_key FROM artist WHERE deezer_id = ?"

SELECT_ARTISTS = "SELECT artist_key, name FROM artist ORDER BY artist_key"
SELECT_ALBUMS = "SELECT album_key, title FROM album ORDER BY album_key"
SELECT_TRACKS = "SELECT track_key, title, duration FROM track ORDER BY track_key"
SELECT_FANS = ("SELECT artist_key, snapshot_date, nb_fan, retrieved_at FROM artist_fans "
               "ORDER BY artist_key, snapshot_date")
SELECT_RECORDINGS = ("SELECT recording_key, length_ms, first_release_date, retrieved_at "
                     "FROM recording ORDER BY recording_key")

UPSERT_ARTIST = """
INSERT INTO artist_clean (artist_key, name_raw, name, name_key, name_flag) VALUES (?, ?, ?, ?, ?)
ON CONFLICT (artist_key) DO UPDATE SET name_raw = excluded.name_raw, name = excluded.name,
    name_key = excluded.name_key, name_flag = excluded.name_flag
"""
UPSERT_ALBUM = """
INSERT INTO album_clean (album_key, title_raw, title, title_key, title_flag) VALUES (?, ?, ?, ?, ?)
ON CONFLICT (album_key) DO UPDATE SET title_raw = excluded.title_raw, title = excluded.title,
    title_key = excluded.title_key, title_flag = excluded.title_flag
"""
UPSERT_TRACK = """
INSERT INTO track_clean (track_key, title_raw, title, title_key, title_flag,
                         duration_raw, duration, duration_flag)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (track_key) DO UPDATE SET title_raw = excluded.title_raw, title = excluded.title,
    title_key = excluded.title_key, title_flag = excluded.title_flag,
    duration_raw = excluded.duration_raw, duration = excluded.duration,
    duration_flag = excluded.duration_flag
"""
UPSERT_FANS = """
INSERT INTO artist_fans_clean (artist_key, snapshot_date, nb_fan_raw, nb_fan, nb_fan_flag)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT (artist_key, snapshot_date) DO UPDATE SET nb_fan_raw = excluded.nb_fan_raw,
    nb_fan = excluded.nb_fan, nb_fan_flag = excluded.nb_fan_flag
"""
UPSERT_RECORDING = """
INSERT INTO recording_clean (recording_key, length_ms_raw, length_ms, length_ms_flag,
                             first_release_date_raw, first_release_date, first_release_date_flag)
VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (recording_key) DO UPDATE SET length_ms_raw = excluded.length_ms_raw,
    length_ms = excluded.length_ms, length_ms_flag = excluded.length_ms_flag,
    first_release_date_raw = excluded.first_release_date_raw,
    first_release_date = excluded.first_release_date,
    first_release_date_flag = excluded.first_release_date_flag
"""
CLEAR_IDENTITY_MAP = "DELETE FROM identity_map"   # rebuilt from the CSV on every run
INSERT_IDENTITY = """
INSERT INTO identity_map (alias_artist_key, canonical_artist_key, decision, decided_by,
                          decided_at, note) VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT (alias_artist_key, canonical_artist_key) DO UPDATE SET decision = excluded.decision,
    decided_by = excluded.decided_by, decided_at = excluded.decided_at, note = excluded.note
"""
UNRESOLVED_NAME_COLLISIONS = """
SELECT COUNT(DISTINCT a.name_key) FROM artist_clean AS a
WHERE a.name_key IN (SELECT name_key FROM artist_clean WHERE name_key IS NOT NULL
                     GROUP BY name_key HAVING COUNT(*) > 1)
  AND NOT EXISTS (SELECT 1 FROM identity_map AS m
                  WHERE m.alias_artist_key = a.artist_key OR m.canonical_artist_key = a.artist_key)
"""

# cleaned table -> (count in the cleaned table, count in the M2 table it cleans)
ROW_COUNTS = {
    "artist_clean": ("SELECT COUNT(*) FROM artist_clean", "SELECT COUNT(*) FROM artist"),
    "album_clean": ("SELECT COUNT(*) FROM album_clean", "SELECT COUNT(*) FROM album"),
    "track_clean": ("SELECT COUNT(*) FROM track_clean", "SELECT COUNT(*) FROM track"),
    "artist_fans_clean": ("SELECT COUNT(*) FROM artist_fans_clean",
                          "SELECT COUNT(*) FROM artist_fans"),
    "recording_clean": ("SELECT COUNT(*) FROM recording_clean", "SELECT COUNT(*) FROM recording"),
}
CLEAN_QUERIES = {
    "artist_clean": "SELECT * FROM artist_clean",
    "album_clean": "SELECT * FROM album_clean",
    "track_clean": "SELECT * FROM track_clean",
    "artist_fans_clean": "SELECT * FROM artist_fans_clean",
    "recording_clean": "SELECT * FROM recording_clean",
    "identity_map": "SELECT * FROM identity_map",
}


# ---------- cleaning rules ----------

def clean_text(raw):
    """Returns (cleaned text, flag)."""
    if raw is None or raw.strip() == "":
        return None, "missing_not_reported"
    nfc = unicodedata.normalize("NFC", raw)        # e + combining accent -> single letter
    spaced = " ".join(nfc.split())                 # non-breaking spaces, padding, double spaces
    if nfc != raw:
        return spaced, "unicode_normalised"
    if spaced != nfc:
        return spaced, "whitespace_fixed"
    return spaced, "ok"


def match_key(text):
    """For matching names only: NFKD, drop accents, fold Turkish i, casefold, single spaces."""
    if text is None:
        return None
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("\u0131", "i")             # dotless i
    return " ".join(text.casefold().split())


def fences(values, transform):
    """IQR fences (Tukey). Not distorted by the outliers they look for."""
    shaped = [transform(v) for v in values]
    if len(shaped) < 2:
        return -math.inf, math.inf
    q1, _, q3 = statistics.quantiles(shaped, n=4, method="inclusive")
    spread = q3 - q1
    return q1 - cfg.IQR_K * spread, q3 + cfg.IQR_K * spread


def number_flag(raw, low_limit, high_limit, fence, transform):
    """Returns (cleaned value, flag). Never fills in a missing value."""
    if raw is None:
        return None, "missing_not_reported"
    if raw < low_limit or raw > high_limit:
        return None, "invalid_range"
    low, high = fence
    if transform(raw) > high:
        return raw, "unusual_high"
    if transform(raw) < low:
        return raw, "unusual_low"
    return raw, "ok"


def identity(x):
    return x


def log_count(x):
    return math.log10(x + 1)


# ---------- building the cleaned tables ----------

def clean_names(con, stats, select, upsert, table):
    for key, raw in con.execute(select).fetchall():
        value, flag = clean_text(raw)
        con.execute(upsert, (key, raw, value, match_key(value), flag))
        stats[table]["text_flag"][flag] += 1
        stats[table]["rows"] += 1


def clean_tracks(con, stats):
    rows = con.execute(SELECT_TRACKS).fetchall()
    valid = [d for _, _, d in rows if d is not None and 0 < d <= cfg.MAX_DURATION_S]
    fence = fences(valid, identity)
    for key, title, duration in rows:
        value, flag = clean_text(title)
        number, number_flag_ = number_flag(duration, 1, cfg.MAX_DURATION_S, fence, identity)
        con.execute(UPSERT_TRACK, (key, title, value, match_key(value), flag,
                                   duration, number, number_flag_))
        stats["track_clean"]["text_flag"][flag] += 1
        stats["track_clean"]["number_flag"][number_flag_] += 1
        stats["track_clean"]["rows"] += 1


def clean_fans(con, stats):
    rows = con.execute(SELECT_FANS).fetchall()
    valid = [n for _, _, n, _ in rows if n is not None and n >= 0]
    fence = fences(valid, log_count)            # fan counts span 6 orders of magnitude: use log
    for key, day, nb_fan, _ in rows:
        value, flag = number_flag(nb_fan, 0, math.inf, fence, log_count)
        con.execute(UPSERT_FANS, (key, day, nb_fan, value, flag))
        stats["artist_fans_clean"]["number_flag"][flag] += 1
        stats["artist_fans_clean"]["rows"] += 1


def clean_recordings(con, stats):
    rows = con.execute(SELECT_RECORDINGS).fetchall()
    valid = [m for _, m, _, _ in rows if m is not None and 0 < m <= cfg.MAX_LENGTH_MS]
    fence = fences(valid, identity)
    for key, length, released, retrieved_at in rows:
        value, flag = number_flag(length, 1, cfg.MAX_LENGTH_MS, fence, identity)
        if released is None:
            date_value, date_flag = None, "missing_not_reported"
        elif released > retrieved_at[:10]:         # released after the day we retrieved it
            date_value, date_flag = None, "invalid_future"
        else:
            date_value, date_flag = released, "ok"
        con.execute(UPSERT_RECORDING, (key, length, value, flag, released, date_value, date_flag))
        stats["recording_clean"]["number_flag"][flag] += 1
        stats["recording_clean"]["date_flag"][date_flag] += 1
        stats["recording_clean"]["rows"] += 1


def load_identity_map(con, stats, csv_path):
    """Loads the identity decisions from the committed CSV. Unmatched rows are reported."""
    con.execute(CLEAR_IDENTITY_MAP)
    with open(csv_path, encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        needed = {"alias_source_id", "canonical_source_id", "decision", "decided_by",
                  "decided_at", "note"}
        if not needed <= set(reader.fieldnames or []):
            raise ValueError("mapping CSV needs the columns: " + ", ".join(sorted(needed)))
        for row in reader:
            stats["mapping_rows_in_csv"] += 1
            try:
                alias = con.execute(ARTIST_KEY, (int(row["alias_source_id"]),)).fetchone()
                canonical = con.execute(ARTIST_KEY, (int(row["canonical_source_id"]),)).fetchone()
            except ValueError:
                alias = canonical = None
            if alias is None or canonical is None:
                stats["mapping_unmatched"].append("%s -> %s" % (row["alias_source_id"],
                                                                row["canonical_source_id"]))
                continue
            con.execute(INSERT_IDENTITY, (alias[0], canonical[0], row["decision"],
                                          row["decided_by"], row["decided_at"], row["note"]))
            stats["mapping_loaded"] += 1


def fingerprint(con):
    """One hash per M2 table, to prove that cleaning did not change them."""
    return {table: hashlib.sha256(repr(rows).encode("utf-8")).hexdigest()
            for table, rows in db.snapshot(con).items()}


def new_stats():
    tables = ["artist_clean", "album_clean", "track_clean", "artist_fans_clean", "recording_clean"]
    return {"mapping_rows_in_csv": 0, "mapping_loaded": 0, "mapping_unmatched": [],
            "collisions": 0,
            **{t: {"rows": 0, "text_flag": Counter(), "number_flag": Counter(),
                   "date_flag": Counter()} for t in tables}}


def build(con, mapping_csv=None):
    """Builds the whole cleaned layer in ONE transaction: all of it, or nothing."""
    stats = new_stats()
    before = fingerprint(con)
    with con:
        clean_names(con, stats, SELECT_ARTISTS, UPSERT_ARTIST, "artist_clean")
        clean_names(con, stats, SELECT_ALBUMS, UPSERT_ALBUM, "album_clean")
        clean_tracks(con, stats)
        clean_fans(con, stats)
        clean_recordings(con, stats)
        load_identity_map(con, stats, mapping_csv or cfg.MAPPING_CSV)
        stats["collisions"] = con.execute(UNRESOLVED_NAME_COLLISIONS).fetchone()[0]
        for table, (clean_sql, raw_sql) in ROW_COUNTS.items():
            if con.execute(clean_sql).fetchone()[0] != con.execute(raw_sql).fetchone()[0]:
                raise RuntimeError(table + " does not have the same number of rows as its raw table")
        if con.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("foreign_key_check found broken references")
        if fingerprint(con) != before:
            raise RuntimeError("an M2 table was changed: rolling back")
    return stats


def clean_snapshot(con):
    return {table: sorted(con.execute(query).fetchall(), key=repr)
            for table, query in CLEAN_QUERIES.items()}


def print_summary(con, stats):
    for table, (clean_sql, raw_sql) in ROW_COUNTS.items():
        print("%s: %s rows (raw: %s)" % (table, format(con.execute(clean_sql).fetchone()[0], ","),
                                         format(con.execute(raw_sql).fetchone()[0], ",")))
        for kind in ("text_flag", "number_flag", "date_flag"):
            counts = stats[table][kind]
            if counts:
                print("   %-12s %s" % (kind + ":", " | ".join("%s %d" % item
                                                              for item in sorted(counts.items()))))
    print("mappings: identity_map %d of %d CSV rows loaded (unmatched: %s)"
          % (stats["mapping_loaded"], stats["mapping_rows_in_csv"],
             stats["mapping_unmatched"] or "none"))
    print("artist names that are equal after normalising but have no identity decision: %d"
          % stats["collisions"])
    print("M2 tables unchanged: OK")
    print("foreign_key_check: OK")


def main():
    con = db.connect()
    db.create_schema(con)
    con.executescript(CLEAN_SCHEMA.read_text(encoding="utf-8"))
    try:
        stats = build(con)
    except Exception:
        traceback.print_exc()
        print("\nSTATUS: FAILED (the cleaned layer was left as it was)")
        return 1
    print_summary(con, stats)
    print("STATUS: COMPLETE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
