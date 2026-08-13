package com.rklab.healthvault.ui.screens.passwords

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.outlined.StarBorder
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import com.rklab.healthvault.data.model.VaultHistoryOut
import com.rklab.healthvault.data.model.VaultItemOut
import com.rklab.healthvault.data.model.VaultTotpOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.theme.*
import com.rklab.healthvault.util.ClipboardUtil
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
    var showPassword by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

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
    Column(Modifier.fillMaxSize().background(Paper).padding(20.dp).verticalScroll(rememberScrollState())) {
        TextButton(onClick = onBack) { Text("← Vault", color = Navy) }
        if (error != null) Text(error!!, color = StampRed)
        if (current == null) {
            CircularProgressIndicator(color = Navy)
            return@Column
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(current.item_type.uppercase(), style = MaterialTheme.typography.labelMedium, color = InkSoft)
                Text(current.name, style = MaterialTheme.typography.headlineMedium, color = Ink)
            }
            IconButton(onClick = {
                scope.launch {
                    if (current.favorite) repository.unfavoriteVaultItem(itemId) else repository.favoriteVaultItem(itemId)
                    load()
                }
            }) {
                Icon(if (current.favorite) Icons.Filled.Star else Icons.Outlined.StarBorder, null, tint = Mustard)
            }
        }
        Spacer(Modifier.height(16.dp))
        totp?.let {
            Surface(color = SageBg, shape = MaterialTheme.shapes.medium) {
                Row(Modifier.fillMaxWidth().padding(14.dp), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                    Column {
                        Text("Authenticator", color = InkSoft, style = MaterialTheme.typography.labelSmall)
                        Text(it.code, color = Sage, style = MaterialTheme.typography.headlineMedium, fontFamily = FontFamily.Monospace)
                    }
                    Column(horizontalAlignment = Alignment.End) {
                        Text("${it.remaining}s", color = InkSoft)
                        IconButton(onClick = { ClipboardUtil.copy(context, "Code", it.code) }) {
                            Icon(Icons.Filled.ContentCopy, null, tint = Sage)
                        }
                    }
                }
            }
            Spacer(Modifier.height(12.dp))
        }
        CopyRow("Username", current.username)
        CopyRow("Password", current.password, secret = !showPassword, onToggle = { showPassword = !showPassword })
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
        Spacer(Modifier.height(16.dp))
        Button(onClick = onEdit, modifier = Modifier.fillMaxWidth(), colors = ButtonDefaults.buttonColors(containerColor = Navy)) {
            Text("Edit", color = TextWhite)
        }
        Spacer(Modifier.height(8.dp))
        OutlinedButton(onClick = onSend, modifier = Modifier.fillMaxWidth()) { Text("Send a copy", color = Navy) }
        Spacer(Modifier.height(8.dp))
        OutlinedButton(onClick = {
            scope.launch {
                runCatching { repository.trashVaultItem(itemId) }
                onBack()
            }
        }, modifier = Modifier.fillMaxWidth()) { Text("Move to trash", color = StampRed) }
        if (history.isNotEmpty()) {
            Spacer(Modifier.height(20.dp))
            Text("PASSWORD HISTORY", style = MaterialTheme.typography.labelMedium, color = InkSoft)
            Spacer(Modifier.height(8.dp))
            history.forEach { h ->
                CopyRow(h.created_at.take(16).replace('T', ' '), h.password, secret = true)
            }
        }
    }
}

@Composable
private fun CopyRow(label: String, value: String?, secret: Boolean = false, onToggle: (() -> Unit)? = null) {
    if (value.isNullOrBlank()) return
    val context = LocalContext.current
    Row(
        Modifier.fillMaxWidth().padding(vertical = 8.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(Modifier.weight(1f)) {
            Text(label, style = MaterialTheme.typography.labelSmall, color = InkSoft)
            Text(if (secret) "••••••••" else value, color = Ink, fontFamily = if (secret) FontFamily.Monospace else FontFamily.Default)
            if (onToggle != null) {
                TextButton(onClick = onToggle) { Text(if (secret) "Show" else "Hide", color = Navy) }
            }
        }
        IconButton(onClick = { ClipboardUtil.copy(context, label, value) }) {
            Icon(Icons.Filled.ContentCopy, contentDescription = "Copy $label", tint = Navy)
        }
    }
}
