package com.rklab.healthvault.ui.screens.home

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Apps
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.foundation.Canvas
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.rklab.healthvault.data.model.DocCategory
import com.rklab.healthvault.data.model.DocumentOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.components.*
import com.rklab.healthvault.ui.theme.*
import com.rklab.healthvault.util.ViewModelFactory
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit

@Composable
fun HomeScreen(
    repository: HealthVaultRepository,
    onAddFamily: () -> Unit,
    onOpenFolder: (personId: String, category: DocCategory, customCategory: String?, hospital: String?) -> Unit,
    onAddDocument: (personId: String, hospital: String?) -> Unit,
    onOpenDocument: (DocumentOut, String?) -> Unit,
    onAddCard: (personId: String, personName: String) -> Unit,
    onOpenSettings: () -> Unit,
    onOpenModules: () -> Unit = {},
    isViewer: Boolean = false
) {
    val viewModel: HomeViewModel = viewModel(factory = ViewModelFactory(repository))
    val state by viewModel.state.collectAsState()
    val isOffline by viewModel.isOffline.collectAsState()
    val pendingCount by viewModel.pendingUploadCount.collectAsState()

    LaunchedEffect(Unit) { viewModel.load() }

    Column(modifier = Modifier.fillMaxSize().background(HubBg)) {
        OfflineBanner(isOffline = isOffline, pendingCount = pendingCount)

        Box(modifier = Modifier.weight(1f)) {
            if (state.loading) {
                CircularProgressIndicator(modifier = Modifier.align(Alignment.Center), color = Navy)
                return@Box
            }
            if (state.error != null) {
                Column(
                    modifier = Modifier.align(Alignment.Center).padding(24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Text(state.error!!, color = InkSoft, style = MaterialTheme.typography.bodyMedium)
                    Spacer(Modifier.height(12.dp))
                    Button(onClick = { viewModel.load() }, colors = ButtonDefaults.buttonColors(containerColor = Navy)) {
                        Text("Retry", color = White)
                    }
                }
                return@Box
            }

            val activeId = state.activePerson?.id.orEmpty()
            val activeName = state.activePerson?.name.orEmpty()
            LazyColumnContent(
                state, viewModel,
                onAddFamily = onAddFamily,
                onOpenFolder = { cat, customCat, hospital -> onOpenFolder(activeId, cat, customCat, hospital) },
                onAddDocument = { hospital -> onAddDocument(activeId, hospital) },
                onOpenDocument = onOpenDocument,
                onAddCard = { onAddCard(activeId, activeName) },
                onOpenSettings = onOpenSettings,
                onOpenModules = onOpenModules,
                isViewer = isViewer
            )

            if (!isViewer) {
                FloatingActionButton(
                    onClick = {
                        val hospital = state.cards.firstOrNull()?.hospital_name
                        onAddDocument(activeId, hospital)
                    },
                    modifier = Modifier.align(Alignment.BottomEnd).padding(20.dp).size(64.dp),
                    containerColor = Color.Transparent,
                    elevation = FloatingActionButtonDefaults.elevation(0.dp, 0.dp)
                ) {
                    Box(
                        modifier = Modifier.fillMaxSize().background(GradientPrimary, CircleShape),
                        contentAlignment = Alignment.Center
                    ) {
                        Icon(Icons.Filled.Add, contentDescription = "Add document", tint = TextDark, modifier = Modifier.size(32.dp))
                    }
                }
            }
        }
    }
}

@Composable
private fun LazyColumnContent(
    state: HomeUiState,
    viewModel: HomeViewModel,
    onAddFamily: () -> Unit,
    onOpenFolder: (DocCategory, String?, String?) -> Unit,
    onAddDocument: (String?) -> Unit,
    onOpenDocument: (DocumentOut, String?) -> Unit,
    onAddCard: () -> Unit,
    onOpenSettings: () -> Unit,
    onOpenModules: () -> Unit = {},
    isViewer: Boolean = false
) {
    androidx.compose.foundation.lazy.LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 20.dp, end = 20.dp, top = 20.dp, bottom = 110.dp)
    ) {
        item {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.Top) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        "Hi, ${state.activePerson?.name?.split(" ")?.first() ?: "there"}",
                        style = MaterialTheme.typography.headlineLarge.copy(fontWeight = FontWeight.Bold),
                        color = TextWhite
                    )
                    Spacer(Modifier.height(4.dp))
                    Text(
                        "Papers live under a hospital. Insurance stays with the person.",
                        style = MaterialTheme.typography.bodySmall,
                        color = TextGray
                    )
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Box(
                        modifier = Modifier.size(48.dp).clip(CircleShape).background(CardSurface).border(1.dp, CardOutline, CircleShape),
                        contentAlignment = Alignment.Center
                    ) {
                        IconButton(onClick = onOpenModules) {
                            Icon(Icons.Filled.Apps, contentDescription = "Modules", tint = TextGray)
                        }
                    }
                    Box(
                        modifier = Modifier.size(48.dp).clip(CircleShape).background(CardSurface).border(1.dp, CardOutline, CircleShape),
                        contentAlignment = Alignment.Center
                    ) {
                        IconButton(onClick = onOpenSettings) {
                            Icon(Icons.Filled.Settings, contentDescription = "Settings", tint = TextGray)
                        }
                    }
                }
            }
            Spacer(Modifier.height(18.dp))
        }

        item {
            LazyRow(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                items(state.people) { person ->
                    FamilyAvatarChip(
                        name = person.name,
                        initials = person.avatar_initials ?: "?",
                        selected = person.id == state.activePerson?.id,
                        onClick = { viewModel.selectPerson(person) }
                    )
                }
                item {
                    Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.width(64.dp)) {
                        Box(
                            modifier = Modifier
                                .size(52.dp)
                                .clip(CircleShape)
                                .background(Color.Transparent)
                                .border(1.dp, TextGray, CircleShape),
                            contentAlignment = Alignment.Center
                        ) {
                            IconButton(onClick = onAddFamily) {
                                Icon(Icons.Filled.Add, contentDescription = "Add family member", tint = TextGray)
                            }
                        }
                        Spacer(Modifier.height(8.dp))
                        Text("Add", style = MaterialTheme.typography.labelSmall, color = TextGray)
                    }
                }
            }
            Spacer(Modifier.height(22.dp))
        }

        if (state.expiringCards.isNotEmpty() || state.expiringDocuments.isNotEmpty()) {
            item {
                state.expiringCards.forEach { card ->
                    ExpiryAlert(label = "${card.hospital_name} card", validTill = card.valid_till)
                    Spacer(Modifier.height(12.dp))
                }
                state.expiringDocuments.forEach { doc ->
                    ExpiryAlert(label = doc.title, validTill = doc.expiry_date)
                    Spacer(Modifier.height(12.dp))
                }
                Spacer(Modifier.height(10.dp))
            }
        }

        item {
            SectionHead("Hospitals", "${state.cards.size} · ${state.documentCount} documents")
            Spacer(Modifier.height(12.dp))
        }

        if (state.hospitalFolders.isEmpty()) {
            item {
                EmptyCardPrompt(onAddCard)
                Spacer(Modifier.height(24.dp))
            }
        } else {
            items(state.hospitalFolders) { group ->
                HospitalBlock(
                    group = group,
                    folderDefs = state.hospitalFolderDefs,
                    patientName = state.activePerson?.name ?: "",
                    onOpenFolder = { def ->
                        onOpenFolder(def.category, def.customCategory, group.card.hospital_name)
                    },
                    onAddDocument = { onAddDocument(group.card.hospital_name) },
                    isViewer = isViewer
                )
                Spacer(Modifier.height(20.dp))
            }
            if (!isViewer) {
                item {
                    TextButton(onClick = onAddCard) {
                        Text("+ Add hospital", color = Navy, fontWeight = FontWeight.SemiBold)
                    }
                    Spacer(Modifier.height(16.dp))
                }
            }
        }

        item {
            SectionHead("Insurance", "Personal — not under a hospital")
            Spacer(Modifier.height(12.dp))
            LazyRow(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                item {
                    FolderTab(def = InsuranceFolderDef, count = state.insuranceCount) {
                        onOpenFolder(DocCategory.INSURANCE, null, null)
                    }
                }
            }
            Spacer(Modifier.height(24.dp))
        }

        if (state.unassignedCounts.isNotEmpty()) {
            item {
                SectionHead("Unassigned", "Older files without a hospital")
                Spacer(Modifier.height(12.dp))
                LazyRow(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                    items(state.hospitalFolderDefs.filter {
                        val key = it.customCategory ?: it.category.name
                        (state.unassignedCounts[key] ?: 0) > 0
                    }) { def ->
                        val key = def.customCategory ?: def.category.name
                        FolderTab(def = def, count = state.unassignedCounts[key] ?: 0) {
                            onOpenFolder(def.category, def.customCategory, null)
                        }
                    }
                }
                Spacer(Modifier.height(24.dp))
            }
        }

        if (state.labTrends.isNotEmpty()) {
            item {
                SectionHead("Lab trends", "from reports")
                Spacer(Modifier.height(12.dp))
                state.labTrends.take(4).forEach { trend ->
                    LabTrendCard(trend)
                    Spacer(Modifier.height(10.dp))
                }
                Spacer(Modifier.height(18.dp))
            }
        }

        item {
            SectionHead("Recently Added", "This week")
            Spacer(Modifier.height(12.dp))
        }
        item {
            if (state.recentDocuments.isEmpty()) {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(14.dp))
                        .background(HubGlass)
                        .padding(24.dp),
                    contentAlignment = Alignment.Center
                ) {
                    Text("Add a hospital, then upload a document under it.", color = InkSoft, style = MaterialTheme.typography.bodyMedium)
                }
            } else {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(14.dp))
                        .background(HubGlass)
                ) {
                    state.recentDocuments.forEachIndexed { idx, doc ->
                        val metaHospital = when {
                            doc.category == DocCategory.INSURANCE -> "Personal"
                            !doc.hospital_name.isNullOrBlank() -> doc.hospital_name
                            else -> "—"
                        }
                        LedgerRow(
                            title = doc.title,
                            metaLine = "${doc.doc_date ?: doc.created_at.take(10)} · $metaHospital",
                            category = doc.category,
                            tagLabel = if (doc.file_count > 1) "${doc.file_count} files" else "Open",
                            onClick = {
                                if (doc.file_count > 1) {
                                    onOpenFolder(doc.category, doc.custom_category, doc.hospital_name)
                                } else {
                                    onOpenDocument(doc, null)
                                }
                            }
                        )
                        if (idx != state.recentDocuments.lastIndex) {
                            Divider(color = PaperDeep, thickness = 1.dp)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun HospitalBlock(
    group: HospitalFolderGroup,
    folderDefs: List<FolderDef>,
    patientName: String,
    onOpenFolder: (FolderDef) -> Unit,
    onAddDocument: () -> Unit,
    isViewer: Boolean
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(18.dp))
            .background(CardSurface)
            .border(1.dp, CardOutline, RoundedCornerShape(18.dp))
            .padding(16.dp)
    ) {
        HealthIdCard(
            card = group.card,
            patientName = patientName,
            modifier = Modifier.fillMaxWidth()
        )
        Spacer(Modifier.height(14.dp))
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column {
                Text(group.card.hospital_name, style = MaterialTheme.typography.titleSmall, color = TextWhite)
                Text("Documents for this hospital", style = MaterialTheme.typography.labelSmall, color = TextGray)
            }
            if (!isViewer) {
                TextButton(onClick = onAddDocument) {
                    Text("Upload", color = Navy, fontWeight = FontWeight.SemiBold)
                }
            }
        }
        Spacer(Modifier.height(12.dp))
        LazyRow(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            items(folderDefs) { def ->
                val key = def.customCategory ?: def.category.name
                FolderTab(def = def, count = group.counts[key] ?: 0) {
                    onOpenFolder(def)
                }
            }
        }
    }
}

