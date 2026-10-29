from __future__ import annotations

import csv
import io
import json
import sqlite3
from pathlib import Path

import pytest

from app import amount_to_cents, create_app


@pytest.fixture()
def client(tmp_path: Path):
    db_path = tmp_path / "test.db"
    application = create_app(db_path=db_path)
    application.config.update(TESTING=True)
    with application.test_client() as client:
        yield client


def test_add_and_list_expense(client):
    res = client.post(
        "/api/expenses",
        json={"amount": 12.5, "category": "comida", "note": "almuerzo", "spent_on": "2026-09-18"},
    )
    assert res.status_code == 201
    body = res.get_json()
    assert body["category"] == "comida"
    listed = client.get("/api/expenses?month=2026-09").get_json()
    assert len(listed) == 1
    assert listed[0]["amount"] == 12.5


def test_summary_by_category(client):
    client.post(
        "/api/expenses", json={"amount": 10, "category": "comida", "spent_on": "2026-09-01"}
    )
    client.post("/api/expenses", json={"amount": 5, "category": "comida", "spent_on": "2026-09-02"})
    client.post(
        "/api/expenses", json={"amount": 20, "category": "transporte", "spent_on": "2026-09-03"}
    )
    summary = client.get("/api/summary?month=2026-09").get_json()
    assert summary["total"] == 35
    cats = {c["category"]: c["total"] for c in summary["by_category"]}
    assert cats["comida"] == 15
    assert cats["transporte"] == 20


def test_rejects_invalid_amount(client):
    res = client.post(
        "/api/expenses", json={"amount": -1, "category": "otros", "spent_on": "2026-09-18"}
    )
    assert res.status_code == 400


def test_delete_expense(client):
    created = client.post(
        "/api/expenses",
        json={"amount": 3, "category": "hogar", "spent_on": "2026-09-18"},
    ).get_json()
    res = client.delete(f"/api/expenses/{created['id']}")
    assert res.status_code == 200
    listed = client.get("/api/expenses?month=2026-09").get_json()
    assert listed == []


def test_index_renders(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"Registro de gastos" in res.data
    assert b"app.js" in res.data


@pytest.mark.parametrize(
    "amount",
    [
        0,
        -1,
        True,
        None,
        {},
        [],
        "NaN",
        "Infinity",
        "-Infinity",
        "abc",
        "0.001",
        "1.234",
        "1000000000",
        "1e9999",
    ],
)
def test_invalid_amount_never_writes(client, amount):
    response = client.post("/api/expenses", json={"amount": amount, "category": "Otros"})
    assert response.status_code == 400
    assert response.get_json()["error"]
    assert client.get("/api/expenses").get_json() == []


@pytest.mark.parametrize(
    "amount,cents",
    [("0.01", 1), ("12.30", 1230), (0.1, 10), ("1.2300", 123), ("999999999.99", 99999999999)],
)
def test_exact_amount_conversion(amount, cents):
    assert amount_to_cents(amount) == cents


def test_money_totals_do_not_accumulate_float_errors(client):
    for amount in ["0.10", "0.20"]:
        assert (
            client.post(
                "/api/expenses",
                json={"amount": amount, "category": "Comida", "spent_on": "2026-10-01"},
            ).status_code
            == 201
        )
    summary = client.get("/api/summary?month=2026-10").get_json()
    assert summary["total_cents"] == 30
    assert summary["by_category"][0]["total_cents"] == 30
    assert summary["count"] == 2


@pytest.mark.parametrize(
    "spent_on",
    ["2026-02-29", "2026-13-01", "2026-04-31", "20261001", "2026-1-01", None, 123, "0000-01-01"],
)
def test_invalid_date_never_writes(client, spent_on):
    response = client.post(
        "/api/expenses", json={"amount": "10", "category": "Otros", "spent_on": spent_on}
    )
    assert response.status_code == 400


def test_accepts_leap_day_and_trims_text(client):
    response = client.post(
        "/api/expenses",
        json={"amount": "10", "category": " Hogar ", "note": " Ejemplo ", "spent_on": "2028-02-29"},
    )
    assert response.status_code == 201
    assert response.get_json()["category"] == "Hogar"
    assert response.get_json()["note"] == "Ejemplo"


@pytest.mark.parametrize("payload", [[], "text", 5, None])
def test_json_must_be_an_object(client, payload):
    response = client.post(
        "/api/expenses", data=json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    "changes",
    [
        {"category": ""},
        {"category": " "},
        {"category": "x" * 61},
        {"category": []},
        {"note": "x" * 501},
        {"note": False},
    ],
)
def test_text_validation(client, changes):
    response = client.post("/api/expenses", json={"amount": "1", "category": "Hogar", **changes})
    assert response.status_code == 400


@pytest.mark.parametrize(
    "month", ["2026-00", "2026-13", "2026-1", "0000-01", "", "2026-10-01", "x' OR 1=1--"]
)
def test_all_month_endpoints_validate_consistently(client, month):
    for endpoint in ["/api/expenses", "/api/summary", "/api/expenses/export"]:
        response = client.get(endpoint, query_string={"month": month})
        assert response.status_code == 400


def test_month_filter_and_empty_summary(client):
    client.post(
        "/api/expenses", json={"amount": "9.99", "category": "Hogar", "spent_on": "2026-09-30"}
    )
    assert client.get("/api/expenses?month=2026-10").get_json() == []
    summary = client.get("/api/summary?month=2026-10").get_json()
    assert summary["total_cents"] == summary["count"] == 0
    assert summary["by_category"] == []


def test_export_exact_amounts_unicode_and_spreadsheet_safety(client):
    client.post(
        "/api/expenses",
        json={
            "amount": "0.10",
            "category": "=1+1",
            "note": '@SUM(A1:A2), "ejemplo" ñ',
            "spent_on": "2026-10-02",
        },
    )
    client.post(
        "/api/expenses", json={"amount": "99", "category": "Otro mes", "spent_on": "2026-09-02"}
    )
    response = client.get("/api/expenses/export?month=2026-10")
    assert response.status_code == 200
    assert "attachment" in response.headers["Content-Disposition"]
    assert "gastos-2026-10.csv" in response.headers["Content-Disposition"]
    rows = list(csv.DictReader(io.StringIO(response.data.decode("utf-8-sig"))))
    assert len(rows) == 1
    assert rows[0]["monto"] == "0.10"
    assert rows[0]["categoria"] == "'=1+1"
    assert rows[0]["nota"] == '\'@SUM(A1:A2), "ejemplo" ñ'


def test_delete_missing_and_repeated(client):
    assert client.delete("/api/expenses/999").status_code == 404
    expense = client.post("/api/expenses", json={"amount": "1", "category": "Otros"}).get_json()
    assert client.delete(f"/api/expenses/{expense['id']}").status_code == 200
    assert client.delete(f"/api/expenses/{expense['id']}").status_code == 404


def test_multiple_app_instances_are_independent_and_persistent(tmp_path):
    first_path = tmp_path / "first.db"
    first = create_app(first_path).test_client()
    second = create_app(tmp_path / "second.db").test_client()
    first.post(
        "/api/expenses", json={"amount": "1.23", "category": "Primero", "spent_on": "2026-10-01"}
    )
    second.post(
        "/api/expenses", json={"amount": "4.56", "category": "Segundo", "spent_on": "2026-10-01"}
    )
    assert first.get("/api/summary?month=2026-10").get_json()["total_cents"] == 123
    assert second.get("/api/summary?month=2026-10").get_json()["total_cents"] == 456
    restarted = create_app(first_path).test_client()
    assert restarted.get("/api/expenses?month=2026-10").get_json()[0]["category"] == "Primero"


def legacy_database(path, amount):
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, amount REAL NOT NULL, category TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', spent_on TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO expenses VALUES (7, ?, 'Hogar', 'Legado', '2026-10-01')", (amount,)
        )


