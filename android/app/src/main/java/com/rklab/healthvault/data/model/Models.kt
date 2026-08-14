package com.rklab.healthvault.data.model

import com.google.gson.annotations.SerializedName

// ---------- Auth ----------
data class RegisterRequest(val email: String, val password: String, val full_name: String)
data class LoginResponse(
    val access_token: String = "",
    val refresh_token: String = "",
    val token_type: String = "bearer",
    val totp_required: Boolean = false,
    val totp_token: String? = null
)
data class UserOut(
    val id: String,
    val email: String,
    val full_name: String,
    val role: String = "owner",
    val vault_owner_id: String? = null,
    val totp_enabled: Boolean = false,
    val app_approve: Boolean = false
) {
    val isViewer: Boolean get() = role == "viewer"
}

data class AppApproveIn(val enabled: Boolean)

data class InviteViewerRequest(
    val email: String,
    val password: String,
    val full_name: String,
    val person_ids: List<String> = emptyList()
)
data class TotpSetupOut(val secret: String, val otpauth_url: String)
data class TotpVerifyIn(val totp_token: String? = null, val code: String)
data class RefreshIn(val refresh_token: String)
data class DeviceTokenIn(val token: String, val platform: String = "android")
data class LoginChallengeOut(
    val id: String,
    val ip: String? = null,
    val user_agent: String? = null,
    val status: String = "pending",
    val created_at: String? = null,
    val expires_at: String? = null
)

// ---------- People ----------
enum class Relation {
    @SerializedName("self") SELF,
    @SerializedName("spouse") SPOUSE,
    @SerializedName("child") CHILD,
    @SerializedName("parent") PARENT,
    @SerializedName("other") OTHER
}

data class PersonOut(
    val id: String,
    val name: String,
    val relation: Relation,
    val dob: String?,
    val blood_group: String?,
    val avatar_initials: String?,
    val allergies: String? = null,
    val conditions: String? = null,
    val emergency_name: String? = null,
    val emergency_phone: String? = null,
    val abha_id: String? = null,
    val ayushman_id: String? = null,
    val ice_token: String? = null
)

data class PersonCreate(
    val name: String,
    val relation: Relation,
    val dob: String? = null,
    val blood_group: String? = null
)

// ---------- Hospital cards ----------
data class CardOut(
    val id: String,
    val person_id: String,
    val hospital_name: String,
    val ward: String?,
    val blood_group: String?,
    val valid_from: String?,
    val valid_till: String?,
    val patient_id: String?,
    val notes: String?,
    val created_at: String
)

data class CardCreate(
    val person_id: String,
    val hospital_name: String,
    val ward: String? = null,
    val blood_group: String? = null,
    val valid_from: String? = null,
    val valid_till: String? = null,
    val patient_id: String? = null,
    val notes: String? = null
)

// ---------- Documents ----------
enum class DocCategory {
    @SerializedName("hospital_card") HOSPITAL_CARD,
    @SerializedName("prescription") PRESCRIPTION,
    @SerializedName("lab_report") LAB_REPORT,
    @SerializedName("insurance") INSURANCE,
    @SerializedName("vaccination") VACCINATION,
    @SerializedName("bill") BILL,
    @SerializedName("medicine") MEDICINE,
    @SerializedName("other") OTHER;

    /** Everything except insurance must be filed under a hospital. */
    fun requiresHospital(): Boolean = this != INSURANCE
}

/** Categories shown under each hospital on the health overview. */
val HospitalScopedCategories: List<DocCategory> =
    DocCategory.entries.filter { it.requiresHospital() }

data class DocumentOut(
    val id: String,
    val person_id: String,
    val category: DocCategory,
    val custom_category: String?,
    val title: String,
    val hospital_name: String?,
    val doc_date: String?,
    val expiry_date: String? = null,
    val tags: String? = null,
    val version: Int = 1,
    val file_type: String?,
    val file_size: Long?,
    val file_count: Int = 1,
    val notes: String?,
    val extracted_text: String? = null,
    val amount: String? = null,
    val pinned: Boolean = false,
    val favorite: Boolean = false,
    val created_at: String
)

data class DocumentUpdate(
    val title: String? = null,
    val category: DocCategory? = null,
    val custom_category: String? = null,
    val hospital_name: String? = null,
    val doc_date: String? = null,
    val notes: String? = null,
    val expiry_date: String? = null,
    val tags: String? = null,
    val amount: String? = null,
    val pinned: Boolean? = null
)

