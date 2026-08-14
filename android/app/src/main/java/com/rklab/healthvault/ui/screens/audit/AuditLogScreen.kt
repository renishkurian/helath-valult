package com.rklab.healthvault.ui.screens.audit

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
import com.rklab.healthvault.data.model.AuditAction
import com.rklab.healthvault.data.model.AuditLogOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.theme.*
import kotlinx.coroutines.launch

@Composable
fun AuditLogScreen(
    repository: HealthVaultRepository,
    onBack: () -> Unit
) {
    var entries by remember { mutableStateOf<List<AuditLogOut>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(Unit) {
        scope.launch {
            try {
                entries = repository.listAuditLog()
            } catch (e: Exception) {
                error = e.message ?: "Couldn't load activity."
            } finally {
                loading = false
            }
        }
    }

    Column(modifier = Modifier.fillMaxSize().background(HubBg).padding(20.dp)) {
        TextButton(onClick = onBack) { Text("← Back", color = Navy) }
        Text("ACTIVITY", style = MaterialTheme.typography.labelMedium, color = VaultGold)
        Spacer(Modifier.height(4.dp))
        Text("Who viewed what", style = MaterialTheme.typography.headlineMedium, color = Ink)
        Spacer(Modifier.height(18.dp))

        when {
            loading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator(color = Navy) }
            error != null -> Text(error!!, color = StampRed)
            entries.isEmpty() -> Text("No activity yet.", color = InkSoft)
            else -> LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp), contentPadding = PaddingValues(bottom = 40.dp)) {
                items(entries) { entry -> AuditRow(entry) }
            }
        }
    }
}

@Composable
private fun AuditRow(entry: AuditLogOut) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(HubGlass)
            .padding(12.dp)
    ) {
        Text(actionLabel(entry.action), style = MaterialTheme.typography.bodyMedium, color = Ink)
        Spacer(Modifier.height(2.dp))
        Text(
            buildString {
                append(entry.created_at.replace("T", " ").take(16))
                if (!entry.detail.isNullOrBlank()) append(" · ${entry.detail}")
            },
            style = MaterialTheme.typography.labelSmall,
            color = InkSoft
        )
    }
}

private fun actionLabel(action: AuditAction): String = when (action) {
    AuditAction.VIEW -> "Viewed a document"
    AuditAction.DOWNLOAD -> "Downloaded a document"
    AuditAction.SHARE_CREATE -> "Created a share link"
    AuditAction.SHARE_VIEW -> "Someone opened a shared link"
}
