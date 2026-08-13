package com.rklab.healthvault.data.repository

import android.content.Context
import com.rklab.healthvault.data.ServerConfigManager
import com.rklab.healthvault.data.TokenManager
import com.rklab.healthvault.data.local.*
import com.rklab.healthvault.data.model.*
import com.rklab.healthvault.data.remote.ApiService
import com.rklab.healthvault.data.sync.ConnectivityObserver
import com.rklab.healthvault.data.sync.SyncWorker
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.launch
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.File
import java.io.IOException

/** Result type for uploadDocument — distinguishes an online success from an offline queue. */
sealed class UploadResult {
    data class Success(val doc: DocumentOut) : UploadResult()
    /** File saved to pending_uploads; will be sent when the Pi is reachable again. */
    object QueuedOffline : UploadResult()
}

class HealthVaultRepository(
    private val api: ApiService,
    val tokenManager: TokenManager,
    private val serverConfig: ServerConfigManager,
    private val db: AppDatabase,
    val connectivityObserver: ConnectivityObserver,
    private val appContext: Context
) {
    val isLoggedIn: Boolean get() = tokenManager.getAccessToken() != null

    // ---------- Offline indicators (exposed to UI) ----------

    /** Live count of uploads waiting to be sent when the server is back. */
    val pendingUploadCount: Flow<Int> = db.pendingUploadDao().count()

    /** Returns a live list of all distinct hospital names ever entered by this account. */
    fun getAllHospitals(): Flow<List<String>> = combine(
        db.documentDao().getHospitalNames(),
        db.cardDao().getHospitalNames()
    ) { docHospitals, cardHospitals ->
        (docHospitals + cardHospitals).distinct().sorted()
    }

    // ---------- Server configuration ----------
    fun isServerConfigured(): Boolean = serverConfig.isConfigured()
    fun getServerUrl(): String? = serverConfig.getServerUrl()
    fun saveServerUrl(url: String) = serverConfig.setServerUrl(url)
    fun clearServerUrl() = serverConfig.clear()
    suspend fun testServerConnection(url: String): Result<Unit> = serverConfig.testConnection(url)

    // ---------- Auth ----------
    suspend fun login(email: String, password: String) {
        val res = api.login(email, password)
        tokenManager.saveTokens(res.access_token, res.refresh_token)
    }

    suspend fun register(email: String, password: String, fullName: String) {
        val res = api.register(RegisterRequest(email, password, fullName))
        tokenManager.saveTokens(res.access_token, res.refresh_token)
    }

    fun logout() {
        tokenManager.clear()
        // Wipe the local cache so a new user doesn't see the previous user's data.
        CoroutineScope(Dispatchers.IO).launch {
            db.personDao().deleteAll()
            db.cardDao().deleteAll()
            db.documentDao().deleteAll()
            db.reminderDao().deleteAll()
            db.pendingUploadDao().deleteAll()
        }
    }

    suspend fun me(): UserOut = api.me()

    // ---------- People ----------

    /**
     * Cache-first: returns the Room cache immediately if the server is unreachable.
     * On success, updates the cache for next time.
     */
    suspend fun listPeople(): List<PersonOut> = try {
        val people = api.listPeople()
        db.personDao().upsertAll(people.map { it.toEntity() })
        people
    } catch (e: IOException) {
        db.personDao().getAllOnce().map { it.toModel() }
    }

    suspend fun addFamilyMember(name: String, relation: Relation, dob: String?, bloodGroup: String?): PersonOut {
        val person = api.addPerson(PersonCreate(name, relation, dob, bloodGroup))
        db.personDao().upsertAll(listOf(person.toEntity()))
        return person
    }

    suspend fun deletePerson(id: String) {
        api.deletePerson(id)
        db.cardDao().deleteByPerson(id)
        db.documentDao().deleteByPerson(id)
    }

    suspend fun setActivePerson(personId: String) = tokenManager.setActivePerson(personId)
    fun activePersonFlow() = tokenManager.activePersonFlow()

    // ---------- Cards ----------

    suspend fun listCards(personId: String? = null): List<CardOut> = try {
        val cards = api.listCards(personId)
        if (personId != null) {
            db.cardDao().deleteByPerson(personId)
            db.cardDao().upsertAll(cards.map { it.toEntity() })
        }
        cards
    } catch (e: IOException) {
        val cached = if (personId != null)
            db.cardDao().getByPersonOnce(personId)
        else
            emptyList()
        cached.map { it.toModel() }
    }

    suspend fun addCard(
        personId: String, hospitalName: String, ward: String?,
        bloodGroup: String?, validFrom: String?, validTill: String?,
        patientId: String?, notes: String?
    ): CardOut {
        val card = api.addCard(CardCreate(personId, hospitalName, ward, bloodGroup, validFrom, validTill, patientId, notes))
        db.cardDao().upsertAll(listOf(card.toEntity()))
        return card
    }

    suspend fun deleteCard(id: String) = api.deleteCard(id)

    // ---------- Documents ----------

    suspend fun listDocuments(personId: String? = null, category: DocCategory? = null): List<DocumentOut> = try {
        val docs = api.listDocuments(personId, category?.name?.lowercase())
        if (personId != null) {
            if (category == null) {
                db.documentDao().deleteByPerson(personId)
                db.documentDao().upsertAll(docs.map { it.toEntity() })
            } else {
                db.documentDao().upsertAll(docs.map { it.toEntity() })
            }
        }
        docs
    } catch (e: IOException) {
        val cached = when {
            personId != null && category != null ->
                db.documentDao().getByPersonAndCategory(personId, category.name.lowercase())
            personId != null ->
                db.documentDao().getByPersonOnce(personId)
            else -> emptyList()
        }
        cached.map { it.toModel() }
    }

    /**
     * Upload a document.
     * - Online → uploads to Pi immediately and returns [UploadResult.Success].
     * - Offline (IOException) → saves to pending_uploads, enqueues SyncWorker,
     *   and returns [UploadResult.QueuedOffline].
     */
    suspend fun uploadDocument(
        personId: String,
        category: DocCategory,
        customCategory: String?,
        title: String,
        hospitalName: String?,
        docDate: String?,
        notes: String?,
        files: List<File>,
        mimeTypes: List<String>,
        expiryDate: String? = null,
        tags: String? = null
    ): UploadResult {
        fun text(v: String) = v.toRequestBody("text/plain".toMediaTypeOrNull())
        val fileParts = files.mapIndexed { idx, file ->
            val mime = mimeTypes.getOrElse(idx) { "application/octet-stream" }
            MultipartBody.Part.createFormData("files", file.name, file.asRequestBody(mime.toMediaTypeOrNull()))
        }
        return try {
            val doc = api.uploadDocument(
                personId = text(personId),
                category = text(category.name.lowercase()),
                customCategory = customCategory?.let { text(it) },
                title = text(title),
                hospitalName = hospitalName?.let { text(it) },
                docDate = docDate?.let { text(it) },
                notes = notes?.let { text(it) },
                expiryDate = expiryDate?.let { text(it) },
                tags = tags?.let { text(it) },
                files = fileParts
            )
            db.documentDao().upsertAll(listOf(doc.toEntity()))
            
            if (files.isNotEmpty()) {
                val documentsDir = File(appContext.filesDir, "documents")
                documentsDir.mkdirs()
                val dest = File(documentsDir, doc.id)
                files.first().copyTo(dest, overwrite = true)
            }
            
            UploadResult.Success(doc)
        } catch (e: IOException) {
            // Queue the first file locally for offline sync
            val firstFile = files.firstOrNull() ?: return UploadResult.QueuedOffline
            db.pendingUploadDao().insert(
                PendingUploadEntity(
                    person_id = personId,
                    category = category.name.lowercase(),
                    custom_category = customCategory,
                    title = title,
                    hospital_name = hospitalName,
                    doc_date = docDate,
                    notes = notes,
                    file_path = firstFile.absolutePath,
                    mime_type = mimeTypes.firstOrNull() ?: "application/octet-stream"
                )
            )
            SyncWorker.enqueueNow(appContext)
            UploadResult.QueuedOffline
        }
    }

    suspend fun updateDocument(
        documentId: String,
        update: DocumentUpdate
    ): DocumentOut {
        val updated = api.updateDocument(documentId, update)
        db.documentDao().upsertAll(listOf(updated.toEntity()))
        return updated
    }

    suspend fun listDocumentFiles(documentId: String): List<com.rklab.healthvault.data.model.DocumentFileOut> =
        api.listDocumentFiles(documentId)

    // ---------- Versions ----------
    suspend fun replaceDocumentVersion(
        documentId: String, title: String?, notes: String?,
        files: List<File>, mimeTypes: List<String>
    ): DocumentOut {
        fun text(v: String) = v.toRequestBody("text/plain".toMediaTypeOrNull())
        val fileParts = files.mapIndexed { idx, file ->
            val mime = mimeTypes.getOrElse(idx) { "application/octet-stream" }
            MultipartBody.Part.createFormData("files", file.name, file.asRequestBody(mime.toMediaTypeOrNull()))
        }
        val doc = api.replaceDocumentVersion(documentId, title?.let { text(it) }, notes?.let { text(it) }, fileParts)
        db.documentDao().upsertAll(listOf(doc.toEntity()))
        return doc
    }

    suspend fun listDocumentVersions(documentId: String): List<com.rklab.healthvault.data.model.DocumentVersionOut> =
        api.listDocumentVersions(documentId)

    suspend fun downloadDocumentVersionFile(documentId: String, versionId: String, index: Int, destination: File): File {
        val body = api.downloadDocumentVersionFile(documentId, versionId, index)
        body.byteStream().use { input ->
            destination.outputStream().use { output -> input.copyTo(output) }
        }
        return destination
    }

    // ---------- Share links ----------
    suspend fun createShareLink(documentId: String, expiresInHours: Int = 48, maxViews: Int? = null) =
        api.createShareLink(com.rklab.healthvault.data.model.ShareLinkCreate(documentId, expiresInHours, maxViews))

    suspend fun listMyShareLinks() = api.listMyShareLinks()

    suspend fun revokeShareLink(id: String) = api.revokeShareLink(id)

    // ---------- Audit log ----------
    suspend fun listAuditLog(documentId: String? = null, limit: Int = 100) =
        api.listAuditLog(documentId, limit)

    // ---------- Backup ----------
    suspend fun exportBackup(destination: File): File {
        val body = api.exportBackup()
        body.byteStream().use { input ->
            destination.outputStream().use { output -> input.copyTo(output) }
        }
        return destination
    }

    suspend fun downloadDocumentFile(documentId: String, fileId: String, destination: File): File {
        val body = api.downloadDocumentFile(documentId, fileId)
        body.byteStream().use { input ->
            destination.outputStream().use { output -> input.copyTo(output) }
        }
        return destination
    }

    suspend fun downloadDocument(id: String, destination: File): File {
        val body = api.downloadDocument(id)
        body.byteStream().use { input ->
            destination.outputStream().use { output -> input.copyTo(output) }
        }
        return destination
    }

    suspend fun deleteDocument(id: String) {
        api.deleteDocument(id)
        // Remove from local cache
        db.documentDao().deleteAll()   // simple: next listDocuments() will repopulate
    }

    // ---------- Reminders ----------

    suspend fun listReminders(personId: String? = null, upcomingOnly: Boolean = false): List<ReminderOut> = try {
        val reminders = api.listReminders(personId, upcomingOnly)
        db.reminderDao().upsertAll(reminders.map { it.toEntity() })
        reminders
    } catch (e: IOException) {
        val cached = if (personId != null)
            db.reminderDao().getByPersonOnce(personId)
        else
            db.reminderDao().getAllOnce()
        cached.map { it.toModel() }
    }

    suspend fun addReminder(
        personId: String, title: String, description: String?,
        remindAtIso: String, repeatRule: RepeatRule, documentId: String? = null
    ): ReminderOut {
        val reminder = api.addReminder(ReminderCreate(personId, documentId, title, description, remindAtIso, repeatRule))
        db.reminderDao().upsertAll(listOf(reminder.toEntity()))
        return reminder
    }

    suspend fun deleteReminder(id: String) {
        api.deleteReminder(id)
        db.reminderDao().deleteById(id)
    }

    suspend fun completeReminder(id: String): ReminderOut {
        val updated = api.completeReminder(id)
        db.reminderDao().upsertAll(listOf(updated.toEntity()))
        return updated
    }

    // ---------- Search ----------
    suspend fun search(query: String, personId: String? = null): SearchResult = api.search(query, personId)

    // ---------- Internal: called by SyncWorker ----------

    /**
     * Full cache refresh + pending-upload drain.
     * Throws on unrecoverable error so SyncWorker can call Result.retry().
     */
    suspend fun syncAll() {
        // 1. Refresh all people
        val people = api.listPeople()
        db.personDao().upsertAll(people.map { it.toEntity() })

        // 2. Refresh cards, documents for each person
        for (person in people) {
            val cards = api.listCards(person.id)
            db.cardDao().deleteByPerson(person.id)
            db.cardDao().upsertAll(cards.map { it.toEntity() })

            val docs = api.listDocuments(person.id, null)
            db.documentDao().deleteByPerson(person.id)
            db.documentDao().upsertAll(docs.map { it.toEntity() })
        }

        // 3. Refresh reminders
        val reminders = api.listReminders()
        db.reminderDao().upsertAll(reminders.map { it.toEntity() })

        // 4. Drain pending uploads
        val pending = db.pendingUploadDao().getAll()
        for (upload in pending) {
            try {
                val file = File(upload.file_path)
                if (!file.exists()) {
                    // File was cleared by Android (e.g. cache eviction) — drop the entry.
                    db.pendingUploadDao().delete(upload)
                    continue
                }
                fun text(v: String) = v.toRequestBody("text/plain".toMediaTypeOrNull())
                val filePart = MultipartBody.Part.createFormData(
                    "file", file.name,
                    file.asRequestBody(upload.mime_type.toMediaTypeOrNull())
                )
                val doc = api.uploadDocument(
                    personId = text(upload.person_id),
                    category = text(upload.category),
                    customCategory = upload.custom_category?.let { text(it) },
                    title = text(upload.title),
                    hospitalName = upload.hospital_name?.let { text(it) },
                    docDate = upload.doc_date?.let { text(it) },
                    notes = upload.notes?.let { text(it) },
                    files = listOf(filePart)
                )
                db.documentDao().upsertAll(listOf(doc.toEntity()))
                
                val documentsDir = File(appContext.filesDir, "documents")
                documentsDir.mkdirs()
                val dest = File(documentsDir, doc.id)
                file.copyTo(dest, overwrite = true)
                
                db.pendingUploadDao().delete(upload)
            } catch (e: Exception) {
                // Leave this row in the queue; SyncWorker will retry.
            }
        }
    }
}