data class DocumentFileOut(
    val id: String,
    val document_id: String,
    val original_filename: String,
    val file_type: String?,
    val file_size: Long?,
    val created_at: String
)

data class DocumentVersionOut(
    val id: String,
    val document_id: String,
    val version: Int,
    val title: String,
    val notes: String?,
    val created_at: String
)

// ---------- Share links ----------
data class ShareLinkCreate(
    val document_id: String,
    val expires_in_hours: Int = 48,
    val max_views: Int? = null,
    val pin: String? = null,
    val idle_days: Int? = null
)

data class SharePackCreate(
    val title: String = "Hospital pack",
    val document_ids: List<String>,
    val expires_in_hours: Int = 48,
    val max_views: Int? = null,
    val pin: String? = null
)

data class SharePackOut(
    val id: String,
    val token: String,
    val title: String,
    val document_ids: List<String> = emptyList(),
    val expires_at: String,
    val max_views: Int? = null,
    val view_count: Int,
    val revoked: Boolean,
    val has_pin: Boolean = false,
    val created_at: String
)

data class BulkIds(val ids: List<String>, val tags: String? = null)

data class ShareLinkOut(
    val id: String,
    val token: String,
    val document_id: String,
    val document_title: String? = null,
    val expires_at: String,
    val max_views: Int?,
    val view_count: Int,
    val download_count: Int = 0,
    val last_access_at: String? = null,
    val revoked: Boolean,
    val created_at: String
)

data class ShareAccessOut(
    val id: String,
    val action: String,
    val ip: String?,
    val user_agent: String?,
    val created_at: String
)

data class ShareLinkDetailOut(
    val id: String,
    val token: String,
    val document_id: String,
    val document_title: String? = null,
    val expires_at: String,
    val max_views: Int?,
    val view_count: Int,
    val download_count: Int = 0,
    val last_access_at: String? = null,
    val revoked: Boolean,
    val created_at: String,
    val accesses: List<ShareAccessOut> = emptyList()
)

// ---------- Audit log ----------
enum class AuditAction {
    @SerializedName("view") VIEW,
    @SerializedName("download") DOWNLOAD,
    @SerializedName("share_create") SHARE_CREATE,
    @SerializedName("share_view") SHARE_VIEW
}

data class AuditLogOut(
    val id: String,
    val document_id: String?,
    val action: AuditAction,
    val detail: String?,
    val created_at: String
)

// ---------- Reminders ----------
enum class RepeatRule {
    @SerializedName("none") NONE,
    @SerializedName("daily") DAILY,
    @SerializedName("weekly") WEEKLY,
    @SerializedName("monthly") MONTHLY,
    @SerializedName("yearly") YEARLY
}

data class ReminderOut(
    val id: String,
    val person_id: String,
    val document_id: String?,
    val title: String,
    val description: String?,
    val remind_at: String, // ISO 8601
    val repeat_rule: RepeatRule,
    val is_active: Boolean
)

data class ReminderCreate(
    val person_id: String,
    val document_id: String? = null,
    val title: String,
    val description: String? = null,
    val remind_at: String,
    val repeat_rule: RepeatRule = RepeatRule.NONE
)

// ---------- Search ----------
data class SearchResult(val cards: List<CardOut>, val documents: List<DocumentOut>)

data class LabReadingOut(
    val id: String,
    val person_id: String,
    val document_id: String?,
    val metric: String,
    val value: Double,
    val unit: String?,
    val measured_at: String?
)

data class LabTrend(
    val metric: String,
    val unit: String?,
    val points: List<LabReadingOut>
)

data class LabAlert(
    val metric: String,
    val message: String,
    val latest: Double,
    val previous: Double? = null,
    val unit: String? = null
)

data class MedicineIn(
    val person_id: String,
    val name: String,
    val dose: String? = null,
    val timing: String? = null,
    val remaining: Int? = null,
    val refill_at: String? = null,
    val notes: String? = null
)
data class MedicineOut(
    val id: String, val person_id: String, val name: String,
    val dose: String?, val timing: String?, val remaining: Int?,
    val refill_at: String?, val notes: String?, val created_at: String
)

data class VaccinationIn(
    val person_id: String, val vaccine_name: String, val dose_number: Int = 1,
    val given_on: String? = null, val next_due: String? = null, val notes: String? = null
)
data class VaccinationOut(
    val id: String, val person_id: String, val vaccine_name: String, val dose_number: Int,
    val given_on: String?, val next_due: String?, val notes: String?,
    val overdue: Boolean = false, val created_at: String
)

