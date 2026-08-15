package com.rklab.healthvault.ui.screens.passwords

import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.rklab.healthvault.data.model.VaultItemOut
import com.rklab.healthvault.data.model.VaultSendCreate
import com.rklab.healthvault.data.model.VaultSendOut
import com.rklab.healthvault.data.model.VaultSendRequestOut
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
import java.io.File
import kotlin.random.Random
import kotlinx.coroutines.launch

@Composable
fun VaultSendsScreen(repository: HealthVaultRepository, prefillItemId: String? = null) {
    val context = LocalContext.current
    val uriHandler = LocalUriHandler.current
    val scope = rememberCoroutineScope()
    var sends by remember { mutableStateOf<List<VaultSendOut>>(emptyList()) }
    var requests by remember { mutableStateOf<List<VaultSendRequestOut>>(emptyList()) }
    var items by remember { mutableStateOf<List<VaultItemOut>>(emptyList()) }
    var name by remember { mutableStateOf("") }
    var text by remember { mutableStateOf("") }
    var sendType by remember { mutableStateOf(if (prefillItemId != null) "login" else "text") }
    var itemId by remember { mutableStateOf(prefillItemId) }
    var pin by remember { mutableStateOf("") }
    var hours by remember { mutableStateOf("48") }
    var oneTime by remember { mutableStateOf(false) }
    var includeTotp by remember { mutableStateOf(false) }
    var requireGrant by remember { mutableStateOf(false) }
    val fieldColors = vaultFieldColors()
    val selectedItem = items.firstOrNull { it.id == itemId }
    val canIncludeTotp = sendType == "login" && selectedItem?.has_totp == true

    fun reload() {
        scope.launch {
            sends = runCatching { repository.listVaultSends() }.getOrDefault(emptyList())
            requests = runCatching { repository.listVaultSendRequests("all") }.getOrDefault(emptyList())
            items = runCatching { repository.listVaultItems(itemType = "login") }.getOrDefault(emptyList())
            if (prefillItemId != null) {
                items.firstOrNull { it.id == prefillItemId }?.let { name = it.name }
            }
        }
    }
    LaunchedEffect(Unit) { reload() }
    LaunchedEffect(canIncludeTotp) {
        if (!canIncludeTotp) includeTotp = false
    }
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
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = androidx.compose.ui.Alignment.CenterVertically
                ) {
                    OutlinedTextField(
                        pin, { pin = it }, label = { Text("Access code / OTP (optional)") },
                        modifier = Modifier.weight(1f), singleLine = true, colors = fieldColors
                    )
                    TextButton(onClick = { pin = generateAccessCode() }) {
                        Text("Generate", color = VaultGold)
                    }
                }
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
                if (canIncludeTotp) {
                    Row(
                        Modifier.fillMaxWidth(),
                        verticalAlignment = androidx.compose.ui.Alignment.CenterVertically
                    ) {
                        Checkbox(checked = includeTotp, onCheckedChange = { includeTotp = it })
                        Text("Require authenticator to view password", color = HubText)
                    }
                }
                Row(
                    Modifier.fillMaxWidth(),
                    verticalAlignment = androidx.compose.ui.Alignment.CenterVertically
                ) {
                    Checkbox(checked = requireGrant, onCheckedChange = { requireGrant = it })
                    Text("Require access request — hide secret until I grant", color = HubText)
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
                                        include_totp = includeTotp && canIncludeTotp,
                                        require_grant = requireGrant
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
                                name = ""; text = ""; pin = ""; oneTime = false; includeTotp = false; requireGrant = false; reload()
                            }
                        }
                    }
                )
                Spacer(Modifier.height(16.dp))
                if (requests.isNotEmpty()) {
                    Text(
                        "ACCESS REQUESTS",
                        style = MaterialTheme.typography.labelMedium,
                        color = VaultGold
                    )
                    Spacer(Modifier.height(8.dp))
                }
            }
            items(requests, key = { "req-${it.id}" }) { req ->
                AccessRequestCard(
                    repository = repository,
                    req = req,
                    onMaps = { lat, lng ->
                        runCatching {
                            uriHandler.openUri("https://maps.google.com/?q=$lat,$lng")
                        }
                    },
                    onChanged = { reload() }
                )
            }
            item {
                Spacer(Modifier.height(16.dp))
                Text(
                    "YOUR SENDS",
                    style = MaterialTheme.typography.labelMedium,
                    color = VaultGold
                )
            }
            items(sends, key = { it.id }) { send ->
                SendCard(
                    send = send,
                    base = base,
                    onCopy = { label, value -> ClipboardUtil.copy(context, label, value) },
                    onRevoke = {
                        scope.launch { repository.revokeVaultSend(send.id); reload() }
                    }
                )
            }
        }
    }
}

