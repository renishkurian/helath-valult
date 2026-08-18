package com.rklab.healthvault.ui.screens.finance

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.rklab.healthvault.data.model.FinanceTxnOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.theme.HubBg
import com.rklab.healthvault.ui.theme.Ink
import com.rklab.healthvault.ui.theme.InkSoft
import com.rklab.healthvault.ui.theme.StampRed
import kotlinx.coroutines.launch

@Composable
fun FinanceTrashScreen(
    repository: HealthVaultRepository,
    onBack: () -> Unit
) {
    val scope = rememberCoroutineScope()
    var items by remember { mutableStateOf<List<FinanceTxnOut>>(emptyList()) }
    var error by remember { mutableStateOf<String?>(null) }
    var pendingForever by remember { mutableStateOf<FinanceTxnOut?>(null) }
    var emptyConfirm by remember { mutableStateOf(false) }

    fun reload() {
        scope.launch {
            runCatching { items = repository.listFinanceTrash() }
                .onFailure { error = it.message }
        }
    }
    LaunchedEffect(Unit) { reload() }

    Column(Modifier.fillMaxSize().background(HubBg).padding(20.dp)) {
        TextButton(onClick = onBack) { Text("← More", color = InkSoft) }
        Text("Trash", style = MaterialTheme.typography.headlineMedium, color = Ink, fontWeight = FontWeight.Bold)
        Text("Deleted entries stay here until you restore them or empty the trash.", color = InkSoft, style = MaterialTheme.typography.bodySmall)
        if (items.isNotEmpty()) {
            TextButton(onClick = { emptyConfirm = true }) {
                Text("Empty trash", color = StampRed)
            }
        }
        error?.let { Text(it, color = StampRed, modifier = Modifier.padding(top = 8.dp)) }
        if (items.isEmpty()) {
            Text("Trash is empty.", color = InkSoft, modifier = Modifier.padding(top = 24.dp))
        } else {
            LazyColumn(
                Modifier.fillMaxSize().padding(top = 12.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
                contentPadding = PaddingValues(bottom = 24.dp)
            ) {
                items(items, key = { it.id }) { t ->
                    Column {
                        FinanceTxnCard(txn = t)
                        Row {
                            TextButton(onClick = {
                                scope.launch {
                                    runCatching { repository.restoreFinanceTransaction(t.id) }
                                        .onSuccess { reload() }
                                        .onFailure { error = it.message }
                                }
                            }) { Text("Restore") }
                            TextButton(onClick = { pendingForever = t }) {
                                Text("Delete forever", color = StampRed)
                            }
                        }
                    }
                }
            }
        }
    }

    pendingForever?.let { txn ->
        AlertDialog(
            onDismissRequest = { pendingForever = null },
            title = { Text("Delete forever?") },
            text = { Text("This cannot be undone.") },
            confirmButton = {
                TextButton(onClick = {
                    val id = txn.id
                    pendingForever = null
                    scope.launch {
                        runCatching { repository.permanentDeleteFinanceTransaction(id) }
                            .onSuccess { reload() }
                            .onFailure { error = it.message }
                    }
                }) { Text("Delete", color = StampRed) }
            },
            dismissButton = {
                TextButton(onClick = { pendingForever = null }) { Text("Cancel") }
            }
        )
    }
    if (emptyConfirm) {
        AlertDialog(
            onDismissRequest = { emptyConfirm = false },
            title = { Text("Empty trash?") },
            text = { Text("Permanently delete everything in trash? This cannot be undone.") },
            confirmButton = {
                TextButton(onClick = {
                    emptyConfirm = false
                    scope.launch {
                        runCatching { repository.emptyFinanceTrash() }
                            .onSuccess { reload() }
                            .onFailure { error = it.message }
                    }
                }) { Text("Empty", color = StampRed) }
            },
            dismissButton = {
                TextButton(onClick = { emptyConfirm = false }) { Text("Cancel") }
            }
        )
    }
}