data class VisitIn(
    val person_id: String, val hospital_name: String? = null, val doctor_name: String? = null,
    val visit_date: String? = null, val reason: String? = null, val notes: String? = null
)
data class VisitOut(
    val id: String, val person_id: String, val hospital_name: String?, val doctor_name: String?,
    val visit_date: String?, val reason: String?, val notes: String?, val created_at: String
)

data class ClaimIn(
    val person_id: String, val insurer: String? = null, val claim_number: String? = null,
    val amount: String? = null, val status: String = "draft", val submitted_on: String? = null
)
data class ClaimOut(
    val id: String, val person_id: String, val insurer: String?, val claim_number: String?,
    val amount: String?, val status: String, val submitted_on: String?, val created_at: String
)

data class DoctorIn(
    val name: String, val specialty: String? = null, val hospital_name: String? = null,
    val phone: String? = null, val last_visit: String? = null
)
data class DoctorOut(
    val id: String, val name: String, val specialty: String?, val hospital_name: String?,
    val phone: String?, val last_visit: String?, val created_at: String
)

data class GrowthIn(
    val person_id: String, val measured_at: String,
    val height_cm: String? = null, val weight_kg: String? = null
)
data class GrowthOut(
    val id: String, val person_id: String, val measured_at: String,
    val height_cm: String?, val weight_kg: String?, val created_at: String
)

data class UhidIn(val person_id: String, val hospital_name: String, val uhid: String)
data class UhidOut(val id: String, val person_id: String, val hospital_name: String, val uhid: String, val created_at: String)