def test_legacy_database_is_backed_up_and_migrated_once(tmp_path):
    path = tmp_path / "legacy.db"
    legacy_database(path, 12.345)
    client = create_app(path).test_client()
    expense = client.get("/api/expenses?month=2026-10").get_json()[0]
    assert expense["id"] == 7
    assert expense["amount_cents"] == 1235
    backups = list(tmp_path.glob("legacy.db.pre-cents-*.bak"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as conn:
        assert conn.execute("SELECT amount FROM expenses").fetchone()[0] == 12.345
    create_app(path)
    assert len(list(tmp_path.glob("legacy.db.pre-cents-*.bak"))) == 1
    created = client.post("/api/expenses", json={"amount": "1", "category": "Nuevo"}).get_json()
    assert created["id"] > 7


def test_invalid_legacy_amount_leaves_original_intact(tmp_path):
    path = tmp_path / "legacy.db"
    legacy_database(path, float("inf"))
    with pytest.raises(ValueError):
        create_app(path)
    with sqlite3.connect(path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(expenses)")}
        assert "amount" in columns and "amount_cents" not in columns
        assert conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] == 1


def test_demo_seed_is_safe_and_reproducible(tmp_path):
    app = create_app(tmp_path / "demo.db")
    runner = app.test_cli_runner()
    result = runner.invoke(args=["seed-demo", "--month", "2026-10"])
    assert result.exit_code == 0
    client = app.test_client()
    assert client.get("/api/summary?month=2026-10").get_json()["total_cents"] == 153490
    assert len(client.get("/api/expenses?month=2026-10").get_json()) == 6
    repeated = runner.invoke(args=["seed-demo", "--month", "2026-10"])
    assert repeated.exit_code != 0
    assert len(client.get("/api/expenses?month=2026-10").get_json()) == 6


def test_security_headers_and_payload_limit(client):
    response = client.get("/")
    assert "script-src 'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert client.get("/api/expenses").headers["Cache-Control"] == "no-store"
    response = client.post("/api/expenses", data="x" * 17000, content_type="application/json")
    assert response.status_code == 413
    assert response.is_json
