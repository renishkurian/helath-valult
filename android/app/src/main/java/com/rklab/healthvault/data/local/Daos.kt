package com.rklab.healthvault.data.local

import androidx.room.*
import kotlinx.coroutines.flow.Flow

@Dao
interface PersonDao {
    @Query("SELECT * FROM people")
    suspend fun getAllOnce(): List<PersonEntity>

    @Upsert
    suspend fun upsertAll(people: List<PersonEntity>)

    @Query("DELETE FROM people")
    suspend fun deleteAll()
}

@Dao
interface CardDao {
    @Query("SELECT * FROM cards WHERE person_id = :personId ORDER BY created_at DESC")
    suspend fun getByPersonOnce(personId: String): List<CardEntity>

    @Upsert
    suspend fun upsertAll(cards: List<CardEntity>)

    @Query("DELETE FROM cards WHERE person_id = :personId")
    suspend fun deleteByPerson(personId: String)

    @Query("DELETE FROM cards")
    suspend fun deleteAll()

    @Query("SELECT DISTINCT hospital_name FROM cards WHERE hospital_name IS NOT NULL AND hospital_name != ''")
    fun getHospitalNames(): Flow<List<String>>
}

@Dao
interface DocumentDao {
    @Query("SELECT * FROM documents WHERE person_id = :personId ORDER BY created_at DESC")
    suspend fun getByPersonOnce(personId: String): List<DocumentEntity>

    @Query("SELECT * FROM documents WHERE person_id = :personId AND category = :category ORDER BY created_at DESC")
    suspend fun getByPersonAndCategory(personId: String, category: String): List<DocumentEntity>

    @Upsert
    suspend fun upsertAll(docs: List<DocumentEntity>)

    @Query("DELETE FROM documents WHERE person_id = :personId")
    suspend fun deleteByPerson(personId: String)

    @Query("DELETE FROM documents")
    suspend fun deleteAll()

    @Query("SELECT DISTINCT hospital_name FROM documents WHERE hospital_name IS NOT NULL AND hospital_name != ''")
    fun getHospitalNames(): Flow<List<String>>
}

@Dao
interface ReminderDao {
    @Query("SELECT * FROM reminders ORDER BY remind_at ASC")
    suspend fun getAllOnce(): List<ReminderEntity>

    @Query("SELECT * FROM reminders WHERE person_id = :personId ORDER BY remind_at ASC")
    suspend fun getByPersonOnce(personId: String): List<ReminderEntity>

    @Upsert
    suspend fun upsertAll(reminders: List<ReminderEntity>)

    @Query("DELETE FROM reminders WHERE id = :id")
    suspend fun deleteById(id: String)

    @Query("DELETE FROM reminders")
    suspend fun deleteAll()
}

@Dao
interface PendingUploadDao {
    @Insert
    suspend fun insert(upload: PendingUploadEntity): Long

    @Query("SELECT * FROM pending_uploads ORDER BY queued_at ASC")
    suspend fun getAll(): List<PendingUploadEntity>

    @Query("SELECT COUNT(*) FROM pending_uploads")
    fun count(): Flow<Int>

    @Delete
    suspend fun delete(upload: PendingUploadEntity)

    @Query("DELETE FROM pending_uploads")
    suspend fun deleteAll()
}
