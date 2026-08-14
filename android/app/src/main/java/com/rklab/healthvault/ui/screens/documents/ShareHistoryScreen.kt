package com.rklab.healthvault.ui.screens.documents

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
import com.rklab.healthvault.data.model.ShareAccessOut
import com.rklab.healthvault.data.model.ShareLinkDetailOut
import com.rklab.healthvault.data.model.ShareLinkOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.theme.*
import kotlinx.coroutines.launch

@Composable
fun ShareHistoryScreen(
    repository: HealthVaultRepository,
    onBack: () -> Unit
) {
    var links by remember { mutableStateOf<List<ShareLinkOut>>(emptyList()) }
    var expandedId by remember { mutableStateOf<String?>(null) }
    var detail by remember { mutableStateOf<ShareLinkDetailOut?>(null) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()

    fun reload() {
        scope.launch {
            try {
                links = repository.listMyShareLinks()
                error = null
            } catch (e: Exception) {
                error = e.message ?: "Couldn't load shared links."
            } finally {
                loading = false
            }
        }
    }

    LaunchedEffect(Unit) { reload() }

    LaunchedEffect(expandedId) {
        val id = expandedId ?: return@LaunchedEffect
        detail = null
        try {
            detail = repository.getShareLink(id)
        } catch (e: Exception) {
            error = e.message ?: "Couldn't load access history."
        }
    }

    Column(modifier = Modifier.fillMaxSize().background(HubBg).padding(20.dp)) {
        TextButton(onClick = onBack) { Text("← Back", color = Navy) }
        Text("SHARED LINKS", style = MaterialTheme.typography.labelMedium, color = VaultGold)
        Spacer(Modifier.height(4.dp))
        Text("Who opened what", style = MaterialTheme.typography.headlineMedium, color = Ink)
        Spacer(Modifier.height(8.dp))
        Text(
            "Each open and download is logged with time, IP, and browser. Revoke a link to cut it off immediately.",
            style = MaterialTheme.typography.bodySmall,
            color = InkSoft
        )
        Spacer(Modifier.height(18.dp))

        when {
            loading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator(color = Navy)
            }
            error != null && links.isEmpty() -> Text(error!!, color = StampRed)
            links.isEmpty() -> Text("No share links yet. Open a document and tap Share.", color = InkSoft)
            else -> LazyColumn(
                verticalArrangement = Arrangement.spacedBy(10.dp),
                contentPadding = PaddingValues(bottom = 40.dp)
            ) {
                items(links, key = { it.id }) { link ->
                    ShareLinkCard(
                        link = link,
                        expanded = expandedId == link.id,
                        detail = if (expandedId == link.id) detail else null,
                        onToggle = { expandedId = if (expandedId == link.id) null else link.id },
                        onRevoke = {
                            scope.launch {
                                try {
                                    repository.revokeShareLink(link.id)
                                    reload()
                                    if (expandedId == link.id) {
                                        detail = repository.getShareLink(link.id)
                                    }
                                } catch (e: Exception) {
                                    error = e.message ?: "Couldn't revoke link."
                                }
                            }
                        }
                    )
                }
            }
        }
    }
}

@Composable
private fun ShareLinkCard(
    link: ShareLinkOut,
    expanded: Boolean,
    detail: ShareLinkDetailOut?,
    onToggle: () -> Unit,
    onRevoke: () -> Unit
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(HubGlass)
            .padding(14.dp)
    ) {
        Text(link.document_title ?: "Document", style = MaterialTheme.typography.bodyMedium, color = Ink)
        Spacer(Modifier.height(4.dp))
        Text(
            buildString {
                append("${link.view_count} opens")
                append(" · ${link.download_count} downloads")
                append(" · expires ${link.expires_at.replace("T", " ").take(16)}")
                if (link.revoked) append(" · revoked")
            },
            style = MaterialTheme.typography.labelSmall,
            color = if (link.revoked) StampRed else InkSoft
        )
        Spacer(Modifier.height(8.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            TextButton(onClick = onToggle) {
                Text(if (expanded) "Hide history" else "View history", color = Navy)
            }
            if (!link.revoked) {
                TextButton(onClick = onRevoke) { Text("Revoke", color = StampRed) }
            }
        }
        if (expanded) {
            Spacer(Modifier.height(8.dp))
            when {
                detail == null -> CircularProgressIndicator(modifier = Modifier.size(18.dp), color = Navy, strokeWidth = 2.dp)
                detail.accesses.isEmpty() -> Text("Not opened yet.", color = InkSoft, style = MaterialTheme.typography.bodySmall)
                else -> detail.accesses.forEach { AccessRow(it) }
            }
        }
    }
}

@Composable
private fun AccessRow(access: ShareAccessOut) {
    Column(modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
        Text(
            "${if (access.action == "download") "Downloaded" else "Opened"}  ·  ${access.created_at.replace("T", " ").take(19)}",
            style = MaterialTheme.typography.bodySmall,
            color = Ink
        )
        Text(
            buildString {
                append(access.ip ?: "unknown IP")
                if (!access.user_agent.isNullOrBlank()) append("  ·  ${access.user_agent}")
            },
            style = MaterialTheme.typography.labelSmall,
            color = InkSoft
        )
        Divider(color = CardOutline, modifier = Modifier.padding(top = 6.dp))
    }
}
