"""Data-quality expectations as code. Run: python src/validate.py

Every check prints PASS, WARN or STOP. The exit code is 1 if any STOP check fails.
"""
import sys

import clean
import clean_config as cfg
import db

# ---------- SQL (values come in through ? placeholders) ----------
IMPOSSIBLE_VALUES = {
    "duration outside 1..max": (
        "SELECT COUNT(*) FROM track_clean WHERE duration <= 0 OR duration > ?",
        (cfg.MAX_DURATION_S,)),
    "negative fan count": (
        "SELECT COUNT(*) FROM artist_fans_clean WHERE nb_fan < 0", ()),
    "recording length outside 1..max": (
        "SELECT COUNT(*) FROM recording_clean WHERE length_ms <= 0 OR length_ms > ?",
        (cfg.MAX_LENGTH_MS,)),
    "release date after retrieval": (
        "SELECT COUNT(*) FROM recording_clean WHERE first_release_date > date('now')", ()),
    "padded or non-breaking text (artist)": (
        "SELECT COUNT(*) FROM artist_clean WHERE name <> trim(name) OR instr(name, char(160)) > 0",
        ()),
    "padded or non-breaking text (album)": (
        "SELECT COUNT(*) FROM album_clean WHERE title <> trim(title) OR instr(title, char(160)) > 0",
        ()),
    "padded or non-breaking text (track)": (
        "SELECT COUNT(*) FROM track_clean WHERE title <> trim(title) OR instr(title, char(160)) > 0",
        ()),
}
COUNT_ARTISTS = "SELECT COUNT(*) FROM artist"
COUNT_ARTISTS_WITH_FANS = "SELECT COUNT(DISTINCT artist_key) FROM artist_fans"
COUNT_RECORDINGS = "SELECT COUNT(*) FROM recording_clean"
MISSING_RELEASE_DATE = ("SELECT COUNT(*) FROM recording_clean "
                        "WHERE first_release_date_flag = 'missing_not_reported'")
MISSING_LENGTH = ("SELECT COUNT(*) FROM recording_clean "
                  "WHERE length_ms_flag = 'missing_not_reported'")
LATEST_DAY = "SELECT MAX(snapshot_date) FROM chart_entry"
GENRES_TOTAL = "SELECT COUNT(*) FROM genre"
GENRES_WITH_LATEST = "SELECT COUNT(DISTINCT genre_key) FROM chart_entry WHERE snapshot_date = ?"
BAD_CHART_VALUES = ("SELECT COUNT(*) FROM chart_entry WHERE position < 1 OR position > ? "
                    "OR rank <= 0")
SAME_SONG_GROUPS = ("SELECT COUNT(*) FROM (SELECT 1 FROM track_named WHERE title_key IS NOT NULL "
                    "GROUP BY resolved_artist_key, title_key HAVING COUNT(*) > 1)")


def scalar(con, sql, params=()):
    return con.execute(sql, params).fetchone()[0]


def run_checks(con):
    """Returns a list of (level, name, passed, detail). level is STOP or WARN."""
    results = []

    # --- STOP checks ---
    unequal = [t for t, (clean_sql, raw_sql) in clean.ROW_COUNTS.items()
               if scalar(con, clean_sql) != scalar(con, raw_sql)]
    results.append(("STOP", "cleaned tables have the same row count as raw", not unequal,
                    "all %d equal" % len(clean.ROW_COUNTS) if not unequal
                    else "different: " + ", ".join(unequal)))

    bad = {name: scalar(con, sql, params) for name, (sql, params) in IMPOSSIBLE_VALUES.items()}
    bad = {name: n for name, n in bad.items() if n}
    results.append(("STOP", "no impossible value in a cleaned column", not bad,
                    "0 found" if not bad else ", ".join("%s: %d" % item for item in bad.items())))

    broken = con.execute("PRAGMA foreign_key_check").fetchall()
    results.append(("STOP", "foreign_key_check is empty", not broken,
                    "OK" if not broken else "%d broken references" % len(broken)))

    # --- WARN checks ---
    recordings = scalar(con, COUNT_RECORDINGS) or 1
    shares = {"first_release_date": scalar(con, MISSING_RELEASE_DATE) / recordings,
              "length_ms": scalar(con, MISSING_LENGTH) / recordings}
    over = {name: share for name, share in shares.items() if share > cfg.MAX_MISSING_SHARE}
    results.append(("WARN", "missing share per recording column at most %d%%"
                    % round(100 * cfg.MAX_MISSING_SHARE), not over,
                    ", ".join("%s %.1f%%" % (n, 100 * s) for n, s in shares.items())))

    artists = scalar(con, COUNT_ARTISTS) or 1
    with_fans = scalar(con, COUNT_ARTISTS_WITH_FANS)
    results.append(("WARN", "at least %d%% of artists have a fan count" % round(100 * cfg.MIN_FAN_COVERAGE),
                    with_fans / artists >= cfg.MIN_FAN_COVERAGE,
                    "%d of %d artists (%.1f%%)" % (with_fans, artists, 100 * with_fans / artists)))

    day = scalar(con, LATEST_DAY)
    genres = scalar(con, GENRES_TOTAL)
    current = scalar(con, GENRES_WITH_LATEST, (day,)) if day else 0
    results.append(("WARN", "every genre has a chart on the latest day (%s)" % day,
                    day is not None and current == genres, "%d of %d genres" % (current, genres)))

    bad_chart = scalar(con, BAD_CHART_VALUES, (cfg.CHART_SIZE,))
    results.append(("WARN", "chart positions within 1..%d and rank > 0" % cfg.CHART_SIZE,
                    bad_chart == 0, "%d bad rows" % bad_chart))

    collisions = scalar(con, clean.UNRESOLVED_NAME_COLLISIONS)
    results.append(("WARN", "no artist-name collision without an identity decision",
                    collisions == 0, "%d unresolved" % collisions))

    groups = scalar(con, SAME_SONG_GROUPS)
    results.append(("WARN", "no song under several track ids (same artist, same title)",
                    groups == 0, "%d groups (kept separate, see report)" % groups))
    return results


def run(con):
    """Prints every check and returns the exit code (1 if a STOP check failed)."""
    exit_code = 0
    for level, name, passed, detail in run_checks(con):
        status = "PASS" if passed else level
        if not passed and level == "STOP":
            exit_code = 1
        print("%-5s %-60s %s" % (status, name, detail))
    print("\nSTATUS:", "STOP (a STOP check failed)" if exit_code else "OK (see WARN lines, if any)")
    return exit_code


def main():
    return run(db.connect())


if __name__ == "__main__":
    sys.exit(main())
