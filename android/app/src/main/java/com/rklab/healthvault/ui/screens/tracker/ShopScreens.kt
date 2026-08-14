package com.rklab.healthvault.ui.screens.tracker

import android.content.Intent
import android.widget.Toast
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
import androidx.compose.material.icons.filled.Delete
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
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

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
                    Text("EXPENSE TRACKER", style = MaterialTheme.typography.labelMedium, color = VaultGold)
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
                                    "${lst.item_count} items" +
                                        (if (lst.pending_count > 0) " · ${lst.pending_count} pending" else "") +
                                        (if (lst.completed) " · done" else ""),
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
    var useAi by remember { mutableStateOf(true) }
    var suggestions by remember { mutableStateOf<List<ShopGroceryItemOut>>(emptyList()) }

    fun reload() {
        scope.launch {
            loading = true
            runCatching { lst = repository.getShopList(listId) }
            loading = false
        }
    }
    LaunchedEffect(listId) { reload() }
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

    Column(Modifier.fillMaxSize().background(HubBg)) {
        Row(
            Modifier.fillMaxWidth().padding(8.dp, 12.dp, 8.dp, 0.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            TextButton(onClick = onBack) { Text("Back", color = VaultGold) }
            Spacer(Modifier.weight(1f))
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
        }
        Text(
            lst?.name ?: "List",
            style = MaterialTheme.typography.headlineMedium,
            color = Ink,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(horizontal = 20.dp)
        )
        Text(
            "${lst?.item_count ?: 0} items · ${lst?.checked_count ?: 0} done",
            color = InkSoft,
            modifier = Modifier.padding(horizontal = 20.dp, vertical = 4.dp)
        )
        Row(
            Modifier.fillMaxWidth().padding(20.dp, 8.dp),
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
                if (name.isEmpty()) return@IconButton
                scope.launch {
                    runCatching { repository.addShopItem(listId, ShopItemIn(name)) }
                        .onSuccess {
                            newItem = ""
                            suggestions = emptyList()
                            reload()
                        }
                }
            }) {
                Icon(Icons.Filled.Add, contentDescription = "Add", tint = VaultGold)
            }
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
                            .clickable {
                                newItem = hit.english
                                scope.launch {
                                    runCatching { repository.addShopItem(listId, ShopItemIn(hit.english)) }
                                        .onSuccess {
                                            newItem = ""
                                            suggestions = emptyList()
                                            reload()
                                        }
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
                                    if (item.status == "pending") append("pending")
                                    item.guest_name?.let { if (isNotEmpty()) append(" · "); append(it) }
                                }
                                if (meta.isNotBlank()) Text(meta, color = InkSoft, style = MaterialTheme.typography.bodySmall)
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
    var name by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }

    fun reload() {
        scope.launch {
            runCatching { friends = repository.listShopFriends() }
            runCatching { inbox = repository.shopInbox() }
        }
    }
    LaunchedEffect(Unit) { reload() }

    Column(Modifier.fillMaxSize().background(HubBg).padding(20.dp, 16.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Column {
                Text("EXPENSE TRACKER", style = MaterialTheme.typography.labelMedium, color = VaultGold)
                Text("Friends", style = MaterialTheme.typography.headlineMedium, color = Ink, fontWeight = FontWeight.Bold)
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
