"""Gastos del mes — control de gastos del hogar con SQLite + HTML/JS."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from flask import Flask, g, jsonify, render_template, request

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "gastos.db"

app = Flask(__name__)


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db


@app.teardown_appcontext
def close_db(_: object | None = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount REAL NOT NULL CHECK(amount > 0),
            category TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            spent_on TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/expenses")
def list_expenses():
    month = request.args.get("month") or date.today().strftime("%Y-%m")
    rows = get_db().execute(
        """
        SELECT id, amount, category, note, spent_on
        FROM expenses
        WHERE substr(spent_on, 1, 7) = ?
        ORDER BY spent_on DESC, id DESC
        """,
        (month,),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.get("/api/summary")
def summary():
    month = request.args.get("month") or date.today().strftime("%Y-%m")
    db = get_db()
    total = db.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total FROM expenses WHERE substr(spent_on, 1, 7) = ?",
        (month,),
    ).fetchone()["total"]
    by_cat = db.execute(
        """
        SELECT category, ROUND(SUM(amount), 2) AS total
        FROM expenses
        WHERE substr(spent_on, 1, 7) = ?
        GROUP BY category
        ORDER BY total DESC
        """,
        (month,),
    ).fetchall()
    return jsonify({"month": month, "total": float(total), "by_category": [dict(r) for r in by_cat]})


@app.post("/api/expenses")
def add_expense():
    data = request.get_json(force=True, silent=True) or {}
    try:
        amount = float(data.get("amount", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "amount must be a number"}), 400
    category = str(data.get("category") or "").strip()
    note = str(data.get("note") or "").strip()
    spent_on = str(data.get("spent_on") or date.today().isoformat()).strip()
    if amount <= 0:
        return jsonify({"error": "amount must be > 0"}), 400
    if not category:
        return jsonify({"error": "category required"}), 400
    cur = get_db().execute(
        "INSERT INTO expenses(amount, category, note, spent_on) VALUES (?, ?, ?, ?)",
        (amount, category, note, spent_on),
    )
    get_db().commit()
    row = get_db().execute("SELECT * FROM expenses WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(dict(row)), 201


@app.delete("/api/expenses/<int:expense_id>")
def delete_expense(expense_id: int):
    cur = get_db().execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    get_db().commit()
    if cur.rowcount == 0:
        return jsonify({"error": "not found"}), 404
    return jsonify({"ok": True})


def create_app(db_path: Path | None = None) -> Flask:
    global DB_PATH
    if db_path is not None:
        DB_PATH = Path(db_path)
    init_db()
    return app


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