@Composable
private fun EmptyCardPrompt(onAddCard: () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(18.dp))
            .background(CardSurface)
            .border(1.dp, CardOutline, RoundedCornerShape(18.dp))
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text("No hospitals yet", style = MaterialTheme.typography.titleLarge, color = TextWhite)
        Spacer(Modifier.height(6.dp))
        Text(
            "Add a hospital first. Prescriptions, labs, bills, and vaccines are filed under it.",
            style = MaterialTheme.typography.bodyMedium,
            color = TextGray
        )
        Spacer(Modifier.height(14.dp))
        Button(
            onClick = onAddCard,
            contentPadding = PaddingValues(0.dp),
            shape = RoundedCornerShape(12.dp),
            modifier = Modifier.height(48.dp).fillMaxWidth(0.8f),
            colors = ButtonDefaults.buttonColors(containerColor = Color.Transparent, contentColor = TextWhite)
        ) {
            Box(
                modifier = Modifier.fillMaxSize().background(GradientPrimary),
                contentAlignment = Alignment.Center
            ) {
                Text("Add hospital", color = TextWhite, fontWeight = FontWeight.SemiBold)
            }
        }
    }
}

@Composable
private fun LabTrendCard(trend: com.rklab.healthvault.data.model.LabTrend) {
    val points = trend.points.map { it.value }
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .background(HubGlass)
            .padding(16.dp)
    ) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(trend.metric.replace('_', ' '), style = MaterialTheme.typography.titleSmall, color = Ink)
            Text(
                buildString {
                    append(points.lastOrNull()?.let { "%.1f".format(it) } ?: "—")
                    if (!trend.unit.isNullOrBlank()) append(" ${trend.unit}")
                },
                style = MaterialTheme.typography.labelMedium,
                color = Navy
            )
        }
        if (points.size >= 2) {
            Spacer(Modifier.height(10.dp))
            val min = points.min()
            val max = points.max().let { if (it == min) it + 1 else it }
            Canvas(modifier = Modifier.fillMaxWidth().height(56.dp)) {
                val path = Path()
                points.forEachIndexed { i, v ->
                    val x = size.width * i / (points.size - 1).coerceAtLeast(1)
                    val y = size.height - ((v - min) / (max - min)).toFloat() * size.height
                    if (i == 0) path.moveTo(x, y) else path.lineTo(x, y)
                }
                drawPath(path, color = Navy, style = Stroke(width = 4f))
            }
        }
    }
}

