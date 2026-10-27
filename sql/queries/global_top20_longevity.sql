-- Question: which tracks stayed in the global top 20 on the most snapshot days?
--           (a first look at chart longevity, the question of this project)
-- Result grain: one row per track.
-- chart_entry has one row per (genre, day, position). Filtering to the global chart
-- (Deezer genre id 0) and position <= 20 leaves at most one row per track per day,
-- so COUNT(DISTINCT snapshot_date) counts days. The joins to track and artist are
-- many-to-one (a track has one artist), so they do not multiply rows.
SELECT t.title,
       a.name                         AS artist,
       COUNT(DISTINCT c.snapshot_date) AS days_in_top20,
       MIN(c.position)                AS best_position
FROM chart_entry AS c
JOIN genre  AS g ON g.genre_key  = c.genre_key
JOIN track  AS t ON t.track_key  = c.track_key
JOIN artist AS a ON a.artist_key = t.artist_key
WHERE g.deezer_id = 0
  AND c.position <= 20
GROUP BY t.track_key
ORDER BY days_in_top20 DESC, best_position ASC
LIMIT 10;