data class TimelineItem(val kind: String, val at: String, val title: String, val detail: String?, val ref_id: String?)
data class StorageStats(val bytes_used: Long, val file_count: Int, val backup_dir: String?)
data class GoogleDriveStatus(
    val connected: Boolean = false,
    val email: String? = null,
    val enabled: Boolean = false,
    val hour: Int = 3,
    val keep_days: Int = 14,
    val has_password: Boolean = false,
    val has_client: Boolean = false,
    val server_oauth: Boolean = false,
    val last_run_at: String? = null,
    val last_ok: Boolean? = null,
    val last_error: String? = null,
    val last_file_name: String? = null
)
data class GoogleDriveSettingsIn(
    val enabled: Boolean? = null,
    val hour: Int? = null,
    val keep_days: Int? = null,
    val password: String? = null
)
data class GoogleDriveRunOut(
    val ok: Boolean = false,
    val file: String? = null,
    val bytes: Long? = null
)
data class SpendOut(val year: Int, val bills: Double, val claims: Double, val total: Double)
// ---------- Password Vault ----------
data class VaultFolderIn(val name: String)
data class VaultFolderOut(
    val id: String,
    val name: String,
    val item_count: Int = 0,
    val created_at: String
)
data class VaultItemIn(
    val folder_id: String? = null,
    val item_type: String = "login",
    val name: String,
    val favorite: Boolean = false,
    val username: String? = null,
    val password: String? = null,
    val totp_secret: String? = null,
    val uris: List<String> = emptyList(),
    val notes: String? = null,
    val cardholder_name: String? = null,
    val card_brand: String? = null,
    val card_number: String? = null,
    val card_exp_month: String? = null,
    val card_exp_year: String? = null,
    val card_cvv: String? = null,
    val identity_title: String? = null,
    val first_name: String? = null,
    val middle_name: String? = null,
    val last_name: String? = null,
    val email: String? = null,
    val phone: String? = null,
    val address1: String? = null,
    val address2: String? = null,
    val city: String? = null,
    val state: String? = null,
    val postal_code: String? = null,
    val country: String? = null,
    val ssn: String? = null,
    val license_number: String? = null,
    val passport_number: String? = null
)
data class VaultItemUpdate(
    val folder_id: String? = null,
    val name: String? = null,
    val favorite: Boolean? = null,
    val username: String? = null,
    val password: String? = null,
    val totp_secret: String? = null,
    val uris: List<String>? = null,
    val notes: String? = null,
    val cardholder_name: String? = null,
    val card_brand: String? = null,
    val card_number: String? = null,
    val card_exp_month: String? = null,
    val card_exp_year: String? = null,
    val card_cvv: String? = null,
    val first_name: String? = null,
    val last_name: String? = null,
    val email: String? = null,
    val phone: String? = null,
    val ssn: String? = null,
    val license_number: String? = null,
    val passport_number: String? = null
)
data class VaultItemOut(
    val id: String,
    val folder_id: String? = null,
    val item_type: String,
    val name: String,
    val favorite: Boolean = false,
    val username: String? = null,
    val password: String? = null,
    val totp_secret: String? = null,
    val has_totp: Boolean = false,
    val uris: List<String> = emptyList(),
    val notes: String? = null,
    val cardholder_name: String? = null,
    val card_brand: String? = null,
    val card_number: String? = null,
    val card_exp_month: String? = null,
    val card_exp_year: String? = null,
    val card_cvv: String? = null,
    val identity_title: String? = null,
    val first_name: String? = null,
    val middle_name: String? = null,
    val last_name: String? = null,
    val email: String? = null,
    val phone: String? = null,
    val address1: String? = null,
    val address2: String? = null,
    val city: String? = null,
    val state: String? = null,
    val postal_code: String? = null,
    val country: String? = null,
    val ssn: String? = null,
    val license_number: String? = null,
    val passport_number: String? = null,
    val password_changed_at: String? = null,
    val deleted_at: String? = null,
    val created_at: String,
    val updated_at: String? = null
)
data class VaultTotpOut(val code: String, val period: Int = 30, val remaining: Int)
data class VaultHistoryOut(val id: String, val password: String, val created_at: String)
data class VaultGenerateIn(
    val kind: String = "password",
    val length: Int = 16,
    val uppercase: Boolean = true,
    val lowercase: Boolean = true,
    val numbers: Boolean = true,
    val symbols: Boolean = true,
    val avoid_ambiguous: Boolean = true,
    val word_count: Int = 4,
    val separator: String = "-"
)
data class VaultGenerateOut(val value: String, val score: Int, val length: Int)
data class VaultHealthIssue(
    val item_id: String,
    val name: String,
    val username: String? = null,
    val reason: String
)
data class VaultHealthOut(
    val weak: List<VaultHealthIssue> = emptyList(),
    val reused: List<VaultHealthIssue> = emptyList(),
    val no_totp: List<VaultHealthIssue> = emptyList(),
    val old: List<VaultHealthIssue> = emptyList(),
    val total_logins: Int = 0
)
data class VaultSendCreate(
    val name: String,
    val send_type: String = "text",
    val text: String? = null,
    val item_id: String? = null,
    val notes: String? = null,
    val pin: String? = null,
    val expires_in_hours: Int = 48,
    val max_views: Int? = null
)
data class VaultSendOut(
    val id: String,
    val token: String,
    val name: String,
    val send_type: String,
    val expires_at: String,
    val max_views: Int? = null,
    val view_count: Int = 0,
    val revoked: Boolean = false,
    val has_pin: Boolean = false,
    val created_at: String
)

data class PersonUpdate(
    val allergies: String? = null,
    val conditions: String? = null,
    val emergency_name: String? = null,
    val emergency_phone: String? = null,
    val abha_id: String? = null,
    val ayushman_id: String? = null,
    val blood_group: String? = null
)

