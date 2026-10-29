"""Local household expenses with exact amounts and isolated app instances."""

from __future__ import annotations

import csv
import io
import os
import re
import sqlite3
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

import click
from flask import Flask, Response, current_app, g, jsonify, render_template, request

ROOT = Path(__file__).resolve().parent
MAX_AMOUNT = Decimal("999999999.99")
SCHEMA = """
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
    category TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    spent_on TEXT NOT NULL
)
"""


def amount_to_cents(value: object, *, legacy: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("El monto debe ser un número.")
    try:
        amount = Decimal(str(value).strip())
        if not amount.is_finite() or not Decimal("0") < amount <= MAX_AMOUNT:
            raise ValueError("El monto debe ser mayor a cero y no superar 999999999.99.")
        rounded = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if not legacy and amount != rounded:
            raise ValueError("El monto admite hasta dos decimales.")
        cents = int(rounded * 100)
        if cents <= 0:
            raise ValueError("El monto mínimo es 0.01.")
        return cents
    except (InvalidOperation, OverflowError) as exc:
        raise ValueError("El monto debe ser un número válido.") from exc


def valid_month(value: str) -> str:
    if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", value):
        raise ValueError("El mes debe tener el formato AAAA-MM.")
    date.fromisoformat(value + "-01")
    return value


def selected_month() -> str:
    return valid_month(request.args.get("month", date.today().strftime("%Y-%m")))


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        conn = sqlite3.connect(current_app.config["DATABASE"])
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db


def close_db(_: BaseException | None = None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(expenses)")}
        if "amount" in columns and "amount_cents" not in columns:
            # Back up the original database before an atomic migration.
            stamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
            backup = db_path.with_name(f"{db_path.name}.pre-cents-{stamp}.bak")
            with sqlite3.connect(backup) as target:
                conn.backup(target)
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                "SELECT id, amount, category, note, spent_on FROM expenses ORDER BY id"
            ).fetchall()
            converted = [(row[0], amount_to_cents(row[1], legacy=True), *row[2:]) for row in rows]
            conn.execute("ALTER TABLE expenses RENAME TO expenses_legacy")
            conn.execute(SCHEMA)
            conn.executemany(
                "INSERT INTO expenses(id, amount_cents, category, note, spent_on) "
                "VALUES (?, ?, ?, ?, ?)",
                converted,
            )
            conn.execute("DROP TABLE expenses_legacy")
        else:
            conn.execute(SCHEMA)


def expense_dict(row: sqlite3.Row) -> dict:
    item = dict(row)
    # Keep amount for v0.1 clients; amount_cents is authoritative.
    item["amount"] = item["amount_cents"] / 100
    return item


def expense_rows(month: str) -> list[sqlite3.Row]:
    return (
        get_db()
        .execute(
            "SELECT id, amount_cents, category, note, spent_on FROM expenses "
            "WHERE substr(spent_on, 1, 7) = ? ORDER BY spent_on DESC, id DESC",
            (month,),
        )
        .fetchall()
    )


def csv_text(value: str) -> str:
    # CSV quoting alone does not neutralize spreadsheet formulas.
    if value.startswith(("\t", "\r", "\n")) or value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def create_app(db_path: Path | None = None, test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(
        DATABASE=str(db_path or os.environ.get("GASTOS_DATABASE") or ROOT / "data" / "gastos.db"),
        MAX_CONTENT_LENGTH=16 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    app.config["DATABASE"] = str(Path(app.config["DATABASE"]).resolve())
    init_db(Path(app.config["DATABASE"]))
    app.teardown_appcontext(close_db)

    @app.after_request
    def security_headers(response):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(413)
    def too_large(_):
        return jsonify(error="La solicitud supera el tamaño permitido."), 413

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/expenses")
    def list_expenses():
        try:
            month = selected_month()
        except ValueError:
            return jsonify(error="Elegí un mes válido con formato AAAA-MM."), 400
        return jsonify([expense_dict(row) for row in expense_rows(month)])

    @app.get("/api/summary")
    def summary():
        try:
            month = selected_month()
        except ValueError:
            return jsonify(error="Elegí un mes válido con formato AAAA-MM."), 400
        grouped = (
            get_db()
            .execute(
                "SELECT category, SUM(amount_cents) AS total_cents, COUNT(*) AS count "
                "FROM expenses WHERE substr(spent_on, 1, 7) = ? "
                "GROUP BY category ORDER BY total_cents DESC, category",
                (month,),
            )
            .fetchall()
        )
        total = sum(row["total_cents"] for row in grouped)
        return jsonify(
            month=month,
            total_cents=total,
            total=total / 100,
            count=sum(row["count"] for row in grouped),
            by_category=[{**dict(row), "total": row["total_cents"] / 100} for row in grouped],
        )

    @app.post("/api/expenses")
    def add_expense():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error="Enviá un objeto JSON válido."), 400
        try:
            cents = amount_to_cents(data.get("amount"))
            category = data.get("category")
            note = data.get("note", "")
            spent_on = data.get("spent_on", date.today().isoformat())
            if not isinstance(category, str) or not 1 <= len(category.strip()) <= 60:
                raise ValueError("La categoría debe tener entre 1 y 60 caracteres.")
            if not isinstance(note, str) or len(note) > 500:
                raise ValueError("La nota debe ser texto de hasta 500 caracteres.")
            if not isinstance(spent_on, str) or not re.fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}", spent_on
            ):
                raise ValueError("La fecha debe tener el formato AAAA-MM-DD.")
            try:
                date.fromisoformat(spent_on)
            except ValueError as exc:
                raise ValueError("La fecha no existe en el calendario.") from exc
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        db = get_db()
        cur = db.execute(
            "INSERT INTO expenses(amount_cents, category, note, spent_on) VALUES (?, ?, ?, ?)",
            (cents, category.strip(), note.strip(), spent_on),
        )
        db.commit()
        row = db.execute("SELECT * FROM expenses WHERE id = ?", (cur.lastrowid,)).fetchone()
        return jsonify(expense_dict(row)), 201

    @app.delete("/api/expenses/<int:expense_id>")
    def delete_expense(expense_id: int):
        db = get_db()
        cur = db.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
        db.commit()
        if cur.rowcount == 0:
            return jsonify(error="El gasto no existe."), 404
        return jsonify(ok=True)

    @app.get("/api/expenses/export")
    def export_expenses():
        try:
            month = selected_month()
        except ValueError:
            return jsonify(error="Elegí un mes válido con formato AAAA-MM."), 400
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["id", "fecha", "categoria", "monto", "nota"])
        for row in expense_rows(month):
            writer.writerow(
                [
                    row["id"],
                    csv_text(row["spent_on"]),
                    csv_text(row["category"]),
                    f"{row['amount_cents'] // 100}.{row['amount_cents'] % 100:02d}",
                    csv_text(row["note"]),
                ]
            )
        return Response(
            "\ufeff" + output.getvalue(),
            content_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="gastos-{month}.csv"'},
        )

    @app.cli.command("seed-demo")
    @click.option("--month", default=None, help="Mes ficticio: AAAA-MM (por defecto, actual).")
    def seed_demo(month):
        """Insert fictional expenses only into an empty database."""
        try:
            month = valid_month(month or date.today().strftime("%Y-%m"))
        except ValueError as exc:
            raise click.ClickException("Elegí un mes válido con formato AAAA-MM.") from exc
        rows = [
            (48550, "Comida", "Compra semanal · ejemplo", f"{month}-03"),
            (12800, "Transporte", "Recarga de transporte · ejemplo", f"{month}-05"),
            (32990, "Servicios", "Internet del hogar · ejemplo", f"{month}-08"),
            (18750, "Comida", "Almuerzo compartido · ejemplo", f"{month}-12"),
            (24500, "Hogar", "Artículos de limpieza · ejemplo", f"{month}-15"),
            (15900, "Salud", "Farmacia · ejemplo", f"{month}-18"),
        ]
        db = get_db()
        try:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]:
                raise click.ClickException(
                    "La demo requiere una base vacía; no se modificó ningún gasto."
                )
            db.executemany(
                "INSERT INTO expenses(amount_cents, category, note, spent_on) VALUES (?, ?, ?, ?)",
                rows,
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        click.echo(f"Demo: 6 gastos ficticios para {month}. Total: 1534.90.")

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=False)
