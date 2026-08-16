package com.rklab.healthvault.ui.screens.locker

import android.content.Intent
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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Apps
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.DocumentScanner
import androidx.compose.material.icons.filled.InsertDriveFile
import androidx.compose.material.icons.filled.PhotoLibrary
import androidx.compose.material.icons.filled.PictureAsPdf
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import com.rklab.healthvault.data.model.LockerFileOut
import com.rklab.healthvault.data.model.LockerItemOut
import com.rklab.healthvault.data.model.LockerTypeOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.theme.*
import com.rklab.healthvault.util.DocumentScannerHelper
import com.rklab.healthvault.util.FileUtil
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

val LOCKER_TYPES = listOf(
    "aadhaar" to "Aadhaar",
    "pan" to "PAN",
    "passport" to "Passport",
    "driving_license" to "Licence",
    "voter_id" to "Voter ID",
    "certificate" to "Certificate",
    "rc" to "RC",
    "insurance" to "Insurance",
    "warranty" to "Warranty",
    "property" to "Property",
    "other" to "Other"
)

private fun typeColor(id: String): Color = when (id) {
    "aadhaar" -> CatHospitalCard
    "pan" -> Mustard
    "passport" -> PurpleAccent
    "driving_license" -> Sage
    "voter_id" -> Color(0xFF22D3EE)
    "certificate" -> StampRed
    "rc" -> Color(0xFFF97316)
    "insurance" -> Mustard
    "warranty" -> Sage
    "property" -> BlueAccent
    else -> TextGray
}

