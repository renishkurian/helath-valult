package com.rklab.healthvault.ui.screens.settings

import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Cloud
import androidx.compose.material.icons.outlined.CloudDone
import androidx.compose.material.icons.outlined.CloudOff
import androidx.compose.material.icons.outlined.DarkMode
import androidx.compose.material.icons.outlined.Dns
import androidx.compose.material.icons.outlined.Fingerprint
import androidx.compose.material.icons.outlined.FormatSize
import androidx.compose.material.icons.outlined.History
import androidx.compose.material.icons.outlined.Link
import androidx.compose.material.icons.outlined.Logout
import androidx.compose.material.icons.outlined.PhoneAndroid
import androidx.compose.material.icons.outlined.QrCodeScanner
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material.icons.outlined.Shield
import androidx.compose.material.icons.outlined.Storage
import androidx.compose.material.icons.outlined.Sync
import androidx.compose.material.icons.outlined.Widgets
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.viewmodel.compose.viewModel
import com.rklab.healthvault.data.model.GoogleDriveSettingsIn
import com.rklab.healthvault.data.model.GoogleDriveStatus
import com.rklab.healthvault.data.model.LoginChallengeOut
import com.rklab.healthvault.data.model.StorageStats
import com.rklab.healthvault.data.model.UserOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.screens.login.LoginChallengeDialog
import com.rklab.healthvault.ui.screens.server.ServerSetupState
import com.rklab.healthvault.ui.screens.server.ServerSetupViewModel
import com.rklab.healthvault.ui.theme.*
import com.rklab.healthvault.util.ViewModelFactory
import kotlinx.coroutines.launch

