**Cleaning Report: deezer-chart-longevity-pipeline**  
**1. Summary**  
The data are Deezer genre charts (23 charts of 100 tracks, one snapshot day, 2026-10-12), Deezer detail  
   
 records for the first 100 tracks, artists and albums that the charts mention, and the 102 MusicBrainz  
   
 recordings matched to those tracks by ISRC. The profile found no impossible values, but it found four  
   
 kinds of problems: text that looks equal but is not (trailing and non-breaking spaces, decomposed  
   
 accents), artists that may be one entity recorded twice (or two entities with the same name), a few  
   
 extreme but real numbers (very long tracks, artists with 597 or 21 million fans), and a large coverage  
   
 gap: only 100 of 1,176 artists have a fan count, because `ingest.py` fetches details for at most 100  
   
 items per type. The cleaned layer keeps every M2 row, stores raw value, cleaned value and flag side by  
   
 side, fixes only text, and sets a value to NULL only when it is impossible; nothing is imputed. What we  
   
 still cannot say is anything about change over time (there is one snapshot day) and anything about the  
   
 artists without a fan count. M2 changes needed for M3: none.  
**2. Profile highlights**  
The full profile is in [notebooks/m3_profile.ipynb (it reads the M2  
   
 database and changes nothing). The parts that led to findings:](../notebooks/m3_profile.ipynb "../notebooks/m3_profile.ipynb")  
  
|  |  |  |  
| - | - | - |  
| **Profile section** |  **Result** |  **Led to** |  
| 2 Missing |  `recording.first_release_date` 9 of 102 NULL; `recording.length_ms` 1 of 102 |  I-03, I-04 |  
| 3 Numbers |  `track.duration` 25 to 1638 s; `artist_fans.nb_fan` 597 to 20,933,670 |  I-09, I-10 |  
| 5 Text |  artist names: 3 padded, 1 non-breaking space; track titles: 3 not NFC, 2 padded |  I-05 |  
| 6 Identity |  2 artist names shared by 2 ids (LiSA/LISA, Vacra); 13 track rows share title and artist |  I-06, I-07, I-08 |  
| 7 Coverage |  1076 of 1176 artists without fan count; 1 of 23 charts has 99 rows |  I-01, I-02, I-11 |  
| 8 Sequences |  only one snapshot day: no day-to-day change can be measured |  "Checked and not found" |  
  
   
**3. Issues register**  
  
