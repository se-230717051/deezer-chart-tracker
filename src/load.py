"""Loads the raw files in data/raw/ into the SQLite database.

Run from the repository root:  python src/load.py
It never calls the API. You can run it as often as you like: the result is always the same.
"""
import json
import os
import re
import sys
import traceback
from datetime import datetime
from pathlib import Path

import db

RAW_DIR = Path(os.environ.get("RAW_DIR") or db.ROOT / "data" / "raw")

# ---------- SQL (values always go in through ? placeholders) ----------

GENRE_KEY = "SELECT genre_key FROM genre WHERE deezer_id = ?"
ARTIST_KEY = "SELECT artist_key FROM artist WHERE deezer_id = ?"
ALBUM_KEY = "SELECT album_key FROM album WHERE deezer_id = ?"
TRACK_KEY = "SELECT track_key FROM track WHERE deezer_id = ?"
RECORDING_KEY = "SELECT recording_key FROM recording WHERE mbid = ?"
TRACKS_BY_ISRC = "SELECT track_key FROM track_detail WHERE isrc = ?"

# "latest retrieved_at wins": an older file can never overwrite a newer row.
UPSERT_GENRE = """
INSERT INTO genre (deezer_id, name, retrieved_at) VALUES (?, ?, ?)
ON CONFLICT (deezer_id) DO UPDATE SET
    name = excluded.name, retrieved_at = excluded.retrieved_at
WHERE excluded.retrieved_at >= genre.retrieved_at
"""
UPSERT_ARTIST = """
INSERT INTO artist (deezer_id, name, retrieved_at) VALUES (?, ?, ?)
ON CONFLICT (deezer_id) DO UPDATE SET
    name = excluded.name, retrieved_at = excluded.retrieved_at
WHERE excluded.retrieved_at >= artist.retrieved_at
"""
UPSERT_ALBUM = """
INSERT INTO album (deezer_id, title, retrieved_at) VALUES (?, ?, ?)
ON CONFLICT (deezer_id) DO UPDATE SET
    title = excluded.title, retrieved_at = excluded.retrieved_at
WHERE excluded.retrieved_at >= album.retrieved_at
"""
UPSERT_TRACK = """
INSERT INTO track (deezer_id, title, duration, explicit, artist_key, album_key, retrieved_at)
VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (deezer_id) DO UPDATE SET
    title = excluded.title, duration = excluded.duration, explicit = excluded.explicit,
    artist_key = excluded.artist_key, album_key = excluded.album_key,
    retrieved_at = excluded.retrieved_at
WHERE excluded.retrieved_at >= track.retrieved_at
"""
UPSERT_CHART_ENTRY = """
INSERT INTO chart_entry (genre_key, snapshot_date, position, track_key, rank, retrieved_at)
VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT (genre_key, snapshot_date, position) DO UPDATE SET
    track_key = excluded.track_key, rank = excluded.rank,
    retrieved_at = excluded.retrieved_at
WHERE excluded.retrieved_at >= chart_entry.retrieved_at
"""
UPSERT_TRACK_DETAIL = """
INSERT INTO track_detail (track_key, isrc, release_date, retrieved_at) VALUES (?, ?, ?, ?)
ON CONFLICT (track_key) DO UPDATE SET
    isrc = excluded.isrc, release_date = excluded.release_date,
    retrieved_at = excluded.retrieved_at
WHERE excluded.retrieved_at >= track_detail.retrieved_at
"""
UPSERT_ALBUM_DETAIL = """
INSERT INTO album_detail (album_key, release_date, nb_tracks, retrieved_at) VALUES (?, ?, ?, ?)
ON CONFLICT (album_key) DO UPDATE SET
    release_date = excluded.release_date, nb_tracks = excluded.nb_tracks,
    retrieved_at = excluded.retrieved_at
WHERE excluded.retrieved_at >= album_detail.retrieved_at
"""
UPSERT_ARTIST_FANS = """
INSERT INTO artist_fans (artist_key, snapshot_date, nb_fan, retrieved_at) VALUES (?, ?, ?, ?)
ON CONFLICT (artist_key, snapshot_date) DO UPDATE SET
    nb_fan = excluded.nb_fan, retrieved_at = excluded.retrieved_at
WHERE excluded.retrieved_at >= artist_fans.retrieved_at
"""
UPSERT_RECORDING = """
INSERT INTO recording (mbid, title, length_ms, first_release_date, retrieved_at)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT (mbid) DO UPDATE SET
    title = excluded.title, length_ms = excluded.length_ms,
    first_release_date = excluded.first_release_date, retrieved_at = excluded.retrieved_at
WHERE excluded.retrieved_at >= recording.retrieved_at
"""
UPSERT_TRACK_RECORDING = """
INSERT INTO track_recording (track_key, recording_key, retrieved_at) VALUES (?, ?, ?)
ON CONFLICT (track_key, recording_key) DO UPDATE SET retrieved_at = excluded.retrieved_at
WHERE excluded.retrieved_at >= track_recording.retrieved_at
"""
INSERT_QUARANTINE = """
INSERT INTO quarantine (source, file_name, record_ref, reason, raw_record, retrieved_at)
VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT (source, file_name, record_ref) DO UPDATE SET
    reason = excluded.reason, raw_record = excluded.raw_record
"""

