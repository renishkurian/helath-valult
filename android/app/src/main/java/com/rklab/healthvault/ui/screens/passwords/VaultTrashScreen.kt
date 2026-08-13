package com.rklab.healthvault.ui.screens.passwords

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.rklab.healthvault.data.model.VaultItemOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.theme.*
import kotlinx.coroutines.launch

@Composable
fun VaultTrashScreen(repository: HealthVaultRepository, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    var items by remember { mutableStateOf<List<VaultItemOut>>(emptyList()) }
    fun reload() { scope.launch { items = runCatching { repository.listVaultTrash() }.getOrDefault(emptyList()) } }
    LaunchedEffect(Unit) { reload() }

    Column(Modifier.fillMaxSize().background(Paper).padding(20.dp)) {
        TextButton(onClick = onBack) { Text("← Vault", color = Navy) }
        Text("TRASH", style = MaterialTheme.typography.labelMedium, color = InkSoft)
        Text("Deleted items", style = MaterialTheme.typography.headlineMedium, color = Ink)
        if (items.isNotEmpty()) {
            TextButton(onClick = { scope.launch { repository.emptyVaultTrash(); reload() } }) {
                Text("Empty trash", color = StampRed)
            }
        }
        LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(items, key = { it.id }) { item ->
                Column(Modifier.fillMaxWidth().padding(vertical = 8.dp)) {
                    Text(item.name, color = Ink)
                    Text(item.item_type, color = InkSoft, style = MaterialTheme.typography.bodySmall)
                    Row {
                        TextButton(onClick = { scope.launch { repository.restoreVaultItem(item.id); reload() } }) {
                            Text("Restore", color = Navy)
                        }
                        TextButton(onClick = { scope.launch { repository.deleteVaultItemForever(item.id); reload() } }) {
                            Text("Delete forever", color = StampRed)
                        }
                    }
                }
            }
            if (items.isEmpty()) item { Text("Trash is empty.", color = InkSoft) }
        }
    }
}
