package com.rklab.healthvault.ui.screens.passwords

import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.rklab.healthvault.data.model.VaultItemOut
import com.rklab.healthvault.data.model.VaultSendCreate
import com.rklab.healthvault.data.model.VaultSendOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.components.VaultCardShape
import com.rklab.healthvault.ui.components.VaultFilterChip
import com.rklab.healthvault.ui.components.VaultPageHeader
import com.rklab.healthvault.ui.components.VaultPrimaryButton
import com.rklab.healthvault.ui.components.vaultFieldColors
import com.rklab.healthvault.ui.theme.HubBg
import com.rklab.healthvault.ui.theme.HubGlass
import com.rklab.healthvault.ui.theme.HubStroke
import com.rklab.healthvault.ui.theme.HubText
import com.rklab.healthvault.ui.theme.HubTextDim
import com.rklab.healthvault.ui.theme.StampRed
import com.rklab.healthvault.ui.theme.VaultGold
import com.rklab.healthvault.util.ClipboardUtil
import kotlinx.coroutines.launch

@Composable
fun VaultSendsScreen(repository: HealthVaultRepository, prefillItemId: String? = null) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var sends by remember { mutableStateOf<List<VaultSendOut>>(emptyList()) }
    var items by remember { mutableStateOf<List<VaultItemOut>>(emptyList()) }
    var name by remember { mutableStateOf("") }
    var text by remember { mutableStateOf("") }
    var sendType by remember { mutableStateOf(if (prefillItemId != null) "login" else "text") }
    var itemId by remember { mutableStateOf(prefillItemId) }
    var pin by remember { mutableStateOf("") }
    var hours by remember { mutableStateOf("48") }
    var oneTime by remember { mutableStateOf(false) }
    var includeTotp by remember { mutableStateOf(false) }
    val fieldColors = vaultFieldColors()

    fun reload() {
        scope.launch {
            sends = runCatching { repository.listVaultSends() }.getOrDefault(emptyList())
            items = runCatching { repository.listVaultItems(itemType = "login") }.getOrDefault(emptyList())
            if (prefillItemId != null) {
                items.firstOrNull { it.id == prefillItemId }?.let { name = it.name }
            }
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
            eyebrow = "SEND",
            title = "Share a secret"
        )
        Spacer(Modifier.height(4.dp))
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
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    VaultFilterChip(
                        selected = sendType == "text",
                        onClick = { sendType = "text" },
                        label = "Text"
                    )
                    VaultFilterChip(
                        selected = sendType == "login",
                        onClick = { sendType = "login" },
                        label = "Login"
                    )
                }
                Spacer(Modifier.height(8.dp))
                if (sendType == "text") {
                    OutlinedTextField(
                        text, { text = it }, label = { Text("Text") },
                        modifier = Modifier.fillMaxWidth(), colors = fieldColors
                    )
                } else {
                    Row(
                        Modifier.horizontalScroll(rememberScrollState()),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        items.forEach { item ->
                            VaultFilterChip(
                                selected = itemId == item.id,
                                onClick = { itemId = item.id; if (name.isBlank()) name = item.name },
                                label = item.name
                            )
                        }
                    }
                }
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(
                    pin, { pin = it }, label = { Text("Access code / OTP (optional)") },
                    modifier = Modifier.fillMaxWidth(), singleLine = true, colors = fieldColors
                )
                OutlinedTextField(
                    hours, { hours = it.filter(Char::isDigit) }, label = { Text("Expires in hours") },
                    modifier = Modifier.fillMaxWidth(), singleLine = true, colors = fieldColors
                )
                Row(
                    Modifier.fillMaxWidth().padding(top = 4.dp),
                    verticalAlignment = androidx.compose.ui.Alignment.CenterVertically
                ) {
                    Checkbox(checked = oneTime, onCheckedChange = { oneTime = it })
                    Text("One-time view", color = HubText)
                }
                if (sendType == "login") {
                    Row(
                        Modifier.fillMaxWidth(),
                        verticalAlignment = androidx.compose.ui.Alignment.CenterVertically
                    ) {
                        Checkbox(checked = includeTotp, onCheckedChange = { includeTotp = it })
                        Text("Require authenticator to view password", color = HubText)
                    }
                }
                Spacer(Modifier.height(8.dp))
                VaultPrimaryButton(
                    text = "Create send",
                    onClick = {
                        scope.launch {
                            runCatching {
                                val created = repository.createVaultSend(
                                    VaultSendCreate(
                                        name = name.ifBlank { "Send" },
                                        send_type = sendType,
                                        text = text.ifBlank { null },
                                        item_id = itemId,
                                        pin = pin.ifBlank { null },
                                        expires_in_hours = hours.toIntOrNull() ?: 48,
                                        max_views = if (oneTime) 1 else null,
                                        include_totp = includeTotp && sendType == "login"
                                    )
                                )
                                val url = "$base/v/${created.token}"
                                val shareText = if (created.requires_totp) {
                                    "Password: $url\nAuthenticator QR: $url/qr"
                                } else url
                                ClipboardUtil.copy(context, "Send link", shareText)
                                context.startActivity(Intent(Intent.ACTION_SEND).apply {
                                    type = "text/plain"
                                    putExtra(Intent.EXTRA_TEXT, shareText)
                                })
                                name = ""; text = ""; pin = ""; oneTime = false; includeTotp = false; reload()
                            }
                        }
                    }
                )
                Spacer(Modifier.height(16.dp))
                Text(
                    "YOUR SENDS",
                    style = MaterialTheme.typography.labelMedium,
                    color = VaultGold
                )
            }
            items(sends, key = { it.id }) { send ->
                Column(
                    Modifier
                        .fillMaxWidth()
                        .clip(VaultCardShape)
                        .background(HubGlass)
                        .border(1.dp, HubStroke, VaultCardShape)
                        .padding(14.dp)
                ) {
                    Text(send.name, color = HubText, fontWeight = FontWeight.SemiBold)
                    Text(
                        "${send.send_type} · ${send.view_count} views · ${if (send.revoked) "revoked" else "active"}",
                        color = HubTextDim,
                        style = MaterialTheme.typography.bodySmall
                    )
                    val url = "$base/v/${send.token}"
                    Text(url, color = VaultGold, style = MaterialTheme.typography.bodySmall)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        TextButton(onClick = { ClipboardUtil.copy(context, "Send link", url) }) {
                            Text("Copy link", color = VaultGold)
                        }
                        if (!send.revoked) {
                            TextButton(onClick = {
                                scope.launch { repository.revokeVaultSend(send.id); reload() }
                            }) { Text("Revoke", color = StampRed) }
                        }
                    }
                }
            }
        }
    }
}
