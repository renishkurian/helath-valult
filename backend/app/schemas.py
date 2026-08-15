from datetime import datetime
from typing import Optional, List, Dict
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
    app_approve: bool = False

    class Config:
        from_attributes = True


class AppApproveIn(BaseModel):
    enabled: bool


class RefreshIn(BaseModel):
    refresh_token: str


class DeviceTokenIn(BaseModel):
    token: str
    platform: str = "android"


class LoginChallengeOut(BaseModel):
    id: str
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    class Config:
        from_attributes = True


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


class GoogleDriveStatus(BaseModel):
    connected: bool = False
    email: Optional[str] = None
    enabled: bool = False
    hour: int = 3
    keep_days: int = 14
    has_password: bool = False
    has_client: bool = False
    server_oauth: bool = False
    last_run_at: Optional[str] = None
    last_ok: Optional[bool] = None
    last_error: Optional[str] = None
    last_file_name: Optional[str] = None


class GoogleDriveSettingsIn(BaseModel):
    enabled: Optional[bool] = None
    hour: Optional[int] = None
    keep_days: Optional[int] = None
    password: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None


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


# ---------- Finance / Money Manager ----------
class FinanceAccountIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    account_type: str = "cash"  # cash | bank | credit_card | loan | wallet | other
    currency: str = "INR"
    opening_balance: float = 0
    credit_limit: Optional[float] = None
    institution: Optional[str] = None
    last4: Optional[str] = None


class FinanceAccountOut(BaseModel):
    id: str
    name: str
    account_type: str
    currency: str
    opening_balance: float
    credit_limit: Optional[float] = None
    institution: Optional[str] = None
    last4: Optional[str] = None
    archived: bool = False
    balance: float = 0
    is_liability: bool = False
    created_at: datetime


class FinanceCategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: str = "expense"
    color: Optional[str] = None
    account_id: Optional[str] = None  # null = general / all accounts
    parent_id: Optional[str] = None  # null = top-level; set to add a subcategory


class FinanceCategoryOut(BaseModel):
    id: str
    name: str
    kind: str
    color: Optional[str] = None
    is_system: bool = False
    account_id: Optional[str] = None
    account_name: Optional[str] = None
    parent_id: Optional[str] = None
    parent_name: Optional[str] = None
    scope: str = "general"  # general | account


class FinanceTxnIn(BaseModel):
    account_id: str
    to_account_id: Optional[str] = None
    category_id: Optional[str] = None
    txn_type: str = "expense"
    amount: float
    txn_date: str
    txn_time: Optional[str] = None
    payee: Optional[str] = None
    notes: Optional[str] = None
    description: Optional[str] = None
    payment_method: Optional[str] = None  # upi | credit_card | debit_card | atm | netbanking | cash | other
    tags: Optional[str] = None
    frequency: Optional[str] = None  # if set, also create recurring


class FinanceTxnOut(BaseModel):
    id: str
    account_id: str
    account_name: str = ""
    to_account_id: Optional[str] = None
    to_account_name: Optional[str] = None
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    category_color: Optional[str] = None
    txn_type: str
    amount: float
    currency: str = "INR"
    txn_date: str
    txn_time: Optional[str] = None
    payee: Optional[str] = None
    notes: Optional[str] = None
    description: Optional[str] = None
    payment_method: Optional[str] = None
    tags: Optional[str] = None
    source: str = "manual"
    has_image: bool = False
    created_at: datetime


class FinanceBudgetIn(BaseModel):
    category_id: str
    year_month: str
    amount: float


class FinanceBudgetOut(BaseModel):
    id: str
    category_id: str
    category_name: str = ""
    year_month: str
    amount: float
    spent: float = 0


class FinanceEmiIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    kind: str = "emi"  # emi | chitty | loan | insurance | rent | subscription | other
    account_id: str
    category_id: Optional[str] = None
    amount: float
    start_date: str
    end_date: str
    day_of_month: Optional[int] = None
    auto_post: bool = True
    notify_days: int = 2
    notes: Optional[str] = None


