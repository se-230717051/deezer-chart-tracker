# Data source cards

Fields marked TODO are filled in by hand.

## Deezer - charts and genres

```
source_name: Deezer API - genre list and top-100 charts per genre
provider: Deezer
url: https://developers.deezer.com/api  (/genre, /chart/{genre_id}/tracks)
access_method: REST API, no key needed
licence: I found nothing about redistribution
terms_notes: Checked the terms on 2026-10-12.Raw data is not committed.
update_cadence: daily
coverage: current chart only, no history. Genre 0 = global chart.
record_meaning: one row = one track at one chart position in one genre chart
join_key: artist.id -> Deezer artist, album.id -> Deezer album, track.id -> Deezer track
first_retrieved: 2026-10-12T00:22:37Z
known_issues:
  - Only the current ranking is returned, so history needs repeated runs.
  - Rate limit is about 50 requests per 5 seconds. Deezer can report errors with HTTP 200
    and an "error" field in the body.
  - Some genre charts can be empty. Nested artist/album fields can be missing.
```

## Deezer - track, artist and album details

```
source_name: Deezer API - track, artist and album details
provider: Deezer
url: https://developers.deezer.com/api  (/track/{id}, /artist/{id}, /album/{id})
access_method: REST API, no key needed
licence: same as chart 1
terms_notes: same as chart 1
update_cadence: fan counts change continuously
coverage: only items that appear in the charts, at most MAX_ITEMS of each type per run
record_meaning: one row = one track (with ISRC), one artist (with fan count) or one album (with release date)
join_key: artist.id, album.id (from charts); track ISRC -> MusicBrainz
first_retrieved: 2026-10-12T00:22:53Z
known_issues:
  - MAX_ITEMS means not every chart item is fetched.
  - Some tracks have no ISRC.
```

## MusicBrainz

```
source_name: MusicBrainz API - recordings looked up by ISRC
provider: MetaBrainz Foundation
url: https://musicbrainz.org/doc/MusicBrainz_API  (/ws/2/isrc/{isrc})
access_method: REST API, no key, but a User-Agent with contact info is required
licence:  CC0
terms_notes: about 1 request per second. Raw data is not committed.
update_cadence: edited by the community all the time
coverage: only ISRCs found in the Deezer track records, at most MAX_ITEMS per run
record_meaning: one row = one recording (with artist credits and tags) for one ISRC
join_key: ISRC (Deezer track -> MusicBrainz recording)
first_retrieved: 2026-10-12T00:25:24Z
known_issues:
  - Many ISRCs are not found (HTTP 404), so the match rate is below 100%.
  - One ISRC can match several recordings.
  - Artist country is not in these files; it needs a separate artist lookup (later milestone).
```
