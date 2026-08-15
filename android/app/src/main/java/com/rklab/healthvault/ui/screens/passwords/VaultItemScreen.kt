package com.rklab.healthvault.ui.screens.passwords

import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material.icons.outlined.StarBorder
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import com.rklab.healthvault.data.model.VaultHistoryOut
import com.rklab.healthvault.data.model.VaultItemOut
import com.rklab.healthvault.data.model.VaultSendCreate
import com.rklab.healthvault.data.model.VaultTotpOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.components.VaultBackLink
import com.rklab.healthvault.ui.components.VaultGlassCard
import com.rklab.healthvault.ui.components.VaultOutlinedButton
import com.rklab.healthvault.ui.components.VaultPrimaryButton
import com.rklab.healthvault.ui.components.vaultFieldColors
import com.rklab.healthvault.ui.theme.HubBg
import com.rklab.healthvault.ui.theme.HubText
import com.rklab.healthvault.ui.theme.HubTextDim
import com.rklab.healthvault.ui.theme.Sage
import com.rklab.healthvault.ui.theme.SageBg
import com.rklab.healthvault.ui.theme.StampRed
import com.rklab.healthvault.ui.theme.VaultGold
import com.rklab.healthvault.util.ClipboardUtil
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

@Composable
fun VaultItemScreen(
    repository: HealthVaultRepository,
    itemId: String,
    onBack: () -> Unit,
    onEdit: () -> Unit,
    onSend: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var item by remember { mutableStateOf<VaultItemOut?>(null) }
    var totp by remember { mutableStateOf<VaultTotpOut?>(null) }
    var history by remember { mutableStateOf<List<VaultHistoryOut>>(emptyList()) }
    var error by remember { mutableStateOf<String?>(null) }
    var showShare by remember { mutableStateOf(false) }
    var sharePin by remember { mutableStateOf("") }
    var shareHours by remember { mutableStateOf("48") }
    var shareOneTime by remember { mutableStateOf(false) }
    var shareIncludeTotp by remember { mutableStateOf(false) }
    var shareRequireGrant by remember { mutableStateOf(false) }
    var shareEmailOtp by remember { mutableStateOf(false) }
    var shareAllowedEmails by remember { mutableStateOf("") }
    var shareBusy by remember { mutableStateOf(false) }
    var shareError by remember { mutableStateOf<String?>(null) }
    var shareReady by remember { mutableStateOf<Pair<String, Boolean>?>(null) }
    val fieldColors = vaultFieldColors()

    fun load() {
        scope.launch {
            runCatching {
                item = repository.getVaultItem(itemId)
                history = repository.vaultItemHistory(itemId)
                totp = if (item?.has_totp == true) repository.vaultItemTotp(itemId) else null
            }.onFailure { error = it.message }
        }
    }
    LaunchedEffect(itemId) { load() }
    LaunchedEffect(item?.has_totp) {
        while (item?.has_totp == true) {
            totp = runCatching { repository.vaultItemTotp(itemId) }.getOrNull()
            delay(((totp?.remaining ?: 1).coerceAtLeast(1)) * 1000L)
        }
    }

    val current = item
    Column(
        Modifier
            .fillMaxSize()
            .background(HubBg)
            .padding(20.dp)
            .verticalScroll(rememberScrollState())
    ) {
        VaultBackLink("← Vault", onBack)
        if (error != null) Text(error!!, color = StampRed)
        if (current == null) {
            CircularProgressIndicator(color = VaultGold)
            return@Column
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(current.item_type.uppercase(), style = MaterialTheme.typography.labelMedium, color = VaultGold)
                Text(current.name, style = MaterialTheme.typography.headlineMedium, color = HubText)
            }
            IconButton(onClick = {
                scope.launch {
                    if (current.favorite) repository.unfavoriteVaultItem(itemId) else repository.favoriteVaultItem(itemId)
                    load()
                }
            }) {
                Icon(if (current.favorite) Icons.Filled.Star else Icons.Outlined.StarBorder, null, tint = VaultGold)
            }
        }
        Spacer(Modifier.height(16.dp))
        totp?.let {
            Column(
                Modifier
                    .fillMaxWidth()
                    .background(SageBg, RoundedCornerShape(16.dp))
                    .padding(14.dp)
            ) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                    Column {
                        Text("Authenticator", color = HubTextDim, style = MaterialTheme.typography.labelSmall)
                        Text(it.code, color = Sage, style = MaterialTheme.typography.headlineMedium, fontFamily = FontFamily.Monospace)
                    }
                    Column(horizontalAlignment = Alignment.End) {
                        Text("${it.remaining}s", color = HubTextDim)
                        IconButton(onClick = { ClipboardUtil.copy(context, "Code", it.code) }) {
                            Icon(Icons.Filled.ContentCopy, null, tint = Sage)
                        }
                    }
                }
            }
            Spacer(Modifier.height(12.dp))
        }
        VaultGlassCard {
            CopyRow("Username", current.username)
            CopyRow("Password", current.password, secret = true)
            current.uris.forEach { CopyRow("URI", it) }
            CopyRow("Notes", current.notes)
            CopyRow("Card number", current.card_number, secret = true)
            CopyRow("CVV", current.card_cvv, secret = true)
            CopyRow("Cardholder", current.cardholder_name)
            CopyRow("Expiry", listOfNotNull(current.card_exp_month, current.card_exp_year).joinToString("/").ifBlank { null })
            CopyRow("Name", listOfNotNull(current.first_name, current.last_name).joinToString(" ").ifBlank { null })
            CopyRow("Email", current.email)
            CopyRow("Phone", current.phone)
            CopyRow("SSN", current.ssn, secret = true)
            CopyRow("License", current.license_number, secret = true)
            CopyRow("Passport", current.passport_number, secret = true)
        }
        Spacer(Modifier.height(16.dp))
        VaultPrimaryButton("Edit", onEdit)
        Spacer(Modifier.height(8.dp))
        if (current.item_type == "login") {
            VaultOutlinedButton("Share", {
                sharePin = ""
                shareHours = "48"
                shareOneTime = false
                shareIncludeTotp = false
                shareRequireGrant = false
                shareEmailOtp = false
                shareAllowedEmails = ""
                shareError = null
                shareReady = null
                showShare = true
            })
            Spacer(Modifier.height(8.dp))
        }
        VaultOutlinedButton("Send a copy", onSend)
        Spacer(Modifier.height(8.dp))
        VaultOutlinedButton("Move to trash", {
            scope.launch {
                runCatching { repository.trashVaultItem(itemId) }
                onBack()
            }
        }, color = StampRed)
        Spacer(Modifier.height(24.dp))
        Text("ITEM HISTORY", style = MaterialTheme.typography.labelMedium, color = VaultGold)
        Spacer(Modifier.height(8.dp))
        MetaRow("Last edited", formatVaultDate(current.updated_at ?: current.created_at))
        MetaRow("Created", formatVaultDate(current.created_at))
        current.password_changed_at?.takeIf { it.isNotBlank() }?.let {
            MetaRow("Password changed", formatVaultDate(it))
        }
        if (history.isNotEmpty()) {
            Spacer(Modifier.height(20.dp))
            Text("PASSWORD HISTORY", style = MaterialTheme.typography.labelMedium, color = VaultGold)
            Spacer(Modifier.height(8.dp))
            VaultGlassCard {
                history.forEach { h ->
                    CopyRow(formatVaultDate(h.created_at), h.password, secret = true)
                }
            }
        }
        Spacer(Modifier.height(24.dp))
    }

    if (showShare && item?.item_type == "login") {
        val currentItem = item!!
        val base = repository.getServerUrl()?.trimEnd('/') ?: ""
        AlertDialog(
            onDismissRequest = { if (!shareBusy) showShare = false },
            title = { Text("Share this login") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    shareReady?.let { (token, needsTotp) ->
                        val url = "$base/v/$token"
                        Text("Share link ready", color = HubText)
                        Text(url, color = VaultGold, fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.bodySmall)
                        if (needsTotp) {
                            Text(
                                "$url/qr",
                                color = HubTextDim,
                                fontFamily = FontFamily.Monospace,
                                style = MaterialTheme.typography.bodySmall
                            )
                            Text("Send the QR link separately from the password link.", color = HubTextDim, style = MaterialTheme.typography.bodySmall)
                        }
                        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                            TextButton(onClick = { ClipboardUtil.copy(context, "Password link", url) }) {
                                Text("Copy password link", color = VaultGold)
                            }
                            if (needsTotp) {
                                TextButton(onClick = { ClipboardUtil.copy(context, "QR link", "$url/qr") }) {
                                    Text("Copy QR link", color = VaultGold)
                                }
                            }
                        }
                    } ?: run {
                        Row(
                            Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            OutlinedTextField(
                                sharePin,
                                { sharePin = it },
                                label = { Text("Access code (optional)") },
                                modifier = Modifier.weight(1f),
                                singleLine = true,
                                colors = fieldColors
                            )
                            TextButton(onClick = { sharePin = generateAccessCode() }) {
                                Text("Generate", color = VaultGold)
                            }
                        }
                        OutlinedTextField(
                            shareHours,
                            { shareHours = it.filter(Char::isDigit) },
                            label = { Text("Expires in hours") },
                            modifier = Modifier.fillMaxWidth(),
                            singleLine = true,
                            colors = fieldColors
                        )
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Checkbox(checked = shareOneTime, onCheckedChange = { shareOneTime = it })
                            Text("One-time view", color = HubText)
                        }
                        if (currentItem.has_totp) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Checkbox(checked = shareIncludeTotp, onCheckedChange = { shareIncludeTotp = it })
                                Text("Require authenticator to view password", color = HubText)
                            }
                        }
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Checkbox(checked = shareRequireGrant, onCheckedChange = { shareRequireGrant = it })
                            Text("Require access request — hide password until I grant", color = HubText)
                        }
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Checkbox(checked = shareEmailOtp, onCheckedChange = { shareEmailOtp = it })
                            Text("Require Email OTP to view password", color = HubText)
                        }
                        if (shareEmailOtp) {
                            OutlinedTextField(
                                value = shareAllowedEmails,
                                onValueChange = { shareAllowedEmails = it },
                                label = { Text("Allowed emails (optional)") },
                                modifier = Modifier.fillMaxWidth(),
                                colors = fieldColors
                            )
                            Text(
                                "If set, only these addresses can get a code. Leave blank for any email.",
                                color = HubTextDim,
                                style = MaterialTheme.typography.bodySmall
                            )
                        }
                        shareError?.let { Text(it, color = StampRed, style = MaterialTheme.typography.bodySmall) }
                    }
                }
            },
            confirmButton = {
                if (shareReady != null) {
                    TextButton(onClick = {
                        val (token, needsTotp) = shareReady!!
                        val url = "$base/v/$token"
                        val shareText = if (needsTotp) "Password: $url\nAuthenticator QR: $url/qr" else url
                        context.startActivity(Intent(Intent.ACTION_SEND).apply {
                            type = "text/plain"
                            putExtra(Intent.EXTRA_TEXT, shareText)
                        })
                        showShare = false
                    }) { Text("Share", color = VaultGold) }
                } else {
                    TextButton(
                        enabled = !shareBusy,
                        onClick = {
                            scope.launch {
                                shareBusy = true
                                shareError = null
                                val emails = shareAllowedEmails
                                    .split(',', ';', '\n')
                                    .map { it.trim() }
                                    .filter { it.contains('@') }
                                runCatching {
                                    repository.createVaultSend(
                                        VaultSendCreate(
                                            name = currentItem.name,
                                            send_type = "login",
                                            item_id = itemId,
                                            pin = sharePin.ifBlank { null },
                                            expires_in_hours = shareHours.toIntOrNull() ?: 48,
                                            max_views = if (shareOneTime) 1 else null,
                                            include_totp = shareIncludeTotp && currentItem.has_totp,
                                            require_grant = shareRequireGrant,
                                            require_email_otp = shareEmailOtp,
                                            allowed_emails = emails,
                                            require_vault_user_email = false
                                        )
                                    )
                                }.onSuccess { created ->
                                    shareReady = created.token to created.requires_totp
                                    val url = "$base/v/${created.token}"
                                    val shareText = if (created.requires_totp) {
                                        "Password: $url\nAuthenticator QR: $url/qr"
                                    } else url
                                    ClipboardUtil.copy(context, "Send link", shareText)
                                }.onFailure {
                                    shareError = it.message ?: "Could not create share"
                                }
                                shareBusy = false
                            }
                        }
                    ) { Text(if (shareBusy) "Creating…" else "Create share link", color = VaultGold) }
                }
            },
            dismissButton = {
                TextButton(onClick = { if (!shareBusy) showShare = false }) {
                    Text("Close", color = HubTextDim)
                }
            }
        )
    }
}

