package com.rklab.healthvault.ui.screens.diary

import android.net.Uri
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Apps
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.rklab.healthvault.data.model.DiaryCategoryOut
import com.rklab.healthvault.data.model.DiaryEntryOut
import com.rklab.healthvault.data.model.DiaryEntryUpdate
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.theme.*
import com.rklab.healthvault.util.FileUtil
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.time.LocalDate

@Composable
fun DiaryListScreen(
    repository: HealthVaultRepository,
    onOpenEntry: (String) -> Unit,
    onAdd: () -> Unit,
    onOpenModules: () -> Unit,
    pinnedOnly: Boolean = false
) {
    val scope = rememberCoroutineScope()
    var query by remember { mutableStateOf("") }
    var categoryId by remember { mutableStateOf<String?>(null) }
    var entries by remember { mutableStateOf<List<DiaryEntryOut>>(emptyList()) }
    var categories by remember { mutableStateOf<List<DiaryCategoryOut>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var showNewFolder by remember { mutableStateOf(false) }
    var newFolderName by remember { mutableStateOf("") }
    var creatingFolder by remember { mutableStateOf(false) }
    val context = LocalContext.current

    fun reload() {
        scope.launch {
            loading = true
            error = null
            runCatching {
                categories = repository.listDiaryCategories()
                entries = repository.listDiaryEntries(categoryId, query.ifBlank { null }, pinnedOnly)
            }.onFailure { error = it.message ?: "Could not load diary" }
            loading = false
        }
    }
    LaunchedEffect(query, categoryId, pinnedOnly) {
        delay(350)
        reload()
    }

    if (showNewFolder) {
        AlertDialog(
            onDismissRequest = { if (!creatingFolder) showNewFolder = false },
            title = { Text("New folder") },
            text = {
                OutlinedTextField(
                    value = newFolderName,
                    onValueChange = { newFolderName = it },
                    singleLine = true,
                    placeholder = { Text("e.g. Thidanad trip") },
                    modifier = Modifier.fillMaxWidth()
                )
            },
            confirmButton = {
                TextButton(
                    enabled = newFolderName.isNotBlank() && !creatingFolder,
                    onClick = {
                        creatingFolder = true
                        scope.launch {
                            runCatching {
                                val created = repository.createDiaryCategory(newFolderName.trim())
                                categoryId = created.id
                                newFolderName = ""
                                showNewFolder = false
                                reload()
                                Toast.makeText(context, "Folder created", Toast.LENGTH_SHORT).show()
                            }.onFailure {
                                Toast.makeText(context, it.message ?: "Could not create folder", Toast.LENGTH_LONG).show()
                            }
                            creatingFolder = false
                        }
                    }
                ) { Text(if (creatingFolder) "…" else "Create") }
            },
            dismissButton = {
                TextButton(onClick = { showNewFolder = false }, enabled = !creatingFolder) {
                    Text("Cancel")
                }
            }
        )
    }

    Box(Modifier.fillMaxSize().background(HubBg)) {
        Column(Modifier.fillMaxSize()) {
            Row(
                Modifier.fillMaxWidth().padding(16.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text("Digital Diary", color = HubText, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
                    Text(if (pinnedOnly) "Pinned notes" else "Your journal", color = HubTextDim, style = MaterialTheme.typography.bodySmall)
                }
                IconButton(onClick = onOpenModules) {
                    Icon(Icons.Filled.Apps, contentDescription = "Modules", tint = HubText)
                }
            }
            OutlinedTextField(
                value = query,
                onValueChange = { query = it },
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
                placeholder = { Text("Search title, story, tags, mood…") },
                leadingIcon = { Icon(Icons.Filled.Search, null) },
                singleLine = true
            )
            Spacer(Modifier.height(8.dp))
            LazyRow(
                contentPadding = PaddingValues(horizontal = 16.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                item {
                    FilterChip(
                        selected = categoryId == null,
                        onClick = { categoryId = null },
                        label = { Text("All") }
                    )
                }
                items(categories) { cat ->
                    FilterChip(
                        selected = categoryId == cat.id,
                        onClick = { categoryId = cat.id },
                        label = { Text(cat.name) }
                    )
                }
                item {
                    FilterChip(
                        selected = false,
                        onClick = { showNewFolder = true; newFolderName = "" },
                        label = { Text("+ Folder") }
                    )
                }
            }
            when {
                loading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = HubMint)
                }
                error != null -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text(error!!, color = StampRed)
                }
                entries.isEmpty() -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text("No entries yet", color = HubTextDim)
                }
                else -> LazyColumn(
                    contentPadding = PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    items(entries, key = { it.id }) { entry ->
                        Card(
                            modifier = Modifier.fillMaxWidth().clickable { onOpenEntry(entry.id) },
                            colors = CardDefaults.cardColors(containerColor = HubGlass)
                        ) {
                            Column(Modifier.padding(14.dp)) {
                                Row(horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
                                    Text(entry.title, color = HubText, fontWeight = FontWeight.SemiBold)
                                    Text(entry.entry_date, color = HubTextFaint, style = MaterialTheme.typography.labelSmall)
                                }
                                if (!entry.category_name.isNullOrBlank()) {
                                    Text(entry.category_name, color = Color(android.graphics.Color.parseColor(entry.category_color ?: "#8B95A8")), style = MaterialTheme.typography.labelMedium)
                                }
                                if (!entry.body.isNullOrBlank()) {
                                    Spacer(Modifier.height(4.dp))
                                    Text(entry.body.take(120), color = HubTextDim, style = MaterialTheme.typography.bodySmall, maxLines = 2)
                                }
                                if (entry.image_count > 0) {
                                    Text("${entry.image_count} photo(s)", color = HubTextFaint, style = MaterialTheme.typography.labelSmall)
                                }
                            }
                        }
                    }
                }
            }
        }
        FloatingActionButton(
            onClick = onAdd,
            modifier = Modifier.align(Alignment.BottomEnd).padding(20.dp),
            containerColor = HubMint
        ) {
            Icon(Icons.Filled.Add, contentDescription = "New entry")
        }
    }
}

