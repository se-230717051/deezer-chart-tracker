# deezer-chart-longevity-pipeline

## The question

Can we predict whether a track that enters a Deezer genre chart will still be in the top 20 (or climb)
seven days later, using artist fan count, album age, genre, track duration and the explicit-content flag?
The project also looks at which factors (artist popularity, release recency or genre) matter most for
chart longevity. A label, playlist curator or artist manager could use this to decide which new releases
deserve promotion. MusicBrainz metadata (artist country, tags) adds context that Deezer alone does not give.

## Data sources

Details are in [docs/sources.md](docs/sources.md).

- Deezer charts and genres
- Deezer track, artist and album details
- MusicBrainz recordings (looked up by ISRC)

Data from the [Deezer API](https://developers.deezer.com/api) and [MusicBrainz](https://musicbrainz.org).
Raw data is not committed to this repository.

## How to run it

Needs Python 3.9 or newer.

```bash
git clone https://github.com/<your-github-username>/deezer-chart-tracker.git
cd deezer-chart-tracker

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env            # Windows: copy .env.example .env
# open .env and put your e-mail after MUSICBRAINZ_CONTACT=

python src/ingest.py
```

No API key is needed. Environment variables:

- `MUSICBRAINZ_CONTACT` (required): your e-mail, sent to MusicBrainz in the User-Agent header
- `MAX_ITEMS` (optional, default 100): max tracks / artists / albums / ISRC lookups per run

A run takes a few minutes. Every run saves new files in `data/raw/<source>/` named with the UTC time
(for example `20261012T091244Z_genre0_p1.json`). Old files are never overwritten.
The script prints a summary at the end.

## Repository structure

- `src/ingest.py` - the ingestion script
- `data/raw/` - downloaded raw data (not committed, created by the script)
- `docs/sources.md` - data source cards
- `requirements.txt` - Python packages
- `.env.example` - names of the environment variables
- `.gitignore` - files Git should ignore (.env, data/raw/, ...)

## Status

M1 — ingestion complete

## Team

- Hasan Alparslan (230717051) - GitHub: `se-230717051`
