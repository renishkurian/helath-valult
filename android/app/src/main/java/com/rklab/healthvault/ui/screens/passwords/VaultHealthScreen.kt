package com.rklab.healthvault.ui.screens.passwords

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.rklab.healthvault.data.model.VaultHealthIssue
import com.rklab.healthvault.data.model.VaultHealthOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.components.VaultGlassCard
import com.rklab.healthvault.ui.components.VaultListRow
import com.rklab.healthvault.ui.components.VaultPageHeader
import com.rklab.healthvault.ui.theme.HubBg
import com.rklab.healthvault.ui.theme.Sage
import com.rklab.healthvault.ui.theme.StampRed
import com.rklab.healthvault.ui.theme.VaultGold

@Composable
fun VaultHealthScreen(repository: HealthVaultRepository, onOpenItem: (String) -> Unit) {
    var report by remember { mutableStateOf<VaultHealthOut?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) {
        runCatching { report = repository.vaultHealth() }.onFailure { error = it.message }
    }
    Column(
        Modifier
            .fillMaxSize()
            .background(HubBg)
            .padding(horizontal = 20.dp)
    ) {
        VaultPageHeader(
            eyebrow = "PASSWORD HEALTH",
            title = "Exposed risks",
            subtitle = report?.let { "${it.total_logins} logins checked" }
        )
        if (error != null) Text(error!!, color = StampRed)
        val data = report
        if (data == null) {
            CircularProgressIndicator(color = VaultGold)
            return@Column
        }
        LazyColumn(
            verticalArrangement = Arrangement.spacedBy(12.dp),
            contentPadding = PaddingValues(top = 8.dp, bottom = 40.dp)
        ) {
            item { IssueGroup("Weak", data.weak, onOpenItem) }
            item { IssueGroup("Reused", data.reused, onOpenItem) }
            item { IssueGroup("No authenticator", data.no_totp, onOpenItem) }
            item { IssueGroup("Older than a year", data.old, onOpenItem) }
        }
    }
}

@Composable
private fun IssueGroup(title: String, rows: List<VaultHealthIssue>, onOpenItem: (String) -> Unit) {
    VaultGlassCard {
        Text(
            "$title · ${rows.size}",
            style = MaterialTheme.typography.labelMedium,
            color = VaultGold
        )
        Spacer(Modifier.height(10.dp))
        if (rows.isEmpty()) {
            Text("None", color = Sage, style = MaterialTheme.typography.bodySmall)
        } else {
            rows.distinctBy { it.item_id }.forEachIndexed { index, row ->
                if (index > 0) Spacer(Modifier.height(8.dp))
                VaultListRow(
                    title = row.name,
                    subtitle = row.username.orEmpty().ifBlank { "—" },
                    onClick = { onOpenItem(row.item_id) }
                )
            }
        }
    }
}