@Composable
fun DiaryAddScreen(
    repository: HealthVaultRepository,
    onDone: () -> Unit,
    onBack: () -> Unit
) {
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    var title by remember { mutableStateOf("") }
    var body by remember { mutableStateOf("") }
    var tags by remember { mutableStateOf("") }
    var mood by remember { mutableStateOf("") }
    var entryDate by remember { mutableStateOf(LocalDate.now().toString()) }
    var categoryId by remember { mutableStateOf<String?>(null) }
    var categories by remember { mutableStateOf<List<DiaryCategoryOut>>(emptyList()) }
    var pinned by remember { mutableStateOf(false) }
    var imageUris by remember { mutableStateOf<List<Uri>>(emptyList()) }
    var saving by remember { mutableStateOf(false) }

    val picker = rememberLauncherForActivityResult(ActivityResultContracts.GetMultipleContents()) { uris ->
        imageUris = imageUris + uris
    }

    LaunchedEffect(Unit) {
        categories = runCatching { repository.listDiaryCategories() }.getOrDefault(emptyList())
    }

    Column(
        Modifier.fillMaxSize().background(HubBg).verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        TextButton(onClick = onBack) { Text("Back", color = HubTextDim) }
        Text("New entry", color = HubText, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
        OutlinedTextField(value = title, onValueChange = { title = it }, label = { Text("Title") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
        OutlinedTextField(value = entryDate, onValueChange = { entryDate = it }, label = { Text("Date (YYYY-MM-DD)") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
        OutlinedTextField(value = body, onValueChange = { body = it }, label = { Text("Description") }, modifier = Modifier.fillMaxWidth().heightIn(min = 140.dp), minLines = 5)
        OutlinedTextField(value = tags, onValueChange = { tags = it }, label = { Text("Tags") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
        OutlinedTextField(value = mood, onValueChange = { mood = it }, label = { Text("Mood") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
        if (categories.isNotEmpty()) {
            Text("Folder", color = HubTextDim)
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                item {
                    FilterChip(selected = categoryId == null, onClick = { categoryId = null }, label = { Text("None") })
                }
                items(categories) { cat ->
                    FilterChip(selected = categoryId == cat.id, onClick = { categoryId = cat.id }, label = { Text(cat.name) })
                }
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Checkbox(checked = pinned, onCheckedChange = { pinned = it })
            Text("Pin entry", color = HubText)
        }
        TextButton(onClick = { picker.launch("image/*") }) { Text("Add photos (${imageUris.size})") }
        Button(
            enabled = title.isNotBlank() && !saving,
            onClick = {
                scope.launch {
                    saving = true
                    runCatching {
                        val files = imageUris.mapIndexed { idx, uri ->
                            FileUtil.copyUriToCacheFile(context, uri, "diary_${System.currentTimeMillis()}_$idx")
                        }
                        repository.createDiaryEntry(
                            title = title.trim(),
                            body = body.ifBlank { null },
                            entryDate = entryDate.ifBlank { null },
                            categoryId = categoryId,
                            tags = tags.ifBlank { null },
                            mood = mood.ifBlank { null },
                            pinned = pinned,
                            images = files
                        )
                    }.onSuccess {
                        Toast.makeText(context, "Saved", Toast.LENGTH_SHORT).show()
                        onDone()
                    }.onFailure {
                        Toast.makeText(context, it.message ?: "Save failed", Toast.LENGTH_LONG).show()
                    }
                    saving = false
                }
            },
            modifier = Modifier.fillMaxWidth()
        ) {
            Text(if (saving) "Saving…" else "Save entry")
        }
    }
}

@Composable
fun DiaryEntryScreen(
    repository: HealthVaultRepository,
    entryId: String,
    onBack: () -> Unit
) {
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    var entry by remember { mutableStateOf<DiaryEntryOut?>(null) }
    var title by remember { mutableStateOf("") }
    var body by remember { mutableStateOf("") }
    var loading by remember { mutableStateOf(true) }
    var saving by remember { mutableStateOf(false) }

    LaunchedEffect(entryId) {
        loading = true
        runCatching { repository.getDiaryEntry(entryId) }
            .onSuccess {
                entry = it
                title = it.title
                body = it.body.orEmpty()
            }
        loading = false
    }

    if (loading || entry == null) {
        Box(Modifier.fillMaxSize().background(HubBg), contentAlignment = Alignment.Center) {
            CircularProgressIndicator(color = HubMint)
        }
        return
    }

    Column(
        Modifier.fillMaxSize().background(HubBg).verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        TextButton(onClick = onBack) { Text("Back", color = HubTextDim) }
        Text(entry!!.entry_date, color = HubTextFaint)
        OutlinedTextField(value = title, onValueChange = { title = it }, label = { Text("Title") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(value = body, onValueChange = { body = it }, label = { Text("Description") }, modifier = Modifier.fillMaxWidth().heightIn(min = 160.dp), minLines = 6)
        if (!entry!!.category_name.isNullOrBlank()) {
            Text("Category: ${entry!!.category_name}", color = HubTextDim)
        }
        if (entry!!.image_count > 0) {
            Text("${entry!!.image_count} photo(s) attached", color = HubTextDim)
        }
        Button(
            enabled = !saving,
            onClick = {
                scope.launch {
                    saving = true
                    runCatching {
                        repository.updateDiaryEntry(entryId, DiaryEntryUpdate(title = title.trim(), body = body))
                    }.onSuccess {
                        Toast.makeText(context, "Saved", Toast.LENGTH_SHORT).show()
                        onBack()
                    }.onFailure {
                        Toast.makeText(context, it.message ?: "Save failed", Toast.LENGTH_LONG).show()
                    }
                    saving = false
                }
            },
            modifier = Modifier.fillMaxWidth()
        ) { Text("Save") }
        TextButton(
            onClick = {
                scope.launch {
                    runCatching { repository.deleteDiaryEntry(entryId) }
                        .onSuccess { onBack() }
                        .onFailure { Toast.makeText(context, it.message ?: "Delete failed", Toast.LENGTH_LONG).show() }
                }
            }
        ) { Text("Delete entry", color = StampRed) }
    }
}