@Composable
fun LockerListScreen(
    repository: HealthVaultRepository,
    onOpenItem: (String) -> Unit,
    onAdd: (String?) -> Unit,
    onScan: (String?) -> Unit = onAdd,
    onOpenModules: () -> Unit,
    expiringOnly: Boolean = false
) {
    val scope = rememberCoroutineScope()
    var query by remember { mutableStateOf("") }
    var type by remember { mutableStateOf<String?>(null) }
    var items by remember { mutableStateOf<List<LockerItemOut>>(emptyList()) }
    var types by remember { mutableStateOf<List<LockerTypeOut>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }

    fun reload() {
        scope.launch {
            loading = true
            error = null
            runCatching {
                types = repository.listLockerTypes()
                items = repository.listLockerItems(type, query.ifBlank { null }, expiringOnly)
            }.onFailure { error = it.message ?: "Could not load locker" }
            loading = false
        }
    }
    LaunchedEffect(query, type, expiringOnly) { reload() }

    Box(Modifier.fillMaxSize().background(HubBg)) {
        Column(Modifier.fillMaxSize()) {
            Row(
                Modifier.fillMaxWidth().padding(20.dp, 16.dp, 8.dp, 0.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text("DOCUMENT VAULT", style = MaterialTheme.typography.labelMedium, color = VaultTeal)
                    Text(
                        if (expiringOnly) "Expiring" else "Locker",
                        style = MaterialTheme.typography.headlineMedium,
                        color = Ink,
                        fontWeight = FontWeight.Bold
                    )
                    if (!expiringOnly) {
                        Text(
                            "Scan IDs & papers · saved on phone + encrypted vault",
                            color = InkSoft,
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                }
                IconButton(onClick = onOpenModules) {
                    Icon(Icons.Filled.Apps, contentDescription = "Modules", tint = InkSoft)
                }
            }
            OutlinedTextField(
                value = query,
                onValueChange = { query = it },
                placeholder = { Text("Search locker") },
                leadingIcon = { Icon(Icons.Filled.Search, null) },
                singleLine = true,
                shape = RoundedCornerShape(16.dp),
                modifier = Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 8.dp)
            )
            LazyRow(
                contentPadding = PaddingValues(horizontal = 20.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                item {
                    FilterChip(selected = type == null, onClick = { type = null }, label = { Text("All") })
                }
                items(types) { t ->
                    FilterChip(
                        selected = type == t.id,
                        onClick = { type = if (type == t.id) null else t.id },
                        label = { Text("${t.label} ${t.count}") }
                    )
                }
            }
            when {
                loading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = Navy)
                }
                error != null -> Text(error!!, color = StampRed, modifier = Modifier.padding(20.dp))
                items.isEmpty() -> Text(
                    "No documents yet. Tap Scan to capture Aadhaar, PAN, RC…",
                    color = InkSoft,
                    modifier = Modifier.padding(20.dp)
                )
                else -> LazyColumn(
                    contentPadding = PaddingValues(20.dp, 12.dp, 20.dp, 88.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    items(items, key = { it.id }) { item ->
                        Surface(
                            shape = RoundedCornerShape(16.dp),
                            color = HubGlass,
                            modifier = Modifier.fillMaxWidth().clickable { onOpenItem(item.id) }
                        ) {
                            Row(
                                Modifier.padding(14.dp),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(12.dp)
                            ) {
                                Box(
                                    Modifier.size(40.dp).clip(RoundedCornerShape(10.dp)).background(typeColor(item.doc_type)),
                                    contentAlignment = Alignment.Center
                                ) {
                                    Text(
                                        item.type_label.take(3).uppercase(),
                                        color = Color.White,
                                        style = MaterialTheme.typography.labelSmall,
                                        fontWeight = FontWeight.Bold
                                    )
                                }
                                Column(Modifier.weight(1f)) {
                                    Text(item.title, color = Ink, fontWeight = FontWeight.SemiBold)
                                    Text(
                                        listOfNotNull(item.type_label, item.holder_name, item.expiry_date).joinToString(" · "),
                                        color = InkSoft,
                                        style = MaterialTheme.typography.bodySmall
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }
        Column(
            modifier = Modifier.align(Alignment.BottomEnd).padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
            horizontalAlignment = Alignment.End
        ) {
            if (!expiringOnly) {
                ExtendedFloatingActionButton(
                    onClick = { onScan(type) },
                    containerColor = VaultTeal,
                    contentColor = TextDark,
                    icon = { Icon(Icons.Filled.DocumentScanner, contentDescription = null) },
                    text = { Text("Scan", fontWeight = FontWeight.SemiBold) }
                )
            }
            FloatingActionButton(
                onClick = { onAdd(type) },
                containerColor = CardSurfaceRaised,
                contentColor = Ink
            ) {
                Icon(Icons.Filled.Add, contentDescription = "Add file")
            }
        }
    }
}

@Composable
fun LockerAddScreen(
    repository: HealthVaultRepository,
    defaultType: String?,
    startWithScanner: Boolean = false,
    onDone: () -> Unit,
    onBack: () -> Unit
) {
    val context = LocalContext.current
    val activity = context as? android.app.Activity
    val scope = rememberCoroutineScope()
    var docType by remember { mutableStateOf(defaultType ?: "aadhaar") }
    var customType by remember { mutableStateOf("") }
    var title by remember { mutableStateOf("") }
    var holder by remember { mutableStateOf("") }
    var issuer by remember { mutableStateOf("") }
    var idNumber by remember { mutableStateOf("") }
    var expiry by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }
    var picked by remember { mutableStateOf<List<Pair<File, String>>>(emptyList()) }
    var preferPdf by remember { mutableStateOf(true) }
    var pageCount by remember { mutableStateOf(0) }
    var saving by remember { mutableStateOf(false) }
    var scannerBusy by remember { mutableStateOf(false) }
    var captureFile by remember { mutableStateOf<File?>(null) }

    fun applyFiles(files: List<Pair<File, String>>, pages: Int = files.size) {
        picked = files
        pageCount = pages
        if (title.isBlank() && files.isNotEmpty()) {
            title = "Scan ${java.text.SimpleDateFormat("dd MMM yyyy", java.util.Locale.getDefault()).format(java.util.Date())}"
        }
    }

    val picker = rememberLauncherForActivityResult(ActivityResultContracts.GetMultipleContents()) { uris: List<Uri> ->
        val mapped = uris.mapIndexed { idx, uri ->
            FileUtil.copyUriToCacheFile(context, uri, "locker_${System.currentTimeMillis()}_$idx") to FileUtil.mimeTypeOf(context, uri)
        }
        applyFiles(mapped)
    }

    val takePicture = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { ok ->
        val file = captureFile
        if (ok && file != null && file.exists()) {
            val enhanced = FileUtil.enhanceImageFile(file)
            applyFiles(picked + (enhanced to "image/jpeg"))
        }
    }

    val scannerLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.StartIntentSenderForResult()
    ) { result ->
        scannerBusy = false
        if (result.resultCode != android.app.Activity.RESULT_OK) return@rememberLauncherForActivityResult
        val scan = DocumentScannerHelper.parseResult(context, result.data)
        if (scan == null) {
            Toast.makeText(context, "No pages captured", Toast.LENGTH_SHORT).show()
            return@rememberLauncherForActivityResult
        }
        applyFiles(
            DocumentScannerHelper.filesForUpload(context, scan, preferPdf = preferPdf),
            pages = scan.pageCount
        )
        Toast.makeText(
            context,
            if (preferPdf) "Ready as PDF (${scan.pageCount} page${if (scan.pageCount == 1) "" else "s"})"
            else "${scan.pageCount} page(s) ready",
            Toast.LENGTH_SHORT
        ).show()
    }

    fun launchScanner() {
        val act = activity
        if (act == null) {
            Toast.makeText(context, "Scanner needs the app activity", Toast.LENGTH_SHORT).show()
            return
        }
        scannerBusy = true
        DocumentScannerHelper.start(
            activity = act,
            launcher = scannerLauncher,
            onError = { msg ->
                scannerBusy = false
                Toast.makeText(context, msg, Toast.LENGTH_LONG).show()
            }
        )
    }

    fun launchCamera() {
        val file = FileUtil.newCaptureFile(context)
        captureFile = file
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
        takePicture.launch(uri)
    }

    LaunchedEffect(Unit) {
        if (startWithScanner) launchScanner()
    }

    Column(Modifier.fillMaxSize().background(HubBg).verticalScroll(rememberScrollState()).padding(20.dp)) {
        TextButton(onClick = onBack) { Text("← Locker", color = VaultTeal) }
        Text("Add to Document Vault", style = MaterialTheme.typography.headlineMedium, color = Ink, fontWeight = FontWeight.Bold)
        Text(
            "Scan like Adobe Scan — edges, crop, filters, multi-page — then save on this phone and upload encrypted to your vault.",
            color = InkSoft,
            style = MaterialTheme.typography.bodySmall,
            modifier = Modifier.padding(top = 6.dp, bottom = 16.dp)
        )

        Text("Capture", style = MaterialTheme.typography.labelLarge, color = InkSoft)
        Spacer(Modifier.height(8.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            Button(
                onClick = { launchScanner() },
                enabled = !scannerBusy,
                modifier = Modifier.weight(1f),
                colors = ButtonDefaults.buttonColors(containerColor = VaultTeal, contentColor = TextDark)
            ) {
                Icon(Icons.Filled.DocumentScanner, null, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(6.dp))
                Text(if (scannerBusy) "Opening…" else "Scan")
            }
            OutlinedButton(onClick = { launchCamera() }, modifier = Modifier.weight(1f)) {
                Icon(Icons.Filled.CameraAlt, null, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(6.dp))
                Text("Camera")
            }
        }
        Spacer(Modifier.height(8.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            OutlinedButton(onClick = { picker.launch("image/*") }, modifier = Modifier.weight(1f)) {
                Icon(Icons.Filled.PhotoLibrary, null, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(6.dp))
                Text("Gallery")
            }
            OutlinedButton(onClick = { picker.launch("application/pdf") }, modifier = Modifier.weight(1f)) {
                Icon(Icons.Filled.PictureAsPdf, null, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(6.dp))
                Text("PDF file")
            }
        }

        Spacer(Modifier.height(12.dp))
        Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(HubGlass).padding(14.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(Modifier.weight(1f)) {
                Text("Save as PDF", fontWeight = FontWeight.SemiBold, color = Ink)
                Text("Merge scanned pages into one PDF for the vault", color = InkSoft, style = MaterialTheme.typography.bodySmall)
            }
            Switch(
                checked = preferPdf,
                onCheckedChange = { preferPdf = it },
                colors = SwitchDefaults.colors(checkedTrackColor = VaultTeal, checkedThumbColor = TextDark)
            )
        }
        if (picked.isNotEmpty()) {
            Text(
                buildString {
                    append("${picked.size} file(s) ready")
                    if (pageCount > 0) append(" · $pageCount page(s)")
                    if (picked.any { it.second.contains("pdf") }) append(" · PDF")
                },
                color = VaultTeal,
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.padding(top = 8.dp)
            )
            if (picked.count { it.second.startsWith("image/") } >= 2) {
                TextButton(
                    onClick = {
                        val images = picked.filter { it.second.startsWith("image/") }.map { it.first }
                        val pdf = FileUtil.mergeImagesToPdf(context, images)
                        applyFiles(listOf(pdf to "application/pdf"), pages = images.size)
                        preferPdf = true
                    }
                ) { Text("Convert images → single PDF", color = VaultTeal) }
            }
        }

        Spacer(Modifier.height(16.dp))
        LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            items(LOCKER_TYPES) { (id, label) ->
                FilterChip(selected = docType == id, onClick = { docType = id }, label = { Text(label) })
            }
        }
        if (docType == "other") {
            Spacer(Modifier.height(8.dp))
            OutlinedTextField(customType, { customType = it }, label = { Text("Custom type") }, modifier = Modifier.fillMaxWidth())
        }
        Spacer(Modifier.height(12.dp))
        OutlinedTextField(title, { title = it }, label = { Text("Title") }, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(holder, { holder = it }, label = { Text("Holder") }, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(issuer, { issuer = it }, label = { Text("Issuer") }, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(idNumber, { idNumber = it }, label = { Text("ID / number") }, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(expiry, { expiry = it }, label = { Text("Expiry (YYYY-MM-DD)") }, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(notes, { notes = it }, label = { Text("Notes") }, modifier = Modifier.fillMaxWidth(), minLines = 2)
        Spacer(Modifier.height(20.dp))
        Button(
            onClick = {
                if (title.isBlank() || picked.isEmpty()) {
                    Toast.makeText(context, "Title and at least one scan/file are required", Toast.LENGTH_SHORT).show()
                    return@Button
                }
                saving = true
                scope.launch {
                    runCatching {
                        withContext(Dispatchers.IO) {
                            FileUtil.archiveLockerScan(
                                context,
                                title.trim(),
                                picked.map { it.first },
                                picked.map { it.second }
                            )
                        }
                        repository.createLockerItem(
                            title = title.trim(),
                            docType = docType,
                            customType = customType.ifBlank { null },
                            holderName = holder.ifBlank { null },
                            issuer = issuer.ifBlank { null },
                            idNumber = idNumber.ifBlank { null },
                            issuedOn = null,
                            expiryDate = expiry.ifBlank { null },
                            tags = "scanned",
                            notes = notes.ifBlank { null },
                            files = picked.map { it.first },
                            mimeTypes = picked.map { it.second }
                        )
                    }.onSuccess {
                        Toast.makeText(context, "Saved on device and Document Vault", Toast.LENGTH_SHORT).show()
                        onDone()
                    }.onFailure {
                        Toast.makeText(context, it.message ?: "Upload failed", Toast.LENGTH_LONG).show()
                    }
                    saving = false
                }
            },
            enabled = !saving,
            modifier = Modifier.fillMaxWidth().height(52.dp),
            shape = RoundedCornerShape(16.dp),
            colors = ButtonDefaults.buttonColors(containerColor = VaultTeal, contentColor = TextDark)
        ) {
            Text(if (saving) "Saving…" else "Save to phone + vault", fontWeight = FontWeight.SemiBold)
        }
        Spacer(Modifier.height(24.dp))
    }
}

@Composable
fun LockerItemScreen(
    repository: HealthVaultRepository,
    itemId: String,
    onBack: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var item by remember { mutableStateOf<LockerItemOut?>(null) }
    var files by remember { mutableStateOf<List<LockerFileOut>>(emptyList()) }
    var error by remember { mutableStateOf<String?>(null) }

    fun reload() {
        scope.launch {
            runCatching {
                item = repository.getLockerItem(itemId)
                files = repository.listLockerFiles(itemId)
            }.onFailure { error = it.message }
        }
    }
    LaunchedEffect(itemId) { reload() }

    fun openFile(fileId: String?, name: String, mime: String?) {
        scope.launch {
            try {
                val dest = File(context.cacheDir.resolve("locker").apply { mkdirs() }, name.ifBlank { "file" })
                withContext(Dispatchers.IO) {
                    if (fileId != null) repository.downloadLockerFile(itemId, fileId, dest)
                    else repository.downloadLockerItem(itemId, dest)
                }
                val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", dest)
                context.startActivity(Intent(Intent.ACTION_VIEW).apply {
                    setDataAndType(uri, mime ?: "*/*")
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                })
            } catch (e: Exception) {
                Toast.makeText(context, e.message ?: "Could not open file", Toast.LENGTH_SHORT).show()
            }
        }
    }

    Column(Modifier.fillMaxSize().background(HubBg).padding(20.dp)) {
        TextButton(onClick = onBack) { Text("← Locker", color = Navy) }
        val current = item
        if (error != null) Text(error!!, color = StampRed)
        else if (current == null) Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            CircularProgressIndicator(color = Navy)
        } else {
            Text(current.type_label.uppercase(), style = MaterialTheme.typography.labelMedium, color = InkSoft)
            Text(current.title, style = MaterialTheme.typography.headlineMedium, color = Ink, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(8.dp))
            current.holder_name?.let { Text("Holder  $it", color = Ink) }
            current.issuer?.let { Text("Issuer  $it", color = InkSoft) }
            current.id_number?.let { Text("ID  $it", color = Ink) }
            current.expiry_date?.let { Text("Expires  $it", color = InkSoft) }
            current.notes?.let { Text(it, color = InkSoft, modifier = Modifier.padding(top = 8.dp)) }
            Spacer(Modifier.height(16.dp))
            Text("Files", fontWeight = FontWeight.SemiBold, color = Ink)
            files.forEach { f ->
                Surface(
                    shape = RoundedCornerShape(14.dp),
                    color = HubGlass,
                    modifier = Modifier.fillMaxWidth().padding(top = 8.dp).clickable {
                        openFile(f.id, f.original_filename, f.file_type)
                    }
                ) {
                    Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Filled.InsertDriveFile, null, tint = Navy)
                        Spacer(Modifier.width(10.dp))
                        Column {
                            Text(f.original_filename, color = Ink, fontWeight = FontWeight.Medium)
                            Text(f.file_type ?: "file", color = InkSoft, style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
            }
            Spacer(Modifier.height(24.dp))
            OutlinedButton(
                onClick = {
                    scope.launch {
                        runCatching { repository.deleteLockerItem(itemId) }
                            .onSuccess { onBack() }
                            .onFailure { Toast.makeText(context, it.message, Toast.LENGTH_SHORT).show() }
                    }
                },
                colors = ButtonDefaults.outlinedButtonColors(contentColor = StampRed)
            ) { Text("Delete document") }
        }
    }
}