class FinanceEmiOut(BaseModel):
    id: str
    name: str
    kind: str = "emi"
    kind_label: str = "EMI"
    account_id: str
    account_name: str = ""
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    amount: float
    start_date: str
    end_date: str
    day_of_month: int
    next_due: Optional[str] = None
    auto_post: bool = True
    notify_days: int = 2
    notes: Optional[str] = None
    active: bool = True
    status: str = "pending"  # pending | overdue | completed
    total_installments: int = 0
    paid_count: int = 0
    remaining: int = 0
    created_at: datetime


class FinanceRecurringIn(BaseModel):
    account_id: str
    category_id: Optional[str] = None
    txn_type: str = "expense"
    amount: float
    payee: Optional[str] = None
    notes: Optional[str] = None
    frequency: str = "monthly"
    next_due: str


class FinanceRecurringOut(BaseModel):
    id: str
    account_id: str
    account_name: str = ""
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    txn_type: str
    amount: float
    payee: Optional[str] = None
    notes: Optional[str] = None
    frequency: str
    next_due: str
    active: bool = True


class FinanceAiKeyIn(BaseModel):
    """Deprecated alias — use AiProviderIn. Kept for Android /finance/ai-keys."""
    name: str
    kind: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    is_default: bool = False


class FinanceAiKeyOut(BaseModel):
    id: str
    name: str
    kind: str
    base_url: Optional[str] = None
    model: Optional[str] = None
    is_default: bool = False
    enabled: bool = True
    has_key: bool = False


class AiProviderIn(BaseModel):
    name: str
    kind: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    is_default: bool = False


class AiProviderOut(BaseModel):
    id: str
    name: str
    kind: str
    base_url: Optional[str] = None
    model: Optional[str] = None
    is_default: bool = False
    enabled: bool = True
    has_key: bool = False


class AiStatusOut(BaseModel):
    count: int = 0
    has_default: bool = False
    default_name: Optional[str] = None
    default_kind: Optional[str] = None
    default_id: Optional[str] = None
    default_model: Optional[str] = None


class AiConnectionTestOut(BaseModel):
    ok: bool = True
    name: Optional[str] = None
    kind: Optional[str] = None
    model: Optional[str] = None
    sample: str = ""
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


class AiChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    thread_id: Optional[str] = None


class AiChatMessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime


