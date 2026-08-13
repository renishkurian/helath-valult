package com.rklab.healthvault.ui.screens.passwords

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.rklab.healthvault.data.model.VaultHealthIssue
import com.rklab.healthvault.data.model.VaultHealthOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.theme.*

@Composable
fun VaultHealthScreen(repository: HealthVaultRepository, onOpenItem: (String) -> Unit) {
    var report by remember { mutableStateOf<VaultHealthOut?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) {
        runCatching { report = repository.vaultHealth() }.onFailure { error = it.message }
    }
    Column(Modifier.fillMaxSize().background(Paper).padding(20.dp)) {
        Text("PASSWORD HEALTH", style = MaterialTheme.typography.labelMedium, color = InkSoft)
        Text("Exposed risks", style = MaterialTheme.typography.headlineMedium, color = Ink)
        Spacer(Modifier.height(8.dp))
        report?.let { Text("${it.total_logins} logins checked", color = InkSoft) }
        if (error != null) Text(error!!, color = StampRed)
        val data = report
        if (data == null) {
            CircularProgressIndicator(color = Navy)
            return@Column
        }
        LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp), contentPadding = PaddingValues(top = 16.dp, bottom = 40.dp)) {
            item { IssueGroup("Weak", data.weak, onOpenItem) }
            item { IssueGroup("Reused", data.reused, onOpenItem) }
            item { IssueGroup("No authenticator", data.no_totp, onOpenItem) }
            item { IssueGroup("Older than a year", data.old, onOpenItem) }
        }
    }
}

@Composable
private fun IssueGroup(title: String, rows: List<VaultHealthIssue>, onOpenItem: (String) -> Unit) {
    Column {
        Text("$title · ${rows.size}", style = MaterialTheme.typography.labelMedium, color = InkSoft)
        Spacer(Modifier.height(6.dp))
        if (rows.isEmpty()) {
            Text("None", color = Sage, style = MaterialTheme.typography.bodySmall)
        } else {
            rows.distinctBy { it.item_id }.forEach { row ->
                Column(
                    Modifier.fillMaxWidth().clickable { onOpenItem(row.item_id) }.padding(vertical = 8.dp)
                ) {
                    Text(row.name, color = Ink)
                    if (!row.username.isNullOrBlank()) Text(row.username, color = InkSoft, style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}
