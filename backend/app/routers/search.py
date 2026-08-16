from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.deps import get_current_user, vault_id
from app.routers.cards import _to_out as card_to_out
from app.routers.documents import _to_out as doc_to_out

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=schemas.SearchResult)
def search(
    q: str,
    person_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    like = f"%{q}%"
    owner = vault_id(current_user)

    card_q = (
        db.query(models.HospitalCard)
        .join(models.Person)
        .filter(models.Person.user_id == owner)
        .filter(
            or_(
                models.HospitalCard.hospital_name.ilike(like),
                models.HospitalCard.ward.ilike(like),
            )
        )
    )
    doc_q = (
        db.query(models.Document)
        .join(models.Person)
        .filter(models.Person.user_id == owner)
        .filter(models.Document.deleted_at.is_(None))
        .filter(
            or_(
                models.Document.title.ilike(like),
                models.Document.hospital_name.ilike(like),
                models.Document.tags.ilike(like),
                models.Document.custom_category.ilike(like),
                models.Document.extracted_text.ilike(like),
            )
        )
    )
    if person_id:
        card_q = card_q.filter(models.HospitalCard.person_id == person_id)
        doc_q = doc_q.filter(models.Document.person_id == person_id)

    return schemas.SearchResult(
        cards=[card_to_out(c) for c in card_q.limit(50).all()],
        documents=[doc_to_out(d) for d in doc_q.limit(50).all()],
    )
