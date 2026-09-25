"""Booking endpoints. All require authentication and enforce ownership."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import Pagination, get_current_user, pagination_params
from app.models import Booking, BookingStatus, CentreTest, User
from app.schemas import BookingCreate, BookingOut, Page

router = APIRouter(prefix="/bookings", tags=["bookings"])
logger = logging.getLogger("eve.bookings")


def _get_owned_booking(booking_id: str, user: User, db: Session) -> Booking:
    """Fetch a booking and ensure it belongs to the current user.

    Returns 404 (not 403) when the booking belongs to someone else, so we do
    not leak the existence of other users' bookings.
    """
    booking = db.get(Booking, booking_id)
    if not booking or booking.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")
    return booking


@router.post("", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
def create_booking(
    payload: BookingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Booking:
    centre_test = db.get(CentreTest, payload.centre_test_id)
    if not centre_test:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Diagnostic test offering not found"
        )

    # Amount is derived from the catalogue price, never trusted from the client.
    booking = Booking(
        user_id=current_user.id,
        centre_test_id=centre_test.id,
        appointment_time=payload.appointment_time,
        amount=centre_test.price,
        status=BookingStatus.PENDING,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    logger.info(
        "booking_created",
        extra={"booking_id": booking.id, "user_id": current_user.id},
    )
    return booking


@router.get("", response_model=Page)
def list_my_bookings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: Pagination = Depends(pagination_params),
) -> Page:
    q = (
        db.query(Booking)
        .filter(Booking.user_id == current_user.id)
        .order_by(Booking.created_at.desc())
    )
    total = q.count()
    items = q.offset(page.offset).limit(page.limit).all()
    return Page(
        total=total,
        limit=page.limit,
        offset=page.offset,
        items=[BookingOut.model_validate(b) for b in items],
    )


@router.get("/{booking_id}", response_model=BookingOut)
def get_booking(
    booking_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Booking:
    return _get_owned_booking(booking_id, current_user, db)


@router.post("/{booking_id}/cancel", response_model=BookingOut)
def cancel_booking(
    booking_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Booking:
    booking = _get_owned_booking(booking_id, current_user, db)

    if booking.status == BookingStatus.CANCELLED:
        return booking  # idempotent: already cancelled
    if booking.status == BookingStatus.CONFIRMED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Confirmed (paid) bookings cannot be cancelled here",
        )
    if booking.status == BookingStatus.FAILED:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Failed bookings cannot be cancelled"
        )

    booking.status = BookingStatus.CANCELLED
    db.commit()
    db.refresh(booking)
    logger.info("booking_cancelled", extra={"booking_id": booking.id})
    return booking
