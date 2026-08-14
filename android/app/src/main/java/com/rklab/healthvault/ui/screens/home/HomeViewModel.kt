package com.rklab.healthvault.ui.screens.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.rklab.healthvault.data.model.*
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.components.FolderDef
import com.rklab.healthvault.ui.components.HospitalScopedFolderDefs
import com.rklab.healthvault.ui.theme.CatOther
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

data class HospitalFolderGroup(
    val card: CardOut,
    val counts: Map<String, Int>
)

data class HomeUiState(
    val loading: Boolean = true,
    val error: String? = null,
    val people: List<PersonOut> = emptyList(),
    val activePerson: PersonOut? = null,
    val cards: List<CardOut> = emptyList(),
    val hospitalFolders: List<HospitalFolderGroup> = emptyList(),
    val hospitalFolderDefs: List<FolderDef> = emptyList(),
    val insuranceCount: Int = 0,
    val unassignedCounts: Map<String, Int> = emptyMap(),
    val recentDocuments: List<DocumentOut> = emptyList(),
    val expiringCards: List<CardOut> = emptyList(),
    val expiringDocuments: List<DocumentOut> = emptyList(),
    val labTrends: List<LabTrend> = emptyList(),
    val documentCount: Int = 0
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

        val folderDefs = HospitalScopedFolderDefs.toMutableList()
        val customFolders = linkedSetOf<String>()
        documents.forEach { doc ->
            if (doc.category == DocCategory.OTHER && !doc.custom_category.isNullOrBlank()) {
                customFolders.add(doc.custom_category)
            }
        }
        customFolders.sorted().forEach { name ->
            folderDefs += FolderDef(
                category = DocCategory.OTHER,
                customCategory = name,
                label = name,
                bg = CatOther
            )
        }

        val cardKeys = cards.associateBy { it.hospital_name.trim().lowercase() }
        val perHospital = cardKeys.keys.associateWith {
            mutableMapOf<String, Int>().withDefault { 0 }
        }.toMutableMap()
        val unassigned = mutableMapOf<String, Int>().withDefault { 0 }
        var insuranceCount = 0

        fun countKey(doc: DocumentOut): String =
            if (doc.category == DocCategory.OTHER && !doc.custom_category.isNullOrBlank()) {
                doc.custom_category
            } else {
                doc.category.name
            }

        documents.forEach { doc ->
            if (doc.category == DocCategory.INSURANCE) {
                insuranceCount++
                return@forEach
            }
            if (!doc.category.requiresHospital() && doc.category != DocCategory.OTHER) return@forEach
            val key = countKey(doc)
            val hospKey = doc.hospital_name?.trim()?.lowercase().orEmpty()
            if (hospKey.isNotEmpty() && perHospital.containsKey(hospKey)) {
                val map = perHospital.getValue(hospKey)
                map[key] = map.getValue(key) + 1
            } else {
                unassigned[key] = unassigned.getValue(key) + 1
            }
        }

        val hospitalFolders = cards.map { card ->
            val key = card.hospital_name.trim().lowercase()
            HospitalFolderGroup(card = card, counts = perHospital[key]?.toMap() ?: emptyMap())
        }

        val expiring = cards.filter { isExpiringSoon(it.valid_till) }
        val expiringDocs = documents.filter { isExpiringSoon(it.expiry_date) }
        val trends = try { repository.labTrends(active.id) } catch (_: Exception) { emptyList() }

        _state.value = HomeUiState(
            loading = false,
            people = people,
            activePerson = active,
            cards = cards,
            hospitalFolders = hospitalFolders,
            hospitalFolderDefs = folderDefs,
            insuranceCount = insuranceCount,
            unassignedCounts = unassigned.filterValues { it > 0 },
            recentDocuments = documents.sortedByDescending { it.created_at }.take(6),
            expiringCards = expiring,
            expiringDocuments = expiringDocs,
            labTrends = trends,
            documentCount = documents.size
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
