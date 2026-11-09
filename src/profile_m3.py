"""M3 profiling: looks at the M2 database and prints what looks wrong. Changes nothing.
Run: python src/profile_m3.py   (needs pandas: pip install pandas)
"""
import unicodedata
from datetime import date

import pandas as pd

import db

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 30)

con = db.connect()
tables = {name: pd.read_sql_query(query, con) for name, query in db.TABLE_QUERIES.items()}


def title(text):
    print("\n" + "=" * 70 + "\n" + text + "\n" + "=" * 70)


# ---------------------------------------------------------------- 1. rows
title("1. ROW COUNTS")
for name, df in tables.items():
    print("%-16s %8d rows" % (name, len(df)))

# ---------------------------------------------------------------- 2. missing
title("2. MISSING VALUES (NULL or empty text)")
for name, df in tables.items():
    if name == "quarantine":
        continue
    for column in df.columns:
        missing = int(df[column].isna().sum() + (df[column] == "").sum())
        if missing:
            print("%s.%s: %d of %d (%.1f%%)" % (name, column, missing, len(df),
                                                100 * missing / len(df)))

# ---------------------------------------------------------------- 3. numbers
title("3. NUMBERS: min / median / max, zeros, negatives, most frequent value")
numeric = {"track": ["duration", "explicit"], "album_detail": ["nb_tracks"],
           "artist_fans": ["nb_fan"], "chart_entry": ["position", "rank"],
           "recording": ["length_ms"]}
for name, columns in numeric.items():
    for column in columns:
        s = tables[name][column].dropna()
        if s.empty:
            print("%s.%s: no values" % (name, column))
            continue
        top = s.value_counts().head(3).to_dict()
        print("%s.%s: min %s | median %s | max %s | zeros %d | negatives %d | most frequent %s"
              % (name, column, s.min(), s.median(), s.max(), (s == 0).sum(), (s < 0).sum(), top))

# ---------------------------------------------------------------- 4. dates
title("4. DATES")
today = date.today().isoformat()
for name, column in [("track_detail", "release_date"), ("album_detail", "release_date"),
                     ("recording", "first_release_date")]:
    s = tables[name][column].dropna()
    print("%s.%s: %s .. %s | in the future: %d | before 1950: %d"
          % (name, column, s.min() if len(s) else None, s.max() if len(s) else None,
             (s > today).sum(), (s < "1950").sum()))
days = tables["chart_entry"]["snapshot_date"]
print("chart snapshot days:", sorted(days.unique()))

# ---------------------------------------------------------------- 5. text
title("5. TEXT: do equal things look equal?")
for name, column in [("artist", "name"), ("album", "title"), ("track", "title"), ("genre", "name")]:
    s = tables[name][column].dropna()
    not_nfc = s[s != s.map(lambda x: unicodedata.normalize("NFC", x))]
    padded = s[s != s.str.strip()]
    nbsp = s[s.str.contains("\u00a0", regex=False)]
    double = s[s.str.contains("  ", regex=False)]
    print("%s.%s: not NFC %d | leading/trailing space %d | non-breaking space %d | double space %d"
          % (name, column, len(not_nfc), len(padded), len(nbsp), len(double)))
    for label, sample in [("not NFC", not_nfc), ("padded", padded), ("nbsp", nbsp)]:
        for value in sample.head(3):
            print("    %s: %r" % (label, value))

# ---------------------------------------------------------------- 6. identity
title("6. IDENTITY: one thing recorded as two?")
artist = tables["artist"].copy()
artist["same_name"] = artist["name"].str.casefold().str.strip()
dup = artist[artist.duplicated("same_name", keep=False) & artist["same_name"].notna()]
print("artists with the same name but different Deezer id:", dup["same_name"].nunique(), "names")
print(dup.sort_values("same_name")[["deezer_id", "name"]].head(15).to_string(index=False))
track = tables["track"].copy()
track["same_title"] = track["title"].str.casefold().str.strip()
dup = track[track.duplicated(["same_title", "artist_key"], keep=False)]
print("\ntracks with the same title and artist but different track id:",
      len(dup), "rows")
print(dup.sort_values("same_title")[["deezer_id", "title", "artist_key"]].head(10).to_string(index=False))
isrc = tables["track_detail"].dropna(subset=["isrc"])
shared = isrc[isrc.duplicated("isrc", keep=False)]
print("\nISRCs shared by more than one track:", shared["isrc"].nunique())

# ---------------------------------------------------------------- 7. coverage
title("7. CHART COVERAGE: equal things compared equally?")
chart = tables["chart_entry"]
per_chart = chart.groupby(["genre_key", "snapshot_date"]).size().rename("rows").reset_index()
print("rows per (genre, day): min %d | median %d | max %d"
      % (per_chart["rows"].min(), per_chart["rows"].median(), per_chart["rows"].max()))
print("charts with fewer than 100 rows:", int((per_chart["rows"] < 100).sum()), "of", len(per_chart))
print("days per genre:", chart.groupby("genre_key")["snapshot_date"].nunique().describe()[["min", "max"]].to_dict())
same_chart = chart.groupby(["genre_key", "snapshot_date", "track_key"]).size()
print("tracks in more than one position of the same chart:", int((same_chart > 1).sum()))
have = set(tables["artist_fans"]["artist_key"])
print("artists that appear in charts but have no fan count:",
      len(set(tables["artist"]["artist_key"]) - have), "of", len(tables["artist"]))

# ---------------------------------------------------------------- 8. sequences
title("8. SEQUENCES: only visible over time")
chart = chart.sort_values(["genre_key", "track_key", "snapshot_date"])
chart["jump"] = chart.groupby(["genre_key", "track_key"])["position"].diff().abs()
print("largest position jumps between two days:")
print(chart.nlargest(5, "jump")[["genre_key", "track_key", "snapshot_date", "position", "jump"]]
      .to_string(index=False))
stuck = chart.groupby(["genre_key", "track_key"])["rank"].agg(["nunique", "count"])
print("tracks whose rank is identical on 3 or more days:",
      int(((stuck["nunique"] == 1) & (stuck["count"] >= 3)).sum()))
fans = tables["artist_fans"].sort_values(["artist_key", "snapshot_date"])
fans["change"] = fans.groupby("artist_key")["nb_fan"].diff()
print("artists whose fan count decreased between two days:", int((fans["change"] < 0).sum()),
      "| biggest decrease:", fans["change"].min())

# ---------------------------------------------------------------- 9. quarantine
title("9. QUARANTINE (records M2 could not load)")
print(tables["quarantine"].groupby(["source", "reason"]).size().rename("how_many").to_string())
