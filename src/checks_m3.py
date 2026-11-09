"""Proves that clean.py and validate.py behave. Run: python src/checks_m3.py

Works on temporary copies of the database; the real one is never touched.
Needs a database built with: python src/load.py
"""
import contextlib
import io
import shutil
import sys
import tempfile
from pathlib import Path

import clean
import clean_config as cfg
import db
import validate

results = []


def report(name, passed, detail=""):
    results.append(passed)
    print("%-34s %s %s" % (name + ":", "PASS" if passed else "FAIL", detail))


def open_copy(source, target):
    shutil.copyfile(source, target)
    con = db.connect(target)
    con.executescript(clean.CLEAN_SCHEMA.read_text(encoding="utf-8"))
    return con


def stop_failures(path):
    """Names of the STOP checks that fail on this database, and validate's exit code."""
    con = db.connect(path)
    failed = [name for level, name, passed, _ in validate.run_checks(con)
              if level == "STOP" and not passed]
    with contextlib.redirect_stdout(io.StringIO()):
        code = validate.run(con)
    con.close()
    return failed, code


def main():
    if not db.DB_PATH.exists():
        print("No database found. Run python src/load.py first.")
        return 1
    with tempfile.TemporaryDirectory() as folder:
        tmp = Path(folder)
        con = open_copy(db.DB_PATH, tmp / "work.db")

        # --- clean.py ---
        before = clean.fingerprint(con)
        clean.build(con)
        report("M2 tables unchanged", clean.fingerprint(con) == before)

        first = clean.clean_snapshot(con)
        clean.build(con)
        report("idempotent (run twice)", clean.clean_snapshot(con) == first)

        cfg.IQR_K = 3.0
        try:
            clean.build(con)
            wider = clean.clean_snapshot(con)
        finally:
            cfg.IQR_K = 1.5
        changed = sum(1 for t in first for a, b in zip(first[t], wider[t]) if a != b)
        clean.build(con)
        report("threshold change and change back", clean.clean_snapshot(con) == first,
               "(IQR_K 1.5 -> 3.0 changed %d rows, changing back restored them)" % changed)

        bad_csv = tmp / "bad.csv"
        bad_csv.write_text("wrong,columns\n1,2\n", encoding="utf-8")
        cfg.IQR_K = 3.0
        failed = False
        try:
            clean.build(con, bad_csv)
        except Exception:
            failed = True
        finally:
            cfg.IQR_K = 1.5
        report("atomic (failure mid-build)", failed and clean.clean_snapshot(con) == first,
               "" if failed else "(the broken CSV did not make the build fail)")
        con.close()
        shutil.copyfile(tmp / "work.db", tmp / "built.db")

        # --- validate.py: every STOP check must fail when it should ---
        names = [n for l, n, _, _ in validate.run_checks(db.connect(tmp / "built.db")) if l == "STOP"]
        ok, code = stop_failures(tmp / "built.db")
        report("validate passes on good data", not ok and code == 0)

        con = open_copy(tmp / "built.db", tmp / "t1.db")       # one extra cleaned row
        con.execute("INSERT INTO artist_fans_clean (artist_key, snapshot_date, nb_fan_flag) "
                    "VALUES ((SELECT MIN(artist_key) FROM artist), ?, ?)", ("1999-01-01", "ok"))
        con.commit()
        con.close()
        failing, code = stop_failures(tmp / "t1.db")
        report("STOP: row count", names[0] in failing and code == 1)

        con = open_copy(tmp / "built.db", tmp / "t2.db")       # an impossible value
        con.execute("UPDATE track_clean SET duration = ? "
                    "WHERE track_key = (SELECT MIN(track_key) FROM track_clean)", (-5,))
        con.commit()
        con.close()
        failing, code = stop_failures(tmp / "t2.db")
        report("STOP: impossible value", names[1] in failing and code == 1)

        con = open_copy(tmp / "built.db", tmp / "t3.db")       # a broken reference
        con.execute("PRAGMA foreign_keys = OFF")
        con.execute("INSERT INTO chart_entry (genre_key, snapshot_date, position, track_key, "
                    "retrieved_at) VALUES (?, ?, ?, ?, ?)",
                    (-1, "2026-01-01", 1, -1, "2026-01-01T00:00:00Z"))
        con.commit()
        con.close()
        failing, code = stop_failures(tmp / "t3.db")
        report("STOP: foreign_key_check", names[2] in failing and code == 1)

    print("\n%d of %d checks passed" % (sum(results), len(results)))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
