package com.rklab.healthvault.ui.screens.tracker

import android.content.Intent
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Apps
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.DoneAll
import androidx.compose.material.icons.filled.RadioButtonUnchecked
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import com.rklab.healthvault.data.model.*
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.theme.HubBg
import com.rklab.healthvault.ui.theme.HubGlass
import com.rklab.healthvault.ui.theme.Ink
import com.rklab.healthvault.ui.theme.InkSoft
import com.rklab.healthvault.ui.theme.Navy
import com.rklab.healthvault.ui.theme.StampRed
import com.rklab.healthvault.ui.theme.TextDark
import com.rklab.healthvault.ui.theme.VaultGold
import com.rklab.healthvault.util.FileUtil
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.net.URLEncoder
import android.net.Uri

private fun shopDateLabel(raw: String?): String? {
    val value = raw?.trim().orEmpty()
    if (value.isBlank()) return null
    return value.take(16).replace('T', ' ')
}

@Composable
fun ShopListScreen(
    repository: HealthVaultRepository,
    onOpenList: (String) -> Unit,
    onOpenModules: () -> Unit
) {
    val scope = rememberCoroutineScope()
    var lists by remember { mutableStateOf<List<ShopListOut>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var showCreate by remember { mutableStateOf(false) }
    var newName by remember { mutableStateOf("") }

    fun reload() {
        scope.launch {
            loading = true
            error = null
            runCatching { lists = repository.listShopLists() }
                .onFailure { error = it.message ?: "Could not load lists" }
            loading = false
        }
    }
    LaunchedEffect(Unit) { reload() }

    Box(Modifier.fillMaxSize().background(HubBg)) {
        Column(Modifier.fillMaxSize()) {
            Row(
                Modifier.fillMaxWidth().padding(20.dp, 16.dp, 8.dp, 0.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text("SHOPPING LIST", style = MaterialTheme.typography.labelMedium, color = VaultGold)
                    Text("Lists", style = MaterialTheme.typography.headlineMedium, color = Ink, fontWeight = FontWeight.Bold)
                }
                IconButton(onClick = onOpenModules) {
                    Icon(Icons.Filled.Apps, contentDescription = "Modules", tint = InkSoft)
                }
            }
            when {
                loading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = Navy)
                }
                error != null -> Text(error!!, color = StampRed, modifier = Modifier.padding(20.dp))
                lists.isEmpty() -> Text(
                    "No shopping lists yet. Create one for this week’s market run.",
                    color = InkSoft,
                    modifier = Modifier.padding(20.dp)
                )
                else -> LazyColumn(
                    contentPadding = PaddingValues(20.dp, 12.dp, 20.dp, 88.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    items(lists, key = { it.id }) { lst ->
                        Surface(
                            shape = RoundedCornerShape(16.dp),
                            color = HubGlass,
                            modifier = Modifier.fillMaxWidth().clickable { onOpenList(lst.id) }
                        ) {
                            Column(Modifier.padding(16.dp)) {
                                Text(lst.name, color = Ink, fontWeight = FontWeight.SemiBold)
                                Text(
                                    buildString {
                                        append("${lst.item_count} items")
                                        lst.owner_name?.takeIf { it.isNotBlank() }?.let {
                                            append(" · "); append(it)
                                        }
                                        shopDateLabel(lst.created_at)?.let {
                                            append(" · "); append(it.take(10))
                                        }
                                        if (lst.pending_count > 0) append(" · ${lst.pending_count} pending")
                                        if (lst.completed) append(" · done")
                                    },
                                    color = InkSoft,
                                    style = MaterialTheme.typography.bodySmall
                                )
                            }
                        }
                    }
                }
            }
        }
        FloatingActionButton(
            onClick = { showCreate = true },
            modifier = Modifier.align(Alignment.BottomEnd).padding(20.dp),
            containerColor = Navy
        ) {
            Icon(Icons.Filled.Add, contentDescription = "New list", tint = TextDark)
        }
    }

    if (showCreate) {
        AlertDialog(
            onDismissRequest = { showCreate = false },
            title = { Text("New list") },
            text = {
                OutlinedTextField(
                    value = newName,
                    onValueChange = { newName = it },
                    label = { Text("Name") },
                    singleLine = true
                )
            },
            confirmButton = {
                TextButton(onClick = {
                    val name = newName.trim()
                    if (name.isEmpty()) return@TextButton
                    scope.launch {
                        runCatching { repository.createShopList(ShopListIn(name)) }
                            .onSuccess {
                                newName = ""
                                showCreate = false
                                reload()
                            }
                    }
                }) { Text("Create") }
            },
            dismissButton = { TextButton(onClick = { showCreate = false }) { Text("Cancel") } }
        )
    }
}