// ---------- Money Manager ----------
data class FinanceAccountOut(
    val id: String,
    val name: String,
    val account_type: String,
    val currency: String = "INR",
    val opening_balance: Double = 0.0,
    val credit_limit: Double? = null,
    val institution: String? = null,
    val last4: String? = null,
    val archived: Boolean = false,
    val balance: Double = 0.0,
    val is_liability: Boolean = false,
    val created_at: String = ""
)
data class FinanceAccountIn(
    val name: String,
    val account_type: String = "cash",
    val opening_balance: Double = 0.0,
    val credit_limit: Double? = null
)
data class FinanceCategoryOut(
    val id: String,
    val name: String,
    val kind: String,
    val color: String? = null,
    val is_system: Boolean = false,
    val account_id: String? = null,
    val account_name: String? = null,
    val parent_id: String? = null,
    val parent_name: String? = null,
    val scope: String = "general"
)
data class FinanceCategoryIn(
    val name: String,
    val kind: String = "expense",
    val account_id: String? = null,
    val parent_id: String? = null
)
data class FinanceTxnOut(
    val id: String,
    val account_id: String,
    val account_name: String = "",
    val to_account_id: String? = null,
    val to_account_name: String? = null,
    val category_id: String? = null,
    val category_name: String? = null,
    val category_color: String? = null,
    val txn_type: String,
    val amount: Double,
    val currency: String = "INR",
    val txn_date: String,
    val txn_time: String? = null,
    val payee: String? = null,
    val notes: String? = null,
    val description: String? = null,
    val payment_method: String? = null,
    val tags: String? = null,
    val source: String = "manual",
    val has_image: Boolean = false,
    val created_at: String = ""
)
data class FinanceTxnIn(
    val account_id: String,
    val to_account_id: String? = null,
    val category_id: String? = null,
    val txn_type: String = "expense",
    val amount: Double,
    val txn_date: String,
    val txn_time: String? = null,
    val payee: String? = null,
    val notes: String? = null,
    val description: String? = null,
    val payment_method: String? = null,
    val frequency: String? = null
)
data class FinanceSummaryOut(
    val year_month: String,
    val income: Double = 0.0,
    val expense: Double = 0.0,
    val total: Double = 0.0,
    val opening: Double = 0.0,
    val closing: Double = 0.0,
    val prev_month: String? = null,
    val prev_income: Double = 0.0,
    val prev_expense: Double = 0.0,
    val prev_total: Double = 0.0,
    val assets: Double = 0.0,
    val liabilities: Double = 0.0,
    val net: Double = 0.0,
    val pending_messages: Int = 0
)
data class FinanceReportRow(val name: String, val amount: Double, val pct: Double, val color: String? = null)
data class FinanceReportOut(
    val year_month: String,
    val kind: String,
    val total: Double = 0.0,
    val rows: List<FinanceReportRow> = emptyList()
)
data class FinanceEmiIn(
    val name: String,
    val kind: String = "emi",
    val account_id: String,
    val category_id: String? = null,
    val amount: Double,
    val start_date: String,
    val end_date: String,
    val day_of_month: Int? = null,
    val auto_post: Boolean = true,
    val notify_days: Int = 2,
    val notes: String? = null
)
data class FinanceEmiOut(
    val id: String,
    val name: String,
    val kind: String = "emi",
    val kind_label: String = "EMI",
    val account_id: String,
    val account_name: String = "",
    val category_id: String? = null,
    val category_name: String? = null,
    val amount: Double,
    val start_date: String,
    val end_date: String,
    val day_of_month: Int = 1,
    val next_due: String? = null,
    val auto_post: Boolean = true,
    val notify_days: Int = 2,
    val notes: String? = null,
    val active: Boolean = true,
    val status: String = "pending",
    val total_installments: Int = 0,
    val paid_count: Int = 0,
    val remaining: Int = 0,
    val created_at: String = ""
)
data class FinanceAiKeyIn(
    val name: String,
    val kind: String,
    val api_key: String? = null,
    val base_url: String? = null,
    val model: String? = null,
    val is_default: Boolean = false
)
data class FinanceAiKeyOut(
    val id: String,
    val name: String,
    val kind: String,
    val base_url: String? = null,
    val model: String? = null,
    val is_default: Boolean = false,
    val enabled: Boolean = true,
    val has_key: Boolean = false
)
data class FinanceMessageIn(
    val text: String,
    val account_id: String? = null,
    val auto_accept: Boolean = false
)
data class FinanceMessageOut(
    val id: String,
    val raw_text: String,
    val direction: String,
    val amount: Double? = null,
    val payee: String? = null,
    val txn_date: String? = null,
    val payment_method: String? = null,
    val category_id: String? = null,
    val suggested_category: String? = null,
    val confidence: Double? = null,
    val provider_used: String? = null,
    val status: String,
    val transaction_id: String? = null,
    val created_at: String = ""
)

// ---------- Document Vault / Locker ----------
data class LockerFileOut(
    val id: String,
    val item_id: String,
    val original_filename: String,
    val file_type: String? = null,
    val file_size: Long? = null,
    val created_at: String = ""
)

data class LockerItemOut(
    val id: String,
    val doc_type: String,
    val type_label: String,
    val custom_type: String? = null,
    val title: String,
    val holder_name: String? = null,
    val issuer: String? = null,
    val id_number: String? = null,
    val issued_on: String? = null,
    val expiry_date: String? = null,
    val tags: String? = null,
    val notes: String? = null,
    val pinned: Boolean = false,
    val file_type: String? = null,
    val file_size: Long? = null,
    val file_count: Int = 0,
    val created_at: String = ""
)