# ---------- small helpers ----------


def one(con, sql, value):
    """Run a lookup query and return the first column of the first row (or None)."""
    row = con.execute(sql, (value,)).fetchone()
    return row[0] if row else None


def clean_int(value, stats):
    """Whole number or None. Text like 'n/a' becomes None and is counted."""
    if value is None or value == "":
        return None
    if isinstance(value, float) and not value.is_integer():
        stats["cleaned"] += 1
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        stats["cleaned"] += 1
        return None


def clean_flag(value, stats):
    """0, 1 or None."""
    if value is None:
        return None
    if value in (True, False, 0, 1):
        return int(value)
    stats["cleaned"] += 1
    return None


def clean_date(value, stats):
    """YYYY-MM-DD (zero padded) or None. Deezer's '0000-00-00' becomes None."""
    if value is None or value == "":
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        stats["cleaned"] += 1
        return None


def clean_text(value):
    return value if isinstance(value, str) and value != "" else None


def raw_files(source):
    """List (retrieved_at, label, path) for one raw folder, oldest first.
    retrieved_at comes from the file name, not from the order the files are read in."""
    files = []
    for path in (RAW_DIR / source).glob("*.json"):
        stamp, _, label = path.stem.partition("_")
        try:
            when = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ")
        except ValueError:
            continue  # not a file written by ingest.py
        files.append((when.strftime("%Y-%m-%dT%H:%M:%SZ"), label, path))
    return sorted(files)


def read_file(stats, retrieved_at, path):
    """Parse one raw file. A file that is not valid JSON stops the whole load."""
    stats["files"] += 1
    stats["first"] = min(stats["first"] or retrieved_at, retrieved_at)
    stats["last"] = max(stats["last"] or retrieved_at, retrieved_at)
    return json.loads(path.read_text(encoding="utf-8"))


def quarantine(con, stats, source, path, ref, reason, record, retrieved_at):
    con.execute(INSERT_QUARANTINE,
                (source, path.name, str(ref), reason, json.dumps(record, sort_keys=True),
                 retrieved_at))
    stats["quarantined"] += 1


# ---------- loading steps ----------


def load_genres(con, stats):
    for retrieved_at, label, path in raw_files("deezer_genres"):
        for genre in read_file(stats, retrieved_at, path)["data"]:
            deezer_id = clean_int(genre.get("id"), stats)
            if deezer_id is None:
                quarantine(con, stats, "deezer_genres", path, genre.get("name"),
                           "genre without a valid id", genre, retrieved_at)
                continue
            con.execute(UPSERT_GENRE, (deezer_id, clean_text(genre.get("name")), retrieved_at))


def load_charts(con, stats):
    for retrieved_at, label, path in raw_files("deezer_chart"):
        records = read_file(stats, retrieved_at, path)["data"]
        match = re.fullmatch(r"genre(\d+)_p\d+", label)
        genre_key = one(con, GENRE_KEY, int(match.group(1))) if match else None
        snapshot_date = retrieved_at[:10]

        for number, track in enumerate(records, 1):
            artist = track.get("artist") or {}
            album = track.get("album") or {}
            track_id = clean_int(track.get("id"), stats)
            artist_id = clean_int(artist.get("id"), stats)
            album_id = clean_int(album.get("id"), stats)
            position = clean_int(track.get("position"), stats)

            if genre_key is None:
                reason = "unknown genre"
            elif None in (track_id, artist_id, album_id, position):
                reason = "missing track/artist/album id or position"
            else:
                reason = None
            if reason:
                quarantine(con, stats, "deezer_chart", path, "item %d" % number, reason,
                           track, retrieved_at)
                continue

            con.execute(UPSERT_ARTIST, (artist_id, clean_text(artist.get("name")), retrieved_at))
            con.execute(UPSERT_ALBUM, (album_id, clean_text(album.get("title")), retrieved_at))
            con.execute(UPSERT_TRACK, (
                track_id, clean_text(track.get("title")), clean_int(track.get("duration"), stats),
                clean_flag(track.get("explicit_lyrics"), stats), one(con, ARTIST_KEY, artist_id),
                one(con, ALBUM_KEY, album_id), retrieved_at))
            con.execute(UPSERT_CHART_ENTRY, (
                genre_key, snapshot_date, position, one(con, TRACK_KEY, track_id),
                clean_int(track.get("rank"), stats), retrieved_at))


