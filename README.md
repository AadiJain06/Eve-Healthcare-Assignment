# EVE Diagnostics — Booking & Payments Service

A small backend service for booking diagnostic tests and processing **simulated**
payments. Built with **FastAPI + SQLAlchemy 2.0 + PostgreSQL**, JWT auth, and an
**idempotent** payment webhook.

Interactive API docs (Swagger UI) are served at **`/docs`** and ReDoc at **`/redoc`**.

---

## Table of contents

- [Tech stack](#tech-stack)
- [Running locally](#running-locally)
- [Running with Docker](#running-with-docker)
- [Environment variables](#environment-variables)
- [Database / schema design](#database--schema-design)
- [API endpoints & examples](#api-endpoints--examples)
- [Payment & webhook design (idempotency)](#payment--webhook-design-idempotency)
- [Edge cases handled](#edge-cases-handled)
- [Tests](#tests)
- [Assumptions](#assumptions)
- [What I'd improve with more time](#what-id-improve-with-more-time)

---

## Tech stack

| Concern            | Choice                                             |
| ------------------ | -------------------------------------------------- |
| Framework          | FastAPI (async, automatic OpenAPI/Swagger)         |
| ORM                | SQLAlchemy 2.0 (typed `Mapped[...]` models)        |
| Database           | PostgreSQL (psycopg3 driver); SQLite for tests     |
| Auth               | JWT (python-jose) + bcrypt password hashing        |
| Validation         | Pydantic v2                                        |
| Logging            | Structured JSON logs (python-json-logger)          |
| Tests              | pytest + FastAPI TestClient                        |
| Packaging          | Docker + docker-compose                            |

---

## Running locally

Prerequisites: Python 3.11+ and a PostgreSQL instance (or use Docker below).

```bash
# 1. Create a virtual environment and install deps
python -m venv .venv
source .venv/bin/activate        # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env             # then edit DATABASE_URL, SECRET_KEY, WEBHOOK_SECRET

# 3. (Optional) seed demo centres, tests, and prices
python -m app.seed

# 4. Run the API
uvicorn app.main:app --reload
```

Open http://localhost:8000/docs.

> Tables are auto-created on startup via `Base.metadata.create_all`. In a real
> deployment this would be replaced by Alembic migrations (see
> [improvements](#what-id-improve-with-more-time)).

---

## Running with Docker

Brings up PostgreSQL + the API, waits for the DB to be healthy, seeds demo data,
then starts the server:

```bash
docker compose up --build
```

- API: http://localhost:8000/docs
- PostgreSQL exposed on `localhost:5432` (user/pass/db: `eve`/`eve`/`eve_diagnostics`)

---

## Environment variables

See `.env.example`. Key settings:

| Variable                      | Description                                           | Default                |
| ----------------------------- | ----------------------------------------------------- | ---------------------- |
| `DATABASE_URL`                | SQLAlchemy URL (`postgresql+psycopg://…`)             | local Postgres         |
| `SECRET_KEY`                  | JWT signing secret                                    | dev placeholder        |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT lifetime                                          | `60`                   |
| `WEBHOOK_SECRET`              | Shared secret for HMAC webhook signatures             | dev placeholder        |
| `PAYMENT_SUCCESS_RATE`        | Probability (0.0–1.0) a simulated payment succeeds    | `1.0`                  |
| `DEBUG`                       | Enables the dev-only webhook signing helper           | `true`                 |

---

## Database / schema design

```
users                     diagnostic_centres        diagnostic_tests
─────                     ──────────────────        ────────────────
id (PK, uuid)             id (PK, uuid)             id (PK, uuid)
email (unique)            name                      name (unique)
full_name                 location                  description
hashed_password
                                   │                        │
                                   └────────┬───────────────┘
                                            ▼
                                    centre_tests            ← junction, carries price
                                    ────────────
                                    id (PK, uuid)
                                    centre_id (FK)
                                    test_id   (FK)
                                    price
                                    UNIQUE(centre_id, test_id)

bookings                              payments                    webhook_events
────────                              ────────                    ──────────────
id (PK, uuid)                         id (PK, uuid)               event_id (PK)   ← idempotency key
user_id (FK → users)                  booking_id (FK → bookings)  received_at
centre_test_id (FK → centre_tests)    amount
appointment_time                      status (PENDING/SUCCESS/FAILED)
amount                                provider_reference (unique)
status (PENDING/CONFIRMED/FAILED/CANCELLED)
```

Design notes:

- **`centre_tests` is a junction table that carries `price`.** The same test can
  be offered by many centres at different prices, so price belongs on the
  centre-test relationship, not on the test itself. A `UNIQUE(centre_id, test_id)`
  constraint prevents duplicate offerings.
- **A booking references a `centre_test`**, which transitively gives us both the
  centre and the test. The booking `amount` is **copied from the catalogue price
  at booking time**, so later price changes don't rewrite historical bookings.
- **`payments.provider_reference` is unique**, so the same provider transaction
  can never be recorded twice.
- **`webhook_events.event_id` is the primary key** — this is the core of webhook
  idempotency (see below).
- All IDs are UUID strings for opacity and to avoid enumerable integer IDs.

---

## API endpoints & examples

Base URL: `http://localhost:8000`

### Auth

| Method | Path            | Auth | Description                     |
| ------ | --------------- | ---- | ------------------------------- |
| POST   | `/auth/signup`  | –    | Create a user                   |
| POST   | `/auth/login`   | –    | Get a JWT (form-encoded)        |
| GET    | `/auth/me`      | ✅   | Current user                    |

```bash
# Signup
curl -X POST localhost:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","full_name":"Alice","password":"supersecret1"}'

# Login (OAuth2 password form → returns access_token)
curl -X POST localhost:8000/auth/login \
  -d "username=alice@example.com&password=supersecret1"
# → {"access_token":"<JWT>","token_type":"bearer"}

TOKEN=<JWT>
```

### Centres & tests

| Method | Path                        | Auth | Description                        |
| ------ | --------------------------- | ---- | ---------------------------------- |
| POST   | `/tests`                    | ✅   | Create a test in the catalogue     |
| GET    | `/tests`                    | –    | List tests (paginated)             |
| POST   | `/centres`                  | ✅   | Create a centre                    |
| GET    | `/centres`                  | –    | List centres (paginated)           |
| GET    | `/centres/{id}`             | –    | Centre detail incl. offered tests  |
| POST   | `/centres/{id}/tests`       | ✅   | Attach a test + price to a centre  |
| GET    | `/centres/{id}/tests`       | –    | List a centre's test offerings     |

```bash
# Create a test and a centre, then attach the test with a price
TEST_ID=$(curl -s -X POST localhost:8000/tests -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"name":"CBC"}' | jq -r .id)

CENTRE_ID=$(curl -s -X POST localhost:8000/centres -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"name":"EVE Koramangala","location":"Bengaluru"}' | jq -r .id)

CENTRE_TEST_ID=$(curl -s -X POST localhost:8000/centres/$CENTRE_ID/tests \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"test_id\":\"$TEST_ID\",\"price\":\"500.00\"}" | jq -r .id)
```

### Bookings

| Method | Path                        | Auth | Description                          |
| ------ | --------------------------- | ---- | ------------------------------------ |
| POST   | `/bookings`                 | ✅   | Create a booking (status `PENDING`)  |
| GET    | `/bookings`                 | ✅   | List **your** bookings (paginated)   |
| GET    | `/bookings/{id}`            | ✅   | Get one of your bookings             |
| POST   | `/bookings/{id}/cancel`     | ✅   | Cancel a `PENDING` booking           |

```bash
BOOKING_ID=$(curl -s -X POST localhost:8000/bookings \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"centre_test_id\":\"$CENTRE_TEST_ID\",\"appointment_time\":\"2030-01-01T10:00:00Z\"}" | jq -r .id)
```

### Payments

| Method | Path                   | Auth | Description                                   |
| ------ | ---------------------- | ---- | --------------------------------------------- |
| POST   | `/payments/`           | ✅   | Simulate a payment for a booking              |
| POST   | `/payments/webhook/`   | –    | Provider webhook (HMAC-signed, idempotent)    |
| GET    | `/payments/webhook/sign` | –  | **DEBUG only** helper to compute a signature  |

```bash
# Simulate payment → SUCCESS confirms the booking, FAILED marks it failed
curl -s -X POST localhost:8000/payments/ -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d "{\"booking_id\":\"$BOOKING_ID\"}"
# → {"id":"…","status":"SUCCESS","provider_reference":"<ref>", ...}

# Simulate a provider webhook. First compute the signature (DEBUG helper):
curl -s "localhost:8000/payments/webhook/sign?event_id=evt_1&provider_reference=<ref>&status_value=SUCCESS"
# → {"signature":"<sig>", ...}

# Then post the webhook. Re-posting the same event_id is a no-op ("ignored").
curl -s -X POST localhost:8000/payments/webhook/ -H "Content-Type: application/json" \
  -d '{"event_id":"evt_1","provider_reference":"<ref>","status":"SUCCESS","signature":"<sig>"}'
```

---

## Payment & webhook design (idempotency)

The payment logic lives in `app/services/payment_service.py`, isolated from the
HTTP layer so the state machine is directly unit-testable.

**`POST /payments/`** — creates a `Payment`, simulates the provider's decision
(`PAYMENT_SUCCESS_RATE`), and moves the booking to `CONFIRMED` or `FAILED`.
Paying an already-`CONFIRMED` or `CANCELLED` booking is rejected (`409`) so we
never double-charge.

**`POST /payments/webhook/`** — accepts asynchronous status updates. Idempotency
is guaranteed at the database level:

1. **Signature check** — the payload is verified with an HMAC-SHA256 signature
   over `event_id:provider_reference:status` using `WEBHOOK_SECRET`. Invalid or
   missing signatures return `401`.
2. **Event claim** — we insert the `event_id` into `webhook_events` (its primary
   key). If the row already exists, the `IntegrityError` tells us this event was
   already processed, so we return `{"status":"ignored"}` **without touching any
   booking or payment**. This makes redelivery safe.
3. **Apply update** — we locate the payment by `provider_reference` and update
   the payment/booking status only if it actually changes.

Because the idempotency key is enforced by a unique/PK constraint (not an
in-memory set), it holds even across process restarts and concurrent workers.

---

## Edge cases handled

- **Invalid requests** → `422` via Pydantic (e.g. short password, past
  `appointment_time`, non-positive price, webhook `status` of `PENDING`).
- **Repeated webhook events** → deduplicated on `event_id`; no duplicate
  payments/bookings or corrupted state.
- **Invalid / unknown IDs** → `404` (booking, centre, test, payment reference).
- **Failed payments** → booking transitions to `FAILED`.
- **Unauthorized access** → endpoints require a valid JWT; a user requesting
  another user's booking/payment gets `404` (existence is not leaked).
- **Duplicate resources** → duplicate signup email (`409`), duplicate test name
  (`409`), duplicate centre-test offering (`409`).
- **Double payment** → paying a confirmed/cancelled booking returns `409`.
- **Unhandled errors** → generic `500` handler returns a safe message and logs
  the stack trace.

---

## Tests

```bash
pytest
```

Tests run against an in-memory SQLite database (no external services needed) and
cover auth, catalogue management, the booking lifecycle, payment success/failure,
authorization boundaries, and — most importantly — **webhook idempotency**
(`processed` then `ignored` on redelivery) and signature verification.

---

## Assumptions

- **No admin/role model yet.** Any authenticated user can create catalogue
  entries (tests, centres, offerings). In production these would be
  admin-only; the auth dependency is already in place to gate them.
- **Payments are fully simulated.** No real gateway; outcome is controlled by
  `PAYMENT_SUCCESS_RATE`. The webhook models an async provider callback.
- **The webhook signing helper (`/payments/webhook/sign`) is a dev convenience**
  only and is disabled when `DEBUG=false`. A real provider computes signatures
  itself.
- **Booking amount is snapshotted** from the catalogue price at booking time.
- **Schema is created at startup** for simplicity; production would use Alembic.
- **One appointment slot is not capacity-checked** — overlapping bookings for the
  same centre/time are allowed (see improvements).

---

## What I'd improve with more time

- **Alembic migrations** instead of `create_all`, for versioned schema changes.
- **Role-based access control** (admin vs patient) for catalogue management.
- **Concurrency hardening**: row-level locking (`SELECT … FOR UPDATE`) around
  payment settlement, and a webhook `INSERT … ON CONFLICT DO NOTHING` to reduce
  the claim to a single round-trip.
- **Retry/outbox handling** for webhook processing and background settlement via
  Celery, plus a dead-letter path for un-matchable events.
- **Redis caching** for the read-heavy centre/test catalogue and **rate limiting**
  on auth and webhook endpoints.
- **Appointment slot capacity** and double-booking prevention.
- **Refresh tokens / token revocation** and stronger password policy.
- **Richer observability**: correlation IDs propagated into all logs, metrics,
  and tracing.
```
