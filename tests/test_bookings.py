"""Booking flow and authorization tests."""
from datetime import datetime, timedelta, timezone


def test_create_booking_derives_amount(client, booking):
    assert booking["status"] == "PENDING"
    assert booking["amount"] == "500.00"


def test_booking_requires_auth(client):
    assert client.post("/bookings", json={}).status_code == 401


def test_booking_invalid_centre_test_404(client, auth_headers):
    appt = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    resp = client.post(
        "/bookings",
        json={"centre_test_id": "nope", "appointment_time": appt},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_booking_past_appointment_rejected(client, auth_headers, booking):
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    resp = client.post(
        "/bookings",
        json={"centre_test_id": booking["centre_test_id"], "appointment_time": past},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_cancel_pending_booking(client, auth_headers, booking):
    resp = client.post(f"/bookings/{booking['id']}/cancel", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "CANCELLED"
    # idempotent second cancel
    resp2 = client.post(f"/bookings/{booking['id']}/cancel", headers=auth_headers)
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "CANCELLED"


def test_cannot_view_others_booking(client, auth_headers, booking):
    # A second user must not see the first user's booking.
    client.post(
        "/auth/signup",
        json={"email": "mallory@example.com", "full_name": "M", "password": "password12"},
    )
    token = client.post(
        "/auth/login", data={"username": "mallory@example.com", "password": "password12"}
    ).json()["access_token"]
    other = {"Authorization": f"Bearer {token}"}
    assert client.get(f"/bookings/{booking['id']}", headers=other).status_code == 404
