package com.rklab.healthvault.ui.screens.passwords

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.graphics.Color
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Apps
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Star
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.rklab.healthvault.data.model.VaultFolderOut
import com.rklab.healthvault.data.model.VaultItemOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.theme.*
import kotlinx.coroutines.launch

@Composable
fun VaultListScreen(
    repository: HealthVaultRepository,
    onOpenItem: (String) -> Unit,
    onAddItem: (String) -> Unit,
    onOpenTrash: () -> Unit,
    onOpenModules: () -> Unit
) {
    val scope = rememberCoroutineScope()
    var query by remember { mutableStateOf("") }
    var type by remember { mutableStateOf<String?>(null) }
    var folderId by remember { mutableStateOf<String?>(null) }
    var items by remember { mutableStateOf<List<VaultItemOut>>(emptyList()) }
    var folders by remember { mutableStateOf<List<VaultFolderOut>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var menu by remember { mutableStateOf(false) }
    var showFolder by remember { mutableStateOf(false) }
    var folderName by remember { mutableStateOf("") }

    fun reload() {
        scope.launch {
            loading = true
            error = null
            runCatching {
                folders = repository.listVaultFolders()
                items = repository.listVaultItems(query.ifBlank { null }, type, folderId)
            }.onFailure { error = it.message ?: "Could not load vault" }
            loading = false
        }
    }
    LaunchedEffect(query, type, folderId) { reload() }

    Box(Modifier.fillMaxSize().background(Paper)) {
        Column(Modifier.fillMaxSize()) {
            Row(
                Modifier.fillMaxWidth().padding(20.dp, 16.dp, 8.dp, 0.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text("PASSWORD VAULT", style = MaterialTheme.typography.labelMedium, color = InkSoft)
                    Text("My vault", style = MaterialTheme.typography.headlineMedium, color = Ink, fontWeight = FontWeight.Bold)
                }
                Row {
                    IconButton(onClick = onOpenModules) {
                        Icon(Icons.Filled.Apps, contentDescription = "Modules", tint = InkSoft)
                    }
                    Box {
                        IconButton(onClick = { menu = true }) {
                            Icon(Icons.Filled.MoreVert, contentDescription = "More", tint = InkSoft)
                        }
                        DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                            DropdownMenuItem(text = { Text("Trash") }, onClick = { menu = false; onOpenTrash() }, leadingIcon = { Icon(Icons.Filled.Delete, null) })
                            DropdownMenuItem(text = { Text("New folder") }, onClick = { menu = false; showFolder = true })
                        }
                    }
                }
            }
            OutlinedTextField(
                value = query,
                onValueChange = { query = it },
                placeholder = { Text("Search vault") },
                leadingIcon = { Icon(Icons.Filled.Search, null) },
                singleLine = true,
                shape = RoundedCornerShape(16.dp),
                modifier = Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 8.dp)
            )
            LazyRow(
                contentPadding = PaddingValues(horizontal = 20.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                val chips = listOf(null to "All", "login" to "Logins", "note" to "Notes", "card" to "Cards", "identity" to "IDs")
                items(chips) { (value, label) ->
                    FilterChip(
                        selected = type == value,
                        onClick = { type = value },
                        label = { Text(label) }
                    )
                }
            }
            if (folders.isNotEmpty()) {
                LazyRow(
                    contentPadding = PaddingValues(start = 20.dp, end = 20.dp, top = 8.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    item {
                        FilterChip(selected = folderId == null, onClick = { folderId = null }, label = { Text("All folders") })
                    }
                    items(folders) { folder ->
                        FilterChip(
                            selected = folderId == folder.id,
                            onClick = { folderId = folder.id },
                            label = { Text("${folder.name} (${folder.item_count})") }
                        )
                    }
                }
            }
            when {
                loading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = Navy)
                }
                error != null -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text(error!!, color = StampRed)
                }
                else -> LazyColumn(
                    contentPadding = PaddingValues(20.dp, 12.dp, 20.dp, 100.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    items(items, key = { it.id }) { item ->
                        Row(
                            modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(White).clickable { onOpenItem(item.id) }.padding(14.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Box(
                                Modifier.size(42.dp).clip(RoundedCornerShape(12.dp)).background(Color(0x335B8CFF)),
                                contentAlignment = Alignment.Center
                            ) {
                                Text(item.name.take(1).uppercase(), color = Navy, fontWeight = FontWeight.Bold)
                            }
                            Spacer(Modifier.width(12.dp))
                            Column(Modifier.weight(1f)) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Text(item.name, color = Ink, fontWeight = FontWeight.SemiBold)
                                    if (item.favorite) {
                                        Spacer(Modifier.width(6.dp))
                                        Icon(Icons.Filled.Star, null, tint = Mustard, modifier = Modifier.size(14.dp))
                                    }
                                }
                                Text(
                                    item.username ?: item.email ?: item.uris.firstOrNull() ?: item.item_type,
                                    color = InkSoft,
                                    style = MaterialTheme.typography.bodySmall
                                )
                            }
                            Text(item.item_type, color = InkSoft, style = MaterialTheme.typography.labelSmall)
                        }
                    }
                    if (items.isEmpty()) {
                        item { Text("No items yet. Tap + to add a login.", color = InkSoft, modifier = Modifier.padding(12.dp)) }
                    }
                }
            }
        }
        FloatingActionButton(
            onClick = { onAddItem(type ?: "login") },
            modifier = Modifier.align(Alignment.BottomEnd).padding(20.dp),
            containerColor = Navy
        ) { Icon(Icons.Filled.Add, contentDescription = "Add", tint = TextWhite) }
    }

    if (showFolder) {
        AlertDialog(
            onDismissRequest = { showFolder = false },
            title = { Text("New folder") },
            text = {
                OutlinedTextField(folderName, { folderName = it }, label = { Text("Name") }, singleLine = true)
            },
            confirmButton = {
                TextButton(onClick = {
                    scope.launch {
                        runCatching { repository.createVaultFolder(folderName.trim()) }
                        folderName = ""; showFolder = false; reload()
                    }
                }) { Text("Create") }
            },
            dismissButton = { TextButton(onClick = { showFolder = false }) { Text("Cancel") } }
        )
    }
}
