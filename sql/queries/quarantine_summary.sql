SELECT source, reason, COUNT(*) AS how_many
FROM quarantine
GROUP BY source, reason;