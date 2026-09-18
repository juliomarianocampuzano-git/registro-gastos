"""Minimal junior CLI: load CSV and print a SQL-ish summary via sqlite3."""
from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "sample.csv"


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def build_db(rows: list[dict[str, str]]) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE items (name TEXT, category TEXT, amount REAL)")
    for row in rows:
        conn.execute(
            "INSERT INTO items(name, category, amount) VALUES (?, ?, ?)",
            (row.get("name", ""), row.get("category", ""), float(row.get("amount", 0) or 0)),
        )
    conn.commit()
    return conn


def summarize(conn: sqlite3.Connection) -> str:
    total = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM items").fetchone()[0]
    lines = [f"total={total:.2f}"]
    for cat, amount in conn.execute(
        "SELECT category, SUM(amount) FROM items GROUP BY category ORDER BY category"
    ):
        lines.append(f"{cat}={amount:.2f}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Junior CSV/SQLite summary")
    parser.add_argument("--data", default=str(DATA))
    args = parser.parse_args(argv)
    path = Path(args.data)
    if not path.exists():
        print(f"missing data file: {path}")
        return 1
    conn = build_db(load_rows(path))
    print(summarize(conn))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
