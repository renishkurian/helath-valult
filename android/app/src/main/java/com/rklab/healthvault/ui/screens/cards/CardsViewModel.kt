package com.rklab.healthvault.ui.screens.cards

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.rklab.healthvault.data.model.CardOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

data class CardsUiState(
    val loading: Boolean = true,
    val cards: List<CardOut> = emptyList(),
    val saving: Boolean = false,
    val error: String? = null
)

class CardsViewModel(private val repository: HealthVaultRepository) : ViewModel() {
    private val _state = MutableStateFlow(CardsUiState())
    val state: StateFlow<CardsUiState> = _state

    fun load(personId: String) {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true)
            try {
                val cards = repository.listCards(personId)
                _state.value = _state.value.copy(loading = false, cards = cards)
            } catch (e: Exception) {
                _state.value = _state.value.copy(loading = false, error = "Couldn't load cards.")
            }
        }
    }

    fun addCard(
        personId: String,
        hospitalName: String,
        ward: String?,
        bloodGroup: String?,
        validFrom: String?,
        validTill: String?,
        patientId: String?,
        notes: String?,
        onDone: () -> Unit
    ) {
        if (hospitalName.isBlank()) return
        viewModelScope.launch {
            _state.value = _state.value.copy(saving = true)
            try {
                repository.addCard(personId, hospitalName.trim(), ward, bloodGroup, validFrom, validTill, patientId, notes)
                _state.value = _state.value.copy(saving = false)
                load(personId)
                onDone()
            } catch (e: Exception) {
                _state.value = _state.value.copy(saving = false, error = "Couldn't save the card.")
            }
        }
    }

    fun deleteCard(personId: String, cardId: String) {
        viewModelScope.launch {
            try {
                repository.deleteCard(cardId)
                load(personId)
            } catch (e: Exception) {
                _state.value = _state.value.copy(error = "Couldn't delete the card.")
            }
        }
    }
}
