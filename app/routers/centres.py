"""Diagnostic centres and tests: management and retrieval."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import Pagination, get_current_user, pagination_params
from app.models import CentreTest, DiagnosticCentre, DiagnosticTest, User
from app.schemas import (
    CentreCreate,
    CentreDetailOut,
    CentreOut,
    CentreTestCreate,
    CentreTestOut,
    DiagnosticTestCreate,
    DiagnosticTestOut,
    Page,
)

router = APIRouter(tags=["centres & tests"])


# ---------------------------------------------------------------------------
# Diagnostic tests (catalogue)
# ---------------------------------------------------------------------------


@router.post(
    "/tests",
    response_model=DiagnosticTestOut,
    status_code=status.HTTP_201_CREATED,
)
def create_test(
    payload: DiagnosticTestCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> DiagnosticTest:
    existing = db.query(DiagnosticTest).filter(DiagnosticTest.name == payload.name).first()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Test with this name already exists")
    test = DiagnosticTest(name=payload.name, description=payload.description)
    db.add(test)
    db.commit()
    db.refresh(test)
    return test


@router.get("/tests", response_model=Page)
def list_tests(
    db: Session = Depends(get_db),
    page: Pagination = Depends(pagination_params),
) -> Page:
    q = db.query(DiagnosticTest)
    total = q.count()
    items = q.offset(page.offset).limit(page.limit).all()
    return Page(
        total=total,
        limit=page.limit,
        offset=page.offset,
        items=[DiagnosticTestOut.model_validate(t) for t in items],
    )


# ---------------------------------------------------------------------------
# Diagnostic centres
# ---------------------------------------------------------------------------


@router.post(
    "/centres",
    response_model=CentreOut,
    status_code=status.HTTP_201_CREATED,
)
def create_centre(
    payload: CentreCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> DiagnosticCentre:
    centre = DiagnosticCentre(name=payload.name, location=payload.location)
    db.add(centre)
    db.commit()
    db.refresh(centre)
    return centre


@router.get("/centres", response_model=Page)
def list_centres(
    db: Session = Depends(get_db),
    page: Pagination = Depends(pagination_params),
) -> Page:
    q = db.query(DiagnosticCentre)
    total = q.count()
    items = q.offset(page.offset).limit(page.limit).all()
    return Page(
        total=total,
        limit=page.limit,
        offset=page.offset,
        items=[CentreOut.model_validate(c) for c in items],
    )


@router.get("/centres/{centre_id}", response_model=CentreDetailOut)
def get_centre(centre_id: str, db: Session = Depends(get_db)) -> DiagnosticCentre:
    centre = db.get(DiagnosticCentre, centre_id)
    if not centre:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Centre not found")
    return centre


@router.post(
    "/centres/{centre_id}/tests",
    response_model=CentreTestOut,
    status_code=status.HTTP_201_CREATED,
)
def add_test_to_centre(
    centre_id: str,
    payload: CentreTestCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> CentreTest:
    centre = db.get(DiagnosticCentre, centre_id)
    if not centre:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Centre not found")
    test = db.get(DiagnosticTest, payload.test_id)
    if not test:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Test not found")

    centre_test = CentreTest(
        centre_id=centre_id, test_id=payload.test_id, price=payload.price
    )
    db.add(centre_test)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This test is already offered by the centre"
        )
    db.refresh(centre_test)
    return centre_test


@router.get("/centres/{centre_id}/tests", response_model=list[CentreTestOut])
def list_centre_tests(
    centre_id: str, db: Session = Depends(get_db)
) -> list[CentreTest]:
    centre = db.get(DiagnosticCentre, centre_id)
    if not centre:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Centre not found")
    return centre.centre_tests
