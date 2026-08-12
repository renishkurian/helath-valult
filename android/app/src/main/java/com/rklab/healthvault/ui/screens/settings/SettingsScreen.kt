package com.rklab.healthvault.ui.screens.settings

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.screens.server.ServerSetupState
import com.rklab.healthvault.ui.screens.server.ServerSetupViewModel
import com.rklab.healthvault.ui.theme.*
import com.rklab.healthvault.util.ViewModelFactory

@Composable
fun SettingsScreen(
    repository: HealthVaultRepository,
    onBack: () -> Unit,
    onLoggedOut: () -> Unit
) {
    val viewModel: ServerSetupViewModel = viewModel(factory = ViewModelFactory(repository))
    val state by viewModel.state.collectAsState()
    var url by remember { mutableStateOf(repository.getServerUrl().orEmpty()) }
    var showLogoutConfirm by remember { mutableStateOf(false) }
    
    val isBiometricEnabled by repository.tokenManager.isBiometricEnabled.collectAsState(initial = false)
    val scope = rememberCoroutineScope()

    LaunchedEffect(state) {
        if (state is ServerSetupState.Success && !repository.isLoggedIn) {
            // Server address changed, which invalidated the current session.
            onLoggedOut()
        }
    }

    Column(modifier = Modifier.fillMaxSize().background(Paper).padding(20.dp)) {
        TextButton(onClick = onBack) { Text("← Back", color = Navy) }
        Text("SETTINGS", style = MaterialTheme.typography.labelMedium, color = InkSoft)
        Spacer(Modifier.height(4.dp))
        Text("App settings", style = MaterialTheme.typography.headlineMedium, color = Ink)
        Spacer(Modifier.height(24.dp))

        Text("SERVER", style = MaterialTheme.typography.labelMedium, color = InkSoft)
        Spacer(Modifier.height(10.dp))
        Column(
            modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(White).padding(16.dp)
        ) {
            OutlinedTextField(
                value = url,
                onValueChange = { url = it },
                label = { Text("Server address") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                modifier = Modifier.fillMaxWidth()
            )
            if (state is ServerSetupState.Error) {
                Spacer(Modifier.height(8.dp))
                Text((state as ServerSetupState.Error).message, color = StampRed, style = MaterialTheme.typography.bodySmall)
            }
            if (state is ServerSetupState.Success) {
                Spacer(Modifier.height(8.dp))
                Text("Saved.", color = Sage, style = MaterialTheme.typography.bodySmall)
            }
            Spacer(Modifier.height(12.dp))
            Button(
                onClick = { viewModel.testAndSave(url) },
                enabled = state !is ServerSetupState.Testing,
                colors = ButtonDefaults.buttonColors(containerColor = Navy)
            ) {
                Text(if (state is ServerSetupState.Testing) "Checking…" else "Test & save", color = White)
            }
        }

        Spacer(Modifier.height(28.dp))
        Text("SECURITY", style = MaterialTheme.typography.labelMedium, color = InkSoft)
        Spacer(Modifier.height(10.dp))
        Column(
            modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(White).padding(16.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = androidx.compose.ui.Alignment.CenterVertically
            ) {
                Text("Enable Biometric Login", style = MaterialTheme.typography.bodyMedium, color = Ink)
                Switch(
                    checked = isBiometricEnabled,
                    onCheckedChange = { 
                        scope.launch { repository.tokenManager.setBiometricEnabled(it) } 
                    },
                    colors = SwitchDefaults.colors(checkedThumbColor = Navy, checkedTrackColor = SageBg)
                )
            }
        }

        Spacer(Modifier.height(28.dp))
        Text("ACCOUNT", style = MaterialTheme.typography.labelMedium, color = InkSoft)
        Spacer(Modifier.height(10.dp))
        Column(
            modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(White).padding(16.dp)
        ) {
            OutlinedButton(
                onClick = { showLogoutConfirm = true },
                colors = ButtonDefaults.outlinedButtonColors(contentColor = StampRed)
            ) { Text("Log out") }
        }
    }

    if (showLogoutConfirm) {
        AlertDialog(
            onDismissRequest = { showLogoutConfirm = false },
            title = { Text("Log out?") },
            text = { Text("You'll need to sign in again to see your cards and documents.") },
            confirmButton = {
                TextButton(onClick = {
                    repository.logout()
                    showLogoutConfirm = false
                    onLoggedOut()
                }) { Text("Log out", color = StampRed) }
            },
            dismissButton = { TextButton(onClick = { showLogoutConfirm = false }) { Text("Cancel", color = InkSoft) } }
        )
    }
}