data class LockerItemUpdate(
    val title: String? = null,
    val doc_type: String? = null,
    val custom_type: String? = null,
    val holder_name: String? = null,
    val issuer: String? = null,
    val id_number: String? = null,
    val issued_on: String? = null,
    val expiry_date: String? = null,
    val tags: String? = null,
    val notes: String? = null,
    val pinned: Boolean? = null
)

data class LockerTypeOut(
    val id: String,
    val label: String,
    val count: Int = 0
)

data class LockerSummaryOut(
    val total: Int = 0,
    val expiring: Int = 0,
    val types: List<LockerTypeOut> = emptyList()
)

// ---------- URL Vault ----------
data class UrlCategoryOut(
    val id: String,
    val name: String,
    val color: String? = null,
    val sort_order: Int = 0,
    val is_default: Boolean = false,
    val count: Int = 0
)

data class UrlCategoryIn(
    val name: String,
    val color: String? = null,
    val sort_order: Int? = null
)

data class UrlTagOut(
    val id: String,
    val name: String,
    val color: String? = null,
    val count: Int = 0
)

data class UrlTagIn(
    val name: String,
    val color: String? = null
)

data class UrlItemOut(
    val id: String,
    val title: String,
    val url: String,
    val category_id: String? = null,
    val category_name: String? = null,
    val category_color: String? = null,
    val tags: List<UrlTagOut> = emptyList(),
    val notes: String? = null,
    val favorite: Boolean = false,
    val og_title: String? = null,
    val og_description: String? = null,
    val og_image: String? = null,
    val og_site_name: String? = null,
    val favicon_url: String? = null,
    val created_at: String = "",
    val updated_at: String? = null
)

data class UrlItemIn(
    val url: String,
    val title: String? = null,
    val category_id: String? = null,
    val tag_ids: List<String> = emptyList(),
    val notes: String? = null,
    val favorite: Boolean = false,
    val fetch_preview: Boolean = true
)

data class UrlItemUpdate(
    val url: String? = null,
    val title: String? = null,
    val category_id: String? = null,
    val tag_ids: List<String>? = null,
    val notes: String? = null,
    val favorite: Boolean? = null,
    val fetch_preview: Boolean? = null
)

data class UrlShareCreate(
    val expires_in_hours: Int = 168,
    val max_views: Int? = null
)

data class UrlShareOut(
    val id: String,
    val token: String,
    val item_id: String,
    val item_title: String? = null,
    val item_url: String? = null,
    val expires_at: String = "",
    val max_views: Int? = null,
    val view_count: Int = 0,
    val revoked: Boolean = false,
    val created_at: String = ""
)

data class UrlSummaryOut(
    val total: Int = 0,
    val favorites: Int = 0,
    val categories: List<UrlCategoryOut> = emptyList(),
    val tags: List<UrlTagOut> = emptyList()
)

// ---------- Shared AI ----------
data class AiStatusOut(
    val count: Int = 0,
    val has_default: Boolean = false,
    val default_name: String? = null,
    val default_kind: String? = null,
    val default_id: String? = null,
    val default_model: String? = null
)

data class AiProviderIn(
    val name: String,
    val kind: String,
    val api_key: String? = null,
    val base_url: String? = null,
    val model: String? = null,
    val is_default: Boolean = false
)

data class AiProviderOut(
    val id: String,
    val name: String,
    val kind: String,
    val base_url: String? = null,
    val model: String? = null,
    val is_default: Boolean = false,
    val enabled: Boolean = true,
    val has_key: Boolean = false
)

data class AiConnectionTestOut(
    val ok: Boolean = true,
    val name: String? = null,
    val kind: String? = null,
    val model: String? = null,
    val sample: String = "",
    val prompt_tokens: Int? = null,
    val completion_tokens: Int? = null,
    val total_tokens: Int? = null
)

data class AiChatIn(
    val message: String,
    val thread_id: String? = null
)

data class AiChatMessageOut(
    val id: String,
    val role: String,
    val content: String,
    val created_at: String = ""
)

data class AiChatThreadOut(
    val id: String,
    val title: String,
    val created_at: String = "",
    val updated_at: String = "",
    val preview: String? = null
)

data class AiChatThreadDetailOut(
    val id: String,
    val title: String,
    val created_at: String = "",
    val updated_at: String = "",
    val messages: List<AiChatMessageOut> = emptyList()
)

data class AiChatReplyOut(
    val thread_id: String,
    val title: String,
    val reply: String,
    val messages: List<AiChatMessageOut> = emptyList()
)

