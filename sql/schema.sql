-- Database schema. Safe to run many times (CREATE TABLE IF NOT EXISTS).
-- Every table is STRICT. Timestamps: TEXT, ISO 8601 UTC (2026-10-12T09:12:44Z).
-- Dates: TEXT, YYYY-MM-DD.

-- ===== entities (surrogate key + source id kept as NOT NULL UNIQUE) =====

CREATE TABLE IF NOT EXISTS genre (
    genre_key    INTEGER PRIMARY KEY,
    deezer_id    INTEGER NOT NULL UNIQUE,
    name         TEXT,
    retrieved_at TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS artist (
    artist_key   INTEGER PRIMARY KEY,
    deezer_id    INTEGER NOT NULL UNIQUE,
    name         TEXT,
    retrieved_at TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS album (
    album_key    INTEGER PRIMARY KEY,
    deezer_id    INTEGER NOT NULL UNIQUE,
    title        TEXT,
    retrieved_at TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS track (
    track_key    INTEGER PRIMARY KEY,
    deezer_id    INTEGER NOT NULL UNIQUE,
    title        TEXT,
    duration     INTEGER,                              -- seconds
    explicit     INTEGER CHECK (explicit IN (0, 1)),   -- 1 = explicit lyrics
    artist_key   INTEGER NOT NULL REFERENCES artist (artist_key),
    album_key    INTEGER NOT NULL REFERENCES album (album_key),
    retrieved_at TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS recording (                 -- a MusicBrainz recording
    recording_key      INTEGER PRIMARY KEY,
    mbid               TEXT NOT NULL UNIQUE,
    title              TEXT,
    length_ms          INTEGER,
    first_release_date TEXT,
    retrieved_at       TEXT NOT NULL
) STRICT;

-- ===== details that come from other endpoints (one row per entity) =====

CREATE TABLE IF NOT EXISTS track_detail (
    track_key    INTEGER PRIMARY KEY REFERENCES track (track_key),
    isrc         TEXT,
    release_date TEXT,
    retrieved_at TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS album_detail (
    album_key    INTEGER PRIMARY KEY REFERENCES album (album_key),
    release_date TEXT,
    nb_tracks    INTEGER,
    retrieved_at TEXT NOT NULL
) STRICT;

-- ===== events =====

-- One chart position in one genre chart on one day.
CREATE TABLE IF NOT EXISTS chart_entry (
    genre_key     INTEGER NOT NULL REFERENCES genre (genre_key),
    snapshot_date TEXT    NOT NULL,
    position      INTEGER NOT NULL,
    track_key     INTEGER NOT NULL REFERENCES track (track_key),
    rank          INTEGER,
    retrieved_at  TEXT    NOT NULL,
    PRIMARY KEY (genre_key, snapshot_date, position)
) STRICT;

-- The fan count of one artist on one day.
CREATE TABLE IF NOT EXISTS artist_fans (
    artist_key    INTEGER NOT NULL REFERENCES artist (artist_key),
    snapshot_date TEXT    NOT NULL,
    nb_fan        INTEGER,
    retrieved_at  TEXT    NOT NULL,
    PRIMARY KEY (artist_key, snapshot_date)
) STRICT;

-- Which MusicBrainz recording belongs to which Deezer track (matched by ISRC).
CREATE TABLE IF NOT EXISTS track_recording (
    track_key     INTEGER NOT NULL REFERENCES track (track_key),
    recording_key INTEGER NOT NULL REFERENCES recording (recording_key),
    retrieved_at  TEXT    NOT NULL,
    PRIMARY KEY (track_key, recording_key)
) STRICT;

-- ===== quarantine: records we could not load =====

CREATE TABLE IF NOT EXISTS quarantine (
    quarantine_key INTEGER PRIMARY KEY,
    source         TEXT NOT NULL,       -- raw folder, e.g. deezer_chart
    file_name      TEXT NOT NULL,
    record_ref     TEXT NOT NULL,       -- which record inside the file
    reason         TEXT NOT NULL,
    raw_record     TEXT NOT NULL,       -- the record as JSON text
    retrieved_at   TEXT NOT NULL,
    UNIQUE (source, file_name, record_ref)
) STRICT;
