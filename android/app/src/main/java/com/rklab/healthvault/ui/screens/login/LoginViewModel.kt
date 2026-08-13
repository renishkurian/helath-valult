package com.rklab.healthvault.ui.screens.login

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.rklab.healthvault.data.repository.HealthVaultRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

sealed class AuthUiState {
    data object Idle : AuthUiState()
    data object Loading : AuthUiState()
    data object Success : AuthUiState()
    data class TotpRequired(val totpToken: String) : AuthUiState()
    data class Error(val message: String) : AuthUiState()
}

class LoginViewModel(private val repository: HealthVaultRepository) : ViewModel() {

    private val _state = MutableStateFlow<AuthUiState>(AuthUiState.Idle)
    val state: StateFlow<AuthUiState> = _state

    fun login(email: String, password: String) {
        if (email.isBlank() || password.isBlank()) {
            _state.value = AuthUiState.Error("Enter your email and password")
            return
        }
        _state.value = AuthUiState.Loading
        viewModelScope.launch {
            try {
                repository.login(email.trim(), password)
                _state.value = AuthUiState.Success
            } catch (e: HealthVaultRepository.TotpNeeded) {
                _state.value = AuthUiState.TotpRequired(e.totpToken)
            } catch (e: Exception) {
                _state.value = AuthUiState.Error(friendlyError(e))
            }
        }
    }

    fun register(email: String, password: String, fullName: String) {
        if (email.isBlank() || password.length < 8 || fullName.isBlank()) {
            _state.value = AuthUiState.Error("Fill in your name, email, and an 8+ character password")
            return
        }
        _state.value = AuthUiState.Loading
        viewModelScope.launch {
            try {
                repository.register(email.trim(), password, fullName.trim())
                _state.value = AuthUiState.Success
            } catch (e: Exception) {
                _state.value = AuthUiState.Error(friendlyError(e))
            }
        }
    }

    fun verifyTotp(token: String, code: String) {
        _state.value = AuthUiState.Loading
        viewModelScope.launch {
            try {
                repository.verifyTotp(token, code)
                _state.value = AuthUiState.Success
            } catch (e: Exception) {
                _state.value = AuthUiState.Error(friendlyError(e))
            }
        }
    }

    private fun friendlyError(e: Exception): String {
        val msg = e.message ?: ""
        return when {
            msg.contains("Unable to resolve host") || msg.contains("ECONNREFUSED") ->
                "Can't reach the server. Check your Pi is on and the app's API address is correct."
            msg.contains("401") -> "Incorrect email or password"
            msg.contains("409") -> "An account with this email already exists"
            else -> "Something went wrong. Please try again."
        }
    }
}