def load_track_details(con, stats):
    for retrieved_at, label, path in raw_files("deezer_track"):
        body = read_file(stats, retrieved_at, path)
        track_key = one(con, TRACK_KEY, clean_int(body.get("id"), stats))
        if track_key is None:
            quarantine(con, stats, "deezer_track", path, label, "track not in any chart",
                       body, retrieved_at)
            continue
        isrc = clean_text(body.get("isrc"))
        con.execute(UPSERT_TRACK_DETAIL, (track_key, isrc.upper() if isrc else None,
                                          clean_date(body.get("release_date"), stats),
                                          retrieved_at))


def load_artist_details(con, stats):
    for retrieved_at, label, path in raw_files("deezer_artist"):
        body = read_file(stats, retrieved_at, path)
        artist_key = one(con, ARTIST_KEY, clean_int(body.get("id"), stats))
        if artist_key is None:
            quarantine(con, stats, "deezer_artist", path, label, "artist not in any chart",
                       body, retrieved_at)
            continue
        con.execute(UPSERT_ARTIST_FANS, (artist_key, retrieved_at[:10],
                                         clean_int(body.get("nb_fan"), stats), retrieved_at))


def load_album_details(con, stats):
    for retrieved_at, label, path in raw_files("deezer_album"):
        body = read_file(stats, retrieved_at, path)
        album_key = one(con, ALBUM_KEY, clean_int(body.get("id"), stats))
        if album_key is None:
            quarantine(con, stats, "deezer_album", path, label, "album not in any chart",
                       body, retrieved_at)
            continue
        con.execute(UPSERT_ALBUM_DETAIL, (album_key, clean_date(body.get("release_date"), stats),
                                          clean_int(body.get("nb_tracks"), stats), retrieved_at))


def load_recordings(con, stats):
    for retrieved_at, label, path in raw_files("musicbrainz_isrc"):
        body = read_file(stats, retrieved_at, path)
        track_keys = [row[0] for row in con.execute(TRACKS_BY_ISRC, (label.upper(),))]
        if not track_keys:
            quarantine(con, stats, "musicbrainz_isrc", path, label,
                       "no Deezer track has this ISRC", body, retrieved_at)
            continue
        for number, rec in enumerate(body.get("recordings") or [], 1):
            mbid = clean_text(rec.get("id"))
            if mbid is None:
                quarantine(con, stats, "musicbrainz_isrc", path, "%s #%d" % (label, number),
                           "recording without id", rec, retrieved_at)
                continue
            con.execute(UPSERT_RECORDING, (
                mbid, clean_text(rec.get("title")), clean_int(rec.get("length"), stats),
                clean_date(rec.get("first-release-date"), stats), retrieved_at))
            recording_key = one(con, RECORDING_KEY, mbid)
            for track_key in track_keys:
                con.execute(UPSERT_TRACK_RECORDING, (track_key, recording_key, retrieved_at))


def load_all(con, raw_dir=None):
    """The whole load in ONE transaction: it is written completely or not at all."""
    global RAW_DIR
    if raw_dir is not None:
        RAW_DIR = Path(raw_dir)
    stats = {"files": 0, "first": None, "last": None, "cleaned": 0, "quarantined": 0}
    with con:  # commits at the end; rolls back if anything raises
        con.execute("DELETE FROM quarantine")  # rebuilt on every run
        load_genres(con, stats)
        load_charts(con, stats)
        load_track_details(con, stats)
        load_artist_details(con, stats)
        load_album_details(con, stats)
        load_recordings(con, stats)
        if con.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("foreign_key_check found broken references")
    return stats


def main():
    con = db.connect()
    db.create_schema(con)
    before = db.row_counts(con)
    try:
        stats = load_all(con)
    except Exception:
        traceback.print_exc()
        print("\nSTATUS: FAILED (nothing was written to the database)")
        return 1
    after = db.row_counts(con)

    if stats["files"] == 0:
        print("No raw files found in", RAW_DIR, "- run python src/ingest.py first.")
        return 1
    print("files read: %d raw files (%s .. %s)" % (stats["files"], stats["first"], stats["last"]))
    for table in after:
        print("%s: %s in database (+%d this run)" % (table, format(after[table], ","),
                                                    after[table] - before[table]))
    print("values cleaned: %d (invalid values -> NULL)" % stats["cleaned"])
    print("quarantined: %d records" % stats["quarantined"])
    print("foreign_key_check: OK")
    print("STATUS: COMPLETE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
