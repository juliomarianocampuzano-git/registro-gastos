from __future__ import annotations

from pathlib import Path

import pytest

from app import create_app


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
    client.post("/api/expenses", json={"amount": 10, "category": "comida", "spent_on": "2026-09-01"})
    client.post("/api/expenses", json={"amount": 5, "category": "comida", "spent_on": "2026-09-02"})
    client.post("/api/expenses", json={"amount": 20, "category": "transporte", "spent_on": "2026-09-03"})
    summary = client.get("/api/summary?month=2026-09").get_json()
    assert summary["total"] == 35
    cats = {c["category"]: c["total"] for c in summary["by_category"]}
    assert cats["comida"] == 15
    assert cats["transporte"] == 20


def test_rejects_invalid_amount(client):
    res = client.post("/api/expenses", json={"amount": -1, "category": "otros", "spent_on": "2026-09-18"})
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
    assert b"Gastos del mes" in res.data
    assert b"app.js" in res.data
