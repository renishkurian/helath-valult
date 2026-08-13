package com.rklab.healthvault.data.model

import com.google.gson.annotations.SerializedName

// ---------- Auth ----------
data class RegisterRequest(val email: String, val password: String, val full_name: String)
data class LoginResponse(val access_token: String, val refresh_token: String, val token_type: String)
data class UserOut(
    val id: String,
    val email: String,
    val full_name: String,
    val role: String = "owner",
    val vault_owner_id: String? = null
) {
    val isViewer: Boolean get() = role == "viewer"
}

data class InviteViewerRequest(val email: String, val password: String, val full_name: String)
data class DeviceTokenIn(val token: String, val platform: String = "android")

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
    val avatar_initials: String?
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
    @SerializedName("other") OTHER
}

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
    val tags: String? = null
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
    val max_views: Int? = null
)

data class ShareLinkOut(
    val id: String,
    val token: String,
    val document_id: String,
    val expires_at: String,
    val max_views: Int?,
    val view_count: Int,
    val revoked: Boolean,
    val created_at: String
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
