package com.rklab.healthvault.ui.screens.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.rklab.healthvault.data.model.*
import com.rklab.healthvault.data.repository.HealthVaultRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit

data class HomeUiState(
    val loading: Boolean = true,
    val error: String? = null,
    val people: List<PersonOut> = emptyList(),
    val activePerson: PersonOut? = null,
    val cards: List<CardOut> = emptyList(),
    val recentDocuments: List<DocumentOut> = emptyList(),
    val folders: List<com.rklab.healthvault.ui.components.FolderDef> = emptyList(),
    val folderCounts: Map<String, Int> = emptyMap(), // key is either category name or custom category name
    val expiringCards: List<CardOut> = emptyList(),
    val expiringDocuments: List<DocumentOut> = emptyList(),
    val labTrends: List<LabTrend> = emptyList()
)

class HomeViewModel(private val repository: HealthVaultRepository) : ViewModel() {

    private val _state = MutableStateFlow(HomeUiState())
    val state: StateFlow<HomeUiState> = _state

    /** true when the device has no internet (or the Pi is unreachable). */
    val isOffline: StateFlow<Boolean> = repository.connectivityObserver.isConnected
        .map { !it }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), false)

    /** Number of uploads waiting to be sent when the Pi is back online. */
    val pendingUploadCount: StateFlow<Int> = repository.pendingUploadCount
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), 0)

    init {
        viewModelScope.launch {
            repository.activePersonFlow().collect { savedActiveId ->
                // When the active person ID changes (e.g. from the Upload screen),
                // we automatically refresh the home screen for that person.
                loadInternal(savedActiveId)
            }
        }
    }

    fun load() {
        viewModelScope.launch {
            val savedActiveId = repository.activePersonFlow().first()
            loadInternal(savedActiveId)
        }
    }

    private suspend fun loadInternal(savedActiveId: String?) {
        _state.value = _state.value.copy(loading = true, error = null)
        try {
            val people = repository.listPeople()
            val active = people.firstOrNull { it.id == savedActiveId }
                ?: people.firstOrNull { it.relation == Relation.SELF }
                ?: people.firstOrNull()

            if (active != null && active.id != savedActiveId) {
                repository.setActivePerson(active.id)
                // This will trigger the collect() block above, but it's fine.
            }

            loadForPerson(people, active)
        } catch (e: Exception) {
            _state.value = _state.value.copy(loading = false, error = "Couldn't reach your server. Pull down to retry.")
        }
    }

    fun selectPerson(person: PersonOut) {
        viewModelScope.launch {
            repository.setActivePerson(person.id)
            loadForPerson(_state.value.people, person)
        }
    }

    private suspend fun loadForPerson(people: List<PersonOut>, active: PersonOut?) {
        if (active == null) {
            _state.value = HomeUiState(loading = false, people = people)
            return
        }
        val cards = repository.listCards(active.id)
        val documents = repository.listDocuments(active.id)
        
        val counts = mutableMapOf<String, Int>()
        val customFolders = mutableSetOf<String>()
        
        documents.forEach { doc ->
            if (doc.category == DocCategory.OTHER && !doc.custom_category.isNullOrBlank()) {
                val customName = doc.custom_category
                customFolders.add(customName)
                counts[customName] = (counts[customName] ?: 0) + 1
            } else {
                val catKey = doc.category.name
                counts[catKey] = (counts[catKey] ?: 0) + 1
            }
        }
        
        // Base folders
        val baseFolders = com.rklab.healthvault.ui.components.FolderDefs
        
        // Generate custom folders
        val generatedCustomFolders = customFolders.map { customName ->
            com.rklab.healthvault.ui.components.FolderDef(
                category = DocCategory.OTHER,
                customCategory = customName,
                label = customName,
                bg = com.rklab.healthvault.ui.theme.CatOther
            )
        }.sortedBy { it.label }
        
        val allFolders = baseFolders + generatedCustomFolders

        val expiring = cards.filter { isExpiringSoon(it.valid_till) }
        val expiringDocs = documents.filter { isExpiringSoon(it.expiry_date) }
        val trends = try { repository.labTrends(active.id) } catch (_: Exception) { emptyList() }

        _state.value = HomeUiState(
            loading = false,
            people = people,
            activePerson = active,
            cards = cards,
            recentDocuments = documents.sortedByDescending { it.created_at }.take(6),
            folders = allFolders,
            folderCounts = counts,
            expiringCards = expiring,
            expiringDocuments = expiringDocs,
            labTrends = trends
        )
    }

    private fun isExpiringSoon(validTill: String?): Boolean {
        if (validTill.isNullOrBlank()) return false
        return try {
            val date = LocalDate.parse(validTill, DateTimeFormatter.ISO_DATE)
            val days = ChronoUnit.DAYS.between(LocalDate.now(), date)
            days in 0..30
        } catch (e: Exception) {
            false
        }
    }
}
