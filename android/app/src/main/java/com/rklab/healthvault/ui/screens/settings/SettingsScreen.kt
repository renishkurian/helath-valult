package com.rklab.healthvault.ui.screens.settings

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import kotlinx.coroutines.launch
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.screens.server.ServerSetupState
import com.rklab.healthvault.ui.screens.server.ServerSetupViewModel
import com.rklab.healthvault.ui.theme.*
import com.rklab.healthvault.util.ViewModelFactory
import androidx.compose.ui.platform.LocalContext
import android.widget.Toast

@Composable
fun SettingsScreen(
    repository: HealthVaultRepository,
    onBack: () -> Unit,
    onLoggedOut: () -> Unit,
    onOpenAuditLog: () -> Unit
) {
    val viewModel: ServerSetupViewModel = viewModel(factory = ViewModelFactory(repository))
    val state by viewModel.state.collectAsState()
    var url by remember { mutableStateOf(repository.getServerUrl().orEmpty()) }
    var showLogoutConfirm by remember { mutableStateOf(false) }
    
    val isBiometricEnabled by repository.tokenManager.isBiometricEnabled.collectAsState(initial = false)
    val scope = rememberCoroutineScope()
    val context = LocalContext.current

    LaunchedEffect(state) {
        if (state is ServerSetupState.Success && !repository.isLoggedIn) {
            // Server address changed, which invalidated the current session.
            onLoggedOut()
        }
    }

    Column(modifier = Modifier.fillMaxSize().background(Paper).padding(20.dp).verticalScroll(rememberScrollState())) {
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
        Text("DATA SYNC", style = MaterialTheme.typography.labelMedium, color = InkSoft)
        Spacer(Modifier.height(10.dp))
        Column(
            modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(White).padding(16.dp)
        ) {
            Button(
                onClick = {
                    scope.launch {
                        try {
                            repository.syncAll()
                            Toast.makeText(context, "Sync completed successfully.", Toast.LENGTH_SHORT).show()
                        } catch (e: Exception) {
                            Toast.makeText(context, "Sync failed: ${e.message}", Toast.LENGTH_SHORT).show()
                        }
                    }
                },
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.buttonColors(containerColor = Navy)
            ) {
                Text("Force Sync", color = White)
            }
        }

        Spacer(Modifier.height(28.dp))
        Text("BACKUP & ACTIVITY", style = MaterialTheme.typography.labelMedium, color = InkSoft)
        Spacer(Modifier.height(10.dp))
        Column(
            modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(White).padding(16.dp)
        ) {
            var exporting by remember { mutableStateOf(false) }
            var backupPassword by remember { mutableStateOf("") }
            var restoring by remember { mutableStateOf(false) }
            val restorePicker = androidx.activity.compose.rememberLauncherForActivityResult(
                androidx.activity.result.contract.ActivityResultContracts.GetContent()
            ) { uri ->
                if (uri == null) return@rememberLauncherForActivityResult
                restoring = true
                scope.launch {
                    try {
                        val tmp = java.io.File(context.cacheDir, "restore-in.bin")
                        context.contentResolver.openInputStream(uri)?.use { input ->
                            tmp.outputStream().use { output -> input.copyTo(output) }
                        }
                        repository.restoreBackup(tmp, backupPassword.ifBlank { null })
                        Toast.makeText(context, "Restore complete.", Toast.LENGTH_SHORT).show()
                    } catch (e: Exception) {
                        Toast.makeText(context, "Restore failed: ${e.message}", Toast.LENGTH_SHORT).show()
                    } finally {
                        restoring = false
                    }
                }
            }
            OutlinedTextField(
                value = backupPassword,
                onValueChange = { backupPassword = it },
                label = { Text("Backup password (optional)") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(Modifier.height(10.dp))
            Button(
                onClick = {
                    exporting = true
                    scope.launch {
                        try {
                            val encrypted = backupPassword.isNotBlank()
                            val dest = java.io.File(
                                context.getExternalFilesDir(null),
                                if (encrypted) "healthvault-backup-${System.currentTimeMillis()}.hvbak"
                                else "healthvault-backup-${System.currentTimeMillis()}.zip"
                            )
                            repository.exportBackup(dest, password = backupPassword.ifBlank { null })
                            val uri = androidx.core.content.FileProvider.getUriForFile(
                                context, "${context.packageName}.fileprovider", dest
                            )
                            val shareIntent = android.content.Intent(android.content.Intent.ACTION_SEND).apply {
                                type = "application/octet-stream"
                                putExtra(android.content.Intent.EXTRA_STREAM, uri)
                                addFlags(android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION)
                            }
                            context.startActivity(android.content.Intent.createChooser(shareIntent, "Save backup"))
                        } catch (e: Exception) {
                            Toast.makeText(context, "Export failed: ${e.message}", Toast.LENGTH_SHORT).show()
                        } finally {
                            exporting = false
                        }
                    }
                },
                enabled = !exporting,
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.buttonColors(containerColor = Sage)
            ) {
                Text(if (exporting) "Exporting…" else "Export full backup", color = White)
            }
            Spacer(Modifier.height(10.dp))
            OutlinedButton(
                onClick = { restorePicker.launch("*/*") },
                enabled = !restoring && !repository.isViewer,
                modifier = Modifier.fillMaxWidth()
            ) { Text(if (restoring) "Restoring…" else "Restore from backup", color = Navy) }
            Spacer(Modifier.height(10.dp))
            OutlinedButton(
                onClick = onOpenAuditLog,
                modifier = Modifier.fillMaxWidth()
            ) { Text("View activity log", color = Navy) }
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