|  |  |  |  |  |  |  |  |  |  |  
| - | - | - | - | - | - | - | - | - | - |  
| **ID** |  **Family** |  **Table.column** |  **What** |  **Where / when / how many** |  **Evidence** |  **Cause** |  **Decision** |  **Flag** |  **Investigated by** |  
| I-01 |  1 Missing |  artist_fans (whole entities) |  No fan count |  1076 of 1176 artists, snapshot 2026-10-12 |  Profile §7; `artist_fans` has 100 rows |  Confirmed: `ingest.py` fetches at most `MAX_ITEMS`=100 artists, in order of first appearance (sources.md, card 2) |  Not fixable by cleaning; reported by validate (WARN) |  none |  H. Alparslan |  
| I-02 |  1 Missing |  track_detail, album_detail (whole entities) |  No ISRC / release date / nb_tracks |  100 of 2048 tracks, 100 of 1745 albums |  Profile §1: 100 rows each |  Confirmed: same `MAX_ITEMS` limit |  As I-01 |  none |  H. Alparslan |  
| I-03 |  1 Missing |  recording.first_release_date |  NULL |  9 of 102 (8.8%) |  Profile §2 |  Inferred: MusicBrainz stores some dates as year only; the M2 loader sets non-full dates to NULL (M2 README). To confirm, count raw MusicBrainz files whose `first-release-date` has 4 characters |  NULL kept, flagged |  first_release_date_flag = missing_not_reported |  H. Alparslan |  
| I-04 |  1 Missing |  recording.length_ms |  NULL |  1 of 102 |  Profile §2 |  Unknown |  NULL kept, flagged |  length_ms_flag = missing_not_reported |  H. Alparslan |  
| I-05 |  5 Text |  artist.name, album.title, track.title |  Trailing spaces (`'ILLIT '`), non-breaking space (`'Bak postacı geliyor\xa0'`), decomposed accents (`'Fille à Papa'` is not NFC) |  Artists 3 padded + 1 nbsp; albums 1 + 1 + 1 not NFC; tracks 2 padded, 2 nbsp, 3 not NFC |  Profile §5, `repr()` of examples |  Inferred: copied text (nbsp) and different Unicode forms from the provider; nothing states it |  Cleaned: NFC, single normal spaces, trimmed. Raw kept next to it |  name_flag, title_flag = unicode_normalised / whitespace_fixed |  H. Alparslan |  
| I-06 |  6 Identity |  artist |  `LiSA` and `LISA`: equal after casefolding, different Deezer ids |  2 artists |  Profile §6 |  Inferred: two different artists (a Japanese singer and a BLACKPINK member) |  Kept separate; recorded as `different_entity` |  identity_map |  H. Alparslan |  
| I-07 |  6 Identity |  artist |  Two Deezer ids named `Vacra` |  2 artists |  Profile §6 |  Inferred (not confirmed): one artist with a duplicate profile |  Mapped as `same_entity`; keys not merged; view `artist_resolved` |  identity_map |  H. Alparslan |  
| I-08 |  6 Identity |  track |  Same title and artist under several track ids (e.g. "Eye of the Tiger" 576431 and 632868, "Dai Dai" x3) |  13 rows |  Profile §6 |  Inferred: versions or re-releases on other albums; ISRC could not be compared (only 100 tracks have an ISRC) |  Not merged; `track_named` gives `title_key` and resolved artist for grouping; validate WARN |  none |  H. Alparslan |  
| I-09 |  3 Unusual |  track.duration |  Very short and very long tracks (25 s to 1638 s) |  88 unusual_high, 3 unusual_low (of 2,048 tracks)   |  Profile §3; IQR fence |  The top “Hanuman Chalisa” is a long book and its audiobook is too. |  Kept, flagged |  duration_flag = unusual_low / unusual_high |  H. Alparslan |  
| I-10 |  3 Unusual |  artist_fans.nb_fan |  Very small and very large fan counts (597 to 20,933,670) |  2 unusual_low, 0 unusual_high (of 100 fan counts) |  Profile §3; IQR fence on log10 |  Unknown (real size differences between artists) |  Kept, flagged |  nb_fan_flag = unusual_low / unusual_high |  H. Alparslan |  
| I-11 |  1 Missing |  chart_entry (one chart) |  A chart with 99 rows instead of 100 |  1 of 23 charts |  Profile §7; quarantine is empty, so the loader dropped nothing |  Unknown (Deezer returned 99 items) |  Nothing to clean; noted |  none |  H. Alparslan |  
  
   
**Checked and not found**  
  
|  |  |  |  
| - | - | - |  
| **Family** |  **Check** |  **Result** |  
| 2 Invalid |  Zero or negative duration, fan count, length |  Profile §3: zeros 0 and negatives 0 for every numeric column |  
| 2 Invalid |  Sentinels (-999, 0, 9999) |  Profile §3 most frequent values: 192 s (22 tracks), no sentinel in any column |  
| 2 Invalid |  Release dates in the future or before 1950 |  Profile §4: 0 and 0. Range 1979-07-27 to 2026-10-09 |  
| 2 Invalid |  Chart position outside 1..100 or rank <= 0 |  Profile §3: position 1..100, rank 6963..1,000,000. validate WARN: 0 bad rows |  
| 1 Missing |  Empty strings |  Profile §2 counts NULL and empty text: only the two recording columns have gaps |  
| 4 Across rows |  Stuck values, spikes, fan counts that decrease |  Not testable: one snapshot day (Profile §8 shows NaN jumps) |  
| 4 Across rows |  A track in two positions of the same chart |  Profile §7: 0 |  
| 6 Identity |  One ISRC shared by several tracks |  Profile §6: 0 (but only 100 tracks have an ISRC) |  
| 5 Text |  Case or Turkish-letter variants of genre names |  Profile §5: genre.name has no problems |  
  
   
**4. Missing values**  
**Fan counts, ISRC and album details (I-01, I-02).** 91.5% of artists have no fan count. The mechanism is  
   
 MAR: `ingest.py` takes the first 100 items in order of first appearance, so the global chart and the first  
   
 genre charts are covered and the rest is not. Missingness depends on chart position, which we observe,  
   
 and chart position is related to popularity. Consequence for M4: averages of fan counts over the 100  
   
 artists describe artists high in the global chart, not artists in general. Do not compare genres by fan  
   
 count. Either raise `MAX_ITEMS` and run `ingest.py` again (the pipeline rebuilds everything) or restrict  
   
 the analysis to the artists with a count and say so.  
