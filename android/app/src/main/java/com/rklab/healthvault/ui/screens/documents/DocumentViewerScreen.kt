package com.rklab.healthvault.ui.screens.documents

import android.graphics.Bitmap
import android.graphics.pdf.PdfRenderer
import android.net.Uri
import android.os.ParcelFileDescriptor
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChevronLeft
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.Group
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.UploadFile
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.rklab.healthvault.data.model.DocumentFileOut
import com.rklab.healthvault.data.model.DocumentOut
import com.rklab.healthvault.data.model.DocumentVersionOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.components.FamilyShareDialog
import com.rklab.healthvault.ui.theme.HubBg
import com.rklab.healthvault.ui.theme.Ink
import com.rklab.healthvault.ui.theme.InkSoft
import com.rklab.healthvault.ui.theme.Navy
import com.rklab.healthvault.ui.theme.VaultGold
import com.rklab.healthvault.util.FileUtil
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DocumentViewerScreen(
    repository: HealthVaultRepository,
    docId: String,
    fileId: String?,
    onBack: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var file by remember { mutableStateOf<File?>(null) }
    var isLoading by remember { mutableStateOf(true) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    var mimeType by remember { mutableStateOf<String?>(null) }
    var extractedText by remember { mutableStateOf<String?>(null) }
    var versions by remember { mutableStateOf<List<DocumentVersionOut>>(emptyList()) }
    var docFiles by remember { mutableStateOf<List<DocumentFileOut>>(emptyList()) }
    var activeFileId by remember(fileId) { mutableStateOf(fileId?.takeIf { it.isNotBlank() }) }
    var showVersions by remember { mutableStateOf(false) }
    var replacing by remember { mutableStateOf(false) }
    var docMeta by remember { mutableStateOf<DocumentOut?>(null) }
    var showFamilyShare by remember { mutableStateOf(false) }
    val isViewer = repository.isViewer
    val canEdit = docMeta?.my_permission == "edit" && !isViewer
    val canFamilyShare = docMeta?.is_owned == true

    val resolvedFileId = activeFileId ?: docFiles.firstOrNull()?.id
    val fileIndex = docFiles.indexOfFirst { it.id == resolvedFileId }.takeIf { it >= 0 } ?: 0
    val hasMulti = docFiles.size > 1
    val prevFile = docFiles.getOrNull(fileIndex - 1)
    val nextFile = docFiles.getOrNull(fileIndex + 1)

    val replaceLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenMultipleDocuments()
    ) { uris: List<Uri> ->
        if (uris.isEmpty()) return@rememberLauncherForActivityResult
        replacing = true
        scope.launch {
            try {
                val files = withContext(Dispatchers.IO) {
                    uris.map { uri ->
                        val mime = FileUtil.mimeTypeOf(context, uri)
                        FileUtil.copyUriToCacheFile(context, uri, "v_${System.currentTimeMillis()}") to mime
                    }
                }
                if (files.isNotEmpty()) {
                    withContext(Dispatchers.IO) {
                        repository.replaceDocumentVersion(
                            docId, null, null,
                            files.map { it.first }, files.map { it.second }
                        )
                    }
                    Toast.makeText(context, "New version saved.", Toast.LENGTH_SHORT).show()
                    versions = withContext(Dispatchers.IO) { repository.listDocumentVersions(docId) }
                    docFiles = withContext(Dispatchers.IO) { repository.listDocumentFiles(docId) }
                }
            } catch (e: Exception) {
                Toast.makeText(context, "Replace failed: ${e.message}", Toast.LENGTH_SHORT).show()
            } finally {
                replacing = false
            }
        }
    }

    LaunchedEffect(docId) {
        docFiles = withContext(Dispatchers.IO) {
            runCatching { repository.listDocumentFiles(docId) }.getOrDefault(emptyList())
        }
        if (activeFileId == null) {
            activeFileId = docFiles.firstOrNull()?.id
        }
    }

    LaunchedEffect(docId, resolvedFileId) {
        isLoading = true
        errorMessage = null
        try {
            val cacheKey = resolvedFileId ?: docId
            val dest = com.rklab.healthvault.data.local.DocumentCache.fileFor(context, cacheKey)
            dest.parentFile?.mkdirs()

            val downloadedFile = withContext(Dispatchers.IO) {
                if (dest.exists() && dest.length() > 0) {
                    dest
                } else if (resolvedFileId != null) {
                    repository.downloadDocumentFile(docId, resolvedFileId, dest)
                } else {
                    repository.downloadDocument(docId, dest)
                }
            }
            file = downloadedFile
            com.rklab.healthvault.data.local.DocumentCache.prune(context)

            val isPdf = withContext(Dispatchers.IO) {
                try {
                    downloadedFile.inputStream().use {
                        val bytes = ByteArray(4)
                        it.read(bytes)
                        bytes[0] == 0x25.toByte() && bytes[1] == 0x50.toByte() &&
                            bytes[2] == 0x44.toByte() && bytes[3] == 0x46.toByte()
                    }
                } catch (e: Exception) {
                    false
                }
            }
            mimeType = if (isPdf) "application/pdf" else "image/*"

            val meta = withContext(Dispatchers.IO) {
                runCatching { repository.getDocument(docId) }.getOrNull()
            }
            if (meta != null) {
                docMeta = meta
                meta.extracted_text?.takeIf { it.isNotBlank() }?.let { extractedText = it }
            }
            versions = withContext(Dispatchers.IO) {
                runCatching { repository.listDocumentVersions(docId) }.getOrDefault(emptyList())
            }
        } catch (e: Exception) {
            errorMessage = e.message ?: "Failed to download file"
        } finally {
            isLoading = false
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text(docMeta?.title ?: "Document Viewer", style = MaterialTheme.typography.titleMedium)
                        when {
                            docMeta?.shared_from != null -> Text(
                                "Shared by ${docMeta?.shared_from?.full_name.orEmpty()}",
                                style = MaterialTheme.typography.labelSmall,
                                color = InkSoft
                            )
                            hasMulti -> Text(
                                "File ${fileIndex + 1} / ${docFiles.size}",
                                style = MaterialTheme.typography.labelSmall,
                                color = InkSoft
                            )
                        }
                    }
                },
                navigationIcon = {
                    TextButton(onClick = onBack) { Text("← Back", color = Navy) }
                },
                actions = {
                    if (hasMulti) {
                        IconButton(
                            onClick = { prevFile?.let { activeFileId = it.id } },
                            enabled = prevFile != null
                        ) {
                            Icon(Icons.Filled.ChevronLeft, contentDescription = "Previous file", tint = Navy)
                        }
                        IconButton(
                            onClick = { nextFile?.let { activeFileId = it.id } },
                            enabled = nextFile != null
                        ) {
                            Icon(Icons.Filled.ChevronRight, contentDescription = "Next file", tint = Navy)
                        }
                    }
                    if (canFamilyShare) {
                        IconButton(onClick = { showFamilyShare = true }) {
                            Icon(Icons.Filled.Group, contentDescription = "Share with family", tint = Navy)
                        }
                    }
                    if (versions.isNotEmpty()) {
                        IconButton(onClick = { showVersions = true }) {
                            Icon(Icons.Filled.History, contentDescription = "Version history", tint = Navy)
                        }
                    }
                    if (canEdit) {
                        IconButton(onClick = { replaceLauncher.launch(arrayOf("*/*")) }, enabled = !replacing) {
                            Icon(Icons.Filled.UploadFile, contentDescription = "Upload new version", tint = Navy)
                        }
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = HubBg)
            )
        },
        containerColor = Color.Black
    ) { padding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
            contentAlignment = Alignment.Center
        ) {
            when {
                isLoading -> {
                    CircularProgressIndicator(color = Color.White)
                }
                errorMessage != null -> {
                    Text("Error: $errorMessage", color = Color.Red)
                }
                file != null -> {
                    Column(Modifier.fillMaxSize()) {
                        Box(Modifier.weight(1f), contentAlignment = Alignment.Center) {
                            if (mimeType == "application/pdf") {
                                PdfViewer(file = file!!)
                            } else {
                                AsyncImage(
                                    model = file,
                                    contentDescription = "Document Image",
                                    modifier = Modifier.fillMaxSize(),
                                    contentScale = ContentScale.Fit
                                )
                            }
                        }
                        if (hasMulti) {
                            Text(
                                docFiles.getOrNull(fileIndex)?.original_filename.orEmpty(),
                                color = Color.White.copy(alpha = 0.7f),
                                style = MaterialTheme.typography.labelSmall,
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .background(Color.Black.copy(alpha = 0.55f))
                                    .padding(horizontal = 16.dp, vertical = 8.dp)
                            )
                        }
                        if (!extractedText.isNullOrBlank()) {
                            Column(
                                Modifier
                                    .fillMaxWidth()
                                    .background(HubBg)
                                    .padding(16.dp)
                            ) {
                                Text("EXTRACTED TEXT", style = MaterialTheme.typography.labelMedium, color = VaultGold)
                                Spacer(Modifier.height(6.dp))
                                Text(extractedText!!, style = MaterialTheme.typography.bodySmall, color = Ink, maxLines = 8)
                            }
                        }
                    }
                }
            }
        }
    }

    if (showVersions) {
        AlertDialog(
            onDismissRequest = { showVersions = false },
            title = { Text("Version history") },
            text = {
                if (versions.isEmpty()) {
                    Text("No older versions.")
                } else {
                    Column {
                        versions.forEach { v ->
                            Text(
                                "v${v.version} · ${v.title} · ${v.created_at.take(10)}",
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clickable {
                                        scope.launch {
                                            try {
                                                val dest = com.rklab.healthvault.data.local.DocumentCache.fileFor(
                                                    context, "${docId}_v${v.version}"
                                                )
                                                withContext(Dispatchers.IO) {
                                                    repository.downloadDocumentVersionFile(docId, v.id, 0, dest)
                                                }
                                                file = dest
                                                showVersions = false
                                            } catch (e: Exception) {
                                                Toast.makeText(context, e.message, Toast.LENGTH_SHORT).show()
                                            }
                                        }
                                    }
                                    .padding(vertical = 8.dp),
                                color = Navy
                            )
                        }
                    }
                }
            },
            confirmButton = {
                TextButton(onClick = { showVersions = false }) { Text("Close") }
            }
        )
    }

    if (showFamilyShare && canFamilyShare) {
        FamilyShareDialog(
            repository = repository,
            resourceType = "health_document",
            resourceId = docId,
            sharedWith = docMeta?.shared_with.orEmpty(),
            onDismiss = { showFamilyShare = false },
            onChanged = {
                scope.launch {
                    docMeta = runCatching { repository.getDocument(docId) }.getOrNull() ?: docMeta
                }
            },
        )
    }
}