@Composable
private fun ExpiryAlert(label: String, validTill: String?) {
    val daysLeft = remember(validTill) {
        try {
            ChronoUnit.DAYS.between(LocalDate.now(), LocalDate.parse(validTill, DateTimeFormatter.ISO_DATE))
        } catch (e: Exception) { null }
    }
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(MustardBg)
            .border(1.dp, Mustard, RoundedCornerShape(12.dp))
            .padding(horizontal = 16.dp, vertical = 16.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(modifier = Modifier.size(8.dp).clip(CircleShape).background(Mustard))
        Spacer(Modifier.width(12.dp))
        Text(
            buildString {
                append(label)
                append(" ")
                append(if (daysLeft != null) "expires in $daysLeft days" else "is expiring soon")
            },
            style = MaterialTheme.typography.bodyMedium,
            color = TextWhite,
            modifier = Modifier.weight(1f)
        )
        Text("RENEW ➔", style = MaterialTheme.typography.labelMedium.copy(fontWeight = FontWeight.Bold), color = Mustard)
    }
}

@Composable
private fun SectionHead(title: String, count: String) {
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(title.uppercase(), style = MaterialTheme.typography.labelMedium, color = InkSoft)
        Text(count, style = MaterialTheme.typography.labelMedium, color = InkSoft)
    }
}
