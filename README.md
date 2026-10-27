**deezer-chart-longevity-pipeline**  
**The question**  
Can we predict whether a track that enters a Deezer genre chart will still be in the top 20 (or climb)  
   
 seven days later, using artist fan count, album age, genre, track duration and the explicit-content flag?  
   
 The project also looks at which factors (artist popularity, release recency or genre) matter most for  
   
 chart longevity. A label, playlist curator or artist manager could use this to decide which new releases  
   
 deserve promotion. MusicBrainz metadata (artist country, tags) adds context that Deezer alone does not give.  
**Data sources**  
Details are in [docs/sources.md.](docs/sources.md "docs/sources.md")  
- Deezer charts and genres  
- Deezer track, artist and album details  
- MusicBrainz recordings (looked up by ISRC)  
Data from the [Deezer API and](https://developers.deezer.com/api "https://developers.deezer.com/api") [MusicBrainz.  
   
 Raw data is not committed to this repository.](https://musicbrainz.org "https://musicbrainz.org")  
**How to run it**  
Needs Python 3.9 or newer.  
```  
git clone https://github.com/<your-github-username>/deezer-chart-tracker.git  
 cd deezer-chart-tracker  
   
 python -m venv venv  
 source venv/bin/activate        # Windows: venv\Scripts\activate  
   
 pip install -r requirements.txt  
   
 cp .env.example .env            # Windows: copy .env.example .env  
 # open .env and put your e-mail after MUSICBRAINZ_CONTACT=  
   
 python src/ingest.py  
   
```  
No API key is needed. Environment variables:  
- `MUSICBRAINZ_CONTACT` (required): your e-mail, sent to MusicBrainz in the User-Agent header  
- `MAX_ITEMS` (optional, default 100): max tracks / artists / albums / ISRC lookups per run  
A run takes a few minutes. Every run saves new files in `data/raw/<source>/` named with the UTC time  
   
 (for example `20261012T091244Z_genre0_p1.json`). Old files are never overwritten.  
   
 The script prints a summary at the end.  
**Repository structure**  
- `src/ingest.py` - the ingestion script  
- `data/raw/` - downloaded raw data (not committed, created by the script)  
- `docs/sources.md` - data source cards  
- `requirements.txt` - Python packages  
- `.env.example` - names of the environment variables  
- `.gitignore` - files Git should ignore (.env, data/raw/, ...)  
**Status**  
M2 — schema and load complete  
**Team**  
- Hasan Alparslan (230717051) - GitHub: `se-230717051`  
   
   
**Data Model**  
**ER diagram**  
```  
erDiagram  
     GENRE ||--o{ CHART_ENTRY : "has"  
     TRACK ||--o{ CHART_ENTRY : "appears in"  
     ARTIST ||--o{ TRACK : "performs"  
     ALBUM ||--o{ TRACK : "contains"  
     ARTIST ||--o{ ARTIST_FANS : "has"  
     TRACK ||--o| TRACK_DETAIL : "has"  
     ALBUM ||--o| ALBUM_DETAIL : "has"  
     TRACK ||--o{ TRACK_RECORDING : "matches"  
     RECORDING ||--o{ TRACK_RECORDING : "matches"  
   
     GENRE { INTEGER genre_key PK  
             INTEGER deezer_id UK  
             TEXT name  
             TEXT retrieved_at }  
     ARTIST { INTEGER artist_key PK  
              INTEGER deezer_id UK  
              TEXT name  
              TEXT retrieved_at }  
     ALBUM { INTEGER album_key PK  
             INTEGER deezer_id UK  
             TEXT title  
             TEXT retrieved_at }  
     TRACK { INTEGER track_key PK  
             INTEGER deezer_id UK  
             TEXT title  
             INTEGER duration  
             INTEGER explicit  
             INTEGER artist_key FK  
             INTEGER album_key FK  
             TEXT retrieved_at }  
     TRACK_DETAIL { INTEGER track_key PK, FK  
                    TEXT isrc  
                    TEXT release_date  
                    TEXT retrieved_at }  
     ALBUM_DETAIL { INTEGER album_key PK, FK  
                    TEXT release_date  
                    INTEGER nb_tracks  
                    TEXT retrieved_at }  
     CHART_ENTRY { INTEGER genre_key PK, FK  
                   TEXT snapshot_date PK  
                   INTEGER position PK  
                   INTEGER track_key FK  
                   INTEGER rank  
                   TEXT retrieved_at }  
     ARTIST_FANS { INTEGER artist_key PK, FK  
                   TEXT snapshot_date PK  
                   INTEGER nb_fan  
                   TEXT retrieved_at }  
     RECORDING { INTEGER recording_key PK  
                 TEXT mbid UK  
                 TEXT title  
                 INTEGER length_ms  
                 TEXT first_release_date  
                 TEXT retrieved_at }  
     TRACK_RECORDING { INTEGER track_key PK, FK  
                       INTEGER recording_key PK, FK  
                       TEXT retrieved_at }  
   
```  
(`quarantine` is not drawn: it has no foreign keys.)  
**Grain of every table**  
- `genre`: one row = one Deezer genre.  
- `artist`: one row = one Deezer artist.  
- `album`: one row = one Deezer album.  
- `track`: one row = one Deezer track.  
- `track_detail`: one row = the extra details (ISRC, release date) of one track.  
- `album_detail`: one row = the extra details (release date, number of tracks) of one album.  
- `chart_entry`: one row = one chart position in one genre chart on one day.  
- `artist_fans`: one row = the fan count of one artist on one day.  
- `recording`: one row = one MusicBrainz recording.  
- `track_recording`: one row = one Deezer track matched to one MusicBrainz recording (by ISRC).  
- `quarantine`: one row = one raw record that could not be loaded, with the reason.  
**Decisions and findings**  
**Keys.** Every entity has a surrogate key and keeps the Deezer id (or the MusicBrainz id) as  
   
 `NOT NULL UNIQUE`. A chart entry is identified by (genre, day, position); the day is the UTC date of the  
   
 file. If the chart was fetched twice on one day, the later file wins. An artist's fan count is identified  
   
 by (artist, day). I tested the keys with `src/explore.py`:  
- (genre, day, position) is unique after keeping the latest file per day:  
\- (genre, day, position) is unique after keeping the latest file per day: 4598 items in the files, 2299 distinct keys; 0 positions missing.  
- A track id always has the same title and artist:  
\- A track id always has the same title and artist: 2048 distinct track ids, 0 whose title or artist changes.  
- Every reference resolves (artists and tracks in the detail files exist in the charts):  
\- Every reference resolves: 1176 artists and 2048 tracks in the charts; 0 artist files and 0 track files point to something that is not in a chart; 0 tracks without ISRC.  
**Missing values.** A missing value (`null`, empty) is stored as NULL and means "not recorded". A real 0  
   
 stays 0 (for example `nb_fan = 0`). Text where a number belongs, and invalid dates such as Deezer's  
   
 `0000-00-00`, become NULL and are counted in "values cleaned". MusicBrainz dates that are only a year  
   
 (`2013`) become NULL too, because the column holds full dates only.  
**Unknown references.** A record that points to something we do not have (a detail file for a track that  
   
 is in no chart, a chart item without a track, artist or album id or without a position, a chart of an unknown genre, an ISRC no  
   
 track has) goes to the `quarantine` table with the reason and the raw record. It is not dropped and it  
   
 does not crash the load. The quarantine table is rebuilt on each run, so it always shows the current state.  
**Change over time.** Names and titles are type 1: the latest retrieved version replaces the old one.  
   
 Things that change daily (chart positions, fan counts) are not stored on the entity but as events with  
   
 a date, so the history is kept.  
**Known issues.**  
- `ingest.py` fetches details for at most `MAX_ITEMS` tracks/artists/albums per run, so many artists have  
   
 no fan count.  
- One ISRC can belong to several Deezer tracks, and one track can match several MusicBrainz recordings.  
- Partial MusicBrainz dates (year only) are lost.  
   
- QUARANTINE: - Nothing was quarantined in my data. 16 values were cleaned to NULL (see the load summary).  
**One analytical query**  
`sql/queries/global_top20_longevity.sql` answers: which tracks stayed in the global top 20 on the most  
   
 snapshot days? Result grain: one row per track.  
```  
Your text here  
```  
SELECT t.title,  
       a.name                         AS artist,  
       COUNT(DISTINCT c.snapshot_date) AS days_in_top20,  
       MIN(c.position)                AS best_position  
FROM chart_entry AS c  
JOIN genre  AS g ON g.genre_key  = c.genre_key  
JOIN track  AS t ON t.track_key  = c.track_key  
JOIN artist AS a ON a.artist_key = t.artist_key  
WHERE g.deezer_id = 0  
  AND c.position <= 20  
GROUP BY t.track_key  
ORDER BY days_in_top20 DESC, best_position ASC  
LIMIT 10;  
Output (`python src/run_query.py sql/queries/global_top20_longevity.sql`  
23:21:12 SELECT t.title,        a.name                         AS artist,        COUNT(DISTINCT c.snapshot_date) AS days_in_top20,        MIN(c.position)                AS best_position FROM chart_entry AS c JOIN genre  AS g ON g.genre_key  = c.genre_key JOIN track  AS t ON t.track_key  = c.track_key JOIN artist AS a ON a.artist_key = t.artist_key WHERE g.deezer_id = 0   AND c.position <= 20 GROUP BY t.track_key ORDER BY days_in_top20 DESC, best_position ASC LIMIT 10 Error Code: 1046. No database selected Select the default DB to be used by double-clicking its name in the SCHEMAS list in the sidebar. 0.0023 sec  
**How to build the database**  
From a fresh clone, with the raw data already landed by `python src/ingest.py`:  
```  
python src/load.py      # builds data/deezer.db from data/raw/ (run it again: nothing changes)  
 python src/checks.py    # six checks, on a temporary copy  
   
```  
   
