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
    class TotpNeeded(val totpToken: String) : Exception("TOTP_REQUIRED")

    suspend fun login(email: String, password: String) {
        val res = api.login(email, password)
        if (res.totp_required) throw TotpNeeded(res.totp_token.orEmpty())
        tokenManager.saveTokens(res.access_token, res.refresh_token)
        runCatching { me() }
    }

    suspend fun verifyTotp(totpToken: String, code: String) {
        val res = api.totpVerify(TotpVerifyIn(totpToken, code))
        tokenManager.saveTokens(res.access_token, res.refresh_token)
        runCatching { me() }
    }

    suspend fun register(email: String, password: String, fullName: String) {
        val res = api.register(RegisterRequest(email, password, fullName))
        tokenManager.saveTokens(res.access_token, res.refresh_token)
        runCatching { me() }
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
            com.rklab.healthvault.data.VaultAutofillStore.clear(appContext)
        }
    }

    suspend fun me(): UserOut {
        val user = api.me()
        tokenManager.setRole(user.role)
        return user
    }

    suspend fun inviteViewer(email: String, password: String, fullName: String, personIds: List<String> = emptyList()) =
        api.inviteViewer(InviteViewerRequest(email, password, fullName, personIds))

    suspend fun totpSetup() = api.totpSetup()
    suspend fun totpEnable(code: String) = api.totpEnable(TotpVerifyIn(code = code))
    suspend fun updatePerson(id: String, update: PersonUpdate) = api.updatePerson(id, update)
    suspend fun enableIce(personId: String) = api.enableIce(personId)
    suspend fun createSharePack(title: String, documentIds: List<String>, pin: String? = null, hours: Int = 48) =
        api.createSharePack(SharePackCreate(title, documentIds, hours, pin = pin))
    suspend fun listSharePacks() = api.listSharePacks()
    suspend fun revokeSharePack(id: String) = api.revokeSharePack(id)
    suspend fun listMedicines(personId: String) = api.listMedicines(personId)
    suspend fun addMedicine(body: MedicineIn) = api.addMedicine(body)
    suspend fun deleteMedicine(id: String) = api.deleteMedicine(id)
    suspend fun listVaccinations(personId: String) = api.listVaccinations(personId)
    suspend fun addVaccination(body: VaccinationIn) = api.addVaccination(body)
    suspend fun listVisits(personId: String) = api.listVisits(personId)
    suspend fun addVisit(body: VisitIn) = api.addVisit(body)
    suspend fun listClaims(personId: String) = api.listClaims(personId)
    suspend fun addClaim(body: ClaimIn) = api.addClaim(body)
    suspend fun yearlySpend(personId: String) = api.yearlySpend(personId)
    suspend fun listDoctors() = api.listDoctors()
    suspend fun addDoctor(body: DoctorIn) = api.addDoctor(body)
    suspend fun listGrowth(personId: String) = api.listGrowth(personId)
    suspend fun addGrowth(body: GrowthIn) = api.addGrowth(body)
    suspend fun listUhids(personId: String) = api.listUhids(personId)
    suspend fun addUhid(body: UhidIn) = api.addUhid(body)
    suspend fun timeline(personId: String) = api.timeline(personId)
    suspend fun storageStats() = api.storageStats()

    // ---------- Password Vault ----------
    suspend fun listVaultFolders() = api.listVaultFolders()
    suspend fun createVaultFolder(name: String) = api.createVaultFolder(VaultFolderIn(name))
    suspend fun deleteVaultFolder(id: String) = api.deleteVaultFolder(id)
    suspend fun listVaultItems(
        q: String? = null,
        itemType: String? = null,
        folderId: String? = null,
        favorite: Boolean = false
    ): List<VaultItemOut> {
        val items = api.listVaultItems(q, itemType, folderId, favorite)
        com.rklab.healthvault.data.VaultAutofillStore.save(appContext, items)
        return items
    }
    suspend fun createVaultItem(body: VaultItemIn): VaultItemOut {
        val item = api.createVaultItem(body)
        runCatching { listVaultItems() }
        return item
    }
    suspend fun getVaultItem(id: String) = api.getVaultItem(id)
    suspend fun updateVaultItem(id: String, body: VaultItemUpdate): VaultItemOut {
        val item = api.updateVaultItem(id, body)
        runCatching { listVaultItems() }
        return item
    }
    suspend fun trashVaultItem(id: String) {
        api.trashVaultItem(id)
        runCatching { listVaultItems() }
    }
    suspend fun restoreVaultItem(id: String) = api.restoreVaultItem(id)
    suspend fun deleteVaultItemForever(id: String) = api.deleteVaultItemForever(id)
    suspend fun favoriteVaultItem(id: String) = api.favoriteVaultItem(id)
    suspend fun unfavoriteVaultItem(id: String) = api.unfavoriteVaultItem(id)
    suspend fun vaultItemTotp(id: String) = api.vaultItemTotp(id)
    suspend fun vaultItemHistory(id: String) = api.vaultItemHistory(id)
    suspend fun generatePassword(body: VaultGenerateIn = VaultGenerateIn()) = api.generatePassword(body)
    suspend fun vaultHealth() = api.vaultHealth()
    suspend fun listVaultTrash() = api.listVaultTrash()
    suspend fun emptyVaultTrash() = api.emptyVaultTrash()
    suspend fun listVaultSends() = api.listVaultSends()
    suspend fun createVaultSend(body: VaultSendCreate) = api.createVaultSend(body)
    suspend fun revokeVaultSend(id: String) = api.revokeVaultSend(id)
    suspend fun labAlerts(personId: String) = api.labAlerts(personId)
    suspend fun favoriteDocument(id: String) = api.favoriteDocument(id)
    suspend fun unfavoriteDocument(id: String) = api.unfavoriteDocument(id)
    suspend fun bulkDeleteDocuments(ids: List<String>) = api.bulkDeleteDocuments(BulkIds(ids))
    suspend fun bulkTagDocuments(ids: List<String>, tags: String) = api.bulkTagDocuments(BulkIds(ids, tags))
    suspend fun recentDocuments() = api.recentDocuments()
    suspend fun listDocumentsFiltered(
        personId: String?,
        category: DocCategory? = null,
        year: String? = null,
        hospital: String? = null,
        tag: String? = null,
        expiring: Boolean = false,
        favorite: Boolean = false
    ) = api.listDocuments(personId, category?.name?.lowercase(), tag, year, hospital, expiring, favorite)

    suspend fun listVaultMembers() = api.listVaultMembers()

    suspend fun removeVaultMember(id: String) = api.removeVaultMember(id)

    val isViewer: Boolean get() = tokenManager.getRole() == "viewer"

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
                    expiry_date = expiryDate,
                    tags = tags,
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
    suspend fun createShareLink(documentId: String, expiresInHours: Int = 48, maxViews: Int? = null, pin: String? = null) =
        api.createShareLink(com.rklab.healthvault.data.model.ShareLinkCreate(documentId, expiresInHours, maxViews, pin))

    suspend fun listMyShareLinks(documentId: String? = null) = api.listMyShareLinks(documentId)

    suspend fun getShareLink(id: String) = api.getShareLink(id)

    suspend fun revokeShareLink(id: String) = api.revokeShareLink(id)

    // ---------- Audit log ----------
    suspend fun listAuditLog(documentId: String? = null, limit: Int = 100) =
        api.listAuditLog(documentId, limit)

    // ---------- Backup ----------
    suspend fun exportBackup(destination: File, personId: String? = null, password: String? = null): File {
        val body = api.exportBackup(personId, password)
        body.byteStream().use { input ->
            destination.outputStream().use { output -> input.copyTo(output) }
        }
        return destination
    }

    suspend fun restoreBackup(file: File, password: String?) {
        val part = MultipartBody.Part.createFormData(
            "file", file.name, file.asRequestBody("application/octet-stream".toMediaTypeOrNull())
        )
        api.restoreBackup(part, password?.toRequestBody("text/plain".toMediaTypeOrNull()))
    }

    suspend fun labTrends(personId: String, metric: String? = null): List<LabTrend> =
        api.labTrends(personId, metric)

    suspend fun getDocument(id: String): DocumentOut = api.getDocument(id)

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
                    expiryDate = upload.expiry_date?.let { text(it) },
                    tags = upload.tags?.let { text(it) },
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
