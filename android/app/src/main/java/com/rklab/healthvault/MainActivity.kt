package com.rklab.healthvault

import android.os.Bundle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.biometric.BiometricPrompt
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.lifecycleScope
import com.rklab.healthvault.ui.navigation.HealthVaultNavGraph
import com.rklab.healthvault.ui.theme.HealthVaultTheme
import com.rklab.healthvault.ui.theme.Paper
import com.rklab.healthvault.ui.theme.Navy
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

class MainActivity : FragmentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        val app = application as HealthVaultApp

        setContent {
            var authState by remember { mutableStateOf<AuthState>(AuthState.Checking) }

            LaunchedEffect(Unit) {
                val isEnabled = app.repository.tokenManager.isBiometricEnabled.first()
                if (isEnabled && app.repository.isLoggedIn) {
                    showBiometricPrompt { success ->
                        if (success) {
                            authState = AuthState.Authenticated
                        } else {
                            finish()
                        }
                    }
                } else {
                    authState = AuthState.Authenticated
                }
            }

            HealthVaultTheme {
                if (authState == AuthState.Checking) {
                    Box(modifier = Modifier.fillMaxSize().background(Paper), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator(color = Navy)
                    }
                } else {
                    HealthVaultNavGraph(repository = app.repository)
                }
            }
        }
    }

    private fun showBiometricPrompt(onResult: (Boolean) -> Unit) {
        val executor = ContextCompat.getMainExecutor(this)
        val biometricPrompt = BiometricPrompt(this, executor,
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationError(errorCode: Int, errString: CharSequence) {
                    super.onAuthenticationError(errorCode, errString)
                    onResult(false)
                }
                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                    super.onAuthenticationSucceeded(result)
                    onResult(true)
                }
                override fun onAuthenticationFailed() {
                    super.onAuthenticationFailed()
                    // Let the user try again; do not fail immediately.
                }
            })

        val promptInfo = BiometricPrompt.PromptInfo.Builder()
            .setTitle("Unlock HealthVault")
            .setSubtitle("Confirm your identity to access your medical records")
            .setNegativeButtonText("Cancel")
            .build()

        biometricPrompt.authenticate(promptInfo)
    }

    enum class AuthState { Checking, Authenticated }
}
