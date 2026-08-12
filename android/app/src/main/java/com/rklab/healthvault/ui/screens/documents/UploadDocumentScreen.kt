package com.rklab.healthvault.ui.screens.documents
import androidx.compose.foundation.clickable
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.rememberScrollState
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.InsertDriveFile
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
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.components.docCategoryColor
import com.rklab.healthvault.ui.theme.*
import com.rklab.healthvault.util.FileUtil
import com.rklab.healthvault.util.ViewModelFactory
import java.io.File

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
    val context = LocalContext.current

    var category by remember { mutableStateOf(defaultCategory ?: DocCategory.OTHER) }
    var title by remember { mutableStateOf("") }
    var hospitalName by remember { mutableStateOf("") }
    var docDate by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }
    var pickedFile by remember { mutableStateOf<File?>(null) }
    var pickedMime by remember { mutableStateOf("application/octet-stream") }
    var captureUri by remember { mutableStateOf<Uri?>(null) }
    var categoryMenuOpen by remember { mutableStateOf(false) }

    val galleryLauncher = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri: Uri? ->
        uri ?: return@rememberLauncherForActivityResult
        pickedMime = FileUtil.mimeTypeOf(context, uri)
        pickedFile = FileUtil.copyUriToCacheFile(context, uri, "doc_${System.currentTimeMillis()}")
    }

    val cameraLauncher = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { success ->
        if (success && captureUri != null) {
            pickedMime = "image/jpeg"
            pickedFile = captureUri?.let { uri ->
                val dest = FileUtil.newCaptureFile(context)
                context.contentResolver.openInputStream(uri)?.use { input ->
                    dest.outputStream().use { output -> input.copyTo(output) }
                }
                dest
            }
        }
    }

    Box(modifier = Modifier.fillMaxSize().background(Paper)) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(20.dp)
                .verticalScrollWorkaround()
        ) {
            TextButton(onClick = onBack) { Text("← Back", color = Navy) }
            Text("ADD DOCUMENT", style = MaterialTheme.typography.labelMedium, color = InkSoft)
            Spacer(Modifier.height(4.dp))
            Text("Add a document", style = MaterialTheme.typography.headlineMedium, color = Ink)
            Spacer(Modifier.height(20.dp))

            // File source
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                SourceButton(
                    icon = Icons.Filled.CameraAlt,
                    label = "Camera",
                    modifier = Modifier.weight(1f)
                ) {
                    val file = FileUtil.newCaptureFile(context)
                    val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
                    captureUri = uri
                    cameraLauncher.launch(uri)
                }
                SourceButton(
                    icon = Icons.Filled.InsertDriveFile,
                    label = "Gallery / Files",
                    modifier = Modifier.weight(1f)
                ) { galleryLauncher.launch("*/*") }
            }

            if (pickedFile != null) {
                Spacer(Modifier.height(10.dp))
                Text("Selected: ${pickedFile!!.name}", style = MaterialTheme.typography.bodySmall, color = Sage)
            }

            Spacer(Modifier.height(18.dp))

            Box {
                OutlinedTextField(
                    value = categoryLabel(category),
                    onValueChange = {},
                    readOnly = true,
                    label = { Text("Category") },
                    modifier = Modifier.fillMaxWidth().clickableOpen { categoryMenuOpen = true }
                )
                DropdownMenu(expanded = categoryMenuOpen, onDismissRequest = { categoryMenuOpen = false }) {
                    DocCategory.entries.forEach { cat ->
                        DropdownMenuItem(text = { Text(categoryLabel(cat)) }, onClick = { category = cat; categoryMenuOpen = false })
                    }
                }
            }
            Spacer(Modifier.height(10.dp))
            OutlinedTextField(value = title, onValueChange = { title = it }, label = { Text("Title*") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            Spacer(Modifier.height(10.dp))
            OutlinedTextField(value = hospitalName, onValueChange = { hospitalName = it }, label = { Text("Hospital / clinic (optional)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            Spacer(Modifier.height(10.dp))
            OutlinedTextField(value = docDate, onValueChange = { docDate = it }, label = { Text("Date (YYYY-MM-DD, optional)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            Spacer(Modifier.height(10.dp))
            OutlinedTextField(value = notes, onValueChange = { notes = it }, label = { Text("Notes (optional, stored encrypted)") }, modifier = Modifier.fillMaxWidth())

            if (state.error != null) {
                Spacer(Modifier.height(10.dp))
                Text(state.error!!, color = StampRed, style = MaterialTheme.typography.bodySmall)
            }

            Spacer(Modifier.height(20.dp))
            Button(
                onClick = {
                    val file = pickedFile ?: return@Button
                    viewModel.upload(
                        personId, category, title.ifBlank { file.name }, hospitalName.ifBlank { null },
                        docDate.ifBlank { null }, notes.ifBlank { null }, file, pickedMime, null, onDone
                    )
                },
                enabled = pickedFile != null && !state.uploading,
                modifier = Modifier.fillMaxWidth().height(48.dp),
                colors = ButtonDefaults.buttonColors(containerColor = docCategoryColor(category))
            ) {
                Text(if (state.uploading) "Uploading…" else "Save document", color = White)
            }
            Spacer(Modifier.height(40.dp))
        }
    }
}

@Composable
private fun SourceButton(icon: androidx.compose.ui.graphics.vector.ImageVector, label: String, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Column(
        modifier = modifier
            .clip(RoundedCornerShape(14.dp))
            .background(White)
            .clickableOpen(onClick)
            .padding(vertical = 18.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Icon(icon, contentDescription = label, tint = Navy)
        Spacer(Modifier.height(6.dp))
        Text(label, style = MaterialTheme.typography.bodySmall, color = Ink)
    }
}

private fun categoryLabel(cat: DocCategory): String = cat.name.lowercase().split("_").joinToString(" ") { it.replaceFirstChar(Char::uppercase) }

@Composable
private fun Modifier.clickableOpen(onClick: () -> Unit): Modifier = this.clickable(onClick = onClick)

private fun Modifier.verticalScrollWorkaround(): Modifier =
    this.verticalScroll(rememberScrollState())
