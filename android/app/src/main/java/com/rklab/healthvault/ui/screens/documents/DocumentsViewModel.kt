package com.rklab.healthvault.ui.screens.documents

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.rklab.healthvault.data.model.DocCategory
import com.rklab.healthvault.data.model.DocumentOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import retrofit2.HttpException
import java.io.File
import java.io.IOException

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
private fun describeUploadError(e: Exception): String = when (e) {
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
    is IOException -> "Couldn't reach the server. Check you're on the same network/VPN as your Pi."
    else -> e.message ?: "Something went wrong."
}

class DocumentsViewModel(private val repository: HealthVaultRepository) : ViewModel() {
    private val _state = MutableStateFlow(DocumentsUiState())
    val state: StateFlow<DocumentsUiState> = _state

    fun load(personId: String, category: DocCategory?) {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null)
            try {
                val docs = repository.listDocuments(personId, category)
                _state.value = _state.value.copy(loading = false, documents = docs)
            } catch (e: Exception) {
                _state.value = _state.value.copy(loading = false, error = describeUploadError(e))
            }
        }
    }

    fun upload(
        personId: String,
        category: DocCategory,
        title: String,
        hospitalName: String?,
        docDate: String?,
        notes: String?,
        file: File,
        mimeType: String,
        reloadCategory: DocCategory?,
        onDone: () -> Unit
    ) {
        viewModelScope.launch {
            _state.value = _state.value.copy(uploading = true, error = null)
            try {
                repository.uploadDocument(personId, category, title, hospitalName, docDate, notes, file, mimeType)
                _state.value = _state.value.copy(uploading = false)
                load(personId, reloadCategory)
                onDone()
            } catch (e: Exception) {
                _state.value = _state.value.copy(uploading = false, error = describeUploadError(e))
            }
        }
    }

    fun delete(personId: String, category: DocCategory?, documentId: String) {
        viewModelScope.launch {
            try {
                repository.deleteDocument(documentId)
                load(personId, category)
            } catch (e: Exception) {
                _state.value = _state.value.copy(error = describeUploadError(e))
            }
        }
    }

    suspend fun download(documentId: String, destination: File): File =
        repository.downloadDocument(documentId, destination)
}
