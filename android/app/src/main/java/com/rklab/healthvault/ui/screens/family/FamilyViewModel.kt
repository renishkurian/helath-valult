package com.rklab.healthvault.ui.screens.family

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.rklab.healthvault.data.model.PersonOut
import com.rklab.healthvault.data.model.Relation
import com.rklab.healthvault.data.repository.HealthVaultRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

data class FamilyUiState(
    val loading: Boolean = true,
    val people: List<PersonOut> = emptyList(),
    val error: String? = null,
    val saving: Boolean = false
)

class FamilyViewModel(private val repository: HealthVaultRepository) : ViewModel() {

    private val _state = MutableStateFlow(FamilyUiState())
    val state: StateFlow<FamilyUiState> = _state

    fun load() {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null)
            try {
                val people = repository.listPeople()
                _state.value = _state.value.copy(loading = false, people = people)
            } catch (e: Exception) {
                _state.value = _state.value.copy(loading = false, error = "Couldn't load family members.")
            }
        }
    }

    fun addMember(name: String, relation: Relation, dob: String?, bloodGroup: String?, onDone: () -> Unit) {
        if (name.isBlank()) return
        viewModelScope.launch {
            _state.value = _state.value.copy(saving = true)
            try {
                repository.addFamilyMember(name.trim(), relation, dob, bloodGroup)
                _state.value = _state.value.copy(saving = false)
                load()
                onDone()
            } catch (e: Exception) {
                _state.value = _state.value.copy(saving = false, error = "Couldn't add family member.")
            }
        }
    }

    fun removeMember(personId: String) {
        viewModelScope.launch {
            try {
                repository.deletePerson(personId)
                load()
            } catch (e: Exception) {
                _state.value = _state.value.copy(error = "Couldn't remove that member.")
            }
        }
    }

    fun inviteViewer(email: String, password: String, fullName: String, onDone: () -> Unit) {
        viewModelScope.launch {
            _state.value = _state.value.copy(saving = true, error = null)
            try {
                repository.inviteViewer(email.trim(), password, fullName.trim())
                _state.value = _state.value.copy(saving = false)
                onDone()
            } catch (e: Exception) {
                _state.value = _state.value.copy(saving = false, error = e.message ?: "Couldn't invite viewer.")
            }
        }
    }
}
