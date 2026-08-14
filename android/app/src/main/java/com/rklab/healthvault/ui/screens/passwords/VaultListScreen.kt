package com.rklab.healthvault.ui.screens.passwords

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Apps
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
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
import androidx.compose.ui.unit.dp
import com.rklab.healthvault.data.model.VaultFolderOut
import com.rklab.healthvault.data.model.VaultItemOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.components.VaultFab
import com.rklab.healthvault.ui.components.VaultFilterChip
import com.rklab.healthvault.ui.components.VaultListRow
import com.rklab.healthvault.ui.components.VaultPageHeader
import com.rklab.healthvault.ui.components.vaultFieldColors
import com.rklab.healthvault.ui.theme.HubAmber
import com.rklab.healthvault.ui.theme.HubBg
import com.rklab.healthvault.ui.theme.HubRose
import com.rklab.healthvault.ui.theme.HubSky
import com.rklab.healthvault.ui.theme.HubTextDim
import com.rklab.healthvault.ui.theme.HubViolet
import com.rklab.healthvault.ui.theme.StampRed
import com.rklab.healthvault.ui.theme.VaultGold
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

    Box(Modifier.fillMaxSize().background(HubBg)) {
        Column(Modifier.fillMaxSize()) {
            VaultPageHeader(
                eyebrow = "PASSWORD VAULT",
                title = "My vault",
                modifier = Modifier.padding(horizontal = 20.dp),
                actions = {
                    IconButton(onClick = onOpenModules) {
                        Icon(Icons.Filled.Apps, contentDescription = "Modules", tint = HubTextDim)
                    }
                    Box {
                        IconButton(onClick = { menu = true }) {
                            Icon(Icons.Filled.MoreVert, contentDescription = "More", tint = HubTextDim)
                        }
                        DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                            DropdownMenuItem(
                                text = { Text("Trash") },
                                onClick = { menu = false; onOpenTrash() },
                                leadingIcon = { Icon(Icons.Filled.Delete, null) }
                            )
                            DropdownMenuItem(
                                text = { Text("New folder") },
                                onClick = { menu = false; showFolder = true }
                            )
                        }
                    }
                }
            )
            OutlinedTextField(
                value = query,
                onValueChange = { query = it },
                placeholder = { Text("Search vault") },
                leadingIcon = { Icon(Icons.Filled.Search, null, tint = HubTextDim) },
                singleLine = true,
                shape = RoundedCornerShape(16.dp),
                colors = vaultFieldColors(),
                modifier = Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 8.dp)
            )
            LazyRow(
                contentPadding = PaddingValues(horizontal = 20.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                val chips = listOf(null to "All", "login" to "Logins", "note" to "Notes", "card" to "Cards", "identity" to "IDs")
                items(chips) { (value, label) ->
                    VaultFilterChip(selected = type == value, onClick = { type = value }, label = label)
                }
            }
            if (folders.isNotEmpty()) {
                LazyRow(
                    contentPadding = PaddingValues(start = 20.dp, end = 20.dp, top = 8.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    item {
                        VaultFilterChip(selected = folderId == null, onClick = { folderId = null }, label = "All folders")
                    }
                    items(folders) { folder ->
                        VaultFilterChip(
                            selected = folderId == folder.id,
                            onClick = { folderId = folder.id },
                            label = "${folder.name} (${folder.item_count})"
                        )
                    }
                }
            }
            when {
                loading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = VaultGold)
                }
                error != null -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text(error!!, color = StampRed)
                }
                else -> LazyColumn(
                    contentPadding = PaddingValues(20.dp, 12.dp, 20.dp, 100.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    items(items, key = { it.id }) { item ->
                        VaultListRow(
                            title = item.name,
                            subtitle = item.username ?: item.email ?: item.uris.firstOrNull() ?: item.item_type,
                            meta = item.item_type,
                            accent = when (item.item_type) {
                                "login" -> HubViolet
                                "note" -> HubAmber
                                "card" -> HubRose
                                else -> HubSky
                            },
                            favorite = item.favorite,
                            onClick = { onOpenItem(item.id) }
                        )
                    }
                    if (items.isEmpty()) {
                        item {
                            Text(
                                "No items yet. Tap + to add a login.",
                                color = HubTextDim,
                                style = MaterialTheme.typography.bodyMedium,
                                modifier = Modifier.padding(12.dp)
                            )
                        }
                    }
                }
            }
        }
        Box(Modifier.align(Alignment.BottomEnd).padding(20.dp)) {
            VaultFab(onClick = { onAddItem(type ?: "login") }, icon = Icons.Filled.Add, contentDescription = "Add")
        }
    }

    if (showFolder) {
        AlertDialog(
            onDismissRequest = { showFolder = false },
            title = { Text("New folder") },
            text = {
                OutlinedTextField(
                    folderName, { folderName = it },
                    label = { Text("Name") },
                    singleLine = true,
                    colors = vaultFieldColors()
                )
            },
            confirmButton = {
                TextButton(onClick = {
                    scope.launch {
                        runCatching { repository.createVaultFolder(folderName.trim()) }
                        folderName = ""; showFolder = false; reload()
                    }
                }) { Text("Create", color = VaultGold) }
            },
            dismissButton = { TextButton(onClick = { showFolder = false }) { Text("Cancel") } }
        )
    }
}
