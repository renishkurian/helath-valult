package com.rklab.healthvault.ui.screens.documents

import android.content.Intent
import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import androidx.lifecycle.viewmodel.compose.viewModel
import com.rklab.healthvault.data.model.DocCategory
import com.rklab.healthvault.data.model.DocumentFileOut
import com.rklab.healthvault.data.model.DocumentOut
import com.rklab.healthvault.ui.components.LedgerRow
import com.rklab.healthvault.ui.components.OfflineBanner
import com.rklab.healthvault.ui.theme.*
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.util.ViewModelFactory
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DocumentListScreen(
    repository: HealthVaultRepository,
    personId: String,
    category: DocCategory?,
    customCategory: String? = null,
    title: String,
    onBack: () -> Unit,
    onAddDocument: () -> Unit,
    onOpenFile: (String, String?) -> Unit,
    onEditDocument: (String) -> Unit
) {
    val viewModel: DocumentsViewModel = viewModel(factory = ViewModelFactory(repository))
    val state by viewModel.state.collectAsState()
    val isOffline by viewModel.isOffline.collectAsState()
    val pendingCount by viewModel.pendingUploadCount.collectAsState()
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    // Download state
    var downloadingDocId by remember { mutableStateOf<String?>(null) }
    
    // Delete confirmation state
    var docToDelete by remember { mutableStateOf<DocumentOut?>(null) }

    // Share link state
    var docToShare by remember { mutableStateOf<DocumentOut?>(null) }
    var selectedIds by remember { mutableStateOf<Set<String>>(emptySet()) }
    var packPin by remember { mutableStateOf("") }
    var showPackDialog by remember { mutableStateOf(false) }
    
    // Multi-file bottom sheet state
    var selectedDocForFiles by remember { mutableStateOf<DocumentOut?>(null) }
    var docFiles by remember { mutableStateOf<List<DocumentFileOut>>(emptyList()) }
    var fetchingFiles by remember { mutableStateOf(false) }

    LaunchedEffect(personId, category, customCategory) { viewModel.load(personId, category, customCategory) }

    // Fetch files when a document is selected for the bottom sheet
    LaunchedEffect(selectedDocForFiles) {
        val doc = selectedDocForFiles ?: return@LaunchedEffect
        fetchingFiles = true
        try {
            docFiles = withContext(Dispatchers.IO) { repository.listDocumentFiles(doc.id) }
        } catch (e: Exception) {
            Toast.makeText(context, "Failed to list files: ${e.message}", Toast.LENGTH_SHORT).show()
            selectedDocForFiles = null
        } finally {
            fetchingFiles = false
        }
    }

    // Helper function to open a file using our new in-app viewer
    fun openFile(docId: String, fileId: String?) {
        onOpenFile(docId, fileId)
    }

    Column(modifier = Modifier.fillMaxSize().background(Paper)) {
        OfflineBanner(isOffline = isOffline, pendingCount = pendingCount)

        Box(modifier = Modifier.weight(1f)) {
            Column(modifier = Modifier.fillMaxSize().padding(20.dp)) {
                TextButton(onClick = onBack) { Text("← Back", color = Navy) }
                Text(title.uppercase(), style = MaterialTheme.typography.labelMedium, color = InkSoft)
                Spacer(Modifier.height(4.dp))
                Text("${state.documents.size} documents", style = MaterialTheme.typography.headlineMedium, color = Ink)
                if (!repository.isViewer) {
                    Spacer(Modifier.height(8.dp))
                    OutlinedButton(onClick = {
                        scope.launch {
                            try {
                                val dest = File(context.getExternalFilesDir(null), "${title}-export.zip")
                                withContext(Dispatchers.IO) { repository.exportBackup(dest, personId = personId) }
                                val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", dest)
                                context.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply {
                                    type = "application/zip"
                                    putExtra(Intent.EXTRA_STREAM, uri)
                                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                                }, "Export documents"))
                            } catch (e: Exception) {
                                Toast.makeText(context, "Export failed: ${e.message}", Toast.LENGTH_SHORT).show()
                            }
                        }
                    }) { Text("Export this person as zip", color = Navy) }
                    if (selectedIds.isNotEmpty()) {
                        Spacer(Modifier.height(8.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            OutlinedButton(onClick = { showPackDialog = true }) { Text("Share ${selectedIds.size} as pack", color = Navy) }
                            OutlinedButton(onClick = {
                                scope.launch {
                                    runCatching { repository.bulkDeleteDocuments(selectedIds.toList()) }
                                    selectedIds = emptySet()
                                    viewModel.load(personId, category, customCategory)
                                }
                            }) { Text("Delete selected", color = StampRed) }
                        }
                    }
                }

                if (state.error != null) {
                    Spacer(Modifier.height(8.dp))
                    Surface(
                        color = MaterialTheme.colorScheme.errorContainer,
                        shape = RoundedCornerShape(8.dp),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text(
                            text = state.error!!,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onErrorContainer,
                            modifier = Modifier.padding(12.dp)
                        )
                    }
                }

                Spacer(Modifier.height(16.dp))

                if (state.loading) {
                    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator(color = Navy)
                    }
                } else if (state.documents.isEmpty()) {
                    Text("Nothing here yet.", color = InkSoft)
                } else {
                    LazyColumn(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(16.dp))
                            .background(CardSurface)
                            .border(1.dp, CardOutline, RoundedCornerShape(16.dp)),
                        contentPadding = PaddingValues(bottom = 90.dp)
                    ) {
                        items(state.documents, key = { it.id }) { doc ->
                            val isDownloading = downloadingDocId == doc.id
                            var menuOpen by remember { mutableStateOf(false) }
                            LedgerRow(
                                title = doc.title,
                                metaLine = buildString {
                                    append(doc.doc_date ?: doc.created_at.take(10))
                                    append(" · ")
                                    append(doc.hospital_name ?: "—")
                                    if (!doc.tags.isNullOrBlank()) append(" · ${doc.tags}")
                                    if (doc.version > 1) append(" · v${doc.version}")
                                },
                                category = doc.category,
                                tagLabel = if (isDownloading) "..." else if (doc.file_count > 1) "${doc.file_count} files" else "Open",
                                onClick = {
                                    if (selectedIds.isNotEmpty()) {
                                        selectedIds = if (doc.id in selectedIds) selectedIds - doc.id else selectedIds + doc.id
                                    } else if (doc.file_count > 1) {
                                        selectedDocForFiles = doc
                                    } else {
                                        openFile(doc.id, null)
                                    }
                                },
                                trailingAction = {
                                    if (!repository.isViewer) {
                                        Row(verticalAlignment = Alignment.CenterVertically) {
                                            IconButton(
                                                onClick = { onEditDocument(doc.id) },
                                                modifier = Modifier.size(40.dp)
                                            ) {
                                                Icon(Icons.Filled.Edit, contentDescription = "Edit", tint = Navy)
                                            }
                                            IconButton(
                                                onClick = { docToShare = doc },
                                                modifier = Modifier.size(40.dp)
                                            ) {
                                                Icon(Icons.Filled.Share, contentDescription = "Share", tint = Navy)
                                            }
                                            Box {
                                                IconButton(
                                                    onClick = { menuOpen = true },
                                                    modifier = Modifier.size(40.dp)
                                                ) {
                                                    Icon(
                                                        Icons.Filled.MoreVert,
                                                        contentDescription = "More",
                                                        tint = TextGray
                                                    )
                                                }
                                                DropdownMenu(
                                                    expanded = menuOpen,
                                                    onDismissRequest = { menuOpen = false },
                                                    containerColor = CardSurface
                                                ) {
                                                    DropdownMenuItem(
                                                        text = { Text(if (doc.id in selectedIds) "Unselect" else "Select for pack", color = TextWhite) },
                                                        onClick = {
                                                            menuOpen = false
                                                            selectedIds = if (doc.id in selectedIds) selectedIds - doc.id else selectedIds + doc.id
                                                        }
                                                    )
                                                    DropdownMenuItem(
                                                        text = { Text("Delete", color = StampRed) },
                                                        leadingIcon = { Icon(Icons.Filled.Delete, null, tint = StampRed) },
                                                        onClick = { menuOpen = false; docToDelete = doc }
                                                    )
                                                }
                                            }
                                        }
                                    }
                                }
                            )
                            Divider(color = CardOutline, thickness = 1.dp)
                        }
                    }
                }
            }

            // Downloading overlay
            if (downloadingDocId != null) {
                Box(
                    modifier = Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center
                ) {
                    Surface(
                        shape = RoundedCornerShape(12.dp),
                        color = MaterialTheme.colorScheme.surface,
                        tonalElevation = 8.dp
                    ) {
                        Row(
                            modifier = Modifier.padding(horizontal = 24.dp, vertical = 16.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(12.dp)
                        ) {
                            CircularProgressIndicator(modifier = Modifier.size(20.dp), color = Navy, strokeWidth = 2.dp)
                            Text("Downloading…", color = Ink)
                        }
                    }
                }
            }

            if (!repository.isViewer) {
            FloatingActionButton(
                onClick = onAddDocument,
                containerColor = Navy,
                contentColor = TextWhite,
                modifier = Modifier.align(Alignment.BottomEnd).padding(20.dp)
            ) { Icon(Icons.Filled.Add, contentDescription = "Add document") }
            }
        }
    }

    // Delete Confirmation Dialog
    if (docToDelete != null) {
        AlertDialog(
            onDismissRequest = { docToDelete = null },
            title = { Text("Delete Document") },
            text = { Text("Are you sure you want to delete '${docToDelete?.title}'? This action cannot be undone.") },
            confirmButton = {
                TextButton(
                    onClick = {
                        val doc = docToDelete
                        if (doc != null) {
                            viewModel.delete(personId, category, doc.id)
                        }
                        docToDelete = null
                    }
                ) { Text("Delete", color = StampRed) }
            },
            dismissButton = {
                TextButton(onClick = { docToDelete = null }) { Text("Cancel", color = Navy) }
            }
        )
    }

    if (showPackDialog) {
        AlertDialog(
            onDismissRequest = { showPackDialog = false },
            title = { Text("Share pack") },
            text = {
                Column {
                    Text("${selectedIds.size} documents. Recipients open one link.")
                    Spacer(Modifier.height(8.dp))
                    OutlinedTextField(packPin, { packPin = it.filter(Char::isDigit).take(8) }, label = { Text("Optional PIN") })
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    scope.launch {
                        try {
                            val pack = repository.createSharePack("Hospital pack", selectedIds.toList(), packPin.ifBlank { null })
                            val url = "${repository.getServerUrl()?.trimEnd('/')}/p/${pack.token}"
                            val uri = android.content.Intent(android.content.Intent.ACTION_SEND).apply {
                                type = "text/plain"
                                putExtra(android.content.Intent.EXTRA_TEXT, url)
                            }
                            context.startActivity(android.content.Intent.createChooser(uri, "Share pack"))
                            showPackDialog = false
                            selectedIds = emptySet()
                        } catch (e: Exception) {
                            Toast.makeText(context, e.message, Toast.LENGTH_SHORT).show()
                        }
                    }
                }) { Text("Create & share", color = Navy) }
            },
            dismissButton = { TextButton(onClick = { showPackDialog = false }) { Text("Cancel") } }
        )
    }

    // Share link dialog
    if (docToShare != null) {
        ShareLinkDialog(
            repository = repository,
            doc = docToShare!!,
            onDismiss = { docToShare = null }
        )
    }

    // Multi-file Bottom Sheet
    if (selectedDocForFiles != null) {
        ModalBottomSheet(
            onDismissRequest = { selectedDocForFiles = null },
            containerColor = Paper
        ) {
            Column(modifier = Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 10.dp)) {
                Text("Files for ${selectedDocForFiles?.title}", style = MaterialTheme.typography.titleMedium, color = Ink)
                Spacer(Modifier.height(16.dp))

                if (fetchingFiles) {
                    Box(Modifier.fillMaxWidth().padding(30.dp), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator(color = Navy)
                    }
                } else if (docFiles.isEmpty()) {
                    Text("No files attached.", color = InkSoft, modifier = Modifier.padding(bottom = 40.dp))
                } else {
                    LazyColumn(contentPadding = PaddingValues(bottom = 40.dp)) {
                        items(docFiles) { file ->
                            LedgerRow(
                                title = file.original_filename,
                                metaLine = "Size: ${file.file_size?.let { it / 1024 } ?: "?"} KB",
                                category = selectedDocForFiles?.category ?: DocCategory.OTHER,
                                tagLabel = "Open",
                                tagColor = Sage,
                                tagBg = SageBg,
                                onClick = {
                                    selectedDocForFiles?.id?.let { docId ->
                                        openFile(docId, file.id)
                                    }
                                }
                            )
                            Divider(color = PaperDeep, thickness = 1.dp)
                        }
                    }
                }
            }
        }
    }
}
