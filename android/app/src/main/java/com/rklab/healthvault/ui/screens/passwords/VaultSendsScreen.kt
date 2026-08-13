package com.rklab.healthvault.ui.screens.passwords

import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.rklab.healthvault.data.model.VaultItemOut
import com.rklab.healthvault.data.model.VaultSendCreate
import com.rklab.healthvault.data.model.VaultSendOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.theme.*
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

    Column(Modifier.fillMaxSize().background(Paper).padding(20.dp)) {
        Text("SEND", style = MaterialTheme.typography.labelMedium, color = InkSoft)
        Text("Share a secret", style = MaterialTheme.typography.headlineMedium, color = Ink)
        Spacer(Modifier.height(12.dp))
        LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp), contentPadding = PaddingValues(bottom = 40.dp)) {
            item {
                OutlinedTextField(name, { name = it }, label = { Text("Name") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterChip(selected = sendType == "text", onClick = { sendType = "text" }, label = { Text("Text") })
                    FilterChip(selected = sendType == "login", onClick = { sendType = "login" }, label = { Text("Login") })
                }
                if (sendType == "text") {
                    OutlinedTextField(text, { text = it }, label = { Text("Text") }, modifier = Modifier.fillMaxWidth())
                } else {
                    items.forEach { item ->
                        FilterChip(
                            selected = itemId == item.id,
                            onClick = { itemId = item.id; if (name.isBlank()) name = item.name },
                            label = { Text(item.name) }
                        )
                    }
                }
                OutlinedTextField(pin, { pin = it }, label = { Text("PIN (optional)") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                OutlinedTextField(hours, { hours = it.filter(Char::isDigit) }, label = { Text("Expires in hours") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                Spacer(Modifier.height(8.dp))
                Button(
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
                                        expires_in_hours = hours.toIntOrNull() ?: 48
                                    )
                                )
                                val url = "$base/v/${created.token}"
                                ClipboardUtil.copy(context, "Send link", url)
                                context.startActivity(Intent(Intent.ACTION_SEND).apply {
                                    type = "text/plain"
                                    putExtra(Intent.EXTRA_TEXT, url)
                                })
                                name = ""; text = ""; pin = ""; reload()
                            }
                        }
                    },
                    modifier = Modifier.fillMaxWidth(),
                    colors = ButtonDefaults.buttonColors(containerColor = Navy)
                ) { Text("Create send", color = TextWhite) }
                Spacer(Modifier.height(16.dp))
                Text("YOUR SENDS", style = MaterialTheme.typography.labelMedium, color = InkSoft)
            }
            items(sends, key = { it.id }) { send ->
                Column(Modifier.fillMaxWidth().padding(vertical = 8.dp)) {
                    Text(send.name, color = Ink)
                    Text(
                        "${send.send_type} · ${send.view_count} views · ${if (send.revoked) "revoked" else "active"}",
                        color = InkSoft,
                        style = MaterialTheme.typography.bodySmall
                    )
                    val url = "$base/v/${send.token}"
                    Text(url, color = Navy, style = MaterialTheme.typography.bodySmall)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        TextButton(onClick = { ClipboardUtil.copy(context, "Send link", url) }) { Text("Copy link", color = Navy) }
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
