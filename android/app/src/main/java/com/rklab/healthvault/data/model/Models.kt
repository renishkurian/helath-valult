package com.rklab.healthvault.data.model

import com.google.gson.annotations.SerializedName

// ---------- Auth ----------
data class RegisterRequest(val email: String, val password: String, val full_name: String)
data class LoginResponse(val access_token: String, val refresh_token: String, val token_type: String)
data class UserOut(val id: String, val email: String, val full_name: String)

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
    val title: String,
    val hospital_name: String?,
    val doc_date: String?,
    val file_type: String?,
    val file_size: Long?,
    val notes: String?,
    val created_at: String
)

// ---------- Reminders ----------
enum class RepeatRule {
    @SerializedName("none") NONE,
    @SerializedName("daily") DAILY,
    @SerializedName("weekly") WEEKLY,
    @SerializedName("monthly") MONTHLY
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