data class AiUsageLogOut(
    val id: String,
    val client: String,
    val client_label: String,
    val provider_name: String? = null,
    val provider_kind: String? = null,
    val model: String? = null,
    val prompt_tokens: Int? = null,
    val completion_tokens: Int? = null,
    val total_tokens: Int? = null,
    val latency_ms: Int? = null,
    val ok: Boolean = true,
    val error: String? = null,
    val request_text: String? = null,
    val response_text: String? = null,
    val created_at: String = ""
)

data class AiUsageSummaryOut(
    val days: Int = 30,
    val calls: Int = 0,
    val ok: Int = 0,
    val failed: Int = 0,
    val prompt_tokens: Int = 0,
    val completion_tokens: Int = 0,
    val total_tokens: Int = 0,
    val by_client: Map<String, Int> = emptyMap()
)

data class ExpenseAnalyserStatusOut(
    val connected: Boolean = false,
    val email: String? = null,
    val server_oauth: Boolean = false,
    val sync_query: String? = null,
    val enabled: Boolean = false,
    val hour: Int = 6,
    val last_sync_at: String? = null,
    val last_ok: Boolean? = null,
    val last_error: String? = null,
    val syncing: Boolean = false,
    val retagging: Boolean = false,
    val pending: Int = 0,
    val matched: Int = 0,
    val missed: Int = 0,
    val posted: Int = 0,
    val corrected: Int = 0,
    val pending_pdfs: Int = 0
)

data class ExpenseAnalyserItemOut(
    val id: String,
    val gmail_message_id: String = "",
    val kind: String = "alert",
    val subject: String? = null,
    val from_addr: String? = null,
    val received_at: String? = null,
    val raw_snippet: String? = null,
    val direction: String = "debit",
    val amount: Double? = null,
    val currency: String = "INR",
    val payee: String? = null,
    val txn_date: String? = null,
    val payment_method: String? = null,
    val suggested_category: String? = null,
    val confidence: Double? = null,
    val status: String = "pending",
    val match_txn_id: String? = null,
    val finance_txn_id: String? = null,
    val notes: String? = null,
    val created_at: String = ""
)

data class ExpenseAnalyserItemUpdate(
    val direction: String? = null,
    val amount: Double? = null,
    val payee: String? = null,
    val txn_date: String? = null,
    val payment_method: String? = null,
    val suggested_category: String? = null,
    val notes: String? = null
)

data class ExpenseAnalyserSyncOut(
    val fetched: Int = 0,
    val created: Int = 0,
    val skipped: Int = 0,
    val matched: Int = 0,
    val missed: Int = 0,
    val error: String? = null,
    val pdfs: Int = 0,
    val pdf_rows: Int = 0,
    val pdf_locked: Int = 0
)

data class ExpenseAnalyserPdfImportOut(
    val ok: Boolean = true,
    val started: Boolean = true,
    val fetched: Int = 0,
    val pdfs: Int = 0,
    val created_rows: Int = 0,
    val skipped: Int = 0,
    val needs_password: Int = 0,
    val failed: Int = 0,
    val parsed: Int = 0
)

data class ShopPdfPasswordIn(
    val identifier: String,
    val password: String,
    val account_type: String = "bank",
    val last_4_digits: String? = null
)

data class ShopPdfPasswordOut(
    val id: String,
    val identifier: String,
    val account_type: String = "bank",
    val last_4_digits: String? = null,
    val created_at: String = ""
)

data class ShopStatementPdfOut(
    val id: String,
    val filename: String? = null,
    val subject: String? = null,
    val from_addr: String? = null,
    val received_at: String? = null,
    val status: String = "parsed",
    val error: String? = null,
    val bank_hint: String? = null,
    val created_count: Int = 0,
    val skipped_count: Int = 0,
    val created_at: String = ""
)

data class ExpenseAnalyserSyncLogOut(
    val id: String,
    val trigger: String = "manual",
    val ok: Boolean = true,
    val fetched: Int = 0,
    val created: Int = 0,
    val skipped: Int = 0,
    val matched: Int = 0,
    val missed: Int = 0,
    val error: String? = null,
    val started_at: String = "",
    val finished_at: String = ""
)

data class ExpenseAnalyserPostIn(
    val account_id: String? = null,
    val category_id: String? = null,
    val subcategory_id: String? = null,
    val new_category: String? = null,
    val new_subcategory: String? = null
)

