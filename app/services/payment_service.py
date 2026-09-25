"""Payment processing and idempotent webhook handling.

Isolated from the HTTP layer so the state machine can be unit-tested directly.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import random
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    Booking,
    BookingStatus,
    Payment,
    PaymentStatus,
    WebhookEvent,
)

logger = logging.getLogger("eve.payments")


class PaymentError(Exception):
    """Domain error carrying an HTTP-friendly status code."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _booking_status_for(payment_status: PaymentStatus) -> BookingStatus:
    return (
        BookingStatus.CONFIRMED
        if payment_status == PaymentStatus.SUCCESS
        else BookingStatus.FAILED
    )


def compute_signature(provider_reference: str, event_id: str, status: str) -> str:
    """HMAC-SHA256 signature the simulated provider would send with a webhook."""
    message = f"{event_id}:{provider_reference}:{status}".encode()
    return hmac.new(
        settings.webhook_secret.encode(), message, hashlib.sha256
    ).hexdigest()


def initiate_payment(db: Session, booking: Booking) -> Payment:
    """Create and settle a simulated payment for a booking.

    Only PENDING bookings can be paid. Reusing this for an already-confirmed
    booking is rejected so we never double-charge.
    """
    if booking.status == BookingStatus.CONFIRMED:
        raise PaymentError(409, "Booking is already paid and confirmed")
    if booking.status == BookingStatus.CANCELLED:
        raise PaymentError(409, "Cannot pay for a cancelled booking")

    provider_reference = uuid.uuid4().hex
    # Simulate the provider's decision.
    succeeded = random.random() < settings.payment_success_rate
    payment_status = PaymentStatus.SUCCESS if succeeded else PaymentStatus.FAILED

    payment = Payment(
        booking_id=booking.id,
        amount=booking.amount,
        status=payment_status,
        provider_reference=provider_reference,
    )
    booking.status = _booking_status_for(payment_status)

    db.add(payment)
    db.commit()
    db.refresh(payment)
    logger.info(
        "payment_processed",
        extra={
            "booking_id": booking.id,
            "payment_id": payment.id,
            "status": payment_status.value,
        },
    )
    return payment


def process_webhook(
    db: Session,
    event_id: str,
    provider_reference: str,
    status: PaymentStatus,
    signature: str | None,
) -> dict:
    """Idempotently apply a payment-status update from the provider.

    Idempotency: the event_id is the primary key of webhook_events. We attempt
    to claim it first; a duplicate insert means the event was already handled,
    so we return without mutating any booking/payment state again.
    """
    # 1. Verify signature (skip only if no secret configured).
    if settings.webhook_secret:
        expected = compute_signature(provider_reference, event_id, status.value)
        if not signature or not hmac.compare_digest(expected, signature):
            raise PaymentError(401, "Invalid webhook signature")

    # 2. Claim the event id (idempotency guard).
    db.add(WebhookEvent(event_id=event_id))
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        logger.info("webhook_duplicate_ignored", extra={"event_id": event_id})
        return {"status": "ignored", "reason": "duplicate_event"}

    # 3. Locate the payment by provider reference.
    payment = (
        db.query(Payment)
        .filter(Payment.provider_reference == provider_reference)
        .first()
    )
    if not payment:
        # Roll back the claimed event so a corrected retry can be processed.
        db.rollback()
        raise PaymentError(404, "No payment found for provider_reference")

    booking = db.get(Booking, payment.booking_id)

    # 4. Apply the update only if it actually changes state.
    if payment.status != status:
        payment.status = status
        if booking and booking.status not in (
            BookingStatus.CANCELLED,
        ):
            booking.status = _booking_status_for(status)

    db.commit()
    logger.info(
        "webhook_processed",
        extra={
            "event_id": event_id,
            "provider_reference": provider_reference,
            "status": status.value,
        },
    )
    return {"status": "processed", "payment_id": payment.id}
