"""Runs a .sql file against the database and prints the result.
Example: python src/run_query.py sql/queries/global_top20_longevity.sql
"""
import sys
from pathlib import Path

import db

con = db.connect()
cursor = con.execute(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(" | ".join(column[0] for column in cursor.description))
for row in cursor.fetchall():
    print(" | ".join(str(value) for value in row))
