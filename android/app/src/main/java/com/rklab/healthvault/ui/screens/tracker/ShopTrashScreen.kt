package com.rklab.healthvault.ui.screens.tracker

import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Apps
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.rklab.healthvault.data.model.ShopListOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.theme.HubBg
import com.rklab.healthvault.ui.theme.HubGlass
import com.rklab.healthvault.ui.theme.Ink
import com.rklab.healthvault.ui.theme.InkSoft
import com.rklab.healthvault.ui.theme.StampRed
import com.rklab.healthvault.ui.theme.VaultGold
import kotlinx.coroutines.launch

@Composable
fun ShopTrashScreen(
    repository: HealthVaultRepository,
    onOpenModules: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var lists by remember { mutableStateOf<List<ShopListOut>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }

    fun reload() {
        scope.launch {
            loading = true
            runCatching { lists = repository.listShopTrash() }
                .onFailure {
                    Toast.makeText(context, it.message ?: "Could not load trash", Toast.LENGTH_SHORT).show()
                }
            loading = false
        }
    }
    LaunchedEffect(Unit) { reload() }

    Column(Modifier.fillMaxSize().background(HubBg)) {
        Row(
            Modifier.fillMaxWidth().padding(20.dp, 16.dp, 8.dp, 0.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column {
                Text("SHOPPING LIST", style = MaterialTheme.typography.labelMedium, color = VaultGold)
                Text("Trash", style = MaterialTheme.typography.headlineMedium, color = Ink, fontWeight = FontWeight.Bold)
            }
            IconButton(onClick = onOpenModules) {
                Icon(Icons.Filled.Apps, contentDescription = "Modules", tint = InkSoft)
            }
        }
        Text(
            "Deleted lists stay here until you restore them or empty the trash.",
            color = InkSoft,
            style = MaterialTheme.typography.bodySmall,
            modifier = Modifier.padding(horizontal = 20.dp, vertical = 8.dp)
        )
        if (lists.isNotEmpty()) {
            TextButton(
                onClick = {
                    scope.launch {
                        runCatching { repository.emptyShopTrash() }
                            .onSuccess {
                                Toast.makeText(context, "Trash emptied", Toast.LENGTH_SHORT).show()
                                reload()
                            }
                            .onFailure {
                                Toast.makeText(context, it.message ?: "Failed", Toast.LENGTH_SHORT).show()
                            }
                    }
                },
                modifier = Modifier.padding(horizontal = 12.dp)
            ) {
                Text("Empty trash", color = StampRed)
            }
        }
        when {
            loading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator(color = VaultGold)
            }
            lists.isEmpty() -> Text(
                "Trash is empty.",
                color = InkSoft,
                modifier = Modifier.padding(20.dp)
            )
            else -> LazyColumn(
                contentPadding = PaddingValues(20.dp, 8.dp, 20.dp, 88.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                items(lists, key = { it.id }) { lst ->
                    Surface(
                        shape = RoundedCornerShape(16.dp),
                        color = HubGlass,
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Column(Modifier.padding(16.dp)) {
                            Text(lst.name, color = Ink, fontWeight = FontWeight.SemiBold)
                            Text(
                                buildString {
                                    append("${lst.item_count} items")
                                    lst.deleted_at?.takeIf { it.isNotBlank() }?.let {
                                        append(" · deleted ")
                                        append(it.take(16).replace('T', ' '))
                                    }
                                },
                                color = InkSoft,
                                style = MaterialTheme.typography.bodySmall
                            )
                            Row(Modifier.padding(top = 4.dp)) {
                                TextButton(onClick = {
                                    scope.launch {
                                        runCatching { repository.restoreShopList(lst.id) }
                                            .onSuccess {
                                                Toast.makeText(context, "Restored", Toast.LENGTH_SHORT).show()
                                                reload()
                                            }
                                            .onFailure {
                                                Toast.makeText(context, it.message ?: "Failed", Toast.LENGTH_SHORT).show()
                                            }
                                    }
                                }) { Text("Restore", color = VaultGold) }
                                TextButton(onClick = {
                                    scope.launch {
                                        runCatching { repository.permanentDeleteShopList(lst.id) }
                                            .onSuccess {
                                                Toast.makeText(context, "Deleted forever", Toast.LENGTH_SHORT).show()
                                                reload()
                                            }
                                            .onFailure {
                                                Toast.makeText(context, it.message ?: "Failed", Toast.LENGTH_SHORT).show()
                                            }
                                    }
                                }) { Text("Delete forever", color = StampRed) }
                            }
                        }
                    }
                }
            }
        }
    }
}
