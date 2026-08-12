package com.rklab.healthvault.ui.screens.server

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.rklab.healthvault.data.repository.HealthVaultRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

sealed class ServerSetupState {
    data object Idle : ServerSetupState()
    data object Testing : ServerSetupState()
    data object Success : ServerSetupState()
    data class Error(val message: String) : ServerSetupState()
}

class ServerSetupViewModel(private val repository: HealthVaultRepository) : ViewModel() {

    private val _state = MutableStateFlow<ServerSetupState>(ServerSetupState.Idle)
    val state: StateFlow<ServerSetupState> = _state

    fun testAndSave(url: String) {
        if (url.isBlank()) {
            _state.value = ServerSetupState.Error("Enter your server's address")
            return
        }
        _state.value = ServerSetupState.Testing
        viewModelScope.launch {
            val result = repository.testServerConnection(url)
            if (result.isSuccess) {
                val previousUrl = repository.getServerUrl()
                repository.saveServerUrl(url)
                // A JWT is only valid for the server that issued it — if this
                // actually changed the server (not just the first-run setup),
                // any stored session is now stale, so force a fresh login.
                if (previousUrl != null && previousUrl != repository.getServerUrl()) {
                    repository.logout()
                }
                _state.value = ServerSetupState.Success
            } else {
                _state.value = ServerSetupState.Error(friendlyError(result.exceptionOrNull()?.message))
            }
        }
    }

    private fun friendlyError(raw: String?): String {
        val msg = raw ?: ""
        return when {
            msg.contains("Unable to resolve host") -> "Can't find that address. Check the IP/domain and try again."
            msg.contains("ECONNREFUSED") || msg.contains("Connection refused") -> "Nothing answered on that address/port. Is the server running?"
            msg.contains("timeout", ignoreCase = true) -> "Timed out reaching that server. Check you're on the same network or VPN."
            msg.isNotBlank() -> msg
            else -> "Couldn't connect. Check the address and try again."
        }
    }
}