data class ExpenseAnalyserPostOut(
    val ok: Boolean = true,
    val finance_txn_id: String? = null
)

data class ExpenseAnalyserScheduleIn(
    val enabled: Boolean = false,
    val hour: Int = 6
)

data class ExpenseAnalyserQueryIn(
    val sync_query: String? = null
)

data class ExpenseAnalyserClearOut(
    val deleted: Int = 0
)

data class ExpenseAnalyserReconcileOut(
    val ok: Boolean = true,
    val updated: Int = 0
)

data class ExpenseAnalyserSlice(
    val name: String = "",
    val amount: Double = 0.0,
    val count: Int = 0,
    val pct: Double = 0.0,
    val color: String? = null
)

data class ExpenseAnalyserDayBar(
    val date: String = "",
    val label: String = "",
    val amount: Double = 0.0,
    val pct: Double = 0.0
)

data class ExpenseAnalyserStatusSlice(
    val name: String = "",
    val count: Int = 0,
    val color: String? = null
)

data class ExpenseAnalyserInsightsOut(
    val year_month: String = "",
    val label: String = "",
    val prev: String = "",
    val next: String = "",
    val debit_total: Double = 0.0,
    val credit_total: Double = 0.0,
    val item_count: Int = 0,
    val by_category: List<ExpenseAnalyserSlice> = emptyList(),
    val by_method: List<ExpenseAnalyserSlice> = emptyList(),
    val by_day: List<ExpenseAnalyserDayBar> = emptyList(),
    val by_status: List<ExpenseAnalyserStatusSlice> = emptyList(),
    val top_payees: List<ExpenseAnalyserSlice> = emptyList()
)

// ---------- Shopping List ----------
data class ShopSummaryOut(
    val lists: Int = 0,
    val open_lists: Int = 0,
    val pending_items: Int = 0,
    val pending_statements: Int = 0,
    val friends: Int = 0,
    val inbox: Int = 0
)

data class ShopListOut(
    val id: String,
    val name: String,
    val description: String? = null,
    val completed: Boolean = false,
    val total_amount: Double = 0.0,
    val item_count: Int = 0,
    val checked_count: Int = 0,
    val pending_count: Int = 0,
    val receipt_count: Int = 0,
    val share_token: String? = null,
    val created_at: String = "",
    val updated_at: String? = null,
    val completed_at: String? = null,
    val revision: String? = null,
    val items: List<ShopItemOut>? = null,
    val receipts: List<ShopReceiptOut>? = null
)

data class ShopReceiptOut(
    val id: String,
    val list_id: String = "",
    val original_name: String? = null,
    val image_mime: String? = null,
    val is_image: Boolean = true,
    val created_at: String = ""
)

data class ShopListIn(
    val name: String,
    val description: String? = null
)

data class ShopItemOut(
    val id: String,
    val list_id: String,
    val name: String,
    val quantity: Double = 1.0,
    val unit: String? = null,
    val price: Double? = null,
    val checked: Boolean = false,
    val emoji: String? = null,
    val category: String? = null,
    val notes: String? = null,
    val added_by: String? = null,
    val guest_name: String? = null,
    val added_by_name: String? = null,
    val status: String = "approved",
    val created_at: String = ""
)

data class ShopGroceryItemOut(
    val english: String,
    val malayalam: String? = null,
    val emoji: String = "🛒",
    val category: String? = null,
    val matched: Boolean = false
)

data class ShopItemIn(
    val name: String,
    val quantity: Double? = 1.0,
    val unit: String? = null,
    val price: Double? = null,
    val emoji: String? = null,
    val category: String? = null,
    val notes: String? = null
)

data class ShopItemUpdate(
    val name: String? = null,
    val quantity: Double? = null,
    val unit: String? = null,
    val price: Double? = null
)

data class ShopShareOut(
    val token: String,
    val url: String,
    val list_id: String
)

data class ShopContactOut(
    val id: String,
    val name: String,
    val email: String? = null,
    val phone: String? = null,
    val relation: String? = null,
    val created_at: String = ""
)

data class ShopContactIn(
    val name: String,
    val email: String? = null,
    val phone: String? = null,
    val relation: String? = null
)

data class ShopSendOut(
    val id: String,
    val sender_id: String,
    val receiver_id: String,
    val sender_name: String? = null,
    val receiver_name: String? = null,
    val list_name: String? = null,
    val status: String,
    val message: String? = null,
    val sent_at: String = ""
)