@Composable
private fun CopyRow(label: String, value: String?, secret: Boolean = false) {
    if (value.isNullOrBlank()) return
    val context = LocalContext.current
    var hidden by remember { mutableStateOf(secret) }
    Row(
        Modifier.fillMaxWidth().padding(vertical = 8.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(Modifier.weight(1f)) {
            Text(label, style = MaterialTheme.typography.labelSmall, color = HubTextDim)
            Text(
                if (hidden) "••••••••" else value,
                color = HubText,
                fontFamily = if (secret) FontFamily.Monospace else FontFamily.Default
            )
        }
        if (secret) {
            IconButton(onClick = { hidden = !hidden }) {
                Icon(
                    if (hidden) Icons.Filled.Visibility else Icons.Filled.VisibilityOff,
                    contentDescription = if (hidden) "Show $label" else "Hide $label",
                    tint = VaultGold
                )
            }
        }
        IconButton(onClick = { ClipboardUtil.copy(context, label, value) }) {
            Icon(Icons.Filled.ContentCopy, contentDescription = "Copy $label", tint = VaultGold)
        }
    }
}

@Composable
private fun MetaRow(label: String, value: String) {
    Row(
        Modifier.fillMaxWidth().padding(vertical = 6.dp),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(label, style = MaterialTheme.typography.labelSmall, color = HubTextDim)
        Text(value, color = HubText, fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.bodySmall)
    }
}

private fun formatVaultDate(iso: String): String = try {
    val text = iso.trim().removeSuffix("Z").replace(" ", "T")
    LocalDateTime.parse(text.take(19), DateTimeFormatter.ISO_LOCAL_DATE_TIME)
        .format(DateTimeFormatter.ofPattern("dd MMM yyyy, h:mm:ss a"))
} catch (_: Exception) {
    iso.replace("T", " ").take(19)
}
