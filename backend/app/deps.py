from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, security

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = security.decode_token(token)
        if payload.get("type") != "access":
            raise credentials_error
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_error
    except ValueError:
        raise credentials_error

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise credentials_error
    return user


def get_owned_person(
    person_id: str,
    db: Session,
    current_user: models.User,
) -> models.Person:
    """Fetch a Person and verify it belongs to the current account (self or family member)."""
    person = db.query(models.Person).filter(
        models.Person.id == person_id,
        models.Person.user_id == current_user.id,
    ).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    return person
