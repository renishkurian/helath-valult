package com.rklab.healthvault.ui.screens.documents

import android.Manifest
import android.content.pm.PackageManager
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.InsertDriveFile
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import androidx.lifecycle.viewmodel.compose.viewModel
import com.rklab.healthvault.data.model.DocCategory
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.components.docCategoryColor
import com.rklab.healthvault.ui.theme.*
import com.rklab.healthvault.util.FileUtil
import com.rklab.healthvault.util.ViewModelFactory
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@Composable
fun UploadDocumentScreen(
    repository: HealthVaultRepository,
    personId: String,
    defaultCategory: DocCategory?,
    onDone: () -> Unit,
    onBack: () -> Unit
) {
    val viewModel: DocumentsViewModel = viewModel(factory = ViewModelFactory(repository))
    val state by viewModel.state.collectAsState()
    val hospitals by viewModel.hospitals.collectAsState()
    val people by viewModel.people.collectAsState()
    val context = LocalContext.current

    var selectedPersonId by remember { mutableStateOf(personId) }
    var category by remember { mutableStateOf(defaultCategory ?: DocCategory.OTHER) }
    var customCategory by remember { mutableStateOf("") }
    var title by remember { mutableStateOf("") }
    var hospitalName by remember { mutableStateOf("") }
    var docDate by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }
    var expiryDate by remember { mutableStateOf("") }
    var tags by remember { mutableStateOf("") }

    // Multi-file: list of (File, mimeType) pairs
    var pickedFiles by remember { mutableStateOf<List<Pair<File, String>>>(emptyList()) }
    // The File the camera is writing into (captureUri points here)
    var captureFile by remember { mutableStateOf<File?>(null) }
    var captureUri by remember { mutableStateOf<Uri?>(null) }
    var categoryMenuOpen by remember { mutableStateOf(false) }
    var permissionDeniedMessage by remember { mutableStateOf<String?>(null) }
    var isProcessingFile by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    // Gallery/file picker: copy URIs to cache on a background thread
    val multiFileLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenMultipleDocuments()
    ) { uris: List<Uri> ->
        if (uris.isEmpty()) return@rememberLauncherForActivityResult
        isProcessingFile = true
        scope.launch {
            val newFiles = withContext(Dispatchers.IO) {
                uris.mapNotNull { uri ->
                    val mime = FileUtil.mimeTypeOf(context, uri)
                    val file = FileUtil.copyUriToCacheFile(context, uri, "doc_${System.currentTimeMillis()}_${uri.lastPathSegment}")
                    file?.let { Pair(it, mime) }
                }
            }
            pickedFiles = pickedFiles + newFiles
            isProcessingFile = false
        }
    }

    // Camera: TakePicture writes directly into captureFile — just add it to the list
    val cameraLauncher = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { success ->
        if (success) {
            captureFile?.let { file ->
                if (file.exists() && file.length() > 0) {
                    pickedFiles = pickedFiles + Pair(file, "image/jpeg")
                }
            }
        }
        captureFile = null
        captureUri = null
    }

    fun launchCamera() {
        val file = FileUtil.newCaptureFile(context)
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
        captureFile = file
        captureUri = uri
        cameraLauncher.launch(uri)
    }

    val cameraPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) {
            permissionDeniedMessage = null
            launchCamera()
        } else {
            permissionDeniedMessage = "Camera permission is needed to take a photo."
        }
    }

    fun onCameraTapped() {
        val hasPermission = ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) ==
            PackageManager.PERMISSION_GRANTED
        if (hasPermission) { permissionDeniedMessage = null; launchCamera() }
        else cameraPermissionLauncher.launch(Manifest.permission.CAMERA)
    }

    Box(modifier = Modifier.fillMaxSize().background(Paper)) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(20.dp)
                .verticalScroll(rememberScrollState())
        ) {
            TextButton(onClick = onBack) { Text("← Back", color = Navy) }
            Text("ADD DOCUMENT", style = MaterialTheme.typography.labelMedium, color = InkSoft)
            Spacer(Modifier.height(4.dp))
            Text("Add a document", style = MaterialTheme.typography.headlineMedium, color = Ink)
            Spacer(Modifier.height(20.dp))

            // File source buttons
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                SourceButton(icon = Icons.Filled.CameraAlt, label = "Camera", modifier = Modifier.weight(1f)) { onCameraTapped() }
                SourceButton(icon = Icons.Filled.InsertDriveFile, label = "Gallery / Files", modifier = Modifier.weight(1f)) {
                    multiFileLauncher.launch(arrayOf("*/*"))
                }
            }

            if (permissionDeniedMessage != null) {
                Spacer(Modifier.height(10.dp))
                Text(permissionDeniedMessage!!, color = StampRed, style = MaterialTheme.typography.bodySmall)
            }

            // Selected files chips
            if (isProcessingFile) {
                Spacer(Modifier.height(14.dp))
                Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    CircularProgressIndicator(modifier = Modifier.size(16.dp), color = Sage, strokeWidth = 2.dp)
                    Text("Preparing files…", style = MaterialTheme.typography.labelMedium, color = Sage)
                }
            }

            if (pickedFiles.isNotEmpty()) {
                Spacer(Modifier.height(14.dp))
                Text(
                    "${pickedFiles.size} file${if (pickedFiles.size > 1) "s" else ""} selected",
                    style = MaterialTheme.typography.labelMedium.copy(fontWeight = FontWeight.SemiBold),
                    color = Sage
                )
                Spacer(Modifier.height(8.dp))
                LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    itemsIndexed(pickedFiles) { idx, (file, mime) ->
                        FileChip(
                            name = file.name.take(20),
                            mime = mime,
                            index = idx + 1,
                            onRemove = { pickedFiles = pickedFiles.toMutableList().also { it.removeAt(idx) } }
                        )
                    }
                }
            }

            Spacer(Modifier.height(18.dp))

            // Category dropdown
            Box {
                OutlinedTextField(
                    value = categoryLabel(category),
                    onValueChange = {},
                    readOnly = true,
                    label = { Text("Category") },
                    modifier = Modifier.fillMaxWidth().clickable { categoryMenuOpen = true }
                )
                DropdownMenu(expanded = categoryMenuOpen, onDismissRequest = { categoryMenuOpen = false }) {
                    DocCategory.entries.forEach { cat ->
                        DropdownMenuItem(text = { Text(categoryLabel(cat)) }, onClick = { category = cat; categoryMenuOpen = false })
                    }
                }
            }
            if (category == DocCategory.OTHER) {
                Spacer(Modifier.height(10.dp))
                OutlinedTextField(
                    value = customCategory,
                    onValueChange = { customCategory = it },
                    label = { Text("Custom folder name (Optional)") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
            }
            Spacer(Modifier.height(10.dp))
            OutlinedTextField(value = title, onValueChange = { title = it }, label = { Text("Title*") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            Spacer(Modifier.height(10.dp))

            if (people.isNotEmpty()) {
                com.rklab.healthvault.ui.components.PersonDropdownField(
                    label = "Family Member",
                    selectedPersonId = selectedPersonId,
                    onPersonSelected = { selectedPersonId = it; viewModel.setActivePerson(it) },
                    people = people,
                    modifier = Modifier.fillMaxWidth()
                )
                Spacer(Modifier.height(10.dp))
            }

            com.rklab.healthvault.ui.components.HospitalDropdownField(
                label = "Hospital / clinic (optional)",
                value = hospitalName,
                onValueChange = { hospitalName = it },
                suggestions = hospitals,
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(Modifier.height(10.dp))

            com.rklab.healthvault.ui.components.DatePickerField(
                label = "Date (optional)",
                value = docDate,
                onValueChange = { docDate = it },
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(Modifier.height(10.dp))
            com.rklab.healthvault.ui.components.DatePickerField(
                label = "Expiry date (optional — insurance, prescription validity etc.)",
                value = expiryDate,
                onValueChange = { expiryDate = it },
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(Modifier.height(10.dp))
            OutlinedTextField(
                value = tags,
                onValueChange = { tags = it },
                label = { Text("Tags (optional, comma-separated)") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(Modifier.height(10.dp))
            OutlinedTextField(value = notes, onValueChange = { notes = it }, label = { Text("Notes (optional, stored encrypted)") }, modifier = Modifier.fillMaxWidth())

            if (state.error != null) {
                Spacer(Modifier.height(10.dp))
                Text(state.error!!, color = StampRed, style = MaterialTheme.typography.bodySmall)
            }

            Spacer(Modifier.height(20.dp))
            Button(
                onClick = {
                    if (pickedFiles.isEmpty()) return@Button
                    viewModel.upload(
                        personId = selectedPersonId,
                        category = category,
                        customCategory = customCategory.ifBlank { null },
                        title = title.ifBlank { pickedFiles.firstOrNull()?.first?.name ?: "Document" },
                        hospitalName = hospitalName.ifBlank { null },
                        docDate = docDate.ifBlank { null },
                        notes = notes.ifBlank { null },
                        files = pickedFiles.map { it.first },
                        mimeTypes = pickedFiles.map { it.second },
                        reloadCategory = null,
                        onDone = onDone,
                        expiryDate = expiryDate.ifBlank { null },
                        tags = tags.ifBlank { null }
                    )
                },
                enabled = pickedFiles.isNotEmpty() && !state.uploading,
                modifier = Modifier.fillMaxWidth().height(52.dp),
                shape = RoundedCornerShape(14.dp),
                colors = ButtonDefaults.buttonColors(containerColor = docCategoryColor(category))
            ) {
                if (state.uploading) {
                    CircularProgressIndicator(modifier = Modifier.size(20.dp), color = White, strokeWidth = 2.dp)
                    Spacer(Modifier.width(8.dp))
                }
                Text(
                    if (state.uploading) "Uploading ${pickedFiles.size} file${if (pickedFiles.size > 1) "s" else ""}…"
                    else "Save document (${pickedFiles.size} file${if (pickedFiles.size > 1) "s" else ""})",
                    color = White,
                    fontWeight = FontWeight.SemiBold
                )
            }
            Spacer(Modifier.height(40.dp))
        }
    }
}

@Composable
private fun FileChip(name: String, mime: String, index: Int, onRemove: () -> Unit) {
    val isPdf = mime.contains("pdf", ignoreCase = true)
    val isImage = mime.startsWith("image/")
    val icon = when {
        isPdf -> "PDF"
        isImage -> "IMG"
        else -> "DOC"
    }
    Row(
        modifier = Modifier
            .clip(RoundedCornerShape(10.dp))
            .background(SageBg)
            .border(1.dp, Sage.copy(alpha = 0.4f), RoundedCornerShape(10.dp))
            .padding(horizontal = 10.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp)
    ) {
        Box(
            modifier = Modifier.size(28.dp).clip(RoundedCornerShape(6.dp)).background(Sage.copy(alpha = 0.2f)),
            contentAlignment = Alignment.Center
        ) {
            Text(icon, style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.Bold, fontSize = 8.sp), color = Sage)
        }
        Column {
            Text("#$index", style = MaterialTheme.typography.labelSmall, color = InkSoft)
            Text(name, style = MaterialTheme.typography.labelMedium.copy(fontWeight = FontWeight.Medium), color = Ink, maxLines = 1)
        }
        Spacer(Modifier.width(2.dp))
        Box(
            modifier = Modifier.size(18.dp).clip(CircleShape).background(Color(0x22FF4444)).clickable { onRemove() },
            contentAlignment = Alignment.Center
        ) {
            Icon(Icons.Filled.Close, contentDescription = "Remove", tint = StampRed, modifier = Modifier.size(12.dp))
        }
    }
}

@Composable
private fun SourceButton(icon: androidx.compose.ui.graphics.vector.ImageVector, label: String, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Column(
        modifier = modifier
            .clip(RoundedCornerShape(14.dp))
            .background(White)
            .clickable(onClick = onClick)
            .padding(vertical = 18.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Icon(icon, contentDescription = label, tint = Navy)
        Spacer(Modifier.height(6.dp))
        Text(label, style = MaterialTheme.typography.bodySmall, color = Ink)
    }
}

private fun categoryLabel(cat: DocCategory): String =
    cat.name.lowercase().split("_").joinToString(" ") { it.replaceFirstChar(Char::uppercase) }
