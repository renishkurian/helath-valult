from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field
from app.models import Relation, DocCategory, RepeatRule, AuditAction, UserRole


# ---------- Auth ----------
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str


class LoginResponse(BaseModel):
    access_token: str = ""
    refresh_token: str = ""
    token_type: str = "bearer"
    totp_required: bool = False
    totp_token: Optional[str] = None


class TotpSetupOut(BaseModel):
    secret: str
    otpauth_url: str


class TotpVerifyIn(BaseModel):
    totp_token: Optional[str] = None
    code: str


class InviteViewerRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str
    person_ids: List[str] = []


class UserOut(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    role: str = UserRole.owner.value
    vault_owner_id: Optional[str] = None
    totp_enabled: bool = False

    class Config:
        from_attributes = True


class DeviceTokenIn(BaseModel):
    token: str
    platform: str = "android"


# ---------- People (self / family members) ----------
class PersonCreate(BaseModel):
    name: str
    relation: Relation = Relation.other
    dob: Optional[str] = None
    blood_group: Optional[str] = None
    allergies: Optional[str] = None
    conditions: Optional[str] = None
    emergency_name: Optional[str] = None
    emergency_phone: Optional[str] = None
    abha_id: Optional[str] = None
    ayushman_id: Optional[str] = None


class PersonUpdate(BaseModel):
    name: Optional[str] = None
    relation: Optional[Relation] = None
    dob: Optional[str] = None
    blood_group: Optional[str] = None
    allergies: Optional[str] = None
    conditions: Optional[str] = None
    emergency_name: Optional[str] = None
    emergency_phone: Optional[str] = None
    abha_id: Optional[str] = None
    ayushman_id: Optional[str] = None


class PersonOut(BaseModel):
    id: str
    name: str
    relation: Relation
    dob: Optional[str]
    blood_group: Optional[str]
    avatar_initials: Optional[str]
    allergies: Optional[str] = None
    conditions: Optional[str] = None
    emergency_name: Optional[str] = None
    emergency_phone: Optional[str] = None
    abha_id: Optional[str] = None
    ayushman_id: Optional[str] = None
    ice_token: Optional[str] = None

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
    expiry_date: Optional[str] = None
    tags: Optional[str] = None  # comma-separated
    amount: Optional[str] = None
    pinned: Optional[bool] = None


class DocumentOut(BaseModel):
    id: str
    person_id: str
    category: DocCategory
    custom_category: Optional[str] = None
    title: str
    hospital_name: Optional[str]
    doc_date: Optional[str]
    expiry_date: Optional[str] = None
    tags: Optional[str] = None
    version: int = 1
    file_type: Optional[str]   # legacy, first file's type for backward compat
    file_size: Optional[int]   # legacy, first file's size
    file_count: int = 1        # total number of attached files
    notes: Optional[str]
    extracted_text: Optional[str] = None
    amount: Optional[str] = None
    pinned: bool = False
    favorite: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class DocumentVersionOut(BaseModel):
    id: str
    document_id: str
    version: int
    title: str
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Share links ----------
class ShareLinkCreate(BaseModel):
    document_id: str
    expires_in_hours: int = Field(default=48, ge=1, le=24 * 30)
    max_views: Optional[int] = Field(default=None, ge=1)
    pin: Optional[str] = Field(default=None, min_length=4, max_length=12)
    idle_days: Optional[int] = Field(default=None, ge=1, le=365)


class ShareAccessOut(BaseModel):
    id: str
    action: str
    ip: Optional[str]
    user_agent: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class ShareLinkOut(BaseModel):
    id: str
    token: str
    document_id: str
    document_title: Optional[str] = None
    expires_at: datetime
    max_views: Optional[int]
    view_count: int
    download_count: int = 0
    last_access_at: Optional[datetime] = None
    revoked: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ShareLinkDetailOut(ShareLinkOut):
    accesses: List[ShareAccessOut] = []


# ---------- Audit log ----------
class AuditLogOut(BaseModel):
    id: str
    document_id: Optional[str]
    action: AuditAction
    detail: Optional[str]
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


class LabReadingOut(BaseModel):
    id: str
    person_id: str
    document_id: Optional[str]
    metric: str
    value: float
    unit: Optional[str]
    measured_at: Optional[str]

    class Config:
        from_attributes = True


class LabTrend(BaseModel):
    metric: str
    unit: Optional[str]
    points: List[LabReadingOut]


class LabAlert(BaseModel):
    metric: str
    message: str
    latest: float
    previous: Optional[float] = None
    unit: Optional[str] = None


class BulkIds(BaseModel):
    ids: List[str]
    tags: Optional[str] = None


class MedicineIn(BaseModel):
    person_id: str
    name: str
    dose: Optional[str] = None
    timing: Optional[str] = None
    remaining: Optional[int] = None
    refill_at: Optional[str] = None
    notes: Optional[str] = None
    document_id: Optional[str] = None


class MedicineOut(BaseModel):
    id: str
    person_id: str
    document_id: Optional[str] = None
    name: str
    dose: Optional[str] = None
    timing: Optional[str] = None
    remaining: Optional[int] = None
    refill_at: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class VaccinationIn(BaseModel):
    person_id: str
    vaccine_name: str
    dose_number: int = 1
    given_on: Optional[str] = None
    next_due: Optional[str] = None
    notes: Optional[str] = None
    document_id: Optional[str] = None


class VaccinationOut(BaseModel):
    id: str
    person_id: str
    document_id: Optional[str] = None
    vaccine_name: str
    dose_number: int
    given_on: Optional[str] = None
    next_due: Optional[str] = None
    notes: Optional[str] = None
    overdue: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class VisitIn(BaseModel):
    person_id: str
    hospital_name: Optional[str] = None
    doctor_name: Optional[str] = None
    visit_date: Optional[str] = None
    reason: Optional[str] = None
    notes: Optional[str] = None


class VisitOut(BaseModel):
    id: str
    person_id: str
    hospital_name: Optional[str] = None
    doctor_name: Optional[str] = None
    visit_date: Optional[str] = None
    reason: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ClaimIn(BaseModel):
    person_id: str
    visit_id: Optional[str] = None
    document_id: Optional[str] = None
    insurer: Optional[str] = None
    claim_number: Optional[str] = None
    amount: Optional[str] = None
    status: str = "draft"
    submitted_on: Optional[str] = None
    notes: Optional[str] = None


class ClaimOut(BaseModel):
    id: str
    person_id: str
    visit_id: Optional[str] = None
    document_id: Optional[str] = None
    insurer: Optional[str] = None
    claim_number: Optional[str] = None
    amount: Optional[str] = None
    status: str
    submitted_on: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class DoctorIn(BaseModel):
    name: str
    specialty: Optional[str] = None
    hospital_name: Optional[str] = None
    phone: Optional[str] = None
    last_visit: Optional[str] = None
    notes: Optional[str] = None


class DoctorOut(BaseModel):
    id: str
    name: str
    specialty: Optional[str] = None
    hospital_name: Optional[str] = None
    phone: Optional[str] = None
    last_visit: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class GrowthIn(BaseModel):
    person_id: str
    measured_at: str
    height_cm: Optional[str] = None
    weight_kg: Optional[str] = None
    notes: Optional[str] = None


class GrowthOut(BaseModel):
    id: str
    person_id: str
    measured_at: str
    height_cm: Optional[str] = None
    weight_kg: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class UhidIn(BaseModel):
    person_id: str
    hospital_name: str
    uhid: str


class UhidOut(BaseModel):
    id: str
    person_id: str
    hospital_name: str
    uhid: str
    created_at: datetime

    class Config:
        from_attributes = True


class TimelineItem(BaseModel):
    kind: str
    at: str
    title: str
    detail: Optional[str] = None
    ref_id: Optional[str] = None


class SharePackCreate(BaseModel):
    title: str = "Hospital pack"
    document_ids: List[str]
    expires_in_hours: int = Field(default=48, ge=1, le=24 * 30)
    max_views: Optional[int] = Field(default=None, ge=1)
    pin: Optional[str] = Field(default=None, min_length=4, max_length=12)


class SharePackOut(BaseModel):
    id: str
    token: str
    title: str
    document_ids: List[str] = []
    expires_at: datetime
    max_views: Optional[int] = None
    view_count: int
    revoked: bool
    has_pin: bool = False
    created_at: datetime


class StorageStats(BaseModel):
    bytes_used: int
    file_count: int
    backup_dir: Optional[str] = None


class DuplicateGroup(BaseModel):
    content_hash: str
    document_ids: List[str]
    filenames: List[str]


class IcePublicOut(BaseModel):
    name: str
    blood_group: Optional[str] = None
    allergies: Optional[str] = None
    conditions: Optional[str] = None
    emergency_name: Optional[str] = None
    emergency_phone: Optional[str] = None
    abha_id: Optional[str] = None
    dob: Optional[str] = None


class SpendOut(BaseModel):
    year: int
    bills: float
    claims: float
    total: float


# ---------- Password Vault ----------
class VaultFolderIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class VaultFolderOut(BaseModel):
    id: str
    name: str
    item_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


class VaultItemIn(BaseModel):
    folder_id: Optional[str] = None
    item_type: str = "login"
    name: str = Field(min_length=1, max_length=255)
    favorite: bool = False
    username: Optional[str] = None
    password: Optional[str] = None
    totp_secret: Optional[str] = None
    uris: List[str] = []
    notes: Optional[str] = None
    cardholder_name: Optional[str] = None
    card_brand: Optional[str] = None
    card_number: Optional[str] = None
    card_exp_month: Optional[str] = None
    card_exp_year: Optional[str] = None
    card_cvv: Optional[str] = None
    identity_title: Optional[str] = None
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address1: Optional[str] = None
    address2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    ssn: Optional[str] = None
    license_number: Optional[str] = None
    passport_number: Optional[str] = None


class VaultItemUpdate(BaseModel):
    folder_id: Optional[str] = None
    name: Optional[str] = None
    favorite: Optional[bool] = None
    username: Optional[str] = None
    password: Optional[str] = None
    totp_secret: Optional[str] = None
    uris: Optional[List[str]] = None
    notes: Optional[str] = None
    cardholder_name: Optional[str] = None
    card_brand: Optional[str] = None
    card_number: Optional[str] = None
    card_exp_month: Optional[str] = None
    card_exp_year: Optional[str] = None
    card_cvv: Optional[str] = None
    identity_title: Optional[str] = None
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address1: Optional[str] = None
    address2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    ssn: Optional[str] = None
    license_number: Optional[str] = None
    passport_number: Optional[str] = None


class VaultItemOut(BaseModel):
    id: str
    folder_id: Optional[str] = None
    item_type: str
    name: str
    favorite: bool = False
    username: Optional[str] = None
    password: Optional[str] = None
    totp_secret: Optional[str] = None
    has_totp: bool = False
    uris: List[str] = []
    notes: Optional[str] = None
    cardholder_name: Optional[str] = None
    card_brand: Optional[str] = None
    card_number: Optional[str] = None
    card_exp_month: Optional[str] = None
    card_exp_year: Optional[str] = None
    card_cvv: Optional[str] = None
    identity_title: Optional[str] = None
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address1: Optional[str] = None
    address2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    ssn: Optional[str] = None
    license_number: Optional[str] = None
    passport_number: Optional[str] = None
    password_changed_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class VaultTotpOut(BaseModel):
    code: str
    period: int = 30
    remaining: int


class VaultHistoryOut(BaseModel):
    id: str
    password: str
    created_at: datetime


class VaultGenerateIn(BaseModel):
    kind: str = "password"  # password | passphrase
    length: int = Field(default=16, ge=8, le=128)
    uppercase: bool = True
    lowercase: bool = True
    numbers: bool = True
    symbols: bool = True
    avoid_ambiguous: bool = True
    word_count: int = Field(default=4, ge=3, le=10)
    separator: str = "-"


class VaultGenerateOut(BaseModel):
    value: str
    score: int  # 0–4
    length: int


class VaultHealthIssue(BaseModel):
    item_id: str
    name: str
    username: Optional[str] = None
    reason: str


class VaultHealthOut(BaseModel):
    weak: List[VaultHealthIssue] = []
    reused: List[VaultHealthIssue] = []
    no_totp: List[VaultHealthIssue] = []
    old: List[VaultHealthIssue] = []
    total_logins: int = 0


class VaultSendCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    send_type: str = "text"  # text | login
    text: Optional[str] = None
    item_id: Optional[str] = None
    notes: Optional[str] = None
    pin: Optional[str] = Field(default=None, min_length=4, max_length=12)
    expires_in_hours: int = Field(default=48, ge=1, le=24 * 30)
    max_views: Optional[int] = Field(default=None, ge=1)


class VaultSendOut(BaseModel):
    id: str
    token: str
    name: str
    send_type: str
    expires_at: datetime
    max_views: Optional[int] = None
    view_count: int
    revoked: bool
    has_pin: bool = False
    created_at: datetime


class VaultSendPublicOut(BaseModel):
    name: str
    send_type: str
    text: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    uris: List[str] = []
    notes: Optional[str] = None
    expires_at: datetime
    has_pin: bool = False
    pin_required: bool = False