@Composable
fun PdfViewer(file: File) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    
    var pdfRenderer by remember { mutableStateOf<PdfRenderer?>(null) }
    var fileDescriptor by remember { mutableStateOf<ParcelFileDescriptor?>(null) }
    var pageCount by remember { mutableStateOf(0) }

    DisposableEffect(file) {
        try {
            val fd = ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY)
            val renderer = PdfRenderer(fd)
            fileDescriptor = fd
            pdfRenderer = renderer
            pageCount = renderer.pageCount
        } catch (e: Exception) {
            Toast.makeText(context, "Cannot open PDF: ${e.message}", Toast.LENGTH_SHORT).show()
        }

        onDispose {
            pdfRenderer?.close()
            fileDescriptor?.close()
        }
    }

    if (pageCount > 0 && pdfRenderer != null) {
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            items(pageCount) { index ->
                PdfPage(pdfRenderer = pdfRenderer!!, pageIndex = index)
            }
        }
    }
}

@Composable
fun PdfPage(pdfRenderer: PdfRenderer, pageIndex: Int) {
    var bitmap by remember { mutableStateOf<Bitmap?>(null) }

    LaunchedEffect(pdfRenderer, pageIndex) {
        withContext(Dispatchers.IO) {
            val page = pdfRenderer.openPage(pageIndex)
            
            // Render at 2x resolution for sharpness on modern screens
            val renderWidth = page.width * 2
            val renderHeight = page.height * 2
            val bm = Bitmap.createBitmap(renderWidth, renderHeight, Bitmap.Config.ARGB_8888)
            
            // Fill white background before rendering PDF (which is transparent)
            bm.eraseColor(android.graphics.Color.WHITE)
            
            page.render(bm, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
            page.close()
            bitmap = bm
        }
    }

    Box(
        modifier = Modifier
            .fillMaxWidth()
            .aspectRatio(
                if (bitmap != null) bitmap!!.width.toFloat() / bitmap!!.height.toFloat()
                else 0.7f // Standard paper aspect ratio fallback
            )
            .background(Color.White),
        contentAlignment = Alignment.Center
    ) {
        if (bitmap != null) {
            Image(
                bitmap = bitmap!!.asImageBitmap(),
                contentDescription = "PDF Page $pageIndex",
                modifier = Modifier.fillMaxSize(),
                contentScale = ContentScale.Fit
            )
        } else {
            CircularProgressIndicator()
        }
    }
}
