"""Payment and webhook tests, including idempotency."""
import uuid

from app.config import settings
from app.services.payment_service import compute_signature


def _pay(client, auth_headers, booking_id):
    return client.post(
        "/payments/", json={"booking_id": booking_id}, headers=auth_headers
    )


def test_successful_payment_confirms_booking(client, auth_headers, booking):
    settings.payment_success_rate = 1.0
    resp = _pay(client, auth_headers, booking["id"])
    assert resp.status_code == 201
    assert resp.json()["status"] == "SUCCESS"

    b = client.get(f"/bookings/{booking['id']}", headers=auth_headers).json()
    assert b["status"] == "CONFIRMED"


def test_failed_payment_marks_booking_failed(client, auth_headers, booking):
    settings.payment_success_rate = 0.0
    resp = _pay(client, auth_headers, booking["id"])
    assert resp.status_code == 201
    assert resp.json()["status"] == "FAILED"

    b = client.get(f"/bookings/{booking['id']}", headers=auth_headers).json()
    assert b["status"] == "FAILED"
    settings.payment_success_rate = 1.0


def test_cannot_pay_others_booking(client, auth_headers, booking):
    client.post(
        "/auth/signup",
        json={"email": "eve@example.com", "full_name": "E", "password": "password12"},
    )
    token = client.post(
        "/auth/login", data={"username": "eve@example.com", "password": "password12"}
    ).json()["access_token"]
    other = {"Authorization": f"Bearer {token}"}
    assert _pay(client, other, booking["id"]).status_code == 404


def test_double_pay_confirmed_booking_rejected(client, auth_headers, booking):
    settings.payment_success_rate = 1.0
    assert _pay(client, auth_headers, booking["id"]).status_code == 201
    # Second attempt on an already-confirmed booking must be rejected.
    assert _pay(client, auth_headers, booking["id"]).status_code == 409


def test_webhook_idempotent(client, auth_headers, booking):
    settings.payment_success_rate = 0.0  # start as failed
    payment = _pay(client, auth_headers, booking["id"]).json()
    provider_ref = payment["provider_reference"]

    event_id = str(uuid.uuid4())
    status_value = "SUCCESS"
    signature = compute_signature(provider_ref, event_id, status_value)
    body = {
        "event_id": event_id,
        "provider_reference": provider_ref,
        "status": status_value,
        "signature": signature,
    }

    first = client.post("/payments/webhook/", json=body)
    assert first.status_code == 200
    assert first.json()["status"] == "processed"

    # Same event again -> ignored, no state corruption.
    second = client.post("/payments/webhook/", json=body)
    assert second.status_code == 200
    assert second.json()["status"] == "ignored"

    b = client.get(f"/bookings/{booking['id']}", headers=auth_headers).json()
    assert b["status"] == "CONFIRMED"
    settings.payment_success_rate = 1.0


def test_webhook_invalid_signature_rejected(client, auth_headers, booking):
    payment = _pay(client, auth_headers, booking["id"]).json()
    body = {
        "event_id": str(uuid.uuid4()),
        "provider_reference": payment["provider_reference"],
        "status": "SUCCESS",
        "signature": "bogus",
    }
    assert client.post("/payments/webhook/", json=body).status_code == 401


def test_webhook_unknown_reference_404(client):
    event_id = str(uuid.uuid4())
    signature = compute_signature("missing-ref", event_id, "SUCCESS")
    body = {
        "event_id": event_id,
        "provider_reference": "missing-ref",
        "status": "SUCCESS",
        "signature": signature,
    }
    assert client.post("/payments/webhook/", json=body).status_code == 404


def test_webhook_pending_status_rejected(client):
    body = {
        "event_id": "e1",
        "provider_reference": "r1",
        "status": "PENDING",
        "signature": "x",
    }
    assert client.post("/payments/webhook/", json=body).status_code == 422
