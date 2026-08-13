package com.rklab.healthvault.ui.screens.reminders

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.rklab.healthvault.data.model.ReminderOut
import com.rklab.healthvault.data.model.RepeatRule
import com.rklab.healthvault.data.repository.HealthVaultRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

data class RemindersUiState(
    val loading: Boolean = true,
    val reminders: List<ReminderOut> = emptyList(),
    val error: String? = null,
    val saving: Boolean = false
)

class RemindersViewModel(private val repository: HealthVaultRepository) : ViewModel() {
    private val _state = MutableStateFlow(RemindersUiState())
    val state: StateFlow<RemindersUiState> = _state

    fun load() {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true)
            try {
                val reminders = repository.listReminders(upcomingOnly = true)
                _state.value = _state.value.copy(loading = false, reminders = reminders.sortedBy { it.remind_at })
            } catch (e: Exception) {
                _state.value = _state.value.copy(loading = false, error = "Couldn't load reminders.")
            }
        }
    }

    fun addReminder(
        personId: String,
        title: String,
        description: String?,
        remindAtIso: String,
        repeatRule: RepeatRule,
        onCreated: (ReminderOut) -> Unit
    ) {
        if (title.isBlank()) return
        viewModelScope.launch {
            _state.value = _state.value.copy(saving = true)
            try {
                val created = repository.addReminder(personId, title.trim(), description, remindAtIso, repeatRule)
                _state.value = _state.value.copy(saving = false)
                load()
                onCreated(created)
            } catch (e: Exception) {
                _state.value = _state.value.copy(saving = false, error = "Couldn't save reminder.")
            }
        }
    }

    fun deleteReminder(id: String) {
        viewModelScope.launch {
            try {
                repository.deleteReminder(id)
                load()
            } catch (e: Exception) {
                _state.value = _state.value.copy(error = "Couldn't delete reminder.")
            }
        }
    }

    fun completeReminder(id: String, onUpdated: (ReminderOut) -> Unit = {}) {
        viewModelScope.launch {
            try {
                val updated = repository.completeReminder(id)
                load()
                onUpdated(updated)
            } catch (e: Exception) {
                _state.value = _state.value.copy(error = "Couldn't update reminder.")
            }
        }
    }
}
