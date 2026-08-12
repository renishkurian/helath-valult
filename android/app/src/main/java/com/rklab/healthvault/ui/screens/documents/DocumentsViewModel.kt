package com.rklab.healthvault.ui.screens.documents

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.rklab.healthvault.data.model.DocCategory
import com.rklab.healthvault.data.model.DocumentOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import java.io.File

data class DocumentsUiState(
    val loading: Boolean = true,
    val documents: List<DocumentOut> = emptyList(),
    val uploading: Boolean = false,
    val error: String? = null
)

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
                _state.value = _state.value.copy(loading = false, error = "Couldn't load documents.")
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
                _state.value = _state.value.copy(uploading = false, error = "Upload failed. Check your connection to the Pi.")
            }
        }
    }

    fun delete(personId: String, category: DocCategory?, documentId: String) {
        viewModelScope.launch {
            try {
                repository.deleteDocument(documentId)
                load(personId, category)
            } catch (e: Exception) {
                _state.value = _state.value.copy(error = "Couldn't delete document.")
            }
        }
    }

    suspend fun download(documentId: String, destination: File): File =
        repository.downloadDocument(documentId, destination)
}
