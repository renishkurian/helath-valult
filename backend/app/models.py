import enum
import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, DateTime, ForeignKey, Enum, Boolean, Integer, Text
)
from sqlalchemy.orm import relationship
from app.database import Base


def gen_id() -> str:
    return uuid.uuid4().hex


class Relation(str, enum.Enum):
    self_ = "self"
    spouse = "spouse"
    child = "child"
    parent = "parent"
    other = "other"


class DocCategory(str, enum.Enum):
    hospital_card = "hospital_card"
    prescription = "prescription"
    lab_report = "lab_report"
    insurance = "insurance"
    vaccination = "vaccination"
    bill = "bill"
    medicine = "medicine"
    other = "other"


class RepeatRule(str, enum.Enum):
    none = "none"
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"
    yearly = "yearly"


class AuditAction(str, enum.Enum):
    view = "view"
    download = "download"
    share_create = "share_create"
    share_view = "share_view"


class User(Base):
    __tablename__ = "users"
    id = Column(String(32), primary_key=True, default=gen_id)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    people = relationship("Person", back_populates="owner", cascade="all, delete-orphan")


class Person(Base):
    """A profile the account manages: the account holder ('self') or a family member."""
    __tablename__ = "people"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    relation = Column(Enum(Relation), default=Relation.other, nullable=False)
    dob = Column(String(20), nullable=True)  # ISO date string
    blood_group = Column(String(10), nullable=True)
    avatar_initials = Column(String(4), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="people")
    cards = relationship("HospitalCard", back_populates="person", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="person", cascade="all, delete-orphan")
    reminders = relationship("Reminder", back_populates="person", cascade="all, delete-orphan")


class HospitalCard(Base):
    """A patient/hospital ID card. A person can have many (n hospitals)."""
    __tablename__ = "hospital_cards"
    id = Column(String(32), primary_key=True, default=gen_id)
    person_id = Column(String(32), ForeignKey("people.id"), nullable=False, index=True)

    hospital_name = Column(String(255), nullable=False, index=True)
    ward = Column(String(100), nullable=True)
    blood_group = Column(String(10), nullable=True)
    valid_from = Column(String(20), nullable=True)
    valid_till = Column(String(20), nullable=True)

    # Encrypted at rest — contains patient ID number / free-text notes.
    patient_id_enc = Column(Text, nullable=True)
    notes_enc = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    person = relationship("Person", back_populates="cards")


class Document(Base):
    """Any stored file: bill, report, prescription, medicine photo, card scan, etc."""
    __tablename__ = "documents"
    id = Column(String(32), primary_key=True, default=gen_id)
    person_id = Column(String(32), ForeignKey("people.id"), nullable=False, index=True)

    category = Column(Enum(DocCategory), nullable=False, index=True)
    custom_category = Column(String(255), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    hospital_name = Column(String(255), nullable=True, index=True)
    doc_date = Column(String(20), nullable=True)
    expiry_date = Column(String(20), nullable=True, index=True)  # ISO date; e.g. insurance/prescription validity
    tags = Column(String(500), nullable=True)  # comma-separated free-text tags, e.g. "diabetes,annual-checkup"
    version = Column(Integer, default=1, nullable=False)  # bumped on each re-upload via /versions

    # Legacy single-file columns — kept for backward compatibility.
    # New uploads use the DocumentFile child table instead.
    file_path = Column(String(500), nullable=True)   # path to the ENCRYPTED file on disk
    file_type = Column(String(100), nullable=True)   # original mime type
    file_size = Column(Integer, nullable=True)        # original (decrypted) size in bytes

    notes_enc = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    person = relationship("Person", back_populates="documents")
    files = relationship("DocumentFile", back_populates="document", cascade="all, delete-orphan", order_by="DocumentFile.created_at")


class DocumentFile(Base):
    """A single page/file attached to a Document entry. A document can have N files."""
    __tablename__ = "document_files"
    id = Column(String(32), primary_key=True, default=gen_id)
    document_id = Column(String(32), ForeignKey("documents.id"), nullable=False, index=True)

    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)    # path to the ENCRYPTED file on disk
    file_type = Column(String(100), nullable=True)     # original mime type
    file_size = Column(Integer, nullable=True)          # original (decrypted) size in bytes

    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="files")




class DocumentVersion(Base):
    """A superseded snapshot of a Document's files, kept when a document is re-uploaded."""
    __tablename__ = "document_versions"
    id = Column(String(32), primary_key=True, default=gen_id)
    document_id = Column(String(32), ForeignKey("documents.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False)

    title = Column(String(255), nullable=False)
    notes_enc = Column(Text, nullable=True)
    # JSON-encoded list of {original_filename, file_path, file_type, file_size} for the files
    # that were current in this version, so they can still be retrieved/downloaded.
    files_json = Column(Text, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document")


class ShareLink(Base):
    """A revocable, expiring, read-only token for sharing a single document with a third party
    (e.g. a hospital front desk) without giving them an account."""
    __tablename__ = "share_links"
    id = Column(String(32), primary_key=True, default=gen_id)
    token = Column(String(64), unique=True, index=True, nullable=False)
    document_id = Column(String(32), ForeignKey("documents.id"), nullable=False, index=True)
    created_by = Column(String(32), ForeignKey("users.id"), nullable=False)

    expires_at = Column(DateTime, nullable=False)
    max_views = Column(Integer, nullable=True)  # None = unlimited until expiry
    view_count = Column(Integer, default=0, nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document")


class AuditLog(Base):
    """Records who viewed/downloaded/shared what — useful once more than one person
    (e.g. a spouse with viewer access) can touch the same vault."""
    __tablename__ = "audit_logs"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=True, index=True)  # null for anonymous share views
    document_id = Column(String(32), ForeignKey("documents.id"), nullable=True, index=True)
    action = Column(Enum(AuditAction), nullable=False)
    detail = Column(String(255), nullable=True)  # e.g. share token suffix, IP, filename
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class Reminder(Base):
    __tablename__ = "reminders"
    id = Column(String(32), primary_key=True, default=gen_id)
    person_id = Column(String(32), ForeignKey("people.id"), nullable=False, index=True)
    document_id = Column(String(32), ForeignKey("documents.id"), nullable=True)

    title = Column(String(255), nullable=False)
    description = Column(String(500), nullable=True)
    remind_at = Column(DateTime, nullable=False)
    repeat_rule = Column(Enum(RepeatRule), default=RepeatRule.none, nullable=False)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    person = relationship("Person", back_populates="reminders")
