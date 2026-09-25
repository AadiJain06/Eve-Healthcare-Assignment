"""Pytest fixtures: isolated in-memory SQLite DB and TestClient."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


@pytest.fixture
def db_session():
    # In-memory SQLite shared across connections within the test.
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers(client):
    """Register a user and return Authorization headers."""
    email = "alice@example.com"
    password = "supersecret1"
    client.post(
        "/auth/signup",
        json={"email": email, "full_name": "Alice", "password": password},
    )
    resp = client.post(
        "/auth/login", data={"username": email, "password": password}
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def booking(client, auth_headers):
    """Create a centre, test, offering and a PENDING booking. Returns its id."""
    from datetime import datetime, timedelta, timezone

    test_id = client.post(
        "/tests", json={"name": "CBC", "description": "d"}, headers=auth_headers
    ).json()["id"]
    centre_id = client.post(
        "/centres", json={"name": "C1", "location": "L1"}, headers=auth_headers
    ).json()["id"]
    centre_test_id = client.post(
        f"/centres/{centre_id}/tests",
        json={"test_id": test_id, "price": "500.00"},
        headers=auth_headers,
    ).json()["id"]

    appt = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    resp = client.post(
        "/bookings",
        json={"centre_test_id": centre_test_id, "appointment_time": appt},
        headers=auth_headers,
    )
    return resp.json()