@Composable
fun SettingsScreen(
    repository: HealthVaultRepository,
    onBack: () -> Unit,
    onLoggedOut: () -> Unit,
    onOpenAuditLog: () -> Unit,
    onOpenShareHistory: () -> Unit,
    onOpenModules: () -> Unit = {},
    onScanQr: () -> Unit = {}
) {
    val viewModel: ServerSetupViewModel = viewModel(factory = ViewModelFactory(repository))
    val state by viewModel.state.collectAsState()
    var url by remember { mutableStateOf(repository.getServerUrl().orEmpty()) }
    var showLogoutConfirm by remember { mutableStateOf(false) }

    val isBiometricEnabled by repository.tokenManager.isBiometricEnabled.collectAsState(initial = false)
    val darkTheme by repository.tokenManager.isDarkTheme.collectAsState(initial = true)
    val largeText by repository.tokenManager.isLargeText.collectAsState(initial = false)
    var pin by remember { mutableStateOf("") }
    var totpSecret by remember { mutableStateOf<String?>(null) }
    var totpCode by remember { mutableStateOf("") }
    var disableCode by remember { mutableStateOf("") }
    var account by remember { mutableStateOf<UserOut?>(null) }
    var drive by remember { mutableStateOf<GoogleDriveStatus?>(null) }
    var storage by remember { mutableStateOf<StorageStats?>(null) }
    var driveError by remember { mutableStateOf<String?>(null) }
    var loading by remember { mutableStateOf(true) }
    var driveBusy by remember { mutableStateOf(false) }
    var pendingChallenge by remember { mutableStateOf<LoginChallengeOut?>(null) }
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current

    fun toast(msg: String) = Toast.makeText(context, msg, Toast.LENGTH_LONG).show()

    suspend fun refreshFromServer() {
        account = runCatching { repository.me() }.getOrNull()
        runCatching { repository.googleDriveStatus() }
            .onSuccess { drive = it; driveError = null }
            .onFailure { drive = null; driveError = it.message }
        storage = runCatching { repository.storageStats() }.getOrNull()
        loading = false
    }

    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                scope.launch { refreshFromServer() }
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    LaunchedEffect(state) {
        if (state is ServerSetupState.Success && !repository.isLoggedIn) {
            onLoggedOut()
        }
    }

    val totpOn = account?.totp_enabled == true
    val approveOn = account?.app_approve == true
    val driveOn = drive?.connected == true && drive?.enabled == true

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(HubBg)
            .padding(horizontal = 20.dp)
            .verticalScroll(rememberScrollState())
    ) {
        TextButton(onClick = onBack, contentPadding = PaddingValues(0.dp)) {
            Text("← Back", color = Navy)
        }
        Text("SETTINGS", style = MaterialTheme.typography.labelMedium, color = VaultGold)
        Spacer(Modifier.height(4.dp))
        Text("App & vault", style = MaterialTheme.typography.headlineMedium, color = Ink)
        account?.let {
            Text(it.email, style = MaterialTheme.typography.bodySmall, color = InkSoft)
        }
        Spacer(Modifier.height(18.dp))

        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
            StatusTile(
                modifier = Modifier.weight(1f),
                icon = Icons.Outlined.Shield,
                label = "Authenticator",
                value = if (loading && account == null) "…" else if (totpOn) "On" else "Off",
                on = totpOn
            )
            StatusTile(
                modifier = Modifier.weight(1f),
                icon = if (driveOn) Icons.Outlined.CloudDone else Icons.Outlined.CloudOff,
                label = "Drive backup",
                value = when {
                    loading && drive == null && driveError == null -> "…"
                    driveOn -> "Daily on"
                    drive?.connected == true -> "Paused"
                    else -> "Off"
                },
                on = driveOn
            )
        }

        Spacer(Modifier.height(22.dp))
        SectionLabel("SERVER")
        SettingsCard {
            OutlinedTextField(
                value = url,
                onValueChange = { url = it },
                label = { Text("Server address") },
                singleLine = true,
                leadingIcon = { Icon(Icons.Outlined.Dns, contentDescription = null, tint = InkSoft) },
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
                Text(if (state is ServerSetupState.Testing) "Checking…" else "Test & save", color = TextDark)
            }
        }

        Spacer(Modifier.height(22.dp))
        SectionLabel("SECURITY")
        SettingsCard {
            SettingsAction(Icons.Outlined.QrCodeScanner, "Scan web login QR", onClick = onScanQr)
            Spacer(Modifier.height(8.dp))
            SettingsAction(Icons.Outlined.PhoneAndroid, "Check web login request") {
                scope.launch {
                    runCatching { repository.pendingLoginChallenges() }
                        .onSuccess { rows ->
                            val next = rows.firstOrNull()
                            pendingChallenge = next
                            toast(
                                if (next == null) "No website login is waiting. Keep the app open, then sign in on the site."
                                else "Website login found. Allow or Deny."
                            )
                        }
                        .onFailure { toast("Could not check: ${it.message ?: "server error"}") }
                }
            }
            pendingChallenge?.let { challenge ->
                LoginChallengeDialog(
                    repository = repository,
                    challenge = challenge,
                    onDone = { pendingChallenge = null }
                )
            }

            Spacer(Modifier.height(14.dp))
            ToggleRow("Biometric login", Icons.Outlined.Fingerprint, isBiometricEnabled) {
                scope.launch { repository.tokenManager.setBiometricEnabled(it) }
            }
            ToggleRow("Dark theme", Icons.Outlined.DarkMode, darkTheme) {
                scope.launch { repository.tokenManager.setDarkTheme(it) }
            }
            ToggleRow("Larger text", Icons.Outlined.FormatSize, largeText) {
                scope.launch { repository.tokenManager.setLargeText(it) }
            }
            ToggleRow(
                "Approve web login from this phone",
                Icons.Outlined.PhoneAndroid,
                approveOn,
                enabled = !repository.isViewer
            ) { on ->
                scope.launch {
                    runCatching { account = repository.setAppApprove(on) }
                        .onFailure { toast(it.message ?: "Could not update") }
                }
            }

            Spacer(Modifier.height(12.dp))
            OutlinedTextField(
                value = pin,
                onValueChange = { if (it.length <= 8) pin = it.filter(Char::isDigit) },
                label = { Text("App PIN (4–8 digits)") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true
            )
            Spacer(Modifier.height(8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = { if (pin.length >= 4) repository.tokenManager.setAppPin(pin) }) {
                    Text("Set PIN", color = Navy)
                }
                OutlinedButton(onClick = { repository.tokenManager.setAppPin(null); pin = "" }) {
                    Text("Clear PIN", color = StampRed)
                }
            }

            Spacer(Modifier.height(18.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Outlined.Shield, contentDescription = null, tint = if (totpOn) Sage else VaultGold)
                Spacer(Modifier.width(8.dp))
                Column(Modifier.weight(1f)) {
                    Text("Authenticator 2FA", style = MaterialTheme.typography.titleMedium, color = Ink)
                    Text(
                        if (totpOn) "On — same as the website Security page"
                        else "Off — website login is password only",
                        style = MaterialTheme.typography.bodySmall,
                        color = InkSoft
                    )
                }
                StatusChip(if (totpOn) "On" else "Off", totpOn)
            }
            if (totpOn) {
                Spacer(Modifier.height(10.dp))
                OutlinedTextField(
                    value = disableCode,
                    onValueChange = { disableCode = it.filter(Char::isDigit).take(6) },
                    label = { Text("Code to turn off") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )
                Spacer(Modifier.height(8.dp))
                OutlinedButton(
                    onClick = {
                        scope.launch {
                            runCatching {
                                repository.totpDisable(disableCode)
                                disableCode = ""
                                totpSecret = null
                                refreshFromServer()
                                toast("Authenticator turned off")
                            }.onFailure { toast(it.message ?: "Could not turn off 2FA") }
                        }
                    },
                    modifier = Modifier.fillMaxWidth()
                ) { Text("Turn off authenticator", color = StampRed) }
            } else {
                Spacer(Modifier.height(10.dp))
                OutlinedButton(
                    onClick = {
                        scope.launch {
                            runCatching { totpSecret = repository.totpSetup().secret }
                                .onFailure { toast(it.message ?: "Could not start 2FA") }
                        }
                    },
                    modifier = Modifier.fillMaxWidth()
                ) { Text("Set up authenticator 2FA", color = Navy) }
                if (totpSecret != null) {
                    Spacer(Modifier.height(8.dp))
                    Text("Secret: $totpSecret", color = InkSoft, style = MaterialTheme.typography.bodySmall)
                    OutlinedTextField(
                        totpCode, { totpCode = it },
                        label = { Text("Code from authenticator") },
                        modifier = Modifier.fillMaxWidth()
                    )
                    Spacer(Modifier.height(8.dp))
                    Button(
                        onClick = {
                            scope.launch {
                                runCatching {
                                    repository.totpEnable(totpCode)
                                    totpSecret = null
                                    totpCode = ""
                                    refreshFromServer()
                                    toast("Authenticator is on")
                                }.onFailure { toast(it.message ?: "Invalid code") }
                            }
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = Navy)
                    ) { Text("Enable 2FA", color = TextDark) }
                }
            }

            Spacer(Modifier.height(12.dp))
            SettingsAction(Icons.Outlined.Widgets, "Set as Android autofill service") {
                val intent = android.content.Intent(android.provider.Settings.ACTION_REQUEST_SET_AUTOFILL_SERVICE).apply {
                    data = android.net.Uri.parse("package:${context.packageName}")
                }
                runCatching { context.startActivity(intent) }
            }
            Spacer(Modifier.height(8.dp))
            SettingsAction(Icons.Outlined.Widgets, "Switch module", onClick = onOpenModules)
        }

        Spacer(Modifier.height(22.dp))
        SectionLabel("DATA SYNC")
        SettingsCard {
            Button(
                onClick = {
                    scope.launch {
                        try {
                            repository.syncAll()
                            toast("Sync completed successfully.")
                        } catch (e: Exception) {
                            toast("Sync failed: ${e.message}")
                        }
                    }
                },
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.buttonColors(containerColor = Navy)
            ) {
                Icon(Icons.Outlined.Sync, contentDescription = null, tint = TextDark)
                Spacer(Modifier.width(8.dp))
                Text("Force Sync", color = TextDark)
            }
        }

        Spacer(Modifier.height(22.dp))
        SectionLabel("BACKUP")
        SettingsCard {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    if (driveOn) Icons.Outlined.CloudDone else Icons.Outlined.Cloud,
                    contentDescription = null,
                    tint = if (driveOn) Sage else VaultGold
                )
                Spacer(Modifier.width(8.dp))
                Column(Modifier.weight(1f)) {
                    Text("Google Drive", style = MaterialTheme.typography.titleMedium, color = Ink)
                    Text(
                        driveStatusLine(drive, driveError),
                        style = MaterialTheme.typography.bodySmall,
                        color = InkSoft
                    )
                }
                StatusChip(
                    when {
                        driveOn -> "Daily on"
                        drive?.connected == true -> "Connected"
                        else -> "Off"
                    },
                    driveOn
                )
            }
            if (drive?.last_file_name != null || drive?.last_error != null) {
                Spacer(Modifier.height(8.dp))
                Text(
                    buildString {
                        drive?.last_file_name?.let { append("Last file: $it") }
                        drive?.last_run_at?.let { append(" · ${it.take(16).replace('T', ' ')}") }
                        if (drive?.last_ok == false && !drive?.last_error.isNullOrBlank()) {
                            append("\n${drive?.last_error}")
                        }
                    },
                    style = MaterialTheme.typography.bodySmall,
                    color = if (drive?.last_ok == false) StampRed else InkSoft
                )
            }
            if (drive?.connected == true && !repository.isViewer) {
                Spacer(Modifier.height(10.dp))
                ToggleRow("Daily upload (same as website)", Icons.Outlined.Cloud, drive?.enabled == true) { on ->
                    scope.launch {
                        runCatching {
                            drive = repository.googleDriveSettings(GoogleDriveSettingsIn(enabled = on))
                        }.onFailure { toast(it.message ?: "Could not update Drive") }
                    }
                }
                Spacer(Modifier.height(8.dp))
                Button(
                    onClick = {
                        driveBusy = true
                        scope.launch {
                            runCatching { repository.googleDriveRun() }
                                .onSuccess {
                                    toast("Uploaded ${it.file}")
                                    refreshFromServer()
                                }
                                .onFailure { toast(it.message ?: "Backup failed") }
                            driveBusy = false
                        }
                    },
                    enabled = !driveBusy,
                    modifier = Modifier.fillMaxWidth(),
                    colors = ButtonDefaults.buttonColors(containerColor = Navy)
                ) { Text(if (driveBusy) "Uploading…" else "Backup to Drive now", color = TextDark) }
            } else if (drive?.connected != true) {
                Spacer(Modifier.height(8.dp))
                Text(
                    "Connect once on the website: Storage → Connect Google Drive. After that, daily backup and this screen stay in sync.",
                    style = MaterialTheme.typography.bodySmall,
                    color = InkSoft
                )
            }
            Spacer(Modifier.height(8.dp))
            OutlinedButton(
                onClick = { scope.launch { refreshFromServer() } },
                modifier = Modifier.fillMaxWidth()
            ) {
                Icon(Icons.Outlined.Refresh, contentDescription = null, tint = Navy)
                Spacer(Modifier.width(8.dp))
                Text("Refresh status", color = Navy)
            }

            Spacer(Modifier.height(16.dp))
            HorizontalDivider(color = CardOutline)
            Spacer(Modifier.height(16.dp))
            storage?.let {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Outlined.Storage, contentDescription = null, tint = InkSoft)
                    Spacer(Modifier.width(8.dp))
                    Text(
                        "${it.file_count} files · ${formatBytes(it.bytes_used)}" +
                            (it.backup_dir?.let { dir -> " · snapshot $dir" } ?: ""),
                        style = MaterialTheme.typography.bodySmall,
                        color = InkSoft
                    )
                }
                Spacer(Modifier.height(12.dp))
            }

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
                        toast("Restore complete.")
                    } catch (e: Exception) {
                        toast("Restore failed: ${e.message}")
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
                            toast("Export failed: ${e.message}")
                        } finally {
                            exporting = false
                        }
                    }
                },
                enabled = !exporting,
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.buttonColors(containerColor = Sage)
            ) {
                Text(if (exporting) "Exporting…" else "Export full backup", color = TextDark)
            }
            Spacer(Modifier.height(10.dp))
            OutlinedButton(
                onClick = { restorePicker.launch("*/*") },
                enabled = !restoring && !repository.isViewer,
                modifier = Modifier.fillMaxWidth()
            ) { Text(if (restoring) "Restoring…" else "Restore from backup", color = Navy) }

            Spacer(Modifier.height(10.dp))
            SettingsAction(Icons.Outlined.Link, "Shared links & access history", onClick = onOpenShareHistory)
            Spacer(Modifier.height(8.dp))
            SettingsAction(Icons.Outlined.History, "View activity log", onClick = onOpenAuditLog)
        }

        Spacer(Modifier.height(22.dp))
        SectionLabel("ACCOUNT")
        SettingsCard {
            OutlinedButton(
                onClick = { showLogoutConfirm = true },
                colors = ButtonDefaults.outlinedButtonColors(contentColor = StampRed),
                modifier = Modifier.fillMaxWidth()
            ) {
                Icon(Icons.Outlined.Logout, contentDescription = null, tint = StampRed)
                Spacer(Modifier.width(8.dp))
                Text("Log out")
            }
        }
        Spacer(Modifier.height(28.dp))
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

