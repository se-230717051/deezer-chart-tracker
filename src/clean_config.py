"""Every threshold and constant of clean.py and validate.py, in one place.
Each one is justified in docs/cleaning_report.md (section 5)."""
import db

MAPPING_CSV = db.ROOT / "data" / "mappings" / "artist_identity.csv"

IQR_K = 1.5                  # a value beyond Q1 - K*IQR or Q3 + K*IQR is "unusual" (kept, flagged)
MAX_DURATION_S = 86400       # a track longer than one day is impossible (seconds)
MAX_LENGTH_MS = 86400000     # same limit for MusicBrainz lengths (milliseconds)
CHART_SIZE = 100             # a Deezer chart has positions 1..100

MAX_MISSING_SHARE = 0.10     # validate: warn if more than 10% of a column is missing
MIN_FAN_COVERAGE = 0.50      # validate: warn if fewer than half of the artists have a fan count
