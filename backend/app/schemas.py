from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field
from app.models import Relation, DocCategory, RepeatRule


# ---------- Auth ----------
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: str
    email: EmailStr
    full_name: str

    class Config:
        from_attributes = True


# ---------- People (self / family members) ----------
class PersonCreate(BaseModel):
    name: str
    relation: Relation = Relation.other
    dob: Optional[str] = None
    blood_group: Optional[str] = None


class PersonUpdate(BaseModel):
    name: Optional[str] = None
    relation: Optional[Relation] = None
    dob: Optional[str] = None
    blood_group: Optional[str] = None


class PersonOut(BaseModel):
    id: str
    name: str
    relation: Relation
    dob: Optional[str]
    blood_group: Optional[str]
    avatar_initials: Optional[str]

    class Config:
        from_attributes = True


# ---------- Hospital cards ----------
class CardCreate(BaseModel):
    person_id: str
    hospital_name: str
    ward: Optional[str] = None
    blood_group: Optional[str] = None
    valid_from: Optional[str] = None
    valid_till: Optional[str] = None
    patient_id: Optional[str] = None   # will be encrypted
    notes: Optional[str] = None        # will be encrypted


class CardUpdate(BaseModel):
    hospital_name: Optional[str] = None
    ward: Optional[str] = None
    blood_group: Optional[str] = None
    valid_from: Optional[str] = None
    valid_till: Optional[str] = None
    patient_id: Optional[str] = None
    notes: Optional[str] = None


class CardOut(BaseModel):
    id: str
    person_id: str
    hospital_name: str
    ward: Optional[str]
    blood_group: Optional[str]
    valid_from: Optional[str]
    valid_till: Optional[str]
    patient_id: Optional[str]   # decrypted before returning
    notes: Optional[str]        # decrypted before returning
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Documents ----------
class DocumentFileOut(BaseModel):
    id: str
    document_id: str
    original_filename: str
    file_type: Optional[str]
    file_size: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[DocCategory] = None
    custom_category: Optional[str] = None
    hospital_name: Optional[str] = None
    doc_date: Optional[str] = None
    notes: Optional[str] = None


class DocumentOut(BaseModel):
    id: str
    person_id: str
    category: DocCategory
    custom_category: Optional[str] = None
    title: str
    hospital_name: Optional[str]
    doc_date: Optional[str]
    file_type: Optional[str]   # legacy, first file's type for backward compat
    file_size: Optional[int]   # legacy, first file's size
    file_count: int = 1        # total number of attached files
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Reminders ----------
class ReminderCreate(BaseModel):
    person_id: str
    document_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    remind_at: datetime
    repeat_rule: RepeatRule = RepeatRule.none


class ReminderUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    remind_at: Optional[datetime] = None
    repeat_rule: Optional[RepeatRule] = None
    is_active: Optional[bool] = None


class ReminderOut(BaseModel):
    id: str
    person_id: str
    document_id: Optional[str]
    title: str
    description: Optional[str]
    remind_at: datetime
    repeat_rule: RepeatRule
    is_active: bool

    class Config:
        from_attributes = True


# ---------- Search ----------
class SearchResult(BaseModel):
    cards: List[CardOut]
    documents: List[DocumentOut]
