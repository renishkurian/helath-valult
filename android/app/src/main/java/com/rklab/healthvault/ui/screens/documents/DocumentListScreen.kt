package com.rklab.healthvault.ui.screens.documents

import android.content.Intent
import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
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
    onAddDocument: () -> Unit
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

    // Helper function to download and open a file
    fun openFile(docId: String, fileId: String?, originalFilename: String, fileType: String?) {
        if (downloadingDocId != null) return
        scope.launch {
            downloadingDocId = docId
            try {
                val safeName = originalFilename
                    .replace(Regex("[^a-zA-Z0-9.\\-]"), "_")
                    .take(80)
                val downloadsDir = context.cacheDir.resolve("downloads")
                downloadsDir.mkdirs()
                val dest = File(downloadsDir, "${fileId ?: docId}_$safeName")
                
                val file = withContext(Dispatchers.IO) {
                    if (fileId != null) {
                        repository.downloadDocumentFile(docId, fileId, dest)
                    } else {
                        viewModel.download(docId, dest)
                    }
                }
                
                val uri = FileProvider.getUriForFile(
                    context,
                    "${context.packageName}.fileprovider",
                    file
                )
                val mimeType = when {
                    !fileType.isNullOrBlank() -> fileType
                    safeName.endsWith(".pdf", true) -> "application/pdf"
                    safeName.endsWith(".jpg", true) || safeName.endsWith(".jpeg", true) -> "image/jpeg"
                    safeName.endsWith(".png", true) -> "image/png"
                    else -> "*/*"
                }
                val intent = Intent(Intent.ACTION_VIEW).apply {
                    setDataAndType(uri, mimeType)
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                }
                context.startActivity(Intent.createChooser(intent, "Open with"))
            } catch (e: retrofit2.HttpException) {
                val errorBody = try { e.response()?.errorBody()?.string() } catch (_: Exception) { null }
                val detail = errorBody?.let { Regex("\"detail\"\\s*:\\s*\"([^\"]*)\"").find(it)?.groupValues?.get(1) }
                Toast.makeText(context, "Server error (${e.code()}): ${detail ?: e.message()}", Toast.LENGTH_LONG).show()
            } catch (e: android.content.ActivityNotFoundException) {
                Toast.makeText(context, "No app found to open this file type.", Toast.LENGTH_LONG).show()
            } catch (e: Exception) {
                val msg = when {
                    isOffline -> "You're offline. Cannot download this file right now."
                    e.message?.contains("No Activity found", ignoreCase = true) == true ->
                        "No app found to open this file type."
                    else -> "Could not open file: ${e.javaClass.simpleName}: ${e.message ?: "(no detail)"}"
                }
                Toast.makeText(context, msg, Toast.LENGTH_LONG).show()
            } finally {
                downloadingDocId = null
            }
        }
    }

    Column(modifier = Modifier.fillMaxSize().background(Paper)) {
        OfflineBanner(isOffline = isOffline, pendingCount = pendingCount)

        Box(modifier = Modifier.weight(1f)) {
            Column(modifier = Modifier.fillMaxSize().padding(20.dp)) {
                TextButton(onClick = onBack) { Text("← Back", color = Navy) }
                Text(title.uppercase(), style = MaterialTheme.typography.labelMedium, color = InkSoft)
                Spacer(Modifier.height(4.dp))
                Text("${state.documents.size} documents", style = MaterialTheme.typography.headlineMedium, color = Ink)

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
                            .clip(RoundedCornerShape(14.dp))
                            .background(White),
                        contentPadding = PaddingValues(bottom = 90.dp)
                    ) {
                        items(state.documents, key = { it.id }) { doc ->
                            val dismissState = rememberSwipeToDismissBoxState(
                                confirmValueChange = { value ->
                                    if (value == SwipeToDismissBoxValue.EndToStart) {
                                        docToDelete = doc
                                        false // Don't dismiss immediately, wait for confirmation
                                    } else {
                                        false
                                    }
                                }
                            )

                            SwipeToDismissBox(
                                state = dismissState,
                                enableDismissFromStartToEnd = false,
                                backgroundContent = {
                                    Box(
                                        Modifier
                                            .fillMaxSize()
                                            .background(StampRed)
                                            .padding(horizontal = 20.dp),
                                        contentAlignment = Alignment.CenterEnd
                                    ) {
                                        Icon(Icons.Default.Delete, contentDescription = "Delete", tint = White)
                                    }
                                }
                            ) {
                                val isDownloading = downloadingDocId == doc.id
                                LedgerRow(
                                    title = doc.title,
                                    metaLine = "${doc.doc_date ?: doc.created_at.take(10)} · ${doc.hospital_name ?: "—"}",
                                    category = doc.category,
                                    tagLabel = if (isDownloading) "..." else if (doc.file_count > 1) "${doc.file_count} files" else "Open",
                                    tagColor = Sage,
                                    tagBg = SageBg,
                                    onClick = {
                                        if (doc.file_count > 1) {
                                            selectedDocForFiles = doc
                                        } else {
                                            openFile(doc.id, null, doc.title, doc.file_type)
                                        }
                                    }
                                )
                            }
                            Divider(color = PaperDeep, thickness = 1.dp)
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

            FloatingActionButton(
                onClick = onAddDocument,
                containerColor = Navy, contentColor = White,
                modifier = Modifier.align(Alignment.BottomEnd).padding(20.dp)
            ) { Icon(Icons.Filled.Add, contentDescription = "Add document") }
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
                                        openFile(docId, file.id, file.original_filename, file.file_type)
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
