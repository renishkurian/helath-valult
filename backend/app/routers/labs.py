from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.deps import get_current_user, get_owned_person, require_vault_unlock_if_needed

router = APIRouter(
    prefix="/labs",
    tags=["labs"],
    dependencies=[Depends(require_vault_unlock_if_needed)],
)


@router.get("/trends", response_model=list[schemas.LabTrend])
def lab_trends(
    person_id: str,
    metric: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Numeric lab/vital values parsed from uploaded reports, grouped for charting."""
    get_owned_person(person_id, db, current_user)
    q = db.query(models.LabReading).filter(models.LabReading.person_id == person_id)
    if metric:
        q = q.filter(models.LabReading.metric == metric)
    rows = q.order_by(models.LabReading.measured_at.asc(), models.LabReading.created_at.asc()).all()

    grouped: dict[str, list[models.LabReading]] = {}
    for r in rows:
        grouped.setdefault(r.metric, []).append(r)

    trends = []
    for name, points in grouped.items():
        unit = points[-1].unit
        trends.append(schemas.LabTrend(
            metric=name,
            unit=unit,
            points=[
                schemas.LabReadingOut(
                    id=p.id,
                    person_id=p.person_id,
                    document_id=p.document_id,
                    metric=p.metric,
                    value=float(p.value),
                    unit=p.unit,
                    measured_at=p.measured_at,
                )
                for p in points
            ],
        ))
    return trends


@router.get("/alerts", response_model=list[schemas.LabAlert])
def lab_alerts(
    person_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    trends = lab_trends(person_id, None, db, current_user)
    alerts: list[schemas.LabAlert] = []
    for t in trends:
        if len(t.points) < 2:
            continue
        latest = t.points[-1].value
        prev = t.points[-2].value
        if prev == 0:
            continue
        if latest > prev * 1.1:
            alerts.append(schemas.LabAlert(
                metric=t.metric,
                message=f"{t.metric} is up vs last reading ({prev:g} → {latest:g})",
                latest=latest,
                previous=prev,
                unit=t.unit,
            ))
        elif latest < prev * 0.9 and t.metric in {"hdl"}:
            alerts.append(schemas.LabAlert(
                metric=t.metric,
                message=f"{t.metric} dropped vs last reading ({prev:g} → {latest:g})",
                latest=latest,
                previous=prev,
                unit=t.unit,
            ))
    return alerts
