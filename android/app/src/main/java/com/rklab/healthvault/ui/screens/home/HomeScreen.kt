package com.rklab.healthvault.ui.screens.home

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.PersonAdd
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
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
    onOpenFolder: (DocCategory) -> Unit,
    onAddDocument: () -> Unit,
    onOpenDocument: (DocumentOut) -> Unit,
    onAddCard: () -> Unit,
    onOpenSettings: () -> Unit
) {
    val viewModel: HomeViewModel = viewModel(factory = ViewModelFactory(repository))
    val state by viewModel.state.collectAsState()

    LaunchedEffect(Unit) { viewModel.load() }

    Box(modifier = Modifier.fillMaxSize().background(Paper)) {
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

        LazyColumnContent(state, viewModel, onAddFamily, onOpenFolder, onAddDocument, onOpenDocument, onAddCard, onOpenSettings)

        FloatingActionButton(
            onClick = onAddDocument,
            containerColor = Navy,
            contentColor = White,
            modifier = Modifier.align(Alignment.BottomEnd).padding(20.dp)
        ) {
            Icon(Icons.Filled.Add, contentDescription = "Add document")
        }
    }
}

@Composable
private fun LazyColumnContent(
    state: HomeUiState,
    viewModel: HomeViewModel,
    onAddFamily: () -> Unit,
    onOpenFolder: (DocCategory) -> Unit,
    onAddDocument: () -> Unit,
    onOpenDocument: (DocumentOut) -> Unit,
    onAddCard: () -> Unit,
    onOpenSettings: () -> Unit
) {
    androidx.compose.foundation.lazy.LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 20.dp, end = 20.dp, top = 20.dp, bottom = 110.dp)
    ) {
        item {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.Top) {
                Column {
                    Text("HEALTH VAULT", style = MaterialTheme.typography.labelMedium, color = InkSoft)
                    Spacer(Modifier.height(4.dp))
                    Text(
                        "Hi, ${state.activePerson?.name?.split(" ")?.first() ?: "there"}",
                        style = MaterialTheme.typography.headlineLarge,
                        color = Ink
                    )
                }
                IconButton(onClick = onOpenSettings) {
                    Icon(Icons.Filled.Settings, contentDescription = "Settings", tint = InkSoft)
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
                                .background(PaperDeep)
                                .then(Modifier),
                            contentAlignment = Alignment.Center
                        ) {
                            IconButton(onClick = onAddFamily) {
                                Icon(Icons.Filled.PersonAdd, contentDescription = "Add family member", tint = InkSoft)
                            }
                        }
                        Spacer(Modifier.height(4.dp))
                        Text("Add", style = MaterialTheme.typography.labelSmall, color = InkSoft)
                    }
                }
            }
            Spacer(Modifier.height(22.dp))
        }

        if (state.cards.isEmpty()) {
            item {
                EmptyCardPrompt(onAddCard)
                Spacer(Modifier.height(24.dp))
            }
        } else {
            items(state.cards) { card ->
                HealthIdCard(
                    card = card,
                    patientName = state.activePerson?.name ?: "",
                    modifier = Modifier.fillMaxWidth()
                )
                Spacer(Modifier.height(24.dp))
            }
        }

        if (state.expiringCards.isNotEmpty()) {
            item {
                state.expiringCards.forEach { card ->
                    ExpiryAlert(hospitalName = card.hospital_name, validTill = card.valid_till)
                    Spacer(Modifier.height(12.dp))
                }
                Spacer(Modifier.height(10.dp))
            }
        }

        item {
            SectionHead("Folders", "${state.folderCounts.values.sum()} documents")
            Spacer(Modifier.height(12.dp))
        }
        item {
            LazyRow {
                items(FolderDefs) { def ->
                    FolderTab(def = def, count = state.folderCounts[def.category] ?: 0) {
                        onOpenFolder(def.category)
                    }
                }
            }
            Spacer(Modifier.height(28.dp))
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
                        .background(White)
                        .padding(24.dp),
                    contentAlignment = Alignment.Center
                ) {
                    Text("No documents yet. Tap + to add your first one.", color = InkSoft, style = MaterialTheme.typography.bodyMedium)
                }
            } else {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(14.dp))
                        .background(White)
                ) {
                    state.recentDocuments.forEachIndexed { idx, doc ->
                        LedgerRow(
                            title = doc.title,
                            metaLine = "${doc.doc_date ?: doc.created_at.take(10)} · ${formatSize(doc.file_size)}",
                            category = doc.category,
                            tagLabel = "Synced",
                            tagColor = Sage,
                            tagBg = SageBg,
                            onClick = { onOpenDocument(doc) }
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
private fun EmptyCardPrompt(onAddCard: () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(18.dp))
            .background(White)
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text("No hospital card yet", style = MaterialTheme.typography.titleLarge, color = Ink)
        Spacer(Modifier.height(6.dp))
        Text(
            "Add a hospital ID card to keep it one tap away.",
            style = MaterialTheme.typography.bodyMedium,
            color = InkSoft
        )
        Spacer(Modifier.height(14.dp))
        Button(onClick = onAddCard, colors = ButtonDefaults.buttonColors(containerColor = Navy)) {
            Text("Add hospital card", color = White)
        }
    }
}

@Composable
private fun ExpiryAlert(hospitalName: String, validTill: String?) {
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
            .padding(horizontal = 13.dp, vertical = 11.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(modifier = Modifier.size(8.dp).clip(CircleShape).background(Mustard))
        Spacer(Modifier.width(10.dp))
        Text(
            buildString {
                append(hospitalName)
                append(" card ")
                append(if (daysLeft != null) "expires in $daysLeft days" else "is expiring soon")
            },
            style = MaterialTheme.typography.bodySmall,
            color = androidx.compose.ui.graphics.Color(0xFF5A4419),
            modifier = Modifier.weight(1f)
        )
    }
}

@Composable
private fun SectionHead(title: String, count: String) {
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(title.uppercase(), style = MaterialTheme.typography.labelMedium, color = InkSoft)
        Text(count, style = MaterialTheme.typography.labelMedium, color = InkSoft)
    }
}

private fun formatSize(bytes: Long?): String {
    if (bytes == null) return "—"
    val kb = bytes / 1024.0
    return if (kb < 1024) "%.0f KB".format(kb) else "%.1f MB".format(kb / 1024.0)
}
