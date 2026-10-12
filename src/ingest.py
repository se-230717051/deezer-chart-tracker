"""Downloads Deezer and MusicBrainz data and saves it, unchanged, in data/raw/.

Run from the repository root:  python src/ingest.py
"""
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()  # reads the .env file if there is one

# --- settings (from environment variables) ---
CONTACT = os.environ.get("MUSICBRAINZ_CONTACT")
MAX_ITEMS = int(os.environ.get("MAX_ITEMS", "100"))  # max tracks/artists/albums/ISRCs per run
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

TIMEOUT = 30      # seconds to wait for one request
MAX_TRIES = 5     # how many times we try one URL
DEEZER = "https://api.deezer.com"
MUSICBRAINZ = "https://musicbrainz.org/ws/2"

saved = {}      # source name -> number of files saved
problems = []   # messages about everything that went wrong


def get(url, pause):
    """Download a URL. Returns the response, or None if it did not work."""
    headers = {"User-Agent": f"deezer-chart-project/0.1 ({CONTACT})"}
    for attempt in range(1, MAX_TRIES + 1):
        time.sleep(pause)  # stay under the rate limit
        try:
            response = requests.get(url, headers=headers, timeout=TIMEOUT)
        except (requests.Timeout, requests.ConnectionError):
            response = None  # network problem -> try again

        if response is not None:
            code = response.status_code
            if code in (401, 403):
                # wrong key / no permission: retrying is pointless
                raise SystemExit(f"STOPPED: authentication error {code} for {url}")
            if code == 404:
                problems.append(f"not found: {url}")
                return None
            if code == 200 and not is_quota_error(response):
                return response
            if code != 200 and code != 429 and code < 500:
                problems.append(f"HTTP {code}: {url}")
                return None
            # otherwise: 429, 5xx or quota error -> wait and try again

        wait = 2 ** attempt  # 2, 4, 8, 16, 32 seconds
        print(f"  problem with {url}, trying again in {wait}s ({attempt}/{MAX_TRIES})")
        time.sleep(wait)

    problems.append(f"gave up after {MAX_TRIES} tries: {url}")
    return None


def is_quota_error(response):
    """Deezer sometimes answers 200 but puts a 'quota' error (code 4) in the body."""
    try:
        body = response.json()
    except ValueError:
        return False
    return isinstance(body, dict) and isinstance(body.get("error"), dict) \
        and body["error"].get("code") == 4


def download(source, name, url, pause=0.2):
    """Download a URL and save the answer unchanged. Returns the parsed JSON or None."""
    response = get(url, pause)
    if response is None:
        return None
    try:
        body = response.json()
    except ValueError:
        problems.append(f"not JSON: {url}")
        return None
    if not body or (isinstance(body, dict) and "error" in body):
        problems.append(f"empty or error answer: {url}")
        return None

    # save the raw bytes; "xb" refuses to overwrite an existing file
    folder = RAW_DIR / source
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with open(folder / f"{stamp}_{name}.json", "xb") as file:
        file.write(response.content)
    saved[source] = saved.get(source, 0) + 1
    return body


def main():
    if not CONTACT:
        raise SystemExit("Set MUSICBRAINZ_CONTACT first (see .env.example).")
    print("Run started. Saving to", RAW_DIR)

    # 1. genre list -> one chart per genre (0 = global chart)
    genre_ids = [0]
    genres = download("deezer_genres", "all", f"{DEEZER}/genre")
    if genres:
        genre_ids += [g["id"] for g in genres.get("data", []) if g["id"] != 0]

    # 2. charts, all pages (index moves forward by 100 while "next" exists)
    track_ids, artist_ids, album_ids = [], [], []
    for genre_id in genre_ids:
        for page in range(10):  # at most 10 pages per genre
            url = f"{DEEZER}/chart/{genre_id}/tracks?limit=100&index={page * 100}"
            body = download("deezer_chart", f"genre{genre_id}_p{page + 1}", url)
            if body is None:
                break
            if not body.get("data"):
                problems.append(f"chart {genre_id} page {page + 1} has no tracks")
                break
            for track in body["data"]:
                artist = track.get("artist") or {}
                album = track.get("album") or {}
                for ids, value in ((track_ids, track.get("id")),
                                   (artist_ids, artist.get("id")),
                                   (album_ids, album.get("id"))):
                    if value is not None and value not in ids:
                        ids.append(value)
            if "next" not in body:
                break

    # 3. details for the tracks, artists and albums found in the charts
    isrcs = []
    for track_id in track_ids[:MAX_ITEMS]:
        track = download("deezer_track", track_id, f"{DEEZER}/track/{track_id}")
        if track and track.get("isrc"):
            isrcs.append(track["isrc"])
    for artist_id in artist_ids[:MAX_ITEMS]:
        download("deezer_artist", artist_id, f"{DEEZER}/artist/{artist_id}")
    for album_id in album_ids[:MAX_ITEMS]:
        download("deezer_album", album_id, f"{DEEZER}/album/{album_id}")

    # 4. MusicBrainz: look up each track by its ISRC (max 1 request per second)
    for isrc in isrcs:
        url = f"{MUSICBRAINZ}/isrc/{isrc}?fmt=json&inc=artist-credits+tags"
        download("musicbrainz_isrc", isrc, url, pause=1.1)

    # 5. summary
    print("\n===== RUN SUMMARY =====")
    for source, count in saved.items():
        print(f"{source}: {count} files saved")
    print(f"Problems: {len(problems)}")
    for message in problems[:10]:
        print("  -", message)
    if len(problems) > 10:
        print(f"  ... and {len(problems) - 10} more")
    if saved.get("deezer_chart", 0) == 0:
        print("RESULT: FAILED (no chart data saved)")
    else:
        print("RESULT: finished" + (" with problems" if problems else " OK"))


if __name__ == "__main__":
    main()
