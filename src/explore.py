"""Tests the keys of the raw data (needed for the README, section 'Data Model').
Run: python src/explore.py
"""
import json
from pathlib import Path

raw = Path("data/raw")


def read(source):
    """(retrieved_at, label, parsed json) for every file of one source, oldest first."""
    out = []
    for path in sorted((raw / source).glob("*.json")):
        stamp, _, label = path.stem.partition("_")
        out.append((stamp, label, json.loads(path.read_text(encoding="utf-8"))))
    return out


# 1. Is (genre, day, position) unique after keeping only the latest file per day?
latest = {}
for stamp, label, body in read("deezer_chart"):
    genre = label.split("_")[0]
    for item in body["data"]:
        latest[(genre, stamp[:8], item.get("position"))] = item.get("id")
rows = sum(len(b["data"]) for _, _, b in read("deezer_chart"))
print("1. chart items in all files:", rows, "| distinct (genre, day, position):", len(latest))
print("   positions that are missing:", sum(1 for k in latest if k[2] is None))

# 2. Does a track id always mean the same title and artist?
seen = {}
for _, _, body in read("deezer_chart"):
    for item in body["data"]:
        artist = (item.get("artist") or {}).get("id")
        seen.setdefault(item["id"], set()).add((item.get("title"), artist))
print("2. distinct track ids:", len(seen),
      "| ids whose title/artist changes:", sum(1 for v in seen.values() if len(v) > 1))

# 3. Does every reference resolve?
artists_in_charts = {(i.get("artist") or {}).get("id") for _, _, b in read("deezer_chart") for i in b["data"]}
tracks_in_charts = {i["id"] for _, _, b in read("deezer_chart") for i in b["data"]}
print("3. artists in charts:", len(artists_in_charts), "| tracks in charts:", len(tracks_in_charts))
print("   artist files for unknown artists:",
      sum(1 for _, _, b in read("deezer_artist") if b.get("id") not in artists_in_charts))
print("   track files for unknown tracks:",
      sum(1 for _, _, b in read("deezer_track") if b.get("id") not in tracks_in_charts))
print("   tracks without ISRC:", sum(1 for _, _, b in read("deezer_track") if not b.get("isrc")))