@Composable
private fun AccessRequestCard(
    repository: HealthVaultRepository,
    req: VaultSendRequestOut,
    onMaps: (String, String) -> Unit,
    onChanged: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var photoFile by remember(req.id, req.has_photo) { mutableStateOf<File?>(null) }

    LaunchedEffect(req.id, req.has_photo) {
        if (!req.has_photo) {
            photoFile = null
            return@LaunchedEffect
        }
        photoFile = runCatching {
            val dest = File(context.cacheDir, "send_req_${req.id}.jpg")
            repository.downloadVaultSendRequestPhoto(req.id, dest)
        }.getOrNull()
    }

    Column(
        Modifier
            .fillMaxWidth()
            .clip(VaultCardShape)
            .background(HubGlass)
            .border(1.dp, HubStroke, VaultCardShape)
            .padding(14.dp)
    ) {
        val who = listOfNotNull(req.name, req.email).joinToString(" · ").ifBlank { "Anonymous" }
        Text(who, color = HubText, fontWeight = FontWeight.SemiBold)
        Text("Asked for ${req.send_name}", color = HubTextDim, style = MaterialTheme.typography.bodySmall)
        Text(
            listOfNotNull(req.ip, req.status, req.created_at.take(16)).joinToString(" · "),
            color = HubTextDim,
            style = MaterialTheme.typography.bodySmall
        )
        req.user_agent?.takeIf { it.isNotBlank() }?.let { ua ->
            Text(
                ua.take(96) + if (ua.length > 96) "…" else "",
                color = HubTextDim,
                style = MaterialTheme.typography.bodySmall
            )
        }
        if (!req.latitude.isNullOrBlank() && !req.longitude.isNullOrBlank()) {
            Text(
                "Loc ${req.latitude}, ${req.longitude} · Open map",
                color = VaultGold,
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.clickable { onMaps(req.latitude!!, req.longitude!!) }
            )
        }
        photoFile?.let { file ->
            Spacer(Modifier.height(8.dp))
            AsyncImage(
                model = file,
                contentDescription = "Access request photo",
                contentScale = ContentScale.Crop,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(160.dp)
                    .clip(RoundedCornerShape(12.dp))
            )
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (req.status == "pending" || req.status == "seen") {
                TextButton(onClick = {
                    scope.launch {
                        runCatching { repository.grantVaultSendRequest(req.id) }
                        onChanged()
                    }
                }) { Text("Grant access", color = VaultGold) }
            }
            if (req.status == "pending") {
                TextButton(onClick = {
                    scope.launch {
                        runCatching { repository.markVaultSendRequestSeen(req.id) }
                        onChanged()
                    }
                }) { Text("Mark seen", color = VaultGold) }
            }
            if (req.status != "dismissed") {
                TextButton(onClick = {
                    scope.launch {
                        runCatching { repository.dismissVaultSendRequest(req.id) }
                        onChanged()
                    }
                }) { Text("Dismiss", color = StampRed) }
            }
        }
    }
}

@Composable
private fun SendCard(
    send: VaultSendOut,
    base: String,
    onCopy: (String, String) -> Unit,
    onRevoke: () -> Unit
) {
    val url = "$base/v/${send.token}"
    val qrUrl = "$url/qr"
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
        Spacer(Modifier.height(6.dp))
        Row(
            Modifier.horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            SendBadge("Expires ${send.expires_at.take(16)}")
            if (send.has_pin) SendBadge("Access code")
            if (send.requires_totp) SendBadge("Authenticator")
            if (send.requires_grant) SendBadge("Grant required")
            send.max_views?.let { SendBadge(if (it == 1) "One-time" else "Max $it views") }
        }
        Spacer(Modifier.height(8.dp))
        Text(url, color = VaultGold, style = MaterialTheme.typography.bodySmall)
        if (send.requires_totp) {
            Text(qrUrl, color = HubTextDim, style = MaterialTheme.typography.bodySmall)
        }
        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            TextButton(onClick = { onCopy("Password link", url) }) {
                Text(if (send.requires_totp) "Copy password link" else "Copy link", color = VaultGold)
            }
            if (send.requires_totp) {
                TextButton(onClick = { onCopy("QR link", qrUrl) }) {
                    Text("Copy QR link", color = VaultGold)
                }
            }
            if (!send.revoked) {
                TextButton(onClick = onRevoke) { Text("Revoke", color = StampRed) }
            }
        }
    }
}

@Composable
private fun SendBadge(label: String) {
    Text(
        label,
        color = HubTextDim,
        style = MaterialTheme.typography.labelSmall,
        modifier = Modifier
            .clip(RoundedCornerShape(999.dp))
            .background(HubBg)
            .border(1.dp, HubStroke, RoundedCornerShape(999.dp))
            .padding(horizontal = 8.dp, vertical = 4.dp)
    )
}

internal fun generateAccessCode(): String =
    (100000 + Random.nextInt(900000)).toString()
