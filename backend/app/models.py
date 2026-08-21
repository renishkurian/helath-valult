import enum
import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, DateTime, ForeignKey, Enum, Boolean, Integer, Text, Numeric, Table,
    UniqueConstraint,
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


# Everything except insurance is filed under a specific hospital/clinic.
HOSPITAL_SCOPED_CATEGORIES = frozenset(
    c for c in DocCategory if c != DocCategory.insurance
)


def category_requires_hospital(category: DocCategory) -> bool:
    return category in HOSPITAL_SCOPED_CATEGORIES


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
    delete = "delete"


class UserRole(str, enum.Enum):
    owner = "owner"
    viewer = "viewer"
    superadmin = "superadmin"


class User(Base):
    __tablename__ = "users"
    id = Column(String(32), primary_key=True, default=gen_id)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    # owner = full access to this vault; viewer = read-only (e.g. spouse abroad)
    role = Column(String(20), default=UserRole.owner.value, nullable=False)
    # The vault this account belongs to. Owners: vault_owner_id == id.
    vault_owner_id = Column(String(32), ForeignKey("users.id"), nullable=True, index=True)
    totp_secret_enc = Column(Text, nullable=True)
    totp_enabled = Column(Boolean, default=False, nullable=False)
    app_approve = Column(Boolean, default=False, nullable=False)
    blocked = Column(Boolean, default=False, nullable=False, index=True)
    # JSON list of module keys the vault may open; null = all default modules.
    enabled_modules = Column(Text, nullable=True)
    last_seen_at = Column(DateTime, nullable=True)
    # Health overview: use uploaded patient-card photo as ID-card background.
    card_image_as_background = Column(Boolean, default=False, nullable=False)
    # Floating Ask AI button on every module (web + app).
    show_ask_ai_fab = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    people = relationship("Person", back_populates="owner", cascade="all, delete-orphan")


class LoginAttempt(Base):
    """Every HTML and API sign-in try — success or failure — for the superadmin log."""
    __tablename__ = "login_attempts"
    id = Column(String(32), primary_key=True, default=gen_id)
    email = Column(String(255), index=True, nullable=False, default="")
    ip = Column(String(64), index=True, nullable=True)
    user_agent = Column(String(400), nullable=True)
    success = Column(Boolean, default=False, nullable=False, index=True)
    reason = Column(String(40), nullable=False, default="bad_credentials")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class ServerSetting(Base):
    """Server-wide keys managed in Super Admin (Google, FCM, reCAPTCHA, lockout)."""
    __tablename__ = "server_settings"
    key = Column(String(64), primary_key=True)
    value = Column(Text, nullable=True)
    value_enc = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow)


