package com.rklab.healthvault.ui.screens.tracker

import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Apps
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.rklab.healthvault.data.model.ShopCatalogItemIn
import com.rklab.healthvault.data.model.ShopCatalogItemOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.theme.HubBg
import com.rklab.healthvault.ui.theme.HubGlass
import com.rklab.healthvault.ui.theme.Ink
import com.rklab.healthvault.ui.theme.InkSoft
import com.rklab.healthvault.ui.theme.Navy
import com.rklab.healthvault.ui.theme.StampRed
import com.rklab.healthvault.ui.theme.TextDark
import com.rklab.healthvault.ui.theme.VaultGold
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

private val catalogCategories = listOf(
    "vegetables", "fruits", "spices", "dals", "grains", "essentials",
    "dairy", "fish", "meat", "snacks", "household", "custom"
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ShopCatalogScreen(
    repository: HealthVaultRepository,
    onOpenModules: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var items by remember { mutableStateOf<List<ShopCatalogItemOut>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var showAdd by remember { mutableStateOf(false) }
    var english by remember { mutableStateOf("") }
    var malayalam by remember { mutableStateOf("") }
    var emoji by remember { mutableStateOf("🛒") }
    var category by remember { mutableStateOf("custom") }
    var scopeKind by remember { mutableStateOf("personal") }
    var aliases by remember { mutableStateOf("") }
    var aiTranslate by remember { mutableStateOf(true) }
    var translateStatus by remember { mutableStateOf("") }
    var lastApplied by remember { mutableStateOf("") }
    var lastQuery by remember { mutableStateOf("") }
    var catOpen by remember { mutableStateOf(false) }
    var scopeOpen by remember { mutableStateOf(false) }
    var translateJob by remember { mutableStateOf<Job?>(null) }

    fun appendAlias(raw: String) {
        val fold = raw.trim().lowercase()
        if (fold.isEmpty()) return
        val parts = aliases.split(",").map { it.trim() }.filter { it.isNotEmpty() }.toMutableList()
        if (parts.none { it.lowercase() == fold }) {
            parts.add(raw.trim())
            aliases = parts.joinToString(", ")
        }
    }

    fun scheduleTranslate(typed: String) {
        translateJob?.cancel()
        if (!aiTranslate) {
            translateStatus = ""
            return
        }
        val q = typed.trim()
        if (q.length < 2 || q == lastApplied || q == lastQuery) return
        translateJob = scope.launch {
            delay(700)
            if (!aiTranslate) return@launch
            translateStatus = "Translating…"
            runCatching { repository.translateShopCatalog(q) }
                .onSuccess { data ->
                    if (english.trim() != q) return@onSuccess
                    lastQuery = q
                    if (data.source == "unchanged") {
                        translateStatus = "Already English"
                        lastApplied = data.english
                        return@onSuccess
                    }
                    english = data.english
                    lastApplied = data.english
                    if (malayalam.isBlank() && !data.malayalam.isNullOrBlank()) {
                        malayalam = data.malayalam
                    }
                    if (data.emoji.isNotBlank()) emoji = data.emoji
                    if (data.category.isNotBlank()) category = data.category
                    appendAlias(data.manglish.ifBlank { q })
                    val via = if (data.source == "ai") "AI" else "dictionary"
                    translateStatus = "Translated via $via: ${data.english}"
                }
                .onFailure {
                    translateStatus = it.message ?: "Translate failed"
                }
        }
    }

    fun reload() {
        scope.launch {
            loading = true
            runCatching { items = repository.listShopCatalog() }
                .onFailure {
                    Toast.makeText(context, it.message ?: "Could not load catalog", Toast.LENGTH_SHORT).show()
                }
            loading = false
        }
    }
    LaunchedEffect(Unit) { reload() }

    Box(Modifier.fillMaxSize().background(HubBg)) {
        Column(Modifier.fillMaxSize()) {
            Row(
                Modifier.fillMaxWidth().padding(20.dp, 16.dp, 8.dp, 0.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text("SHOPPING LIST", style = MaterialTheme.typography.labelMedium, color = VaultGold)
                    Text("Quick add", style = MaterialTheme.typography.headlineMedium, color = Ink, fontWeight = FontWeight.Bold)
                }
                IconButton(onClick = onOpenModules) {
                    Icon(Icons.Filled.Apps, contentDescription = "Modules", tint = InkSoft)
                }
            }
            Text(
                "Personal chips stay in your vault. Global chips appear for every user.",
                color = InkSoft,
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.padding(horizontal = 20.dp, vertical = 4.dp)
            )
            when {
                loading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = Navy)
                }
                items.isEmpty() -> Text(
                    "No custom chips yet. Built-in Kerala groceries stay on every list.",
                    color = InkSoft,
                    modifier = Modifier.padding(20.dp)
                )
                else -> LazyColumn(
                    contentPadding = PaddingValues(20.dp, 12.dp, 20.dp, 88.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    items(items, key = { it.id }) { row ->
                        Surface(shape = RoundedCornerShape(16.dp), color = HubGlass, modifier = Modifier.fillMaxWidth()) {
                            Row(
                                Modifier.padding(16.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Column(Modifier.weight(1f)) {
                                    Text(
                                        "${row.emoji ?: "🛒"} ${row.english}" +
                                            (row.malayalam?.takeIf { it.isNotBlank() }?.let { " ($it)" } ?: ""),
                                        color = Ink,
                                        fontWeight = FontWeight.SemiBold
                                    )
                                    Text(
                                        buildString {
                                            append(row.category)
                                            append(" · ")
                                            append(if (row.scope == "global") "Global" else "Personal")
                                            if (!row.mine) append(" · from another vault")
                                            row.aliases?.takeIf { it.isNotBlank() }?.let {
                                                append(" · "); append(it)
                                            }
                                        },
                                        color = InkSoft,
                                        style = MaterialTheme.typography.bodySmall
                                    )
                                }
                                if (row.mine) {
                                    IconButton(onClick = {
                                        scope.launch {
                                            runCatching { repository.deleteShopCatalogItem(row.id) }
                                                .onSuccess { reload() }
                                                .onFailure {
                                                    Toast.makeText(
                                                        context,
                                                        it.message ?: "Could not delete",
                                                        Toast.LENGTH_SHORT
                                                    ).show()
                                                }
                                        }
                                    }) {
                                        Icon(Icons.Filled.Delete, contentDescription = "Delete", tint = StampRed)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        FloatingActionButton(
            onClick = { showAdd = true },
            modifier = Modifier.align(Alignment.BottomEnd).padding(20.dp),
            containerColor = Navy
        ) {
            Icon(Icons.Filled.Add, contentDescription = "Add chip", tint = TextDark)
        }
    }

    if (showAdd) {
        AlertDialog(
            onDismissRequest = { showAdd = false },
            title = { Text("Add Quick add chip") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = aiTranslate, onCheckedChange = {
                            aiTranslate = it
                            if (it) scheduleTranslate(english) else translateStatus = ""
                        })
                        Text("AI translate Manglish → English", color = Ink, style = MaterialTheme.typography.bodySmall)
                    }
                    if (translateStatus.isNotBlank()) {
                        Text(translateStatus, color = InkSoft, style = MaterialTheme.typography.labelSmall)
                    }
                    OutlinedTextField(
                        value = english,
                        onValueChange = {
                            english = it
                            scheduleTranslate(it)
                        },
                        label = { Text("English name") },
                        placeholder = { Text("e.g. Vazhuthananga") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )
                    OutlinedTextField(
                        value = malayalam,
                        onValueChange = { malayalam = it },
                        label = { Text("Malayalam") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )
                    OutlinedTextField(
                        value = emoji,
                        onValueChange = { emoji = it },
                        label = { Text("Emoji") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )
                    ExposedDropdownMenuBox(expanded = catOpen, onExpandedChange = { catOpen = it }) {
                        OutlinedTextField(
                            value = category,
                            onValueChange = {},
                            readOnly = true,
                            label = { Text("Category") },
                            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(catOpen) },
                            modifier = Modifier.menuAnchor().fillMaxWidth()
                        )
                        ExposedDropdownMenu(expanded = catOpen, onDismissRequest = { catOpen = false }) {
                            catalogCategories.forEach { opt ->
                                DropdownMenuItem(
                                    text = { Text(opt) },
                                    onClick = { category = opt; catOpen = false }
                                )
                            }
                        }
                    }
                    ExposedDropdownMenuBox(expanded = scopeOpen, onExpandedChange = { scopeOpen = it }) {
                        OutlinedTextField(
                            value = if (scopeKind == "global") "Global — all users" else "Personal — only me",
                            onValueChange = {},
                            readOnly = true,
                            label = { Text("Visibility") },
                            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(scopeOpen) },
                            modifier = Modifier.menuAnchor().fillMaxWidth()
                        )
                        ExposedDropdownMenu(expanded = scopeOpen, onDismissRequest = { scopeOpen = false }) {
                            DropdownMenuItem(
                                text = { Text("Personal — only me") },
                                onClick = { scopeKind = "personal"; scopeOpen = false }
                            )
                            DropdownMenuItem(
                                text = { Text("Global — all users") },
                                onClick = { scopeKind = "global"; scopeOpen = false }
                            )
                        }
                    }
                    OutlinedTextField(
                        value = aliases,
                        onValueChange = { aliases = it },
                        label = { Text("Aliases (comma-separated)") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    val name = english.trim()
                    if (name.isEmpty()) return@TextButton
                    scope.launch {
                        runCatching {
                            repository.addShopCatalogItem(
                                ShopCatalogItemIn(
                                    english = name,
                                    malayalam = malayalam.trim().ifBlank { null },
                                    emoji = emoji.trim().ifBlank { "🛒" },
                                    category = category,
                                    scope = scopeKind,
                                    aliases = aliases.trim().ifBlank { null }
                                )
                            )
                        }.onSuccess {
                            english = ""
                            malayalam = ""
                            emoji = "🛒"
                            category = "custom"
                            scopeKind = "personal"
                            aliases = ""
                            translateStatus = ""
                            lastApplied = ""
                            lastQuery = ""
                            showAdd = false
                            reload()
                        }.onFailure {
                            Toast.makeText(context, it.message ?: "Could not save", Toast.LENGTH_SHORT).show()
                        }
                    }
                }) { Text("Add") }
            },
            dismissButton = { TextButton(onClick = { showAdd = false }) { Text("Cancel") } }
        )
    }
}
