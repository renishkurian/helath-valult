package com.rklab.healthvault

import android.content.Intent
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
import androidx.lifecycle.DefaultLifecycleObserver
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.ProcessLifecycleOwner
import androidx.lifecycle.lifecycleScope
import com.rklab.healthvault.ui.navigation.HealthVaultNavGraph
import com.rklab.healthvault.ui.theme.HealthVaultTheme
import com.rklab.healthvault.ui.theme.Paper
import com.rklab.healthvault.ui.theme.Navy
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

class MainActivity : FragmentActivity() {
    
    private val requiresAuthFlow = MutableStateFlow(true) // Start by requiring auth check

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        captureQuickAdd(intent)
        enableEdgeToEdge()

        val app = application as HealthVaultApp

        // Listen for app going to background to lock it again
        ProcessLifecycleOwner.get().lifecycle.addObserver(object : DefaultLifecycleObserver {
            override fun onStop(owner: LifecycleOwner) {
                lifecycleScope.launch {
                    val bio = app.repository.tokenManager.isBiometricEnabled.first()
                    val pin = app.repository.tokenManager.hasAppPin()
                    if ((bio || pin) && app.repository.isLoggedIn) {
                        requiresAuthFlow.value = true
                    }
                }
            }
        })

        setContent {
            val requiresAuth by requiresAuthFlow.collectAsState()
            var authState by remember { mutableStateOf<AuthState>(AuthState.Checking) }
            var pinError by remember { mutableStateOf(false) }
            val darkTheme by app.repository.tokenManager.isDarkTheme.collectAsState(initial = true)
            val largeText by app.repository.tokenManager.isLargeText.collectAsState(initial = false)

            LaunchedEffect(requiresAuth) {
                if (requiresAuth) {
                    authState = AuthState.Checking
                    val bio = app.repository.tokenManager.isBiometricEnabled.first()
                    val pin = app.repository.tokenManager.hasAppPin()
                    when {
                        !app.repository.isLoggedIn -> {
                            authState = AuthState.Authenticated
                            requiresAuthFlow.value = false
                        }
                        pin -> authState = AuthState.Pin
                        bio -> showBiometricPrompt { success ->
                            if (success) {
                                authState = AuthState.Authenticated
                                requiresAuthFlow.value = false
                            } else finish()
                        }
                        else -> {
                            authState = AuthState.Authenticated
                            requiresAuthFlow.value = false
                        }
                    }
                }
            }

            HealthVaultTheme(darkTheme = darkTheme, largeText = largeText) {
                when (authState) {
                    AuthState.Checking -> Box(modifier = Modifier.fillMaxSize().background(Paper), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator(color = Navy)
                    }
                    AuthState.Pin -> com.rklab.healthvault.ui.screens.lock.PinLockScreen(
                        error = pinError,
                        onSubmit = { entered ->
                            if (app.repository.tokenManager.verifyAppPin(entered)) {
                                pinError = false
                                authState = AuthState.Authenticated
                                requiresAuthFlow.value = false
                            } else pinError = true
                        }
                    )
                    AuthState.Authenticated -> HealthVaultNavGraph(repository = app.repository)
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

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        captureQuickAdd(intent)
    }

    private fun captureQuickAdd(intent: Intent?) {
        val app = application as HealthVaultApp
        if (intent?.getBooleanExtra(EXTRA_QUICK_ADD, false) == true) {
            app.pendingQuickAdd = true
        }
        if (intent?.getBooleanExtra(EXTRA_OPEN_CARE, false) == true) {
            app.pendingOpenCare = true
        }
    }

    companion object {
        const val EXTRA_QUICK_ADD = "quick_add"
        const val EXTRA_OPEN_CARE = "open_care"
    }

    enum class AuthState { Checking, Pin, Authenticated }
}
