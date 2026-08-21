package com.rklab.healthvault.ui.screens.locker

import android.content.Intent
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
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Apps
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.CreateNewFolder
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.DocumentScanner
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.Folder
import androidx.compose.material.icons.filled.Group
import androidx.compose.material.icons.filled.InsertDriveFile
import androidx.compose.material.icons.filled.PhotoLibrary
import androidx.compose.material.icons.filled.PictureAsPdf
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Share
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import coil.compose.AsyncImage
import com.rklab.healthvault.data.model.LockerFileOut
import com.rklab.healthvault.data.model.LockerFolderOut
import com.rklab.healthvault.data.model.LockerItemOut
import com.rklab.healthvault.data.model.LockerItemUpdate
import com.rklab.healthvault.data.model.LockerPersonOut
import com.rklab.healthvault.data.model.LockerTypeOut
import com.rklab.healthvault.data.model.PersonOut
import com.rklab.healthvault.data.model.VaultSendCreate
import com.rklab.healthvault.data.model.VaultSendOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.components.FamilyShareBadge
import com.rklab.healthvault.ui.components.FamilyShareDialog
import com.rklab.healthvault.ui.components.vaultFieldColors
import com.rklab.healthvault.ui.screens.passwords.generateAccessCode
import com.rklab.healthvault.ui.theme.*
import com.rklab.healthvault.util.ClipboardUtil
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

private fun niceName(value: String?): String {
    if (value.isNullOrBlank()) return ""
    return value.trim().split(Regex("\\s+")).joinToString(" ") { part ->
        part.replaceFirstChar { if (it.isLowerCase()) it.titlecase() else it.toString() }
    }
}

private fun relationLabel(rel: String?): String = when (rel?.lowercase()) {
    "self" -> "You"
    "spouse" -> "Spouse"
    "child" -> "Child"
    "parent" -> "Parent"
    else -> niceName(rel ?: "Other")
}