@Composable
private fun SectionLabel(text: String) {
    Text(text, style = MaterialTheme.typography.labelMedium, color = VaultGold)
    Spacer(Modifier.height(10.dp))
}

@Composable
private fun SettingsCard(content: @Composable ColumnScope.() -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(White)
            .border(1.dp, CardOutline, RoundedCornerShape(16.dp))
            .padding(16.dp),
        content = content
    )
}

@Composable
private fun StatusTile(
    modifier: Modifier = Modifier,
    icon: ImageVector,
    label: String,
    value: String,
    on: Boolean
) {
    Column(
        modifier = modifier
            .clip(RoundedCornerShape(16.dp))
            .background(White)
            .border(1.dp, if (on) Sage.copy(alpha = 0.35f) else CardOutline, RoundedCornerShape(16.dp))
            .padding(14.dp)
    ) {
        Icon(icon, contentDescription = null, tint = if (on) Sage else VaultGold, modifier = Modifier.size(20.dp))
        Spacer(Modifier.height(10.dp))
        Text(label, style = MaterialTheme.typography.labelSmall, color = InkSoft)
        Text(value, style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.SemiBold), color = Ink)
    }
}

@Composable
private fun StatusChip(text: String, on: Boolean) {
    Text(
        text,
        style = MaterialTheme.typography.labelSmall,
        color = if (on) Sage else InkSoft,
        modifier = Modifier
            .clip(RoundedCornerShape(20.dp))
            .background(if (on) SageBg else VaultGoldSoft)
            .padding(horizontal = 10.dp, vertical = 4.dp)
    )
}

