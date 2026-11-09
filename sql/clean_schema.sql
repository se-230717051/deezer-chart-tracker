-- The cleaned layer. The M2 tables are never changed; these tables sit next to them.
-- Same grain, primary key and number of rows as the M2 table they clean.
-- Columns: <col>_raw = exactly as loaded, <col> = cleaned value, <col>_flag = why they differ.
-- Nothing is imputed: a value we do not trust is NULL.

CREATE TABLE IF NOT EXISTS artist_clean (
    artist_key INTEGER PRIMARY KEY REFERENCES artist (artist_key),
    name_raw   TEXT,
    name       TEXT,
    name_key   TEXT,   -- for matching only: accents removed, Turkish letters folded, casefolded
    name_flag  TEXT NOT NULL CHECK (name_flag IN
        ('ok', 'missing_not_reported', 'unicode_normalised', 'whitespace_fixed'))
) STRICT;

CREATE TABLE IF NOT EXISTS album_clean (
    album_key  INTEGER PRIMARY KEY REFERENCES album (album_key),
    title_raw  TEXT,
    title      TEXT,
    title_key  TEXT,
    title_flag TEXT NOT NULL CHECK (title_flag IN
        ('ok', 'missing_not_reported', 'unicode_normalised', 'whitespace_fixed'))
) STRICT;

CREATE TABLE IF NOT EXISTS track_clean (
    track_key     INTEGER PRIMARY KEY REFERENCES track (track_key),
    title_raw     TEXT,
    title         TEXT,
    title_key     TEXT,
    title_flag    TEXT NOT NULL CHECK (title_flag IN
        ('ok', 'missing_not_reported', 'unicode_normalised', 'whitespace_fixed')),
    duration_raw  INTEGER,
    duration      INTEGER,
    duration_flag TEXT NOT NULL CHECK (duration_flag IN
        ('ok', 'missing_not_reported', 'invalid_range', 'unusual_high', 'unusual_low'))
) STRICT;

CREATE TABLE IF NOT EXISTS artist_fans_clean (
    artist_key    INTEGER NOT NULL REFERENCES artist (artist_key),
    snapshot_date TEXT    NOT NULL,
    nb_fan_raw    INTEGER,
    nb_fan        INTEGER,
    nb_fan_flag   TEXT NOT NULL CHECK (nb_fan_flag IN
        ('ok', 'missing_not_reported', 'invalid_range', 'unusual_high', 'unusual_low')),
    PRIMARY KEY (artist_key, snapshot_date)
) STRICT;

CREATE TABLE IF NOT EXISTS recording_clean (
    recording_key          INTEGER PRIMARY KEY REFERENCES recording (recording_key),
    length_ms_raw          INTEGER,
    length_ms              INTEGER,
    length_ms_flag         TEXT NOT NULL CHECK (length_ms_flag IN
        ('ok', 'missing_not_reported', 'invalid_range', 'unusual_high', 'unusual_low')),
    first_release_date_raw TEXT,
    first_release_date     TEXT,
    first_release_date_flag TEXT NOT NULL CHECK (first_release_date_flag IN
        ('ok', 'missing_not_reported', 'invalid_future'))
) STRICT;

-- Identity decisions, loaded from data/mappings/artist_identity.csv
CREATE TABLE IF NOT EXISTS identity_map (
    alias_artist_key     INTEGER NOT NULL REFERENCES artist (artist_key),
    canonical_artist_key INTEGER NOT NULL REFERENCES artist (artist_key),
    decision             TEXT NOT NULL CHECK (decision IN ('same_entity', 'different_entity')),
    decided_by           TEXT NOT NULL,
    decided_at           TEXT NOT NULL,
    note                 TEXT NOT NULL,
    PRIMARY KEY (alias_artist_key, canonical_artist_key)
) STRICT;

-- Analyses use this view to see data by (resolved) artist. Keys are never renamed.
CREATE VIEW IF NOT EXISTS artist_resolved AS
SELECT a.artist_key,
       COALESCE(m.canonical_artist_key, a.artist_key) AS resolved_artist_key
FROM artist AS a
LEFT JOIN identity_map AS m
       ON m.alias_artist_key = a.artist_key AND m.decision = 'same_entity';

-- Tracks with cleaned names, for short queries.
CREATE VIEW IF NOT EXISTS track_named AS
SELECT t.track_key, tc.title, tc.title_key, ac.name AS artist,
       r.resolved_artist_key, tc.duration, tc.duration_flag
FROM track AS t
JOIN track_clean    AS tc ON tc.track_key  = t.track_key
JOIN artist_clean   AS ac ON ac.artist_key = t.artist_key
JOIN artist_resolved AS r ON r.artist_key  = t.artist_key;
