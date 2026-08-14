package com.rklab.healthvault.ui.screens.passwords

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.rklab.healthvault.data.model.VaultItemOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.components.VaultBackLink
import com.rklab.healthvault.ui.components.VaultCardShape
import com.rklab.healthvault.ui.components.VaultPageHeader
import com.rklab.healthvault.ui.theme.HubBg
import com.rklab.healthvault.ui.theme.HubGlass
import com.rklab.healthvault.ui.theme.HubStroke
import com.rklab.healthvault.ui.theme.HubText
import com.rklab.healthvault.ui.theme.HubTextDim
import com.rklab.healthvault.ui.theme.HubViolet
import com.rklab.healthvault.ui.theme.StampRed
import com.rklab.healthvault.ui.theme.VaultGold
import kotlinx.coroutines.launch

@Composable
fun VaultTrashScreen(repository: HealthVaultRepository, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    var items by remember { mutableStateOf<List<VaultItemOut>>(emptyList()) }
    fun reload() { scope.launch { items = runCatching { repository.listVaultTrash() }.getOrDefault(emptyList()) } }
    LaunchedEffect(Unit) { reload() }

    Column(
        Modifier
            .fillMaxSize()
            .background(HubBg)
            .padding(20.dp)
    ) {
        VaultBackLink("← Vault", onBack)
        VaultPageHeader(
            eyebrow = "TRASH",
            title = "Deleted items"
        )
        if (items.isNotEmpty()) {
            TextButton(onClick = { scope.launch { repository.emptyVaultTrash(); reload() } }) {
                Text("Empty trash", color = StampRed)
            }
        }
        LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(items, key = { it.id }) { item ->
                Column(
                    Modifier
                        .fillMaxWidth()
                        .clip(VaultCardShape)
                        .background(HubGlass)
                        .border(1.dp, HubStroke, VaultCardShape)
                        .padding(14.dp)
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(
                            Modifier
                                .size(42.dp)
                                .clip(RoundedCornerShape(12.dp))
                                .background(HubViolet.copy(alpha = 0.18f)),
                            contentAlignment = Alignment.Center
                        ) {
                            Text(
                                item.name.take(1).uppercase(),
                                color = HubViolet,
                                fontWeight = FontWeight.Bold
                            )
                        }
                        Spacer(Modifier.width(12.dp))
                        Column {
                            Text(item.name, color = HubText, fontWeight = FontWeight.SemiBold)
                            Text(
                                item.item_type,
                                color = HubTextDim,
                                style = MaterialTheme.typography.bodySmall
                            )
                        }
                    }
                    Row {
                        TextButton(onClick = { scope.launch { repository.restoreVaultItem(item.id); reload() } }) {
                            Text("Restore", color = VaultGold)
                        }
                        TextButton(onClick = { scope.launch { repository.deleteVaultItemForever(item.id); reload() } }) {
                            Text("Delete forever", color = StampRed)
                        }
                    }
                }
            }
            if (items.isEmpty()) {
                item { Text("Trash is empty.", color = HubTextDim) }
            }
        }
    }
}
