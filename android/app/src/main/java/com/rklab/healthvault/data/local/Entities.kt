package com.rklab.healthvault.data.local

import androidx.room.Entity
import androidx.room.PrimaryKey

// ---------- People ----------
@Entity(tableName = "people")
data class PersonEntity(
    @PrimaryKey val id: String,
    val name: String,
    val relation: String,
    val dob: String?,
    val blood_group: String?,
    val avatar_initials: String?
)

// ---------- Hospital Cards ----------
@Entity(tableName = "cards")
data class CardEntity(
    @PrimaryKey val id: String,
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

// ---------- Documents (metadata only — files stay on Pi) ----------
@Entity(tableName = "documents")
data class DocumentEntity(
    @PrimaryKey val id: String,
    val person_id: String,
    val category: String,
    val custom_category: String?,
    val title: String,
    val hospital_name: String?,
    val doc_date: String?,
    val expiry_date: String?,
    val tags: String?,
    val version: Int,
    val file_type: String?,
    val file_size: Long?,
    val file_count: Int,
    val notes: String?,
    val created_at: String
)

// ---------- Reminders ----------
@Entity(tableName = "reminders")
data class ReminderEntity(
    @PrimaryKey val id: String,
    val person_id: String,
    val document_id: String?,
    val title: String,
    val description: String?,
    val remind_at: String,
    val repeat_rule: String,
    val is_active: Boolean
)

// ---------- Pending uploads (created while offline) ----------
@Entity(tableName = "pending_uploads")
data class PendingUploadEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val person_id: String,
    val category: String,   // matches DocCategory enum name lowercase
    val custom_category: String?,
    val title: String,
    val hospital_name: String?,
    val doc_date: String?,
    val expiry_date: String?,
    val tags: String?,
    val notes: String?,
    val file_path: String,  // absolute path to the local file copy
    val mime_type: String,
    val queued_at: Long = System.currentTimeMillis()
)
