package com.rklab.healthvault.ui.screens.documents

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.rklab.healthvault.data.model.DocCategory
import com.rklab.healthvault.data.model.DocumentOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.data.repository.UploadResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import retrofit2.HttpException
import java.io.File

data class DocumentsUiState(
    val loading: Boolean = true,
    val documents: List<DocumentOut> = emptyList(),
    val uploading: Boolean = false,
    val error: String? = null
)

/**
 * Turns a raw exception into something you can actually act on, instead of
 * a canned "something went wrong". Retrofit's HttpException carries the
 * real HTTP status + the server's response body (FastAPI's {"detail": ...}
 * for 4xx/5xx), which is what you want to see when a save silently "does
 * nothing" — a 401 (expired session), 413 (file too big), 422 (bad field),
 * and a dropped network connection all need different fixes.
 */
private fun describeError(e: Exception): String = when (e) {
    is HttpException -> {
        val body = try { e.response()?.errorBody()?.string() } catch (_: Exception) { null }
        val detail = body?.let { Regex("\"detail\"\\s*:\\s*\"([^\"]*)\"").find(it)?.groupValues?.get(1) }
        when (e.code()) {
            401 -> "Session expired — please log in again."
            413 -> "That file is too large for the server to accept."
            422 -> "The server rejected the document details" + (detail?.let { ": $it" } ?: " (check required fields).")
            in 500..599 -> "Server error (${e.code()})" + (detail?.let { ": $it" } ?: ". Check the backend logs on your Pi.")
            else -> "Request failed (HTTP ${e.code()})" + (detail?.let { ": $it" } ?: "")
        }
    }
    else -> e.message ?: "Something went wrong."
}

class DocumentsViewModel(private val repository: HealthVaultRepository) : ViewModel() {
    private val _state = MutableStateFlow(DocumentsUiState())
    val state: StateFlow<DocumentsUiState> = _state

    /** true when device has no internet / Pi unreachable. */
    val isOffline: StateFlow<Boolean> = repository.connectivityObserver.isConnected
        .map { !it }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), false)

    /** Live count of queued offline uploads. */
    val pendingUploadCount: StateFlow<Int> = repository.pendingUploadCount
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), 0)

    val hospitals: StateFlow<List<String>> = repository.getAllHospitals()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    val people: StateFlow<List<com.rklab.healthvault.data.model.PersonOut>> = kotlinx.coroutines.flow.flow {
        emit(repository.listPeople()) // Simple fetch; real app might observe a DB flow
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    fun setActivePerson(id: String) {
        viewModelScope.launch {
            repository.setActivePerson(id)
        }
    }

    fun load(personId: String, category: DocCategory?, customCategory: String? = null) {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null)
            try {
                // Repository is cache-first: IOException returns cached data instead of throwing.
                var docs = repository.listDocuments(personId, category)
                if (customCategory != null) {
                    docs = docs.filter { it.custom_category == customCategory }
                }
                _state.value = _state.value.copy(loading = false, documents = docs)
            } catch (e: Exception) {
                _state.value = _state.value.copy(loading = false, error = describeError(e))
            }
        }
    }

    fun upload(
        personId: String,
        category: DocCategory,
        customCategory: String?,
        title: String,
        hospitalName: String?,
        docDate: String?,
        notes: String?,
        files: List<File>,
        mimeTypes: List<String>,
        reloadCategory: DocCategory?,
        onDone: () -> Unit,
        expiryDate: String? = null,
        tags: String? = null
    ) {
        viewModelScope.launch {
            _state.value = _state.value.copy(uploading = true, error = null)
            try {
                when (repository.uploadDocument(personId, category, customCategory, title, hospitalName, docDate, notes, files, mimeTypes, expiryDate, tags)) {
                    is UploadResult.Success -> {
                        _state.value = _state.value.copy(uploading = false)
                        load(personId, reloadCategory)
                        onDone()
                    }
                    is UploadResult.QueuedOffline -> {
                        _state.value = _state.value.copy(
                            uploading = false,
                            error = "You're offline — this document will upload automatically when your Pi is reachable again."
                        )
                        onDone()
                    }
                }
            } catch (e: Exception) {
                _state.value = _state.value.copy(uploading = false, error = describeError(e))
            }
        }
    }

    fun delete(personId: String, category: DocCategory?, documentId: String) {
        viewModelScope.launch {
            try {
                repository.deleteDocument(documentId)
                load(personId, category)
            } catch (e: Exception) {
                _state.value = _state.value.copy(error = describeError(e))
            }
        }
    }

    suspend fun download(documentId: String, destination: File): File =
        repository.downloadDocument(documentId, destination)
}
