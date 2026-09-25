"""Pydantic v2 request/response schemas."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import BookingStatus, PaymentStatus

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    full_name: str
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------------------------------------------------------------------------
# Centres & Tests
# ---------------------------------------------------------------------------


class DiagnosticTestCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1024)


class DiagnosticTestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None


class CentreTestCreate(BaseModel):
    test_id: str
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)


class CentreCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    location: str = Field(min_length=1, max_length=512)


class CentreTestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    test: DiagnosticTestOut
    price: Decimal


class CentreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    location: str


class CentreDetailOut(CentreOut):
    centre_tests: list[CentreTestOut] = []


# ---------------------------------------------------------------------------
# Bookings
# ---------------------------------------------------------------------------


class BookingCreate(BaseModel):
    centre_test_id: str
    appointment_time: datetime

    @field_validator("appointment_time")
    @classmethod
    def must_be_future(cls, v: datetime) -> datetime:
        from datetime import timezone

        now = datetime.now(timezone.utc)
        compare = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        if compare <= now:
            raise ValueError("appointment_time must be in the future")
        return v


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    centre_test_id: str
    appointment_time: datetime
    amount: Decimal
    status: BookingStatus
    created_at: datetime


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------


class PaymentCreate(BaseModel):
    booking_id: str


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    booking_id: str
    amount: Decimal
    status: PaymentStatus
    provider_reference: str
    created_at: datetime


class WebhookPayload(BaseModel):
    """Payload sent by the simulated payment provider."""

    event_id: str = Field(min_length=1)
    provider_reference: str = Field(min_length=1)
    status: PaymentStatus
    signature: str | None = None

    @field_validator("status")
    @classmethod
    def not_pending(cls, v: PaymentStatus) -> PaymentStatus:
        if v == PaymentStatus.PENDING:
            raise ValueError("webhook status must be SUCCESS or FAILED")
        return v


# ---------------------------------------------------------------------------
# Generic
# ---------------------------------------------------------------------------


class Page(BaseModel):
    total: int
    limit: int
    offset: int
    items: list