@Composable
private fun ToggleRow(
    title: String,
    icon: ImageVector,
    checked: Boolean,
    enabled: Boolean = true,
    onCheckedChange: (Boolean) -> Unit
) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Row(Modifier.weight(1f), verticalAlignment = Alignment.CenterVertically) {
            Icon(icon, contentDescription = null, tint = InkSoft, modifier = Modifier.size(18.dp))
            Spacer(Modifier.width(10.dp))
            Text(title, style = MaterialTheme.typography.bodyMedium, color = Ink)
        }
        Switch(
            checked = checked,
            onCheckedChange = onCheckedChange,
            enabled = enabled,
            colors = SwitchDefaults.colors(checkedThumbColor = Navy, checkedTrackColor = SageBg)
        )
    }
}

@Composable
private fun SettingsAction(icon: ImageVector, title: String, onClick: () -> Unit) {
    OutlinedButton(onClick = onClick, modifier = Modifier.fillMaxWidth()) {
        Icon(icon, contentDescription = null, tint = Navy)
        Spacer(Modifier.width(8.dp))
        Text(title, color = Navy)
    }
}

private fun driveStatusLine(drive: GoogleDriveStatus?, error: String?): String {
    return when {
        error != null && drive == null -> "Could not load Drive status. Pull refresh below."
        drive == null -> "Connect Drive on the website: Storage → Google Drive."
        drive.connected && drive.enabled ->
            listOfNotNull(drive.email, "uploads at ${drive.hour}:00", "keeps ${drive.keep_days} days")
                .joinToString(" · ")
        drive.connected -> "Connected${drive.email?.let { " as $it" } ?: ""}. Daily upload is off."
        else -> "Not connected. On the website: Storage → Connect Google Drive."
    }
}

private fun formatBytes(bytes: Long): String {
    if (bytes < 1024) return "$bytes B"
    if (bytes < 1024 * 1024) return "${bytes / 1024} KB"
    return "%.1f MB".format(bytes / 1048576.0)
}
