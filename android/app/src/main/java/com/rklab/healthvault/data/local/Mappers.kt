package com.rklab.healthvault.data.local

import com.rklab.healthvault.data.model.*

// ---------- PersonEntity <-> PersonOut ----------
fun PersonOut.toEntity() = PersonEntity(
    id = id, name = name, relation = relation.name.lowercase(),
    dob = dob, blood_group = blood_group, avatar_initials = avatar_initials
)

fun PersonEntity.toModel() = PersonOut(
    id = id, name = name,
    relation = runCatching { Relation.valueOf(relation.uppercase()) }.getOrDefault(Relation.OTHER),
    dob = dob, blood_group = blood_group, avatar_initials = avatar_initials
)

// ---------- CardEntity <-> CardOut ----------
fun CardOut.toEntity() = CardEntity(
    id = id, person_id = person_id, hospital_name = hospital_name,
    ward = ward, blood_group = blood_group, valid_from = valid_from,
    valid_till = valid_till, patient_id = patient_id, notes = notes,
    created_at = created_at
)

fun CardEntity.toModel() = CardOut(
    id = id, person_id = person_id, hospital_name = hospital_name,
    ward = ward, blood_group = blood_group, valid_from = valid_from,
    valid_till = valid_till, patient_id = patient_id, notes = notes,
    created_at = created_at
)

// ---------- DocumentEntity <-> DocumentOut ----------
fun DocumentOut.toEntity() = DocumentEntity(
    id = id, person_id = person_id, category = category.name.lowercase(),
    custom_category = custom_category,
    title = title, hospital_name = hospital_name, doc_date = doc_date,
    file_type = file_type, file_size = file_size, file_count = file_count, 
    notes = notes, created_at = created_at
)

fun DocumentEntity.toModel() = DocumentOut(
    id = id, person_id = person_id,
    category = runCatching { DocCategory.valueOf(category.uppercase()) }.getOrDefault(DocCategory.OTHER),
    custom_category = custom_category,
    title = title, hospital_name = hospital_name, doc_date = doc_date,
    file_type = file_type, file_size = file_size, file_count = file_count, 
    notes = notes, created_at = created_at
)

// ---------- ReminderEntity <-> ReminderOut ----------
fun ReminderOut.toEntity() = ReminderEntity(
    id = id, person_id = person_id, document_id = document_id,
    title = title, description = description, remind_at = remind_at,
    repeat_rule = repeat_rule.name.lowercase(), is_active = is_active
)

fun ReminderEntity.toModel() = ReminderOut(
    id = id, person_id = person_id, document_id = document_id,
    title = title, description = description, remind_at = remind_at,
    repeat_rule = runCatching { RepeatRule.valueOf(repeat_rule.uppercase()) }.getOrDefault(RepeatRule.NONE),
    is_active = is_active
)
