"""Simulated payment endpoint and idempotent payment webhook."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Booking, User
from app.schemas import PaymentCreate, PaymentOut, WebhookPayload
from app.config import settings
from app.services.payment_service import (
    PaymentError,
    compute_signature,
    initiate_payment,
    process_webhook,
)

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
def create_payment(
    payload: PaymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaymentOut:
    booking = db.get(Booking, payload.booking_id)
    # 404 (not 403) when the booking belongs to another user, to avoid leaking.
    if not booking or booking.user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")

    try:
        payment = initiate_payment(db, booking)
    except PaymentError as exc:
        raise HTTPException(exc.status_code, exc.detail)
    return PaymentOut.model_validate(payment)


@router.post("/webhook/")
def payment_webhook(
    payload: WebhookPayload,
    db: Session = Depends(get_db),
) -> dict:
    """Accept a payment-status update from the simulated provider.

    Public endpoint (no user auth); authenticity is verified via the HMAC
    signature. Idempotent on `event_id`.
    """
    try:
        return process_webhook(
            db=db,
            event_id=payload.event_id,
            provider_reference=payload.provider_reference,
            status=payload.status,
            signature=payload.signature,
        )
    except PaymentError as exc:
        raise HTTPException(exc.status_code, exc.detail)


@router.get("/webhook/sign", tags=["payments"])
def sign_webhook(
    event_id: str,
    provider_reference: str,
    status_value: str,
) -> dict:
    """Dev helper: compute the HMAC signature the provider would send.

    Only available when DEBUG is enabled. Lets you test the webhook without a
    real provider. Use the returned signature in the /payments/webhook/ body.
    """
    if not settings.debug:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    signature = compute_signature(provider_reference, event_id, status_value)
    return {
        "event_id": event_id,
        "provider_reference": provider_reference,
        "status": status_value,
        "signature": signature,
    }
