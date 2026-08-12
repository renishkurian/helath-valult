package com.rklab.healthvault.data.repository

import com.rklab.healthvault.data.ServerConfigManager
import com.rklab.healthvault.data.TokenManager
import com.rklab.healthvault.data.model.*
import com.rklab.healthvault.data.remote.ApiService
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.File

class HealthVaultRepository(
    private val api: ApiService,
    private val tokenManager: TokenManager,
    private val serverConfig: ServerConfigManager
) {
    val isLoggedIn: Boolean get() = tokenManager.getAccessToken() != null

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

    fun logout() = tokenManager.clear()

    suspend fun me(): UserOut = api.me()

    // ---------- People ----------
    suspend fun listPeople(): List<PersonOut> = api.listPeople()

    suspend fun addFamilyMember(name: String, relation: Relation, dob: String?, bloodGroup: String?): PersonOut =
        api.addPerson(PersonCreate(name, relation, dob, bloodGroup))

    suspend fun deletePerson(id: String) = api.deletePerson(id)

    suspend fun setActivePerson(personId: String) = tokenManager.setActivePerson(personId)
    fun activePersonFlow() = tokenManager.activePersonFlow()

    // ---------- Cards ----------
    suspend fun listCards(personId: String? = null): List<CardOut> = api.listCards(personId)

    suspend fun addCard(
        personId: String,
        hospitalName: String,
        ward: String?,
        bloodGroup: String?,
        validFrom: String?,
        validTill: String?,
        patientId: String?,
        notes: String?
    ): CardOut = api.addCard(
        CardCreate(personId, hospitalName, ward, bloodGroup, validFrom, validTill, patientId, notes)
    )

    suspend fun deleteCard(id: String) = api.deleteCard(id)

    // ---------- Documents ----------
    suspend fun listDocuments(personId: String? = null, category: DocCategory? = null): List<DocumentOut> =
        api.listDocuments(personId, category)

    suspend fun uploadDocument(
        personId: String,
        category: DocCategory,
        title: String,
        hospitalName: String?,
        docDate: String?,
        notes: String?,
        file: File,
        mimeType: String
    ): DocumentOut {
        fun text(v: String) = v.toRequestBody("text/plain".toMediaTypeOrNull())
        val filePart = MultipartBody.Part.createFormData(
            "file", file.name, file.asRequestBody(mimeType.toMediaTypeOrNull())
        )
        return api.uploadDocument(
            personId = text(personId),
            category = text(category.name.lowercase()),
            title = text(title),
            hospitalName = hospitalName?.let { text(it) },
            docDate = docDate?.let { text(it) },
            notes = notes?.let { text(it) },
            file = filePart
        )
    }

    suspend fun downloadDocument(id: String, destination: File): File {
        val body = api.downloadDocument(id)
        body.byteStream().use { input ->
            destination.outputStream().use { output -> input.copyTo(output) }
        }
        return destination
    }

    suspend fun deleteDocument(id: String) = api.deleteDocument(id)

    // ---------- Reminders ----------
    suspend fun listReminders(personId: String? = null, upcomingOnly: Boolean = false): List<ReminderOut> =
        api.listReminders(personId, upcomingOnly)

    suspend fun addReminder(
        personId: String,
        title: String,
        description: String?,
        remindAtIso: String,
        repeatRule: RepeatRule,
        documentId: String? = null
    ): ReminderOut = api.addReminder(
        ReminderCreate(personId, documentId, title, description, remindAtIso, repeatRule)
    )

    suspend fun deleteReminder(id: String) = api.deleteReminder(id)

    // ---------- Search ----------
    suspend fun search(query: String, personId: String? = null): SearchResult = api.search(query, personId)
}