class LoginChallenge(Base):
    """Pending web login that the already-signed-in Android app can allow or deny."""
    __tablename__ = "login_challenges"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    ip = Column(String(64), nullable=True)
    user_agent = Column(String(400), nullable=True)
    status = Column(String(20), default="pending", nullable=False, index=True)
    kind = Column(String(20), default="app", nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False, index=True)
    decided_at = Column(DateTime, nullable=True)


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
    allergies = Column(Text, nullable=True)
    conditions = Column(Text, nullable=True)
    emergency_name = Column(String(255), nullable=True)
    emergency_phone = Column(String(40), nullable=True)
    abha_id = Column(String(64), nullable=True)
    ayushman_id = Column(String(64), nullable=True)
    ice_token = Column(String(64), unique=True, index=True, nullable=True)
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
    # Encrypted scan of the physical patient / hospital card.
    image_path = Column(String(500), nullable=True)
    image_mime = Column(String(80), nullable=True)

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
    extracted_text = Column(Text, nullable=True)  # OCR / PDF text, plaintext so /search can match content
    amount = Column(String(20), nullable=True)  # bill / claim amount for yearly spend
    pinned = Column(Boolean, default=False, nullable=False)

    # Legacy single-file columns — kept for backward compatibility.
    # New uploads use the DocumentFile child table instead.
    file_path = Column(String(500), nullable=True)   # path to the ENCRYPTED file on disk
    file_type = Column(String(100), nullable=True)   # original mime type
    file_size = Column(Integer, nullable=True)        # original (decrypted) size in bytes

    notes_enc = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True, index=True)

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
    content_hash = Column(String(64), nullable=True, index=True)

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
    pin_hash = Column(String(255), nullable=True)
    idle_days = Column(Integer, default=14, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document")
    accesses = relationship("ShareAccess", back_populates="share_link", cascade="all, delete-orphan")


class ShareAccess(Base):
    """One open/download of a share link — IP, browser, time, view vs download."""
    __tablename__ = "share_accesses"
    id = Column(String(32), primary_key=True, default=gen_id)
    share_link_id = Column(String(32), ForeignKey("share_links.id"), nullable=False, index=True)
    action = Column(String(20), nullable=False, default="view")  # view | download
    ip = Column(String(64), nullable=True)
    user_agent = Column(String(400), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    share_link = relationship("ShareLink", back_populates="accesses")


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


class LabReading(Base):
    """A numeric lab (or vitals) value parsed from a document, for simple trend charts."""
    __tablename__ = "lab_readings"
    id = Column(String(32), primary_key=True, default=gen_id)
    person_id = Column(String(32), ForeignKey("people.id"), nullable=False, index=True)
    document_id = Column(String(32), ForeignKey("documents.id"), nullable=True, index=True)
    metric = Column(String(40), nullable=False, index=True)  # glucose, hba1c, cholesterol, ldl, hdl, triglycerides, bp_sys, bp_dia, creatinine
    value = Column(String(20), nullable=False)  # stored as string to keep SQLAlchemy simple; parsed as float by API
    unit = Column(String(20), nullable=True)
    measured_at = Column(String(20), nullable=True)  # ISO date from the document
    created_at = Column(DateTime, default=datetime.utcnow)


class DeviceToken(Base):
    """Android FCM (or similar) token so the Pi can push reminder notifications instead of the app polling."""
    __tablename__ = "device_tokens"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    token = Column(String(512), nullable=False, unique=True)
    platform = Column(String(20), default="android", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class ViewerAccess(Base):
    """If any rows exist for a viewer, they may only see these people."""
    __tablename__ = "viewer_access"
    id = Column(String(32), primary_key=True, default=gen_id)
    viewer_user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    person_id = Column(String(32), ForeignKey("people.id"), nullable=False, index=True)


class Favorite(Base):
    __tablename__ = "favorites"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    document_id = Column(String(32), ForeignKey("documents.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class RecentOpen(Base):
    __tablename__ = "recent_opens"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    document_id = Column(String(32), ForeignKey("documents.id"), nullable=False, index=True)
    opened_at = Column(DateTime, default=datetime.utcnow, index=True)


class HospitalUhid(Base):
    __tablename__ = "hospital_uhids"
    id = Column(String(32), primary_key=True, default=gen_id)
    person_id = Column(String(32), ForeignKey("people.id"), nullable=False, index=True)
    hospital_name = Column(String(255), nullable=False)
    uhid = Column(String(80), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Medicine(Base):
    __tablename__ = "medicines"
    id = Column(String(32), primary_key=True, default=gen_id)
    person_id = Column(String(32), ForeignKey("people.id"), nullable=False, index=True)
    document_id = Column(String(32), ForeignKey("documents.id"), nullable=True)
    name = Column(String(255), nullable=False)
    dose = Column(String(80), nullable=True)
    timing = Column(String(120), nullable=True)
    remaining = Column(Integer, nullable=True)
    refill_at = Column(String(20), nullable=True)
    notes = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class VaccinationRecord(Base):
    __tablename__ = "vaccinations"
    id = Column(String(32), primary_key=True, default=gen_id)
    person_id = Column(String(32), ForeignKey("people.id"), nullable=False, index=True)
    document_id = Column(String(32), ForeignKey("documents.id"), nullable=True)
    vaccine_name = Column(String(255), nullable=False)
    dose_number = Column(Integer, default=1, nullable=False)
    given_on = Column(String(20), nullable=True)
    next_due = Column(String(20), nullable=True, index=True)
    notes = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Visit(Base):
    __tablename__ = "visits"
    id = Column(String(32), primary_key=True, default=gen_id)
    person_id = Column(String(32), ForeignKey("people.id"), nullable=False, index=True)
    hospital_name = Column(String(255), nullable=True)
    doctor_name = Column(String(255), nullable=True)
    visit_date = Column(String(20), nullable=True, index=True)
    reason = Column(String(255), nullable=True)
    notes = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Claim(Base):
    __tablename__ = "claims"
    id = Column(String(32), primary_key=True, default=gen_id)
    person_id = Column(String(32), ForeignKey("people.id"), nullable=False, index=True)
    visit_id = Column(String(32), ForeignKey("visits.id"), nullable=True)
    document_id = Column(String(32), ForeignKey("documents.id"), nullable=True)
    insurer = Column(String(255), nullable=True)
    claim_number = Column(String(80), nullable=True)
    amount = Column(String(20), nullable=True)
    status = Column(String(20), default="draft", nullable=False)  # draft/submitted/approved/rejected/paid
    submitted_on = Column(String(20), nullable=True)
    notes = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Doctor(Base):
    __tablename__ = "doctors"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    specialty = Column(String(120), nullable=True)
    hospital_name = Column(String(255), nullable=True)
    phone = Column(String(40), nullable=True)
    last_visit = Column(String(20), nullable=True)
    notes = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class GrowthReading(Base):
    __tablename__ = "growth_readings"
    id = Column(String(32), primary_key=True, default=gen_id)
    person_id = Column(String(32), ForeignKey("people.id"), nullable=False, index=True)
    measured_at = Column(String(20), nullable=False)
    height_cm = Column(String(20), nullable=True)
    weight_kg = Column(String(20), nullable=True)
    notes = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class SharePack(Base):
    __tablename__ = "share_packs"
    id = Column(String(32), primary_key=True, default=gen_id)
    token = Column(String(64), unique=True, index=True, nullable=False)
    created_by = Column(String(32), ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=False, default="Shared pack")
    pin_hash = Column(String(255), nullable=True)
    expires_at = Column(DateTime, nullable=False)
    max_views = Column(Integer, nullable=True)
    view_count = Column(Integer, default=0, nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)
    idle_days = Column(Integer, default=14, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    items = relationship("SharePackItem", back_populates="pack", cascade="all, delete-orphan")
    accesses = relationship("SharePackAccess", back_populates="pack", cascade="all, delete-orphan")


class SharePackItem(Base):
    __tablename__ = "share_pack_items"
    id = Column(String(32), primary_key=True, default=gen_id)
    pack_id = Column(String(32), ForeignKey("share_packs.id"), nullable=False, index=True)
    document_id = Column(String(32), ForeignKey("documents.id"), nullable=False)
    pack = relationship("SharePack", back_populates="items")


class SharePackAccess(Base):
    __tablename__ = "share_pack_accesses"
    id = Column(String(32), primary_key=True, default=gen_id)
    pack_id = Column(String(32), ForeignKey("share_packs.id"), nullable=False, index=True)
    action = Column(String(20), nullable=False, default="view")
    ip = Column(String(64), nullable=True)
    user_agent = Column(String(400), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    pack = relationship("SharePack", back_populates="accesses")


class VaultItemType(str, enum.Enum):
    login = "login"
    note = "note"
    card = "card"
    identity = "identity"


class VaultFolder(Base):
    __tablename__ = "vault_folders"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    items = relationship("VaultItem", back_populates="folder")


class VaultItem(Base):
    """Encrypted login / note / card / identity. Secrets live in *_enc columns."""
    __tablename__ = "vault_items"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    folder_id = Column(String(32), ForeignKey("vault_folders.id"), nullable=True, index=True)
    item_type = Column(String(20), default=VaultItemType.login.value, nullable=False, index=True)
    name = Column(String(255), nullable=False, index=True)
    favorite = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime, nullable=True, index=True)

    username = Column(String(255), nullable=True)
    password_enc = Column(Text, nullable=True)
    totp_secret_enc = Column(Text, nullable=True)
    uris = Column(Text, nullable=True)  # JSON list of URIs / package names
    notes_enc = Column(Text, nullable=True)

    cardholder_name = Column(String(255), nullable=True)
    card_brand = Column(String(40), nullable=True)
    card_number_enc = Column(Text, nullable=True)
    card_exp_month = Column(String(4), nullable=True)
    card_exp_year = Column(String(8), nullable=True)
    card_cvv_enc = Column(Text, nullable=True)

    identity_title = Column(String(40), nullable=True)
    first_name = Column(String(120), nullable=True)
    middle_name = Column(String(120), nullable=True)
    last_name = Column(String(120), nullable=True)
    email = Column(String(255), nullable=True)
    phone = Column(String(40), nullable=True)
    address1 = Column(String(255), nullable=True)
    address2 = Column(String(255), nullable=True)
    city = Column(String(120), nullable=True)
    state = Column(String(120), nullable=True)
    postal_code = Column(String(40), nullable=True)
    country = Column(String(80), nullable=True)
    ssn_enc = Column(Text, nullable=True)
    license_number_enc = Column(Text, nullable=True)
    passport_number_enc = Column(Text, nullable=True)

    password_changed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    folder = relationship("VaultFolder", back_populates="items")
    history = relationship("VaultPasswordHistory", back_populates="item", cascade="all, delete-orphan")


class VaultPasswordHistory(Base):
    __tablename__ = "vault_password_history"
    id = Column(String(32), primary_key=True, default=gen_id)
    item_id = Column(String(32), ForeignKey("vault_items.id"), nullable=False, index=True)
    password_enc = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    item = relationship("VaultItem", back_populates="history")


class VaultSend(Base):
    """Bitwarden-style expiring share of a password or note."""
    __tablename__ = "vault_sends"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    token = Column(String(64), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    send_type = Column(String(20), default="text", nullable=False)  # text | login
    payload_enc = Column(Text, nullable=False)
    notes_enc = Column(Text, nullable=True)
    pin_hash = Column(String(255), nullable=True)
    expires_at = Column(DateTime, nullable=False)
    max_views = Column(Integer, nullable=True)
    view_count = Column(Integer, default=0, nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    accesses = relationship("VaultSendAccess", back_populates="send", cascade="all, delete-orphan")


class VaultSendAccess(Base):
    __tablename__ = "vault_send_accesses"
    id = Column(String(32), primary_key=True, default=gen_id)
    send_id = Column(String(32), ForeignKey("vault_sends.id"), nullable=False, index=True)
    action = Column(String(20), nullable=False, default="view")  # view | password_viewed
    ip = Column(String(64), nullable=True)
    user_agent = Column(String(400), nullable=True)
    email = Column(String(255), nullable=True)
    request_id = Column(String(32), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    send = relationship("VaultSend", back_populates="accesses")


class VaultSendRequest(Base):
    """Guest asked the owner for access to a Send link (optional photo/geo)."""
    __tablename__ = "vault_send_requests"
    id = Column(String(32), primary_key=True, default=gen_id)
    send_id = Column(String(32), ForeignKey("vault_sends.id"), nullable=False, index=True)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)  # owner
    name = Column(String(120), nullable=True)
    email = Column(String(255), nullable=True)
    ip = Column(String(64), nullable=True)
    user_agent = Column(String(400), nullable=True)
    latitude = Column(String(32), nullable=True)
    longitude = Column(String(32), nullable=True)
    photo_path = Column(String(500), nullable=True)  # encrypted relative path (guest selfie at request)
    photo_mime = Column(String(80), nullable=True)
    face_path = Column(String(500), nullable=True)  # encrypted owner capture from live video
    face_mime = Column(String(80), nullable=True)
    face_captured_at = Column(DateTime, nullable=True)
    status = Column(String(20), default="pending", nullable=False)  # pending | seen | granted | dismissed
    video_status = Column(String(20), default="none", nullable=False)  # none | requested | live | ended
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    decided_at = Column(DateTime, nullable=True)
    viewed_at = Column(DateTime, nullable=True)  # password actually shown to this guest

    send = relationship("VaultSend")
    chat_messages = relationship(
        "VaultSendChatMessage",
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="VaultSendChatMessage.created_at",
    )


class VaultSendChatMessage(Base):
    """Short chat between owner and guest while an access request is pending."""
    __tablename__ = "vault_send_chat_messages"
    id = Column(String(32), primary_key=True, default=gen_id)
    request_id = Column(String(32), ForeignKey("vault_send_requests.id"), nullable=False, index=True)
    from_role = Column(String(10), nullable=False)  # admin | guest
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    request = relationship("VaultSendRequest", back_populates="chat_messages")


class VaultSendEmailOtp(Base):
    """Pending email OTP for a Send that requires email verification."""
    __tablename__ = "vault_send_email_otps"
    id = Column(String(32), primary_key=True, default=gen_id)
    send_id = Column(String(32), ForeignKey("vault_sends.id"), nullable=False, index=True)
    email = Column(String(255), nullable=False, index=True)
    code_hash = Column(String(255), nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------- Finance / Money Manager ----------
class FinanceAccount(Base):
    __tablename__ = "finance_accounts"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    account_type = Column(String(30), default="bank", nullable=False)
    currency = Column(String(8), default="INR", nullable=False)
    opening_balance = Column(Numeric(14, 2), default=0, nullable=False)
    credit_limit = Column(Numeric(14, 2), nullable=True)
    institution = Column(String(255), nullable=True)
    last4 = Column(String(8), nullable=True)
    archived = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class FinanceCategory(Base):
    __tablename__ = "finance_categories"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    kind = Column(String(20), default="expense", nullable=False)  # expense | income
    color = Column(String(16), nullable=True)
    is_system = Column(Boolean, default=False, nullable=False)
    account_id = Column(String(32), ForeignKey("finance_accounts.id"), nullable=True, index=True)  # null = general / all accounts
    parent_id = Column(String(32), ForeignKey("finance_categories.id"), nullable=True, index=True)  # null = top-level category
    created_at = Column(DateTime, default=datetime.utcnow)


class FinanceTransaction(Base):
    __tablename__ = "finance_transactions"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    account_id = Column(String(32), ForeignKey("finance_accounts.id"), nullable=False, index=True)
    to_account_id = Column(String(32), ForeignKey("finance_accounts.id"), nullable=True)
    category_id = Column(String(32), ForeignKey("finance_categories.id"), nullable=True, index=True)
    txn_type = Column(String(20), default="expense", nullable=False)  # expense | income | transfer
    amount = Column(Numeric(14, 2), nullable=False)
    currency = Column(String(8), default="INR", nullable=False)
    txn_date = Column(String(20), nullable=False, index=True)
    txn_time = Column(String(8), nullable=True)
    payee = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    payment_method = Column(String(30), nullable=True)  # upi | credit_card | debit_card | atm | netbanking | cash | other
    tags = Column(String(500), nullable=True)
    source = Column(String(20), default="manual", nullable=False)  # manual | message | recurring | emi
    message_id = Column(String(32), nullable=True, index=True)
    emi_id = Column(String(32), ForeignKey("finance_emis.id"), nullable=True, index=True)
    image_path = Column(String(500), nullable=True)
    image_mime = Column(String(80), nullable=True)
    deleted_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class FinanceBudget(Base):
    __tablename__ = "finance_budgets"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    category_id = Column(String(32), ForeignKey("finance_categories.id"), nullable=False, index=True)
    year_month = Column(String(7), nullable=False, index=True)  # 2026-08
    amount = Column(Numeric(14, 2), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class FinanceEmi(Base):
    __tablename__ = "finance_emis"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    kind = Column(String(30), default="emi", nullable=False, index=True)  # emi | chitty | loan | insurance | rent | subscription | other
    account_id = Column(String(32), ForeignKey("finance_accounts.id"), nullable=False, index=True)
    category_id = Column(String(32), ForeignKey("finance_categories.id"), nullable=True)
    amount = Column(Numeric(14, 2), nullable=False)
    start_date = Column(String(20), nullable=False)
    end_date = Column(String(20), nullable=False)
    day_of_month = Column(Integer, default=1, nullable=False)
    next_due = Column(String(20), nullable=True)
    auto_post = Column(Boolean, default=True, nullable=False)
    notify_days = Column(Integer, default=2, nullable=False)
    notes = Column(Text, nullable=True)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class FinanceRecurring(Base):
    __tablename__ = "finance_recurring"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    account_id = Column(String(32), ForeignKey("finance_accounts.id"), nullable=False)
    category_id = Column(String(32), ForeignKey("finance_categories.id"), nullable=True)
    txn_type = Column(String(20), default="expense", nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    payee = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    frequency = Column(String(20), default="monthly", nullable=False)
    next_due = Column(String(20), nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class AiProvider(Base):
    """Vault-wide LLM provider keys — shared by Money Manager, Expense Analyser, etc."""
    __tablename__ = "ai_providers"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    kind = Column(String(30), nullable=False)  # openai | anthropic | openrouter | kimi | groq | ollama | custom
    api_key_enc = Column(Text, nullable=True)
    base_url = Column(String(400), nullable=True)
    model = Column(String(120), nullable=True)
    is_default = Column(Boolean, default=False, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class AiChatThread(Base):
    """Ask AI conversation. Message bodies are encrypted at rest."""
    __tablename__ = "ai_chat_threads"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(200), nullable=False, default="New chat")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

    messages = relationship(
        "AiChatMessage", back_populates="thread", cascade="all, delete-orphan",
        order_by="AiChatMessage.created_at",
    )


class AiChatMessage(Base):
    __tablename__ = "ai_chat_messages"
    id = Column(String(32), primary_key=True, default=gen_id)
    thread_id = Column(String(32), ForeignKey("ai_chat_threads.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # user | assistant
    content_enc = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    thread = relationship("AiChatThread", back_populates="messages")


class AiBrainMemory(Base):
    """Durable household facts Ask AI learns and reuses (encrypted at rest)."""
    __tablename__ = "ai_brain_memories"
    __table_args__ = (
        UniqueConstraint("user_id", "slug", name="uq_ai_brain_user_slug"),
    )
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    kind = Column(String(20), nullable=False, default="fact")  # fact | preference | alias | habit
    slug = Column(String(80), nullable=False)
    content_enc = Column(Text, nullable=False)
    source = Column(String(20), nullable=False, default="chat")  # chat | action | manual
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AiUsageLog(Base):
    """Every LLM call: client, provider, model, token counts, timestamp."""
    __tablename__ = "ai_usage_logs"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    client = Column(String(40), nullable=False, index=True)  # ask_ai | finance_sms | expense_analyser | connection_test | provider_test
    provider_name = Column(String(120), nullable=True)
    provider_kind = Column(String(30), nullable=True)
    model = Column(String(120), nullable=True)
    prompt_tokens = Column(Integer, nullable=True)  # request / input
    completion_tokens = Column(Integer, nullable=True)  # response / output
    total_tokens = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    ok = Column(Boolean, default=True, nullable=False)
    error = Column(Text, nullable=True)
    request_text = Column(Text, nullable=True)  # prompt / user query / SMS body
    response_text = Column(Text, nullable=True)  # model reply or classify JSON
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class FinanceAiProvider(Base):
    """Legacy table — rows are copied into ai_providers on upgrade. Prefer AiProvider."""
    __tablename__ = "finance_ai_providers"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    kind = Column(String(30), nullable=False)
    api_key_enc = Column(Text, nullable=True)
    base_url = Column(String(400), nullable=True)
    model = Column(String(120), nullable=True)
    is_default = Column(Boolean, default=False, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class FinanceRule(Base):
    __tablename__ = "finance_rules"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    match_text = Column(String(255), nullable=False)
    category_id = Column(String(32), ForeignKey("finance_categories.id"), nullable=True)
    txn_type = Column(String(20), nullable=True)  # expense | income
    payee = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class FinanceMessage(Base):
    __tablename__ = "finance_messages"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    raw_text = Column(Text, nullable=False)
    direction = Column(String(20), default="unknown", nullable=False)  # debit | credit | unknown
    amount = Column(Numeric(14, 2), nullable=True)
    payee = Column(String(255), nullable=True)
    txn_date = Column(String(20), nullable=True)
    payment_method = Column(String(30), nullable=True)
    category_id = Column(String(32), ForeignKey("finance_categories.id"), nullable=True)
    suggested_category = Column(String(120), nullable=True)
    confidence = Column(Numeric(4, 3), nullable=True)
    provider_used = Column(String(120), nullable=True)
    status = Column(String(20), default="pending", nullable=False, index=True)  # pending | accepted | ignored
    transaction_id = Column(String(32), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class GoogleDriveBackup(Base):
    """One Google Drive target per vault. Refresh token is encrypted at rest."""
    __tablename__ = "google_drive_backup"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, unique=True, index=True)
    client_id = Column(String(255), nullable=True)
    client_secret_enc = Column(Text, nullable=True)
    refresh_token_enc = Column(Text, nullable=True)
    folder_id = Column(String(128), nullable=True)
    connected_email = Column(String(255), nullable=True)
    enabled = Column(Boolean, default=False, nullable=False)
    hour = Column(Integer, default=3, nullable=False)  # local hour 0-23
    keep_days = Column(Integer, default=14, nullable=False)
    password_enc = Column(Text, nullable=True)
    last_run_at = Column(DateTime, nullable=True)
    last_ok = Column(Boolean, nullable=True)
    last_error = Column(Text, nullable=True)
    last_file_name = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class LockerDocType(str, enum.Enum):
    aadhaar = "aadhaar"
    pan = "pan"
    passport = "passport"
    driving_license = "driving_license"
    voter_id = "voter_id"
    certificate = "certificate"
    rc = "rc"
    insurance = "insurance"
    warranty = "warranty"
    property = "property"
    other = "other"


class LockerFolder(Base):
    """User-created Document Vault folder (Gas book, School papers, …). Supports nesting."""
    __tablename__ = "locker_folders"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    parent_id = Column(String(32), ForeignKey("locker_folders.id"), nullable=True, index=True)
    name = Column(String(120), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    items = relationship("LockerItem", back_populates="folder")
    parent = relationship("LockerFolder", remote_side=[id], backref="children")


class LockerItem(Base):
    """Encrypted household document (Aadhaar, PAN, RC, warranty, etc.)."""
    __tablename__ = "locker_items"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    person_id = Column(String(32), ForeignKey("people.id"), nullable=True, index=True)
    folder_id = Column(String(32), ForeignKey("locker_folders.id"), nullable=True, index=True)
    doc_type = Column(String(40), default=LockerDocType.other.value, nullable=False, index=True)
    custom_type = Column(String(120), nullable=True)
    title = Column(String(255), nullable=False, index=True)
    holder_name = Column(String(255), nullable=True)
    issuer = Column(String(255), nullable=True)
    id_number_enc = Column(Text, nullable=True)
    issued_on = Column(String(20), nullable=True)
    expiry_date = Column(String(20), nullable=True, index=True)
    tags = Column(String(500), nullable=True)
    notes_enc = Column(Text, nullable=True)
    pinned = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    person = relationship("Person")
    folder = relationship("LockerFolder", back_populates="items")
    files = relationship(
        "LockerFile", back_populates="item", cascade="all, delete-orphan",
        order_by="LockerFile.created_at",
    )


class LockerFile(Base):
    __tablename__ = "locker_files"
    id = Column(String(32), primary_key=True, default=gen_id)
    item_id = Column(String(32), ForeignKey("locker_items.id"), nullable=False, index=True)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_type = Column(String(100), nullable=True)
    file_size = Column(Integer, nullable=True)
    content_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    item = relationship("LockerItem", back_populates="files")


class DiaryCategory(Base):
    """User-managed Digital Diary category (Personal, Work, Travel, …)."""
    __tablename__ = "diary_categories"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(80), nullable=False)
    color = Column(String(16), nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    entries = relationship("DiaryEntry", back_populates="category")


class DiaryEntry(Base):
    """A diary note: title, encrypted body, optional category/tags/mood, photos."""
    __tablename__ = "diary_entries"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    category_id = Column(String(32), ForeignKey("diary_categories.id"), nullable=True, index=True)
    entry_date = Column(String(20), nullable=False, index=True)  # ISO date
    title = Column(String(255), nullable=False, index=True)
    body_enc = Column(Text, nullable=True)
    tags = Column(String(500), nullable=True)  # comma-separated
    mood = Column(String(40), nullable=True)
    pinned = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    category = relationship("DiaryCategory", back_populates="entries")
    images = relationship(
        "DiaryImage", back_populates="entry", cascade="all, delete-orphan",
        order_by="DiaryImage.created_at",
    )


class DiaryImage(Base):
    __tablename__ = "diary_images"
    id = Column(String(32), primary_key=True, default=gen_id)
    entry_id = Column(String(32), ForeignKey("diary_entries.id"), nullable=False, index=True)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_type = Column(String(100), nullable=True)
    file_size = Column(Integer, nullable=True)
    content_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    entry = relationship("DiaryEntry", back_populates="images")


url_item_tags = Table(
    "url_item_tags",
    Base.metadata,
    Column("item_id", String(32), ForeignKey("url_items.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", String(32), ForeignKey("url_tags.id", ondelete="CASCADE"), primary_key=True),
)


class UrlCategory(Base):
    """User-managed URL Vault category (Adult, Instagram, News, Songs, …)."""
    __tablename__ = "url_categories"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(80), nullable=False)
    color = Column(String(16), nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    items = relationship("UrlItem", back_populates="category")


class UrlTag(Base):
    """User-managed URL Vault tag."""
    __tablename__ = "url_tags"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(80), nullable=False)
    color = Column(String(16), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    items = relationship("UrlItem", secondary=url_item_tags, back_populates="tags")


class UrlItem(Base):
    """A saved bookmark: URL + title, optional category/tags, Open Graph preview."""
    __tablename__ = "url_items"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False, index=True)
    url = Column(String(2000), nullable=False)
    category_id = Column(String(32), ForeignKey("url_categories.id"), nullable=True, index=True)
    notes_enc = Column(Text, nullable=True)
    favorite = Column(Boolean, default=False, nullable=False, index=True)
    og_title = Column(String(500), nullable=True)
    og_description = Column(Text, nullable=True)
    og_image = Column(String(2000), nullable=True)
    og_site_name = Column(String(255), nullable=True)
    favicon_url = Column(String(2000), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    category = relationship("UrlCategory", back_populates="items")
    tags = relationship("UrlTag", secondary=url_item_tags, back_populates="items")
    shares = relationship("UrlShare", back_populates="item", cascade="all, delete-orphan")


class UrlShare(Base):
    """Expiring public page for a saved URL (read-only, no login)."""
    __tablename__ = "url_shares"
    id = Column(String(32), primary_key=True, default=gen_id)
    token = Column(String(64), unique=True, index=True, nullable=False)
    item_id = Column(String(32), ForeignKey("url_items.id"), nullable=False, index=True)
    created_by = Column(String(32), ForeignKey("users.id"), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    max_views = Column(Integer, nullable=True)
    view_count = Column(Integer, default=0, nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    item = relationship("UrlItem", back_populates="shares")


class ExpenseAnalyserConnection(Base):
    """Per-vault Gmail OAuth for Expense Analyser (separate from Drive backup)."""
    __tablename__ = "expense_analyser_connections"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, unique=True, index=True)
    refresh_token_enc = Column(Text, nullable=True)
    connected_email = Column(String(255), nullable=True)
    sync_query = Column(Text, nullable=True)
    enabled = Column(Boolean, default=False, nullable=False)  # daily auto-sync
    hour = Column(Integer, default=6, nullable=False)  # local hour 0-23
    last_sync_at = Column(DateTime, nullable=True)
    last_ok = Column(Boolean, nullable=True)
    last_error = Column(Text, nullable=True)
    last_history_id = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ExpenseAnalyserItem(Base):
    """Parsed spend from Gmail alerts or credit-card bills — review before Money Manager."""
    __tablename__ = "expense_analyser_items"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    gmail_message_id = Column(String(64), nullable=False, index=True)
    gmail_thread_id = Column(String(64), nullable=True)
    kind = Column(String(20), default="alert", nullable=False)  # alert | bill | bill_line
    subject = Column(String(500), nullable=True)
    from_addr = Column(String(255), nullable=True)
    received_at = Column(DateTime, nullable=True, index=True)
    raw_snippet = Column(Text, nullable=True)
    raw_text_enc = Column(Text, nullable=True)
    direction = Column(String(20), default="unknown", nullable=False)  # debit | credit | unknown
    amount = Column(Numeric(14, 2), nullable=True)
    currency = Column(String(8), default="INR", nullable=False)
    payee = Column(String(255), nullable=True)
    txn_date = Column(String(20), nullable=True, index=True)
    payment_method = Column(String(30), nullable=True)
    suggested_category = Column(String(120), nullable=True)
    confidence = Column(Numeric(4, 3), nullable=True)
    # pending | matched | corrected | posted | ignored | missed
    status = Column(String(20), default="pending", nullable=False, index=True)
    match_txn_id = Column(String(32), nullable=True, index=True)
    finance_txn_id = Column(String(32), nullable=True, index=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ExpenseAnalyserSyncLog(Base):
    """History of Gmail sync runs (manual or scheduled)."""
    __tablename__ = "expense_analyser_sync_logs"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    trigger = Column(String(20), default="manual", nullable=False)  # manual | scheduled
    ok = Column(Boolean, default=True, nullable=False)
    fetched = Column(Integer, default=0, nullable=False)
    created = Column(Integer, default=0, nullable=False)
    skipped = Column(Integer, default=0, nullable=False)
    matched = Column(Integer, default=0, nullable=False)
    missed = Column(Integer, default=0, nullable=False)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


# ---------- Shopping List (grocery lists, live sharing, friends) ----------

class ShopList(Base):
    """A shopping list (purchase bucket) owned by a vault."""
    __tablename__ = "shop_lists"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    completed = Column(Boolean, default=False, nullable=False, index=True)
    total_amount = Column(Numeric(14, 2), default=0, nullable=False)
    image_path = Column(String(500), nullable=True)
    blocked_uids = Column(Text, nullable=True)  # JSON list of guest names / user ids
    finance_category_id = Column(String(32), ForeignKey("finance_categories.id"), nullable=True, index=True)
    finance_txn_id = Column(String(32), nullable=True, index=True)  # posted to Money Manager
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True, index=True)

    items = relationship(
        "ShopItem", back_populates="lst", cascade="all, delete-orphan",
        order_by="ShopItem.created_at",
    )
    receipts = relationship(
        "ShopReceipt", back_populates="lst", cascade="all, delete-orphan",
        order_by="ShopReceipt.created_at",
    )
    shares = relationship("ShopShare", back_populates="lst", cascade="all, delete-orphan")


class ShopItem(Base):
    __tablename__ = "shop_items"
    id = Column(String(32), primary_key=True, default=gen_id)
    list_id = Column(String(32), ForeignKey("shop_lists.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    quantity = Column(Numeric(12, 3), default=1, nullable=False)
    unit = Column(String(40), nullable=True)
    price = Column(Numeric(14, 2), nullable=True)
    checked = Column(Boolean, default=False, nullable=False, index=True)
    emoji = Column(String(16), nullable=True)
    category = Column(String(80), nullable=True)
    notes = Column(Text, nullable=True)
    added_by = Column(String(32), nullable=True)  # user id or "guest"
    guest_name = Column(String(120), nullable=True)
    status = Column(String(20), default="approved", nullable=False, index=True)  # approved | pending
    changes_requested = Column(Text, nullable=True)  # JSON
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    lst = relationship("ShopList", back_populates="items")


class ShopReceipt(Base):
    """A photo or PDF of the shop bill, attached to one shopping list."""
    __tablename__ = "shop_receipts"
    id = Column(String(32), primary_key=True, default=gen_id)
    list_id = Column(String(32), ForeignKey("shop_lists.id"), nullable=False, index=True)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    image_path = Column(String(500), nullable=False)
    image_mime = Column(String(80), nullable=True)
    original_name = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    lst = relationship("ShopList", back_populates="receipts")


class ShopShare(Base):
    """Public collaborative link for a shopping list (no login)."""
    __tablename__ = "shop_shares"
    id = Column(String(32), primary_key=True, default=gen_id)
    list_id = Column(String(32), ForeignKey("shop_lists.id"), nullable=False, index=True)
    token = Column(String(64), unique=True, index=True, nullable=False)
    created_by = Column(String(32), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    use_count = Column(Integer, default=0, nullable=False)

    lst = relationship("ShopList", back_populates="shares")


class ShopContact(Base):
    """Friends & family used as shopping-list recipients."""
    __tablename__ = "shop_contacts"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=True, index=True)
    phone = Column(String(40), nullable=True)
    relation = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ShopSend(Base):
    """A shopping list sent to another vault user."""
    __tablename__ = "shop_sends"
    id = Column(String(32), primary_key=True, default=gen_id)
    sender_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    receiver_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    list_id = Column(String(32), nullable=True)
    list_data = Column(Text, nullable=True)  # JSON snapshot
    status = Column(String(20), default="pending", nullable=False, index=True)  # pending | accepted | rejected
    message = Column(Text, nullable=True)
    sent_at = Column(DateTime, default=datetime.utcnow)
    responded_at = Column(DateTime, nullable=True)


class ShopPdfPassword(Base):
    """Saved bank/credit-card PDF passwords (encrypted at rest)."""
    __tablename__ = "shop_pdf_passwords"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    identifier = Column(String(255), nullable=False)
    password_enc = Column(Text, nullable=False)
    account_type = Column(String(50), default="bank", nullable=False)  # bank | credit_card
    last_4_digits = Column(String(8), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ShopStatementPdf(Base):
    """A Gmail PDF statement tracked for import (password retry without re-search)."""
    __tablename__ = "shop_statement_pdfs"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    gmail_message_id = Column(String(128), nullable=False, index=True)
    # Gmail attachmentIds are often longer than 255 chars; truncating breaks re-download.
    gmail_attachment_id = Column(Text, nullable=True)
    filename = Column(String(255), nullable=True)
    subject = Column(String(500), nullable=True)
    from_addr = Column(String(255), nullable=True)
    received_at = Column(DateTime, nullable=True)
    status = Column(String(30), default="parsed", nullable=False, index=True)
    # parsed | needs_password | failed | ignored
    error = Column(String(500), nullable=True)
    bank_hint = Column(String(80), nullable=True)
    created_count = Column(Integer, default=0, nullable=False)
    skipped_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ShopStatementTxn(Base):
    """A row parsed from a bank/credit-card PDF, reviewed before Money Manager."""
    __tablename__ = "shop_statement_txns"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    txn_date = Column(String(20), nullable=True, index=True)
    description = Column(Text, nullable=True)
    amount = Column(Numeric(14, 2), nullable=True)
    direction = Column(String(20), default="debit", nullable=False)  # debit | credit
    category = Column(String(50), nullable=True, index=True)
    bank_name = Column(String(100), nullable=True)
    account_number = Column(String(50), nullable=True)
    account_type = Column(String(50), nullable=True)
    source_file = Column(String(255), nullable=True)
    transaction_id = Column(String(64), nullable=True, index=True)
    reference_number = Column(String(255), nullable=True)
    status = Column(String(20), default="pending", nullable=False, index=True)  # pending | posted | ignored
    finance_txn_id = Column(String(32), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class ShopDictItem(Base):
    """Grocery dictionary: English + Malayalam + emoji for quick-add and recognition."""
    __tablename__ = "shop_dict_items"
    key = Column(String(255), primary_key=True)
    english = Column(String(255), nullable=False)
    malayalam = Column(String(255), nullable=True)
    emoji = Column(String(16), default="🛒")
    source = Column(String(20), default="seed", nullable=False)  # seed | user
    category = Column(String(80), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ShopCatalogItem(Base):
    """User-managed Quick Add chips — personal (vault) or global (all users)."""
    __tablename__ = "shop_catalog_items"
    id = Column(String(32), primary_key=True, default=gen_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    scope = Column(String(20), default="personal", nullable=False, index=True)  # personal | global
    english = Column(String(255), nullable=False)
    malayalam = Column(String(255), nullable=True)
    emoji = Column(String(16), default="🛒")
    category = Column(String(80), nullable=False, default="essentials", index=True)
    aliases = Column(Text, nullable=True)  # comma-separated extra match keys
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