class AiChatThreadOut(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    preview: Optional[str] = None


class AiChatThreadDetailOut(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    messages: List[AiChatMessageOut] = []


class AiChatReplyOut(BaseModel):
    thread_id: str
    title: str
    reply: str
    messages: List[AiChatMessageOut] = []
    action: Optional[dict] = None


class AiShopListActionIn(BaseModel):
    type: str = "create_shop_list"
    name: str = Field(min_length=1, max_length=120)
    items: List[dict] = Field(min_length=1, max_length=60)


class AiShopListActionOut(BaseModel):
    list_id: str
    name: str
    item_count: int
    url: str


class AiUsageLogOut(BaseModel):
    id: str
    client: str
    client_label: str
    provider_name: Optional[str] = None
    provider_kind: Optional[str] = None
    model: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    latency_ms: Optional[int] = None
    ok: bool = True
    error: Optional[str] = None
    request_text: Optional[str] = None
    response_text: Optional[str] = None
    created_at: datetime


class AiUsageSummaryOut(BaseModel):
    days: int = 30
    calls: int = 0
    ok: int = 0
    failed: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    by_client: Dict[str, int] = {}


class FinanceRuleIn(BaseModel):
    match_text: str
    category_id: Optional[str] = None
    txn_type: Optional[str] = None
    payee: Optional[str] = None


class FinanceRuleOut(BaseModel):
    id: str
    match_text: str
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    txn_type: Optional[str] = None
    payee: Optional[str] = None


class FinanceMessageIn(BaseModel):
    text: str
    account_id: Optional[str] = None
    auto_accept: bool = False


class FinanceMessageOut(BaseModel):
    id: str
    raw_text: str
    direction: str
    amount: Optional[float] = None
    payee: Optional[str] = None
    txn_date: Optional[str] = None
    payment_method: Optional[str] = None
    category_id: Optional[str] = None
    suggested_category: Optional[str] = None
    confidence: Optional[float] = None
    provider_used: Optional[str] = None
    status: str
    transaction_id: Optional[str] = None
    created_at: datetime


class FinanceSummaryOut(BaseModel):
    year_month: str
    income: float
    expense: float
    total: float
    opening: float = 0
    closing: float = 0
    prev_month: Optional[str] = None
    prev_income: float = 0
    prev_expense: float = 0
    prev_total: float = 0
    assets: float
    liabilities: float
    net: float
    pending_messages: int = 0


# ---------- Document Vault / Locker ----------
class LockerFileOut(BaseModel):
    id: str
    item_id: str
    original_filename: str
    file_type: Optional[str] = None
    file_size: Optional[int] = None
    created_at: datetime


class LockerItemUpdate(BaseModel):
    title: Optional[str] = None
    doc_type: Optional[str] = None
    custom_type: Optional[str] = None
    holder_name: Optional[str] = None
    issuer: Optional[str] = None
    id_number: Optional[str] = None
    issued_on: Optional[str] = None
    expiry_date: Optional[str] = None
    tags: Optional[str] = None
    notes: Optional[str] = None
    pinned: Optional[bool] = None


class LockerItemOut(BaseModel):
    id: str
    doc_type: str
    type_label: str
    custom_type: Optional[str] = None
    title: str
    holder_name: Optional[str] = None
    issuer: Optional[str] = None
    id_number: Optional[str] = None
    issued_on: Optional[str] = None
    expiry_date: Optional[str] = None
    tags: Optional[str] = None
    notes: Optional[str] = None
    pinned: bool = False
    file_type: Optional[str] = None
    file_size: Optional[int] = None
    file_count: int = 0
    created_at: datetime


class LockerTypeOut(BaseModel):
    id: str
    label: str
    count: int = 0


class LockerSummaryOut(BaseModel):
    total: int = 0
    expiring: int = 0
    types: List[LockerTypeOut] = []


# ---------- URL Vault ----------
class UrlCategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    color: Optional[str] = Field(default=None, max_length=16)
    sort_order: Optional[int] = None


class UrlCategoryOut(BaseModel):
    id: str
    name: str
    color: Optional[str] = None
    sort_order: int = 0
    is_default: bool = False
    count: int = 0


class UrlTagIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    color: Optional[str] = Field(default=None, max_length=16)


class UrlTagOut(BaseModel):
    id: str
    name: str
    color: Optional[str] = None
    count: int = 0


class UrlItemIn(BaseModel):
    url: str = Field(min_length=3, max_length=2000)
    title: Optional[str] = Field(default=None, max_length=255)
    category_id: Optional[str] = None
    tag_ids: List[str] = []
    notes: Optional[str] = None
    favorite: bool = False
    fetch_preview: bool = True


class UrlItemUpdate(BaseModel):
    url: Optional[str] = Field(default=None, max_length=2000)
    title: Optional[str] = Field(default=None, max_length=255)
    category_id: Optional[str] = None
    tag_ids: Optional[List[str]] = None
    notes: Optional[str] = None
    favorite: Optional[bool] = None
    fetch_preview: Optional[bool] = None


class UrlItemOut(BaseModel):
    id: str
    title: str
    url: str
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    category_color: Optional[str] = None
    tags: List[UrlTagOut] = []
    notes: Optional[str] = None
    favorite: bool = False
    og_title: Optional[str] = None
    og_description: Optional[str] = None
    og_image: Optional[str] = None
    og_site_name: Optional[str] = None
    favicon_url: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class UrlPreviewOut(BaseModel):
    url: str
    title: Optional[str] = None
    description: Optional[str] = None
    image: Optional[str] = None
    site_name: Optional[str] = None
    favicon_url: Optional[str] = None


class UrlPreviewIn(BaseModel):
    url: str = Field(min_length=3, max_length=2000)


class UrlShareCreate(BaseModel):
    expires_in_hours: int = Field(default=168, ge=1, le=24 * 90)
    max_views: Optional[int] = Field(default=None, ge=1)


class UrlShareOut(BaseModel):
    id: str
    token: str
    item_id: str
    item_title: Optional[str] = None
    item_url: Optional[str] = None
    expires_at: datetime
    max_views: Optional[int] = None
    view_count: int = 0
    revoked: bool = False
    created_at: datetime


class UrlSummaryOut(BaseModel):
    total: int = 0
    favorites: int = 0
    categories: List[UrlCategoryOut] = []
    tags: List[UrlTagOut] = []


# ---------- Expense Analyser ----------
class ExpenseAnalyserStatusOut(BaseModel):
    connected: bool = False
    email: Optional[str] = None
    server_oauth: bool = False
    sync_query: Optional[str] = None
    enabled: bool = False
    hour: int = 6
    last_sync_at: Optional[str] = None
    last_ok: Optional[bool] = None
    last_error: Optional[str] = None
    syncing: bool = False
    retagging: bool = False
    pending: int = 0
    matched: int = 0
    missed: int = 0
    posted: int = 0
    corrected: int = 0
    pending_pdfs: int = 0


class ExpenseAnalyserScheduleIn(BaseModel):
    enabled: bool = False
    hour: int = Field(default=6, ge=0, le=23)


class ExpenseAnalyserItemOut(BaseModel):
    id: str
    gmail_message_id: str
    kind: str
    subject: Optional[str] = None
    from_addr: Optional[str] = None
    received_at: Optional[datetime] = None
    raw_snippet: Optional[str] = None
    direction: str
    amount: Optional[float] = None
    currency: str = "INR"
    payee: Optional[str] = None
    txn_date: Optional[str] = None
    payment_method: Optional[str] = None
    suggested_category: Optional[str] = None
    confidence: Optional[float] = None
    status: str
    match_txn_id: Optional[str] = None
    finance_txn_id: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime


class ExpenseAnalyserItemUpdate(BaseModel):
    direction: Optional[str] = None
    amount: Optional[float] = None
    payee: Optional[str] = None
    txn_date: Optional[str] = None
    payment_method: Optional[str] = None
    suggested_category: Optional[str] = None
    notes: Optional[str] = None


class ExpenseAnalyserSyncOut(BaseModel):
    fetched: int = 0
    created: int = 0
    skipped: int = 0
    matched: int = 0
    missed: int = 0
    error: Optional[str] = None
    pdfs: int = 0
    pdf_rows: int = 0
    pdf_locked: int = 0


class ExpenseAnalyserPdfImportOut(BaseModel):
    ok: bool = True
    started: bool = True
    fetched: int = 0
    pdfs: int = 0
    created_rows: int = 0
    skipped: int = 0
    needs_password: int = 0
    failed: int = 0
    parsed: int = 0


class ShopStatementPdfOut(BaseModel):
    id: str
    filename: Optional[str] = None
    subject: Optional[str] = None
    from_addr: Optional[str] = None
    received_at: Optional[datetime] = None
    status: str
    error: Optional[str] = None
    bank_hint: Optional[str] = None
    created_count: int = 0
    skipped_count: int = 0
    created_at: datetime


class ExpenseAnalyserSyncLogOut(BaseModel):
    id: str
    trigger: str
    ok: bool
    fetched: int = 0
    created: int = 0
    skipped: int = 0
    matched: int = 0
    missed: int = 0
    error: Optional[str] = None
    started_at: datetime
    finished_at: datetime


class ExpenseAnalyserPostIn(BaseModel):
    account_id: Optional[str] = None
    category_id: Optional[str] = None
    subcategory_id: Optional[str] = None
    new_category: Optional[str] = None
    new_subcategory: Optional[str] = None


class ExpenseAnalyserRetagIn(BaseModel):
    item_ids: Optional[List[str]] = None
    limit: Optional[int] = Field(default=None, ge=1, le=20)
    force: bool = False


class ExpenseAnalyserQueryIn(BaseModel):
    sync_query: Optional[str] = Field(default=None, max_length=2000)


# ---------- Shopping List ----------
class ShopListIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    finance_category_id: Optional[str] = None


class ShopListUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    completed: Optional[bool] = None
    finance_category_id: Optional[str] = None


class ShopItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    quantity: Optional[float] = 1
    unit: Optional[str] = None
    price: Optional[float] = None
    emoji: Optional[str] = None
    category: Optional[str] = None
    notes: Optional[str] = None
    guest_name: Optional[str] = None


class ShopItemUpdate(BaseModel):
    name: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    price: Optional[float] = None
    emoji: Optional[str] = None
    category: Optional[str] = None
    notes: Optional[str] = None
    checked: Optional[bool] = None
    status: Optional[str] = None


class ShopItemOut(BaseModel):
    id: str
    list_id: str
    name: str
    quantity: float = 1
    unit: Optional[str] = None
    price: Optional[float] = None
    checked: bool = False
    emoji: Optional[str] = None
    category: Optional[str] = None
    notes: Optional[str] = None
    added_by: Optional[str] = None
    guest_name: Optional[str] = None
    added_by_name: Optional[str] = None
    status: str = "approved"
    merged: bool = False
    created_at: datetime


class ShopReceiptOut(BaseModel):
    id: str
    list_id: str
    original_name: Optional[str] = None
    image_mime: Optional[str] = None
    is_image: bool = True
    created_at: datetime


class ShopListOut(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    completed: bool = False
    total_amount: float = 0
    item_count: int = 0
    checked_count: int = 0
    pending_count: int = 0
    receipt_count: int = 0
    share_token: Optional[str] = None
    owner_name: Optional[str] = None
    finance_category_id: Optional[str] = None
    finance_category_name: Optional[str] = None
    finance_txn_id: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    revision: Optional[str] = None
    items: Optional[List[ShopItemOut]] = None
    receipts: Optional[List[ShopReceiptOut]] = None


class ShopListPostFinanceIn(BaseModel):
    account_id: str = Field(min_length=1, max_length=32)
    category_id: Optional[str] = None  # override list tag; defaults to list / Groceries



class ShopShareOut(BaseModel):
    token: str
    url: str
    list_id: str


class ShopContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    relation: Optional[str] = None


class ShopContactOut(BaseModel):
    id: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    relation: Optional[str] = None
    created_at: datetime


class ShopCatalogItemIn(BaseModel):
    english: str = Field(min_length=1, max_length=255)
    malayalam: Optional[str] = Field(default=None, max_length=255)
    emoji: Optional[str] = Field(default="🛒", max_length=16)
    category: str = Field(default="custom", max_length=80)
    scope: str = Field(default="personal", max_length=20)  # personal | global
    aliases: Optional[str] = Field(default=None, max_length=500)


class ShopCatalogItemOut(BaseModel):
    id: str
    english: str
    malayalam: Optional[str] = None
    emoji: Optional[str] = None
    category: str
    scope: str
    aliases: Optional[str] = None
    mine: bool = True
    created_at: datetime
    updated_at: Optional[datetime] = None


class ShopSendIn(BaseModel):
    email: EmailStr
    message: Optional[str] = None


class ShopSendOut(BaseModel):
    id: str
    sender_id: str
    receiver_id: str
    sender_name: Optional[str] = None
    receiver_name: Optional[str] = None
    list_name: Optional[str] = None
    status: str
    message: Optional[str] = None
    sent_at: datetime


class ShopPdfPasswordIn(BaseModel):
    identifier: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1)
    account_type: str = "bank"
    last_4_digits: Optional[str] = None


class ShopPdfPasswordOut(BaseModel):
    id: str
    identifier: str
    account_type: str
    last_4_digits: Optional[str] = None
    created_at: datetime


class ShopStatementTxnOut(BaseModel):
    id: str
    txn_date: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[float] = None
    direction: str
    category: Optional[str] = None
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    account_type: Optional[str] = None
    source_file: Optional[str] = None
    status: str
    finance_txn_id: Optional[str] = None
    created_at: datetime


class ShopStatementPostIn(BaseModel):
    account_id: Optional[str] = None


class ShopRecognizeIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class ShopGroceryItemOut(BaseModel):
    english: str
    malayalam: Optional[str] = None
    emoji: str = "🛒"
    category: Optional[str] = None
    matched: bool = False


class ShopSummaryOut(BaseModel):
    lists: int = 0
    open_lists: int = 0
    pending_items: int = 0
    pending_statements: int = 0
    friends: int = 0
    inbox: int = 0
