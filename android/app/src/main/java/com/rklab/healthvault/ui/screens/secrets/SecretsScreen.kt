package com.rklab.healthvault.ui.screens.secrets

import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Checkbox
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
import androidx.compose.ui.unit.dp
import com.rklab.healthvault.data.model.VaultSendCreate
import com.rklab.healthvault.data.model.VaultSendOut
import com.rklab.healthvault.data.model.VaultSendRequestOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.components.VaultPageHeader
import com.rklab.healthvault.ui.components.VaultPrimaryButton
import com.rklab.healthvault.ui.components.vaultFieldColors
import com.rklab.healthvault.ui.theme.HubBg
import com.rklab.healthvault.ui.theme.HubText
import com.rklab.healthvault.ui.theme.HubTextDim
import com.rklab.healthvault.ui.theme.StampRed
import com.rklab.healthvault.ui.theme.VaultGold
import com.rklab.healthvault.util.ClipboardUtil
import kotlinx.coroutines.launch
import kotlin.random.Random

@Composable
fun SecretsScreen(repository: HealthVaultRepository, onOpenModules: () -> Unit = {}) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val fieldColors = vaultFieldColors()
    var sends by remember { mutableStateOf<List<VaultSendOut>>(emptyList()) }
    var requests by remember { mutableStateOf<List<VaultSendRequestOut>>(emptyList()) }
    var name by remember { mutableStateOf("") }
    var text by remember { mutableStateOf("") }
    var pin by remember { mutableStateOf("") }
    var hours by remember { mutableStateOf("48") }
    var oneTime by remember { mutableStateOf(false) }
    var requireGrant by remember { mutableStateOf(false) }
    var requireEmailOtp by remember { mutableStateOf(false) }
    var allowedEmails by remember { mutableStateOf("") }
    var bindFirstBrowser by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    fun reload() {
        scope.launch {
            sends = runCatching { repository.listSecretSends() }.getOrDefault(emptyList())
            requests = runCatching { repository.listSecretSendRequests("all") }.getOrDefault(emptyList())
        }
    }
    LaunchedEffect(Unit) { reload() }
    val base = repository.getServerUrl()?.trimEnd('/') ?: ""

    Column(
        Modifier
            .fillMaxSize()
            .background(HubBg)
            .padding(horizontal = 20.dp)
    ) {
        VaultPageHeader(
            eyebrow = "SECRET SHARE",
            title = "Share a secret",
            actions = {
                TextButton(onClick = onOpenModules) { Text("Modules", color = HubTextDim) }
            }
        )
        Text(
            "Paste text, create an expiring link. Optional first-browser lock.",
            color = HubTextDim,
            style = MaterialTheme.typography.bodySmall
        )
        Spacer(Modifier.height(8.dp))
        LazyColumn(
            verticalArrangement = Arrangement.spacedBy(10.dp),
            contentPadding = PaddingValues(bottom = 40.dp)
        ) {
            item {
                OutlinedTextField(
                    name, { name = it }, label = { Text("Name") },
                    modifier = Modifier.fillMaxWidth(), singleLine = true, colors = fieldColors
                )
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(
                    text, { text = it }, label = { Text("Secret") },
                    modifier = Modifier.fillMaxWidth().height(120.dp), colors = fieldColors
                )
                Spacer(Modifier.height(8.dp))
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    OutlinedTextField(
                        pin, { pin = it }, label = { Text("Access code (optional)") },
                        modifier = Modifier.weight(1f), singleLine = true, colors = fieldColors
                    )
                    TextButton(onClick = {
                        pin = (1..6).map { Random.nextInt(0, 10) }.joinToString("")
                    }) { Text("Generate", color = VaultGold) }
                }
                OutlinedTextField(
                    hours, { hours = it.filter(Char::isDigit) }, label = { Text("Expires in hours") },
                    modifier = Modifier.fillMaxWidth(), singleLine = true, colors = fieldColors
                )
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(checked = oneTime, onCheckedChange = { oneTime = it })
                    Text("One-time view", color = HubText)
                }
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(checked = requireGrant, onCheckedChange = { requireGrant = it })
                    Text("Require access request", color = HubText)
                }
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(checked = requireEmailOtp, onCheckedChange = { requireEmailOtp = it })
                    Text("Require Email OTP", color = HubText)
                }
                if (requireEmailOtp) {
                    OutlinedTextField(
                        allowedEmails, { allowedEmails = it },
                        label = { Text("Allowed emails (optional)") },
                        modifier = Modifier.fillMaxWidth(), colors = fieldColors
                    )
                }
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(checked = bindFirstBrowser, onCheckedChange = { bindFirstBrowser = it })
                    Text("Lock to first browser that opens the link", color = HubText)
                }
                if (error != null) {
                    Text(error!!, color = StampRed, style = MaterialTheme.typography.bodySmall)
                }
                Spacer(Modifier.height(8.dp))
                VaultPrimaryButton(
                    text = "Create share link",
                    onClick = {
                        scope.launch {
                            error = null
                            if (text.isBlank()) {
                                error = "Secret text is required"
                                return@launch
                            }
                            val emails = allowedEmails
                                .split(',', ';', '\n')
                                .map { it.trim() }
                                .filter { it.contains('@') }
                            runCatching {
                                val created = repository.createSecretSend(
                                    VaultSendCreate(
                                        name = name.ifBlank { "Secret" },
                                        send_type = "secret",
                                        text = text,
                                        pin = pin.ifBlank { null },
                                        expires_in_hours = hours.toIntOrNull() ?: 48,
                                        max_views = if (oneTime) 1 else null,
                                        require_grant = requireGrant,
                                        require_email_otp = requireEmailOtp,
                                        allowed_emails = emails,
                                        bind_first_browser = bindFirstBrowser
                                    )
                                )
                                val url = "$base/v/${created.token}"
                                ClipboardUtil.copy(context, "Secret link", url)
                                context.startActivity(Intent(Intent.ACTION_SEND).apply {
                                    type = "text/plain"
                                    putExtra(Intent.EXTRA_TEXT, url)
                                })
                                name = ""; text = ""; pin = ""; oneTime = false
                                requireGrant = false; requireEmailOtp = false
                                allowedEmails = ""; bindFirstBrowser = false
                                reload()
                            }.onFailure { error = it.message ?: "Could not create share" }
                        }
                    }
                )
            }
            if (requests.isNotEmpty()) {
                item {
                    Text("Access / blocked", color = HubText, style = MaterialTheme.typography.titleMedium)
                }
                items(requests, key = { it.id }) { req ->
                    Column(Modifier.padding(vertical = 4.dp)) {
                        Text(req.send_name.ifBlank { "Share" }, color = HubText)
                        Text(
                            "${req.status} · ${req.user_agent?.take(48) ?: req.ip ?: "—"}",
                            color = HubTextDim,
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                }
            }
            item {
                Text("Active shares", color = HubText, style = MaterialTheme.typography.titleMedium)
            }
            items(sends.filter { !it.revoked }, key = { it.id }) { send ->
                Column(Modifier.padding(vertical = 6.dp)) {
                    Text(send.name, color = HubText)
                    val url = "$base/v/${send.token}"
                    Text(url, color = HubTextDim, style = MaterialTheme.typography.bodySmall)
                    Text(
                        buildString {
                            append("${send.view_count} views · expires ${send.expires_at.take(16)}")
                            if (send.bind_first_browser) {
                                append(" · first browser")
                                if (send.browser_bound) append(" (bound)")
                            }
                        },
                        color = HubTextDim,
                        style = MaterialTheme.typography.bodySmall
                    )
                    Row {
                        TextButton(onClick = { ClipboardUtil.copy(context, "Secret link", url) }) {
                            Text("Copy", color = VaultGold)
                        }
                        TextButton(onClick = {
                            scope.launch {
                                runCatching { repository.revokeSecretSend(send.id) }
                                reload()
                            }
                        }) { Text("Revoke", color = StampRed) }
                    }
                }
            }
        }
    }
}
