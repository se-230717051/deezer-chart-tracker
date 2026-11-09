SELECT title, duration, duration_flag
FROM track_clean
WHERE duration_flag <> 'ok'
ORDER BY duration DESC
LIMIT 15;