@Composable
fun LockerListScreen(
    repository: HealthVaultRepository,
    onOpenItem: (String) -> Unit,
    onAdd: (docType: String?, folderId: String?, personId: String?) -> Unit,
    onScan: (docType: String?, folderId: String?, personId: String?) -> Unit = onAdd,
    onOpenModules: () -> Unit,
    expiringOnly: Boolean = false
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var query by remember { mutableStateOf("") }
    var type by remember { mutableStateOf<String?>(null) }
    var folderId by remember { mutableStateOf<String?>(null) }
    var personId by remember { mutableStateOf<String?>(null) }
    var items by remember { mutableStateOf<List<LockerItemOut>>(emptyList()) }
    var types by remember { mutableStateOf<List<LockerTypeOut>>(emptyList()) }
    var folders by remember { mutableStateOf<List<LockerFolderOut>>(emptyList()) }
    var people by remember { mutableStateOf<List<LockerPersonOut>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var showNewFolder by remember { mutableStateOf(false) }
    var newFolderName by remember { mutableStateOf("") }

    fun reload() {
        scope.launch {
            loading = true
            error = null
            runCatching {
                val summary = repository.lockerSummary()
                types = summary.types.filter { !it.custom }
                folders = summary.folders
                people = summary.people
                items = repository.listLockerItems(
                    docType = type,
                    folderId = folderId,
                    personId = personId,
                    q = query.ifBlank { null },
                    expiring = expiringOnly
                )
            }.onFailure { error = it.message ?: "Could not load locker" }
            loading = false
        }
    }
    LaunchedEffect(query, type, folderId, personId, expiringOnly) { reload() }

    if (showNewFolder) {
        AlertDialog(
            onDismissRequest = { showNewFolder = false },
            title = { Text("Create folder") },
            text = {
                OutlinedTextField(
                    value = newFolderName,
                    onValueChange = { newFolderName = it },
                    label = { Text("Folder name") },
                    placeholder = { Text("Gas book, School papers…") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        val name = newFolderName.trim()
                        if (name.isBlank()) return@TextButton
                        scope.launch {
                            runCatching { repository.createLockerFolder(niceName(name)) }
                                .onSuccess {
                                    showNewFolder = false
                                    newFolderName = ""
                                    folderId = it.id
                                    type = null
                                    Toast.makeText(context, "Folder created", Toast.LENGTH_SHORT).show()
                                    reload()
                                }
                                .onFailure {
                                    Toast.makeText(context, it.message ?: "Could not create folder", Toast.LENGTH_LONG).show()
                                }
                        }
                    }
                ) { Text("Create") }
            },
            dismissButton = { TextButton(onClick = { showNewFolder = false }) { Text("Cancel") } }
        )
    }

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
                            "Scan IDs & papers · folders · family profiles",
                            color = InkSoft,
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                }
                Row {
                    if (!expiringOnly) {
                        IconButton(onClick = { showNewFolder = true; newFolderName = "" }) {
                            Icon(Icons.Filled.CreateNewFolder, contentDescription = "New folder", tint = VaultTeal)
                        }
                    }
                    IconButton(onClick = onOpenModules) {
                        Icon(Icons.Filled.Apps, contentDescription = "Modules", tint = InkSoft)
                    }
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
            if (!expiringOnly) {
                LazyRow(
                    contentPadding = PaddingValues(horizontal = 20.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    modifier = Modifier.padding(bottom = 8.dp)
                ) {
                    item {
                        FilterChip(
                            selected = personId == null,
                            onClick = { personId = null },
                            label = { Text("All people") },
                            leadingIcon = if (personId == null) {
                                { Icon(Icons.Filled.Apps, null, Modifier.size(16.dp)) }
                            } else null
                        )
                    }
                    item {
                        FilterChip(
                            selected = personId == "none",
                            onClick = { personId = if (personId == "none") null else "none" },
                            label = { Text("Unassigned") }
                        )
                    }
                    items(people) { p ->
                        FilterChip(
                            selected = personId == p.id,
                            onClick = { personId = if (personId == p.id) null else p.id },
                            label = {
                                Text("${niceName(p.name)} · ${p.count}")
                            },
                            leadingIcon = {
                                Text(
                                    (p.avatar_initials ?: p.name.take(1)).uppercase(),
                                    style = MaterialTheme.typography.labelSmall,
                                    color = if (personId == p.id) VaultTeal else InkSoft
                                )
                            }
                        )
                    }
                }
            }
            Text(
                "Types & folders",
                style = MaterialTheme.typography.labelMedium,
                color = InkSoft,
                modifier = Modifier.padding(horizontal = 20.dp, vertical = 4.dp)
            )
            LazyRow(
                contentPadding = PaddingValues(horizontal = 20.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                item {
                    FilterChip(
                        selected = type == null && folderId == null,
                        onClick = { type = null; folderId = null },
                        label = { Text("All") }
                    )
                }
                items(types) { t ->
                    FilterChip(
                        selected = type == t.id && folderId == null,
                        onClick = {
                            folderId = null
                            type = if (type == t.id) null else t.id
                        },
                        label = { Text("${t.label} ${t.count}") }
                    )
                }
                items(folders) { f ->
                    FilterChip(
                        selected = folderId == f.id,
                        onClick = {
                            type = null
                            folderId = if (folderId == f.id) null else f.id
                        },
                        label = {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(Icons.Filled.Folder, null, Modifier.size(14.dp))
                                Spacer(Modifier.width(4.dp))
                                Text("${f.name} ${f.count}")
                            }
                        }
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
                                        listOfNotNull(
                                            item.type_label,
                                            item.folder_name,
                                            item.person_name?.let { niceName(it) },
                                            item.holder_name?.let { niceName(it) },
                                            item.expiry_date,
                                            when {
                                                item.shared_from != null -> "Shared"
                                                item.shared_with.isNotEmpty() -> "Shared with family"
                                                else -> null
                                            }
                                        ).joinToString(" · "),
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
                    onClick = { onScan(type, folderId, personId?.takeIf { it != "none" }) },
                    containerColor = VaultTeal,
                    contentColor = TextDark,
                    icon = { Icon(Icons.Filled.DocumentScanner, contentDescription = null) },
                    text = { Text("Scan", fontWeight = FontWeight.SemiBold) }
                )
            }
            FloatingActionButton(
                onClick = { onAdd(type, folderId, personId?.takeIf { it != "none" }) },
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
    defaultFolderId: String? = null,
    defaultPersonId: String? = null,
    startWithScanner: Boolean = false,
    onDone: () -> Unit,
    onBack: () -> Unit
) {
    val context = LocalContext.current
    val activity = context as? android.app.Activity
    val scope = rememberCoroutineScope()
    var docType by remember { mutableStateOf(defaultType ?: "aadhaar") }
    var customType by remember { mutableStateOf("") }
    var folderId by remember { mutableStateOf(defaultFolderId) }
    var personId by remember { mutableStateOf(defaultPersonId) }
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
    var folders by remember { mutableStateOf<List<LockerFolderOut>>(emptyList()) }
    var people by remember { mutableStateOf<List<PersonOut>>(emptyList()) }

    LaunchedEffect(Unit) {
        runCatching {
            folders = repository.listLockerFolders()
            people = repository.listPeople()
            if (holder.isBlank() && !defaultPersonId.isNullOrBlank()) {
                people.firstOrNull { it.id == defaultPersonId }?.let { holder = niceName(it.name) }
            }
        }
    }

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
                Icon(Icons.Filled.DocumentScanner, null, Modifier.size(18.dp))
                Spacer(Modifier.width(6.dp))
                Text(if (scannerBusy) "Opening…" else "Scan")
            }
            OutlinedButton(onClick = { launchCamera() }, modifier = Modifier.weight(1f)) {
                Icon(Icons.Filled.CameraAlt, null, Modifier.size(18.dp))
                Spacer(Modifier.width(6.dp))
                Text("Camera")
            }
        }
        Spacer(Modifier.height(8.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            OutlinedButton(onClick = { picker.launch("image/*") }, modifier = Modifier.weight(1f)) {
                Icon(Icons.Filled.PhotoLibrary, null, Modifier.size(18.dp))
                Spacer(Modifier.width(6.dp))
                Text("Gallery")
            }
            OutlinedButton(onClick = { picker.launch("application/pdf") }, modifier = Modifier.weight(1f)) {
                Icon(Icons.Filled.PictureAsPdf, null, Modifier.size(18.dp))
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
        if (folders.isNotEmpty()) {
            Spacer(Modifier.height(12.dp))
            Text("Folder", style = MaterialTheme.typography.labelLarge, color = InkSoft)
            Spacer(Modifier.height(6.dp))
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                item {
                    FilterChip(selected = folderId == null, onClick = { folderId = null }, label = { Text("None") })
                }
                items(folders) { f ->
                    FilterChip(
                        selected = folderId == f.id,
                        onClick = { folderId = if (folderId == f.id) null else f.id },
                        label = { Text(f.name) }
                    )
                }
            }
        }
        if (people.isNotEmpty()) {
            Spacer(Modifier.height(12.dp))
            Text("Family profile", style = MaterialTheme.typography.labelLarge, color = InkSoft)
            Spacer(Modifier.height(6.dp))
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                item {
                    FilterChip(selected = personId == null, onClick = { personId = null }, label = { Text("Unassigned") })
                }
                items(people) { p ->
                    FilterChip(
                        selected = personId == p.id,
                        onClick = {
                            personId = if (personId == p.id) null else p.id
                            if (holder.isBlank() && personId == p.id) holder = niceName(p.name)
                        },
                        label = {
                            Text("${niceName(p.name)} · ${relationLabel(p.relation.name.lowercase())}")
                        }
                    )
                }
            }
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
                            folderId = folderId,
                            personId = personId,
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
    var folders by remember { mutableStateOf<List<LockerFolderOut>>(emptyList()) }
    var people by remember { mutableStateOf<List<PersonOut>>(emptyList()) }
    var error by remember { mutableStateOf<String?>(null) }
    var editing by remember { mutableStateOf(false) }
    var saving by remember { mutableStateOf(false) }
    var previewFile by remember { mutableStateOf<File?>(null) }
    var previewMime by remember { mutableStateOf<String?>(null) }
    var previewTitle by remember { mutableStateOf("") }
    var confirmDeleteFile by remember { mutableStateOf<LockerFileOut?>(null) }
    var showShare by remember { mutableStateOf(false) }
    var showFamilyShare by remember { mutableStateOf(false) }
    var sharePin by remember { mutableStateOf("") }
    var shareHours by remember { mutableStateOf("48") }
    var shareOneTime by remember { mutableStateOf(false) }
    var shareRequireGrant by remember { mutableStateOf(false) }
    var shareEmailOtp by remember { mutableStateOf(false) }
    var shareFilesOnly by remember { mutableStateOf(false) }
    var shareAllowedEmails by remember { mutableStateOf("") }
    var shareBusy by remember { mutableStateOf(false) }
    var shareError by remember { mutableStateOf<String?>(null) }
    var shareReady by remember { mutableStateOf<String?>(null) }
    var activeSends by remember { mutableStateOf<List<VaultSendOut>>(emptyList()) }

    var title by remember { mutableStateOf("") }
    var docType by remember { mutableStateOf("other") }
    var customType by remember { mutableStateOf("") }
    var folderId by remember { mutableStateOf<String?>(null) }
    var personId by remember { mutableStateOf<String?>(null) }
    var holder by remember { mutableStateOf("") }
    var issuer by remember { mutableStateOf("") }
    var idNumber by remember { mutableStateOf("") }
    var issuedOn by remember { mutableStateOf("") }
    var expiry by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }

    fun reload() {
        scope.launch {
            runCatching {
                val loaded = repository.getLockerItem(itemId)
                item = loaded
                files = repository.listLockerFiles(itemId)
                folders = repository.listLockerFolders()
                people = repository.listPeople()
                activeSends = runCatching { repository.listLockerItemSends(itemId) }.getOrDefault(emptyList())
                title = loaded.title
                docType = loaded.doc_type
                customType = loaded.custom_type.orEmpty()
                folderId = loaded.folder_id
                personId = loaded.person_id
                holder = loaded.holder_name.orEmpty()
                issuer = loaded.issuer.orEmpty()
                idNumber = loaded.id_number.orEmpty()
                issuedOn = loaded.issued_on.orEmpty()
                expiry = loaded.expiry_date.orEmpty()
                notes = loaded.notes.orEmpty()
            }.onFailure { error = it.message }
        }
    }
    LaunchedEffect(itemId) { reload() }

    fun openPreview(file: LockerFileOut) {
        scope.launch {
            try {
                val dest = File(
                    context.cacheDir.resolve("locker").apply { mkdirs() },
                    file.original_filename.ifBlank { "preview" }
                )
                withContext(Dispatchers.IO) {
                    repository.viewLockerFile(itemId, file.id, dest)
                }
                previewMime = file.file_type
                previewTitle = file.original_filename
                previewFile = dest
            } catch (e: Exception) {
                Toast.makeText(context, e.message ?: "Could not open file", Toast.LENGTH_SHORT).show()
            }
        }
    }

    fun downloadExternal(file: LockerFileOut) {
        scope.launch {
            try {
                val dest = File(
                    context.cacheDir.resolve("locker").apply { mkdirs() },
                    file.original_filename.ifBlank { "file" }
                )
                withContext(Dispatchers.IO) {
                    repository.downloadLockerFile(itemId, file.id, dest)
                }
                val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", dest)
                context.startActivity(Intent(Intent.ACTION_VIEW).apply {
                    setDataAndType(uri, file.file_type ?: "*/*")
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                })
            } catch (e: Exception) {
                Toast.makeText(context, e.message ?: "Could not download", Toast.LENGTH_SHORT).show()
            }
        }
    }

    val addPicker = rememberLauncherForActivityResult(ActivityResultContracts.GetMultipleContents()) { uris: List<Uri> ->
        if (uris.isEmpty()) return@rememberLauncherForActivityResult
        scope.launch {
            runCatching {
                val mapped = uris.mapIndexed { idx, uri ->
                    FileUtil.copyUriToCacheFile(context, uri, "locker_add_${System.currentTimeMillis()}_$idx") to
                        FileUtil.mimeTypeOf(context, uri)
                }
                repository.addLockerFiles(itemId, mapped.map { it.first }, mapped.map { it.second })
            }.onSuccess {
                Toast.makeText(context, "Files added", Toast.LENGTH_SHORT).show()
                reload()
            }.onFailure {
                Toast.makeText(context, it.message ?: "Upload failed", Toast.LENGTH_LONG).show()
            }
        }
    }

    if (previewFile != null) {
        AlertDialog(
            onDismissRequest = { previewFile = null },
            title = { Text(previewTitle.ifBlank { "Preview" }, maxLines = 1) },
            text = {
                Box(
                    Modifier.fillMaxWidth().heightIn(min = 220.dp, max = 420.dp),
                    contentAlignment = Alignment.Center
                ) {
                    val mime = previewMime.orEmpty().lowercase()
                    when {
                        mime == "application/pdf" -> LockerPdfPreview(previewFile!!)
                        mime.startsWith("image/") || mime.isBlank() -> AsyncImage(
                            model = previewFile,
                            contentDescription = previewTitle,
                            modifier = Modifier.fillMaxWidth().fillMaxHeight(),
                            contentScale = ContentScale.Fit
                        )
                        else -> Text("Preview not available for this file type. Use Download.", color = InkSoft)
                    }
                }
            },
            confirmButton = {
                TextButton(onClick = { previewFile = null }) { Text("Close") }
            }
        )
    }

    confirmDeleteFile?.let { file ->
        AlertDialog(
            onDismissRequest = { confirmDeleteFile = null },
            title = { Text("Remove file?") },
            text = { Text("Remove ${file.original_filename} from this document?") },
            confirmButton = {
                TextButton(
                    onClick = {
                        scope.launch {
                            runCatching { repository.deleteLockerFile(itemId, file.id) }
                                .onSuccess {
                                    confirmDeleteFile = null
                                    reload()
                                }
                                .onFailure {
                                    Toast.makeText(context, it.message, Toast.LENGTH_SHORT).show()
                                }
                        }
                    },
                    colors = ButtonDefaults.textButtonColors(contentColor = StampRed)
                ) { Text("Remove") }
            },
            dismissButton = { TextButton(onClick = { confirmDeleteFile = null }) { Text("Cancel") } }
        )
    }

    if (showFamilyShare && item?.is_owned == true) {
        FamilyShareDialog(
            repository = repository,
            resourceType = "locker",
            resourceId = itemId,
            sharedWith = item?.shared_with.orEmpty(),
            onDismiss = { showFamilyShare = false },
            onChanged = { reload() },
        )
    }

    if (showShare) {
        val base = repository.getServerUrl()?.trimEnd('/') ?: ""
        val fieldColors = vaultFieldColors()
        AlertDialog(
            onDismissRequest = { if (!shareBusy) showShare = false },
            title = { Text("Share this document") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    shareReady?.let { token ->
                        val url = "$base/v/$token"
                        Text("Share link ready", color = Ink)
                        Text(url, color = VaultTeal, fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.bodySmall)
                        TextButton(onClick = { ClipboardUtil.copy(context, "Document link", url) }) {
                            Text("Copy link", color = VaultTeal)
                        }
                    } ?: run {
                        Text(
                            "Same options as Password Vault Send — PIN, grant, email OTP, one-time link.",
                            color = InkSoft,
                            style = MaterialTheme.typography.bodySmall
                        )
                        Row(
                            Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            OutlinedTextField(
                                sharePin,
                                { sharePin = it },
                                label = { Text("Access code (optional)") },
                                modifier = Modifier.weight(1f),
                                singleLine = true,
                                colors = fieldColors
                            )
                            TextButton(onClick = { sharePin = generateAccessCode() }) {
                                Text("Generate", color = VaultTeal)
                            }
                        }
                        OutlinedTextField(
                            shareHours,
                            { shareHours = it.filter(Char::isDigit) },
                            label = { Text("Expires in hours") },
                            modifier = Modifier.fillMaxWidth(),
                            singleLine = true,
                            colors = fieldColors
                        )
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Checkbox(checked = shareOneTime, onCheckedChange = { shareOneTime = it })
                            Text("One-time view", color = Ink)
                        }
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Checkbox(checked = shareRequireGrant, onCheckedChange = { shareRequireGrant = it })
                            Text("Require access request — hide until I grant", color = Ink)
                        }
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Checkbox(checked = shareEmailOtp, onCheckedChange = { shareEmailOtp = it })
                            Text("Require Email OTP to open", color = Ink)
                        }
                        if (shareEmailOtp) {
                            OutlinedTextField(
                                value = shareAllowedEmails,
                                onValueChange = { shareAllowedEmails = it },
                                label = { Text("Allowed emails (optional)") },
                                modifier = Modifier.fillMaxWidth(),
                                colors = fieldColors
                            )
                        }
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Checkbox(checked = shareFilesOnly, onCheckedChange = { shareFilesOnly = it })
                            Text("Only file view mode", color = Ink)
                        }
                        Text(
                            "Hide document details. Recipients see a print-ready file list only.",
                            color = InkSoft,
                            style = MaterialTheme.typography.bodySmall
                        )
                        shareError?.let { Text(it, color = StampRed, style = MaterialTheme.typography.bodySmall) }
                    }
                }
            },
            confirmButton = {
                if (shareReady != null) {
                    TextButton(onClick = {
                        val url = "$base/v/${shareReady}"
                        context.startActivity(Intent(Intent.ACTION_SEND).apply {
                            type = "text/plain"
                            putExtra(Intent.EXTRA_TEXT, url)
                        })
                        showShare = false
                        reload()
                    }) { Text("Share", color = VaultTeal) }
                } else {
                    TextButton(
                        enabled = !shareBusy,
                        onClick = {
                            scope.launch {
                                shareBusy = true
                                shareError = null
                                val emails = shareAllowedEmails
                                    .split(',', ';', '\n')
                                    .map { it.trim() }
                                    .filter { it.contains('@') }
                                runCatching {
                                    repository.createLockerSend(
                                        itemId,
                                        VaultSendCreate(
                                            name = item?.title ?: "Document",
                                            send_type = "locker",
                                            item_id = itemId,
                                            pin = sharePin.ifBlank { null },
                                            expires_in_hours = shareHours.toIntOrNull() ?: 48,
                                            max_views = if (shareOneTime) 1 else null,
                                            require_grant = shareRequireGrant,
                                            require_email_otp = shareEmailOtp,
                                            allowed_emails = emails,
                                            files_only = shareFilesOnly
                                        )
                                    )
                                }.onSuccess { created ->
                                    shareReady = created.token
                                    ClipboardUtil.copy(context, "Document link", "$base/v/${created.token}")
                                }.onFailure {
                                    shareError = it.message ?: "Could not create share"
                                }
                                shareBusy = false
                            }
                        }
                    ) { Text(if (shareBusy) "Creating…" else "Create share link", color = VaultTeal) }
                }
            },
            dismissButton = {
                TextButton(onClick = { if (!shareBusy) showShare = false }) {
                    Text("Close", color = InkSoft)
                }
            }
        )
    }

    Column(Modifier.fillMaxSize().background(HubBg).verticalScroll(rememberScrollState()).padding(20.dp)) {
        TextButton(onClick = onBack) { Text("← Locker", color = Navy) }
        val current = item
        if (error != null) Text(error!!, color = StampRed)
        else if (current == null) Box(Modifier.fillMaxWidth().height(200.dp), contentAlignment = Alignment.Center) {
            CircularProgressIndicator(color = Navy)
        } else {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(Modifier.weight(1f)) {
                    Text(current.type_label.uppercase(), style = MaterialTheme.typography.labelMedium, color = InkSoft)
                    Text(current.title, style = MaterialTheme.typography.headlineMedium, color = Ink, fontWeight = FontWeight.Bold)
                    FamilyShareBadge(current.shared_from, current.shared_with, current.is_owned)
                }
                Row {
                    if (current.is_owned) {
                        IconButton(onClick = { showFamilyShare = true }) {
                            Icon(Icons.Filled.Group, contentDescription = "Share with family", tint = VaultTeal)
                        }
                        IconButton(onClick = {
                            sharePin = ""
                            shareHours = "48"
                            shareOneTime = false
                            shareRequireGrant = false
                            shareEmailOtp = false
                            shareFilesOnly = false
                            shareAllowedEmails = ""
                            shareError = null
                            shareReady = null
                            showShare = true
                        }) {
                            Icon(Icons.Filled.Share, contentDescription = "Share link", tint = VaultTeal)
                        }
                    }
                    if (current.my_permission == "edit") {
                        IconButton(onClick = { editing = !editing }) {
                            Icon(Icons.Filled.Edit, contentDescription = "Edit", tint = VaultTeal)
                        }
                    }
                }
            }
            if (!editing) {
                Spacer(Modifier.height(8.dp))
                current.person_name?.let { Text("Profile  ${niceName(it)}", color = Ink) }
                current.folder_name?.let { Text("Folder  $it", color = InkSoft) }
                current.holder_name?.let { Text("Holder  ${niceName(it)}", color = Ink) }
                current.issuer?.let { Text("Issuer  $it", color = InkSoft) }
                current.id_number?.let { Text("ID  $it", color = Ink) }
                current.expiry_date?.let { Text("Expires  $it", color = InkSoft) }
                current.notes?.let { Text(it, color = InkSoft, modifier = Modifier.padding(top = 8.dp)) }
            } else {
                Spacer(Modifier.height(12.dp))
                Text("Edit details", fontWeight = FontWeight.SemiBold, color = Ink)
                Spacer(Modifier.height(8.dp))
                LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(LOCKER_TYPES) { (id, label) ->
                        FilterChip(selected = docType == id, onClick = { docType = id }, label = { Text(label) })
                    }
                }
                if (docType == "other") {
                    Spacer(Modifier.height(8.dp))
                    OutlinedTextField(customType, { customType = it }, label = { Text("Custom type") }, modifier = Modifier.fillMaxWidth())
                }
                if (folders.isNotEmpty()) {
                    Spacer(Modifier.height(8.dp))
                    Text("Folder", style = MaterialTheme.typography.labelMedium, color = InkSoft)
                    LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 6.dp)) {
                        item {
                            FilterChip(selected = folderId == null, onClick = { folderId = null }, label = { Text("None") })
                        }
                        items(folders) { f ->
                            FilterChip(
                                selected = folderId == f.id,
                                onClick = { folderId = if (folderId == f.id) null else f.id },
                                label = { Text(f.name) }
                            )
                        }
                    }
                }
                if (people.isNotEmpty()) {
                    Spacer(Modifier.height(8.dp))
                    Text("Family profile", style = MaterialTheme.typography.labelMedium, color = InkSoft)
                    LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 6.dp)) {
                        item {
                            FilterChip(selected = personId == null, onClick = { personId = null }, label = { Text("Unassigned") })
                        }
                        items(people) { p ->
                            FilterChip(
                                selected = personId == p.id,
                                onClick = { personId = if (personId == p.id) null else p.id },
                                label = { Text("${niceName(p.name)} · ${relationLabel(p.relation.name.lowercase())}") }
                            )
                        }
                    }
                }
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(title, { title = it }, label = { Text("Title") }, modifier = Modifier.fillMaxWidth())
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(holder, { holder = it }, label = { Text("Holder") }, modifier = Modifier.fillMaxWidth())
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(issuer, { issuer = it }, label = { Text("Issuer") }, modifier = Modifier.fillMaxWidth())
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(idNumber, { idNumber = it }, label = { Text("ID / number") }, modifier = Modifier.fillMaxWidth())
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(issuedOn, { issuedOn = it }, label = { Text("Issued on (YYYY-MM-DD)") }, modifier = Modifier.fillMaxWidth())
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(expiry, { expiry = it }, label = { Text("Expiry (YYYY-MM-DD)") }, modifier = Modifier.fillMaxWidth())
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(notes, { notes = it }, label = { Text("Notes") }, modifier = Modifier.fillMaxWidth(), minLines = 2)
                Spacer(Modifier.height(12.dp))
                Button(
                    onClick = {
                        if (title.isBlank()) {
                            Toast.makeText(context, "Title is required", Toast.LENGTH_SHORT).show()
                            return@Button
                        }
                        saving = true
                        scope.launch {
                            runCatching {
                                repository.updateLockerItem(
                                    itemId,
                                    LockerItemUpdate(
                                        title = title.trim(),
                                        doc_type = docType,
                                        custom_type = customType.ifBlank { null },
                                        folder_id = folderId ?: "",
                                        person_id = personId ?: "",
                                        holder_name = holder.ifBlank { null },
                                        issuer = issuer.ifBlank { null },
                                        id_number = idNumber.ifBlank { null },
                                        issued_on = issuedOn.ifBlank { null },
                                        expiry_date = expiry.ifBlank { null },
                                        notes = notes.ifBlank { null }
                                    )
                                )
                            }.onSuccess {
                                editing = false
                                Toast.makeText(context, "Saved", Toast.LENGTH_SHORT).show()
                                reload()
                            }.onFailure {
                                Toast.makeText(context, it.message ?: "Save failed", Toast.LENGTH_LONG).show()
                            }
                            saving = false
                        }
                    },
                    enabled = !saving,
                    modifier = Modifier.fillMaxWidth(),
                    colors = ButtonDefaults.buttonColors(containerColor = VaultTeal, contentColor = TextDark)
                ) {
                    Text(if (saving) "Saving…" else "Save changes")
                }
            }

            Spacer(Modifier.height(20.dp))
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text("Files", fontWeight = FontWeight.SemiBold, color = Ink)
                TextButton(onClick = { addPicker.launch("*/*") }) {
                    Icon(Icons.Filled.Add, null, Modifier.size(16.dp))
                    Spacer(Modifier.width(4.dp))
                    Text("Add media", color = VaultTeal)
                }
            }
            if (files.isEmpty()) {
                Text("No files yet — add a scan or PDF.", color = InkSoft, modifier = Modifier.padding(top = 8.dp))
            }
            files.forEach { f ->
                Surface(
                    shape = RoundedCornerShape(14.dp),
                    color = HubGlass,
                    modifier = Modifier.fillMaxWidth().padding(top = 8.dp)
                ) {
                    Row(
                        Modifier.padding(12.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(Icons.Filled.InsertDriveFile, null, tint = Navy)
                        Spacer(Modifier.width(10.dp))
                        Column(Modifier.weight(1f)) {
                            Text(f.original_filename, color = Ink, fontWeight = FontWeight.Medium)
                            Text(f.file_type ?: "file", color = InkSoft, style = MaterialTheme.typography.bodySmall)
                        }
                        IconButton(onClick = { openPreview(f) }) {
                            Icon(Icons.Filled.Visibility, contentDescription = "Open", tint = VaultTeal)
                        }
                        IconButton(onClick = { downloadExternal(f) }) {
                            Icon(Icons.Filled.Download, contentDescription = "Download", tint = InkSoft)
                        }
                        IconButton(onClick = { confirmDeleteFile = f }) {
                            Icon(Icons.Filled.Delete, contentDescription = "Remove", tint = StampRed)
                        }
                    }
                }
            }
            if (activeSends.isNotEmpty()) {
                Spacer(Modifier.height(24.dp))
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("Active shares", fontWeight = FontWeight.SemiBold, color = Ink)
                    TextButton(onClick = {
                        scope.launch {
                            runCatching { repository.revokeAllLockerItemSends(itemId) }
                                .onSuccess { reload() }
                                .onFailure { Toast.makeText(context, it.message, Toast.LENGTH_SHORT).show() }
                        }
                    }) { Text("Revoke all", color = StampRed) }
                }
                val base = repository.getServerUrl()?.trimEnd('/') ?: ""
                activeSends.forEach { send ->
                    Surface(
                        shape = RoundedCornerShape(14.dp),
                        color = HubGlass,
                        modifier = Modifier.fillMaxWidth().padding(top = 8.dp)
                    ) {
                        Row(
                            Modifier.padding(12.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Column(Modifier.weight(1f)) {
                                Text(send.name, color = Ink, fontWeight = FontWeight.Medium)
                                Text(
                                    buildString {
                                        append("${send.view_count}")
                                        send.max_views?.let { append("/$it") }
                                        append(" views")
                                        if (send.has_pin) append(" · PIN")
                                        if (send.requires_grant) append(" · Grant")
                                        if (send.requires_email_otp) append(" · Email OTP")
                                    },
                                    color = InkSoft,
                                    style = MaterialTheme.typography.bodySmall
                                )
                                Text(
                                    "$base/v/${send.token}",
                                    color = InkSoft,
                                    fontFamily = FontFamily.Monospace,
                                    style = MaterialTheme.typography.bodySmall,
                                    maxLines = 1
                                )
                            }
                            IconButton(onClick = {
                                ClipboardUtil.copy(context, "Document link", "$base/v/${send.token}")
                            }) {
                                Icon(Icons.Filled.Share, contentDescription = "Copy link", tint = VaultTeal)
                            }
                            IconButton(onClick = {
                                scope.launch {
                                    runCatching { repository.revokeLockerSend(send.id) }
                                        .onSuccess { reload() }
                                        .onFailure { Toast.makeText(context, it.message, Toast.LENGTH_SHORT).show() }
                                }
                            }) {
                                Icon(Icons.Filled.Delete, contentDescription = "Revoke", tint = StampRed)
                            }
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
            Spacer(Modifier.height(24.dp))
        }
    }
}

@Composable
private fun LockerPdfPreview(file: File) {
    var bitmap by remember(file.absolutePath) { mutableStateOf<android.graphics.Bitmap?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(file.absolutePath) {
        withContext(Dispatchers.IO) {
            runCatching {
                val fd = ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY)
                val renderer = PdfRenderer(fd)
                val page = renderer.openPage(0)
                val bm = android.graphics.Bitmap.createBitmap(
                    page.width.coerceAtLeast(1),
                    page.height.coerceAtLeast(1),
                    android.graphics.Bitmap.Config.ARGB_8888
                )
                page.render(bm, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                page.close()
                renderer.close()
                fd.close()
                bm
            }.onSuccess { bitmap = it }
                .onFailure { error = it.message }
        }
    }
    when {
        error != null -> Text(error!!, color = StampRed)
        bitmap == null -> CircularProgressIndicator(color = Navy)
        else -> Image(
            bitmap = bitmap!!.asImageBitmap(),
            contentDescription = "PDF preview",
            modifier = Modifier.fillMaxWidth(),
            contentScale = ContentScale.Fit
        )
    }
}