**MusicBrainz first release date (I-03).** 8.8% missing. Inferred cause: year-only dates became NULL in M2.  
   
 If that is right, the mechanism is not random: the rows are those with imprecise source dates, which  
   
 are more often older catalogue items. This could not be proved. Consequence: do not compute recording  
   
 age from this column without noting the gap.  
**Recording length (I-04).** One value, mechanism unknown, no consequence at this size.  
**5. Flags and rules**  
Rules run in this order for each value; the first rule that applies wins.  
  
|  |  |  |  |  |  |  
| - | - | - | - | - | - |  
| **Order** |  **Flag** |  **Meaning** |  **Rule** |  **Cleaned value** |  **Count** |  
| 1 |  missing_not_reported |  Source gave no value |  raw is NULL or only spaces |  NULL |  10 |  
| 2 |  invalid_range |  Impossible number |  duration or length <= 0 or above the maximum |  NULL |  0 |  
| 2 |  invalid_future |  Released after we retrieved it |  first_release_date later than the retrieval day |  NULL |  0 |  
| 2 |  unicode_normalised |  Different Unicode form |  NFC changes the text |  NFC text, one space between words |  4 |  
| 3 |  whitespace_fixed |  Padding or non-breaking space |  only whitespace differs |  trimmed, normal spaces |  7 |  
| 3 |  unusual_low / unusual_high |  Extreme but possible |  outside the IQR fence (duration, length, log10 fan count) |  unchanged (kept) |  5/91 |  
| 4 |  ok |  Nothing found |  none of the above |  unchanged |  7204 |  
  
   
**Note**:Counts are values, not rows; one row can have several values.  
**Constants (in** `src/clean_config.py`**)**  
- `IQR_K = 1.5`: the usual Tukey fence. The IQR is not distorted by the extremes it looks for (mean and  
   
 standard deviation would be). Moving it to 3.0 flags fewer values (`src/checks_m3.py` shows how many rows  
   
 change); no value is ever removed because of it, only the flag changes.  
- `MAX_DURATION_S = 86400` and `MAX_LENGTH_MS = 86400000`: a track cannot last longer than a day. The  
   
 longest observed track is 1638 s, so this only catches a unit or parsing error.  
- `CHART_SIZE = 100`: Deezer charts have positions 1 to 100 (`CHART_PAGE_SIZE` in `ingest.py`).  
- `MAX_MISSING_SHARE = 0.10`: a guess for "a small gap"; 8.8% is just under it. Raising it silences the  
   
 warning on `first_release_date`.  
- `MIN_FAN_COVERAGE = 0.50`: a guess. With 8.5% coverage the check always warns (I-01); that is intended.  
**6. Mapping and identity decisions**  
Matching was done in steps: exact name, then `name_key` (accents removed, Turkish letters folded, casefold,  
   
 single spaces), then a human decision. No fuzzy matching was used, so nothing was matched by a threshold  
   
 that nobody reviewed. The key function found the groups below; each decision is a row of  
   
 [data/mappings/artist_identity.csv, with who decided, when and why.](../data/mappings/artist_identity.csv "../data/mappings/artist_identity.csv")  
  
