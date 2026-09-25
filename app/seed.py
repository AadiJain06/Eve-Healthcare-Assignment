"""Seed the database with demo centres, tests, and prices.

Run with:  python -m app.seed
Idempotent: safe to run multiple times.
"""
from __future__ import annotations

from app.database import Base, SessionLocal, engine
from app.models import CentreTest, DiagnosticCentre, DiagnosticTest

SEED_TESTS = [
    ("Complete Blood Count (CBC)", "Measures overall health and detects disorders."),
    ("Lipid Profile", "Measures cholesterol and triglycerides."),
    ("Thyroid Panel (TSH, T3, T4)", "Assesses thyroid function."),
    ("HbA1c", "Average blood sugar over the past 3 months."),
    ("Vitamin D", "Measures 25-hydroxyvitamin D levels."),
]

SEED_CENTRES = [
    ("EVE Diagnostics - Koramangala", "Koramangala, Bengaluru"),
    ("EVE Diagnostics - Andheri", "Andheri West, Mumbai"),
]

# (centre_index, test_index, price)
SEED_PRICES = [
    (0, 0, 350.00),
    (0, 1, 700.00),
    (0, 2, 850.00),
    (1, 0, 400.00),
    (1, 3, 550.00),
    (1, 4, 1200.00),
]


def run() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        tests = []
        for name, desc in SEED_TESTS:
            t = db.query(DiagnosticTest).filter_by(name=name).first()
            if not t:
                t = DiagnosticTest(name=name, description=desc)
                db.add(t)
                db.flush()
            tests.append(t)

        centres = []
        for name, location in SEED_CENTRES:
            c = db.query(DiagnosticCentre).filter_by(name=name).first()
            if not c:
                c = DiagnosticCentre(name=name, location=location)
                db.add(c)
                db.flush()
            centres.append(c)

        for ci, ti, price in SEED_PRICES:
            centre, test = centres[ci], tests[ti]
            exists = (
                db.query(CentreTest)
                .filter_by(centre_id=centre.id, test_id=test.id)
                .first()
            )
            if not exists:
                db.add(CentreTest(centre_id=centre.id, test_id=test.id, price=price))

        db.commit()
        print("Seed complete.")
        print(f"  Centres: {len(centres)}  Tests: {len(tests)}")
    finally:
        db.close()


if __name__ == "__main__":
    run()