@Composable
fun ShopDetailScreen(
    repository: HealthVaultRepository,
    listId: String,
    onBack: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var lst by remember { mutableStateOf<ShopListOut?>(null) }
    var loading by remember { mutableStateOf(true) }
    var newItem by remember { mutableStateOf("") }
    var newNotes by remember { mutableStateOf("") }
    var useAi by remember { mutableStateOf(true) }
    var suggestions by remember { mutableStateOf<List<ShopGroceryItemOut>>(emptyList()) }
    var editing by remember { mutableStateOf<ShopItemOut?>(null) }
    var showSend by remember { mutableStateOf(false) }
    var friends by remember { mutableStateOf<List<ShopContactOut>>(emptyList()) }
    var adding by remember { mutableStateOf(false) }

    fun reload() {
        scope.launch {
            loading = true
            runCatching { lst = repository.getShopList(listId) }
            runCatching { friends = repository.listShopFriends() }
            loading = false
        }
    }
    LaunchedEffect(listId) { reload() }
    LaunchedEffect(listId) {
        while (true) {
            delay(2500)
            runCatching { lst = repository.getShopList(listId) }
        }
    }
    LaunchedEffect(newItem, useAi) {
        val q = newItem.trim()
        if (!useAi || q.length < 2) {
            suggestions = emptyList()
            return@LaunchedEffect
        }
        delay(180)
        runCatching { suggestions = repository.suggestShopItems(q) }
            .onFailure { suggestions = emptyList() }
    }
    val items = lst?.items.orEmpty()
    val receipts = lst?.receipts.orEmpty()
    val pickBill = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            runCatching {
                val copied = FileUtil.copyUriToCacheFile(context, uri, "shop_${System.currentTimeMillis()}")
                val mime = FileUtil.mimeTypeOf(context, uri)
                val file = if (mime.startsWith("image/")) FileUtil.enhanceImageFile(copied) else copied
                repository.uploadShopReceipt(
                    listId,
                    file,
                    if (mime.startsWith("image/")) "image/jpeg" else mime
                )
            }.onSuccess { reload() }
                .onFailure {
                    Toast.makeText(context, it.message ?: "Could not save bill copy", Toast.LENGTH_SHORT).show()
                }
        }
    }

    Column(Modifier.fillMaxSize().background(HubBg)) {
        Row(
            Modifier.fillMaxWidth().padding(8.dp, 12.dp, 8.dp, 0.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            TextButton(onClick = onBack) { Text("Back", color = VaultGold) }
            Spacer(Modifier.weight(1f))
            IconButton(onClick = {
                scope.launch {
                    runCatching {
                        val current = repository.getShopList(listId)
                        repository.updateShopList(
                            listId,
                            ShopListUpdate(completed = !current.completed)
                        )
                    }.onSuccess { reload() }
                        .onFailure {
                            Toast.makeText(context, it.message ?: "Could not update", Toast.LENGTH_SHORT).show()
                        }
                }
            }) {
                Icon(
                    Icons.Filled.DoneAll,
                    contentDescription = if (lst?.completed == true) "Reopen" else "Mark done",
                    tint = if (lst?.completed == true) VaultGold else Ink
                )
            }
            IconButton(onClick = { showSend = true }) {
                Text("Send", color = VaultGold, style = MaterialTheme.typography.labelLarge)
            }
            IconButton(onClick = {
                scope.launch {
                    runCatching {
                        val share = repository.shareShopList(listId)
                        val detail = repository.getShopList(listId)
                        val lines = mutableListOf(detail.name, share.url, "")
                        detail.items.orEmpty().filter { it.status != "pending" }.forEach { item ->
                            var bit = item.name
                            if (item.quantity != 0.0) {
                                bit += " ${item.quantity}"
                                item.unit?.takeIf { it.isNotBlank() }?.let { bit += " $it" }
                            }
                            if (item.checked) bit += " ✓"
                            lines.add(bit)
                        }
                        val text = lines.joinToString("\n")
                        val uri = Uri.parse(
                            "https://wa.me/?text=" + URLEncoder.encode(text, "UTF-8")
                        )
                        context.startActivity(Intent(Intent.ACTION_VIEW, uri))
                    }.onFailure {
                        Toast.makeText(context, it.message ?: "WhatsApp share failed", Toast.LENGTH_SHORT).show()
                    }
                }
            }) {
                Text("WA", color = VaultGold, style = MaterialTheme.typography.labelLarge)
            }
            IconButton(onClick = {
                scope.launch {
                    runCatching { repository.shareShopList(listId) }.onSuccess { share ->
                        val send = Intent(Intent.ACTION_SEND).apply {
                            type = "text/plain"
                            putExtra(Intent.EXTRA_TEXT, share.url)
                        }
                        context.startActivity(Intent.createChooser(send, "Share list"))
                    }.onFailure {
                        Toast.makeText(context, it.message ?: "Share failed", Toast.LENGTH_SHORT).show()
                    }
                }
            }) {
                Icon(Icons.Filled.Share, contentDescription = "Share", tint = Ink)
            }
            IconButton(onClick = {
                scope.launch {
                    runCatching { repository.deleteShopList(listId) }
                        .onSuccess {
                            Toast.makeText(context, "Moved to trash", Toast.LENGTH_SHORT).show()
                            onBack()
                        }
                        .onFailure {
                            Toast.makeText(context, it.message ?: "Could not delete", Toast.LENGTH_SHORT).show()
                        }
                }
            }) {
                Icon(Icons.Filled.Delete, contentDescription = "Move to trash", tint = StampRed)
            }
        }
        Text(
            lst?.name ?: "List",
            style = MaterialTheme.typography.headlineMedium,
            color = Ink,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(horizontal = 20.dp)
        )
        Text(
            buildString {
                append("${lst?.item_count ?: 0} items · ${lst?.checked_count ?: 0} done")
                lst?.owner_name?.takeIf { it.isNotBlank() }?.let {
                    append(" · Created by "); append(it)
                }
                shopDateLabel(lst?.created_at)?.let {
                    append(" · "); append(it)
                }
            },
            color = InkSoft,
            modifier = Modifier.padding(horizontal = 20.dp, vertical = 4.dp)
        )
        Column(Modifier.padding(horizontal = 20.dp, vertical = 8.dp)) {
            Row(
                Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically
            ) {
                OutlinedTextField(
                    value = newItem,
                    onValueChange = { newItem = it },
                    placeholder = { Text("vazhuth or ഉള്ളി") },
                    singleLine = true,
                    modifier = Modifier.weight(1f)
                )
                Spacer(Modifier.width(8.dp))
                IconButton(onClick = {
                    val name = newItem.trim()
                    if (name.isEmpty() || adding) return@IconButton
                    scope.launch {
                        adding = true
                        runCatching {
                            repository.addShopItem(
                                listId,
                                ShopItemIn(name = name, notes = newNotes.trim().ifBlank { null })
                            )
                        }
                            .onSuccess { item ->
                                newItem = ""
                                newNotes = ""
                                suggestions = emptyList()
                                if (item.merged) {
                                    Toast.makeText(
                                        context,
                                        "Already on the list — quantity is now ${item.quantity}",
                                        Toast.LENGTH_SHORT
                                    ).show()
                                }
                                reload()
                            }
                            .onFailure {
                                Toast.makeText(context, it.message ?: "Could not add", Toast.LENGTH_SHORT).show()
                            }
                        adding = false
                    }
                }) {
                    Icon(Icons.Filled.Add, contentDescription = "Add", tint = VaultGold)
                }
            }
            OutlinedTextField(
                value = newNotes,
                onValueChange = { newNotes = it },
                placeholder = { Text("Notes (optional)") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth().padding(top = 6.dp)
            )
        }
        Row(
            Modifier.padding(horizontal = 20.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Checkbox(checked = useAi, onCheckedChange = { useAi = it })
            Text("Use AI (Malayalam & misspellings)", color = InkSoft, style = MaterialTheme.typography.bodySmall)
        }
        if (suggestions.isNotEmpty()) {
            Column(Modifier.padding(horizontal = 20.dp, vertical = 4.dp)) {
                suggestions.take(6).forEach { hit ->
                    val label = buildString {
                        append(hit.emoji)
                        append(" ")
                        append(hit.english)
                        hit.malayalam?.let { append(" ($it)") }
                    }
                    Text(
                        label,
                        color = VaultGold,
                        style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable(enabled = !adding) {
                                if (adding) return@clickable
                                newItem = hit.english
                                scope.launch {
                                    adding = true
                                    runCatching { repository.addShopItem(listId, ShopItemIn(hit.english)) }
                                        .onSuccess { item ->
                                            newItem = ""
                                            suggestions = emptyList()
                                            if (item.merged) {
                                                Toast.makeText(
                                                    context,
                                                    "Already on the list — quantity is now ${item.quantity}",
                                                    Toast.LENGTH_SHORT
                                                ).show()
                                            }
                                            reload()
                                        }
                                    adding = false
                                }
                            }
                            .padding(vertical = 6.dp)
                    )
                }
            }
        }
        if (loading && lst == null) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator(color = Navy)
            }
        } else {
            LazyColumn(
                contentPadding = PaddingValues(20.dp, 8.dp, 20.dp, 24.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                item {
                    Surface(shape = RoundedCornerShape(14.dp), color = HubGlass, modifier = Modifier.fillMaxWidth()) {
                        Column(Modifier.padding(12.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text("Bills & receipts", color = Ink, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                                TextButton(onClick = { pickBill.launch("image/*") }) {
                                    Text("Add copy", color = VaultGold)
                                }
                            }
                            Text(
                                if (receipts.isEmpty()) "Attach a photo of the shop bill to this list."
                                else "${receipts.size} attached",
                                color = InkSoft,
                                style = MaterialTheme.typography.bodySmall
                            )
                            receipts.forEach { rec ->
                                Row(
                                    Modifier
                                        .fillMaxWidth()
                                        .padding(top = 6.dp)
                                        .clickable {
                                            scope.launch {
                                                try {
                                                    val name = rec.original_name ?: "bill.jpg"
                                                    val dest = File(
                                                        context.cacheDir.resolve("shop").apply { mkdirs() },
                                                        name
                                                    )
                                                    withContext(Dispatchers.IO) {
                                                        repository.downloadShopReceipt(listId, rec.id, dest)
                                                    }
                                                    val uri = FileProvider.getUriForFile(
                                                        context,
                                                        "${context.packageName}.fileprovider",
                                                        dest
                                                    )
                                                    context.startActivity(Intent(Intent.ACTION_VIEW).apply {
                                                        setDataAndType(uri, rec.image_mime ?: "image/*")
                                                        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                                                    })
                                                } catch (e: Exception) {
                                                    Toast.makeText(
                                                        context,
                                                        e.message ?: "Could not open bill",
                                                        Toast.LENGTH_SHORT
                                                    ).show()
                                                }
                                            }
                                        },
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Text(
                                        rec.original_name ?: "Bill copy",
                                        color = Ink,
                                        modifier = Modifier.weight(1f),
                                        style = MaterialTheme.typography.bodySmall
                                    )
                                    IconButton(onClick = {
                                        scope.launch {
                                            runCatching { repository.deleteShopReceipt(listId, rec.id) }
                                            reload()
                                        }
                                    }) {
                                        Icon(Icons.Filled.Delete, contentDescription = "Remove bill", tint = InkSoft)
                                    }
                                }
                            }
                        }
                    }
                }
                items(items, key = { it.id }) { item ->
                    Surface(shape = RoundedCornerShape(14.dp), color = HubGlass, modifier = Modifier.fillMaxWidth()) {
                        Row(
                            Modifier.padding(12.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            IconButton(onClick = {
                                scope.launch {
                                    if (item.status == "pending") {
                                        runCatching { repository.approveShopItem(listId, item.id) }
                                    } else {
                                        runCatching { repository.toggleShopItem(listId, item.id) }
                                    }
                                    reload()
                                }
                            }) {
                                Icon(
                                    if (item.checked) Icons.Filled.CheckCircle else Icons.Filled.RadioButtonUnchecked,
                                    contentDescription = "Toggle",
                                    tint = if (item.checked) VaultGold else InkSoft
                                )
                            }
                            Column(Modifier.weight(1f)) {
                                Text(
                                    "${item.emoji ?: "🛒"} ${item.name}",
                                    color = Ink,
                                    fontWeight = FontWeight.Medium,
                                    textDecoration = if (item.checked) TextDecoration.LineThrough else null
                                )
                                val meta = buildString {
                                    append(item.quantity)
                                    item.unit?.takeIf { it.isNotBlank() }?.let { append(" $it") }
                                    if (item.status == "pending") {
                                        if (isNotEmpty()) append(" · ")
                                        append("pending")
                                    }
                                    val who = item.added_by_name ?: item.guest_name
                                    who?.takeIf { it.isNotBlank() }?.let {
                                        if (isNotEmpty()) append(" · ")
                                        append(it)
                                    }
                                    item.notes?.takeIf { it.isNotBlank() }?.let {
                                        if (isNotEmpty()) append(" · ")
                                        append(it)
                                    }
                                }
                                if (meta.isNotBlank()) Text(meta, color = InkSoft, style = MaterialTheme.typography.bodySmall)
                            }
                            TextButton(onClick = { editing = item }) {
                                Text("Edit", color = VaultGold)
                            }
                            if (item.status == "pending") {
                                IconButton(onClick = {
                                    scope.launch {
                                        runCatching { repository.rejectShopItem(listId, item.id) }
                                        reload()
                                    }
                                }) {
                                    Icon(Icons.Filled.Close, contentDescription = "Reject", tint = StampRed)
                                }
                            }
                            IconButton(onClick = {
                                scope.launch {
                                    runCatching { repository.deleteShopItem(listId, item.id) }
                                    reload()
                                }
                            }) {
                                Icon(Icons.Filled.Delete, contentDescription = "Delete", tint = InkSoft)
                            }
                        }
                    }
                }
            }
        }
        editing?.let { item ->
            var name by remember(item.id) { mutableStateOf(item.name) }
            var qty by remember(item.id) { mutableStateOf(item.quantity.toString()) }
            var unit by remember(item.id) { mutableStateOf(item.unit ?: "") }
            var price by remember(item.id) { mutableStateOf(item.price?.toString() ?: "") }
            var notes by remember(item.id) { mutableStateOf(item.notes ?: "") }
            AlertDialog(
                onDismissRequest = { editing = null },
                title = { Text("Edit item") },
                text = {
                    Column {
                        OutlinedTextField(value = name, onValueChange = { name = it }, label = { Text("Name") }, singleLine = true)
                        Spacer(Modifier.height(8.dp))
                        OutlinedTextField(value = qty, onValueChange = { qty = it }, label = { Text("Qty") }, singleLine = true)
                        Spacer(Modifier.height(8.dp))
                        OutlinedTextField(value = unit, onValueChange = { unit = it }, label = { Text("Unit") }, singleLine = true)
                        Spacer(Modifier.height(8.dp))
                        OutlinedTextField(value = price, onValueChange = { price = it }, label = { Text("Price") }, singleLine = true)
                        Spacer(Modifier.height(8.dp))
                        OutlinedTextField(value = notes, onValueChange = { notes = it }, label = { Text("Notes") }, singleLine = true)
                    }
                },
                confirmButton = {
                    TextButton(onClick = {
                        scope.launch {
                            runCatching {
                                repository.updateShopItem(
                                    listId,
                                    item.id,
                                    ShopItemUpdate(
                                        name = name.trim(),
                                        quantity = qty.toDoubleOrNull(),
                                        unit = unit.trim().ifBlank { null },
                                        price = price.toDoubleOrNull(),
                                        notes = notes.trim().ifBlank { null }
                                    )
                                )
                            }.onSuccess {
                                editing = null
                                reload()
                            }
                        }
                    }) { Text("Save") }
                },
                dismissButton = { TextButton(onClick = { editing = null }) { Text("Cancel") } }
            )
        }
        if (showSend) {
            AlertDialog(
                onDismissRequest = { showSend = false },
                title = { Text("Send list to friend") },
                text = {
                    Column {
                        Text(
                            "Pick a person from People. They will get a copy in their inbox.",
                            color = InkSoft,
                            style = MaterialTheme.typography.bodySmall
                        )
                        Spacer(Modifier.height(8.dp))
                        val withEmail = friends.filter { !it.email.isNullOrBlank() }
                        if (withEmail.isEmpty()) {
                            Text("Add a friend with an email on the People tab first.", color = StampRed)
                        } else {
                            withEmail.forEach { friend ->
                                TextButton(onClick = {
                                    scope.launch {
                                        runCatching {
                                            repository.sendShopList(
                                                listId,
                                                ShopSendIn(email = friend.email!!, message = null)
                                            )
                                        }.onSuccess {
                                            Toast.makeText(context, "Sent to ${friend.name}", Toast.LENGTH_SHORT).show()
                                            showSend = false
                                        }.onFailure {
                                            Toast.makeText(context, it.message ?: "Send failed", Toast.LENGTH_LONG).show()
                                        }
                                    }
                                }) {
                                    Text("${friend.name} · ${friend.email}", color = VaultGold)
                                }
                            }
                        }
                    }
                },
                confirmButton = {},
                dismissButton = { TextButton(onClick = { showSend = false }) { Text("Close") } }
            )
        }
    }
}

@Composable
fun ShopFriendsScreen(
    repository: HealthVaultRepository,
    onOpenModules: () -> Unit,
    onOpenList: (String) -> Unit
) {
    val scope = rememberCoroutineScope()
    var friends by remember { mutableStateOf<List<ShopContactOut>>(emptyList()) }
    var inbox by remember { mutableStateOf<List<ShopSendOut>>(emptyList()) }
    var sent by remember { mutableStateOf<List<ShopSendOut>>(emptyList()) }
    var name by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }

    fun reload() {
        scope.launch {
            runCatching { friends = repository.listShopFriends() }
            runCatching { inbox = repository.shopInbox() }
            runCatching { sent = repository.shopSent() }
        }
    }
    LaunchedEffect(Unit) { reload() }

    Column(Modifier.fillMaxSize().background(HubBg).padding(20.dp, 16.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Column {
                Text("SHOPPING LIST", style = MaterialTheme.typography.labelMedium, color = VaultGold)
                Text("People", style = MaterialTheme.typography.headlineMedium, color = Ink, fontWeight = FontWeight.Bold)
            }
            IconButton(onClick = onOpenModules) {
                Icon(Icons.Filled.Apps, contentDescription = "Modules", tint = InkSoft)
            }
        }
        if (inbox.any { it.status == "pending" }) {
            Text("Inbox", color = Ink, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 16.dp, bottom = 8.dp))
            inbox.filter { it.status == "pending" }.forEach { send ->
                Surface(shape = RoundedCornerShape(14.dp), color = HubGlass, modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp)) {
                    Column(Modifier.padding(14.dp)) {
                        Text(send.list_name ?: "Shopping list", color = Ink, fontWeight = FontWeight.Medium)
                        Text("from ${send.sender_name ?: "someone"}", color = InkSoft, style = MaterialTheme.typography.bodySmall)
                        Row {
                            TextButton(onClick = {
                                scope.launch {
                                    runCatching { repository.acceptShopSend(send.id) }.onSuccess { onOpenList(it.id) }
                                }
                            }) { Text("Accept") }
                            TextButton(onClick = {
                                scope.launch {
                                    runCatching { repository.rejectShopSend(send.id) }
                                    reload()
                                }
                            }) { Text("Reject") }
                        }
                    }
                }
            }
        }
        if (sent.any { it.status == "pending" }) {
            Text("Sent", color = Ink, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 8.dp, bottom = 8.dp))
            sent.filter { it.status == "pending" }.forEach { send ->
                Surface(shape = RoundedCornerShape(14.dp), color = HubGlass, modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp)) {
                    Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(send.list_name ?: "Shopping list", color = Ink, fontWeight = FontWeight.Medium)
                            Text("to ${send.receiver_name ?: "someone"}", color = InkSoft, style = MaterialTheme.typography.bodySmall)
                        }
                        TextButton(onClick = {
                            scope.launch {
                                runCatching { repository.recallShopSend(send.id) }
                                reload()
                            }
                        }) { Text("Recall", color = StampRed) }
                    }
                }
            }
        }
        OutlinedTextField(value = name, onValueChange = { name = it }, label = { Text("Name") }, singleLine = true, modifier = Modifier.fillMaxWidth().padding(top = 12.dp))
        OutlinedTextField(value = email, onValueChange = { email = it }, label = { Text("Email") }, singleLine = true, modifier = Modifier.fillMaxWidth().padding(top = 8.dp))
        Button(
            onClick = {
                val n = name.trim()
                if (n.isEmpty()) return@Button
                scope.launch {
                    runCatching {
                        repository.addShopFriend(ShopContactIn(name = n, email = email.trim().ifBlank { null }))
                    }.onSuccess {
                        name = ""
                        email = ""
                        reload()
                    }
                }
            },
            modifier = Modifier.padding(top = 8.dp),
            colors = ButtonDefaults.buttonColors(containerColor = Navy, contentColor = TextDark)
        ) { Text("Add contact") }
        Spacer(Modifier.height(16.dp))
        LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(friends, key = { it.id }) { f ->
                Surface(shape = RoundedCornerShape(14.dp), color = HubGlass, modifier = Modifier.fillMaxWidth()) {
                    Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(f.name, color = Ink, fontWeight = FontWeight.Medium)
                            Text(f.email ?: f.relation ?: "", color = InkSoft, style = MaterialTheme.typography.bodySmall)
                        }
                        IconButton(onClick = {
                            scope.launch {
                                runCatching { repository.deleteShopFriend(f.id) }
                                reload()
                            }
                        }) {
                            Icon(Icons.Filled.Delete, contentDescription = "Remove", tint = InkSoft)
                        }
                    }
                }
            }
        }
    }
}