|  |  |  
| - | - |  
| **Step** |  **Result** |  
| Exact name equal, different id |  1 name (Vacra) |  
| Equal only after `name_key` |  1 name (LiSA / LISA) |  
| Human decision recorded |  2 rows: 1 `same_entity`, 1 `different_entity` |  
| Unmatched CSV rows |  unmatched: none |  
| Collisions without a decision |  0 |  
  
   
Evidence: LiSA and LISA are well-known as different artists (decision by knowledge, not documentation).  
   
 Vacra is inferred from the identical name only; both Deezer profiles must be opened to confirm it, and  
   
 the CSV row changed to `different_entity` if they are different people. For tracks (I-08) no merge was  
   
 made: the same title under several ids can be a different version.  
**7. Counts and validation**  
Output of `python src/clean.py` (final run):  
```  
   
```  
artist_clean: 1,176 rows (raw: 1,176)  
   text_flag:   ok 1172 | whitespace_fixed 4  
album_clean: 1,745 rows (raw: 1,745)  
   text_flag:   ok 1743 | unicode_normalised 1 | whitespace_fixed 1  
track_clean: 2,048 rows (raw: 2,048)  
   text_flag:   ok 2043 | unicode_normalised 3 | whitespace_fixed 2  
   number_flag: ok 1957 | unusual_high 88 | unusual_low 3  
artist_fans_clean: 100 rows (raw: 100)  
   number_flag: ok 98 | unusual_low 2  
recording_clean: 102 rows (raw: 102)  
   number_flag: missing_not_reported 1 | ok 98 | unusual_high 3  
   date_flag:   missing_not_reported 9 | ok 93  
mappings: identity_map 2 of 2 CSV rows loaded (unmatched: none)  
artist names that are equal after normalising but have no identity decision: 0  
M2 tables unchanged: OK  
foreign_key_check: OK  
STATUS: COMPLETE  
Output of `python src/validate.py`:  
```  
   
```  
PASS  cleaned tables have the same row count as raw                all 5 equal  
PASS  no impossible value in a cleaned column                      0 found  
PASS  foreign_key_check is empty                                   OK  
PASS  missing share per recording column at most 10%               first_release_date 8.8%, length_ms 1.0%  
WARN  at least 50% of artists have a fan count                     100 of 1176 artists (8.5%)  
PASS  every genre has a chart on the latest day (2026-10-12)       23 of 23 genres  
PASS  chart positions within 1..100 and rank > 0                   0 bad rows  
PASS  no artist-name collision without an identity decision        0 unresolved  
WARN  no song under several track ids (same artist, same title)    6 groups (kept separate, see report)  
   
STATUS: OK (see WARN lines, if any)  
Every WARN, classified:  
  
|  |  |  
| - | - |  
| **WARN** |  **Problem in the world, the measurement or the pipeline?** |  
| Fan coverage below 50% |  Pipeline: `MAX_ITEMS` limit of `ingest.py` (I-01) |  
| Missing share of first_release_date |  Measurement/pipeline: year-only dates in the source, NULLed by the loader (I-03) |  
| Songs under several track ids |  World: re-releases and versions exist (I-08) |  
  
   
How each STOP check was made to fail once (`python src/checks_m3.py`, on a temporary copy):  
- Row count: one extra row inserted into `artist_fans_clean` -> STOP, exit code 1.  
- Impossible value: `track_clean.duration` set to -5 -> STOP, exit code 1.  
- foreign_key_check: with foreign keys off, a `chart_entry` row pointing to a missing genre and track -> STOP, exit code 1.  
The same script shows that M2 tables are unchanged by `clean.py`, that running it twice gives the same  
   
 result, that changing `IQR_K` and changing it back restores the original, and that a failure in the  
   
 middle of the build leaves the cleaned layer as it was.  
**8. What we can't say**  
- Anything about change over time: there is one snapshot day, so chart longevity (the project question)  
   
 cannot be measured yet. M4 needs more snapshot days.  
- Anything about the 1,076 artists without a fan count, and about release dates of 95% of tracks (I-01, I-02).  
- Whether Vacra is one artist (I-07, inferred) and whether same-title tracks are the same song (I-08).  
- Why a recording has no length, and why one chart has 99 rows (unknown).  
- The thresholds are conventions or guesses (section 5); with more data they would be revisited.  
