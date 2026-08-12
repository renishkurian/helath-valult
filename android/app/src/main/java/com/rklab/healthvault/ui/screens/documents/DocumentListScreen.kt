package com.rklab.healthvault.ui.screens.documents

import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
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
import com.rklab.healthvault.ui.components.LedgerRow
import com.rklab.healthvault.ui.components.OfflineBanner
import com.rklab.healthvault.ui.theme.*
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.util.ViewModelFactory
import kotlinx.coroutines.launch
import java.io.File

@Composable
fun DocumentListScreen(
    repository: HealthVaultRepository,
    personId: String,
    category: DocCategory?,
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

    LaunchedEffect(personId, category) { viewModel.load(personId, category) }

    Column(modifier = Modifier.fillMaxSize().background(Paper)) {
        // Offline banner at top — slides in when Pi is unreachable.
        OfflineBanner(isOffline = isOffline, pendingCount = pendingCount)

        Box(modifier = Modifier.weight(1f)) {
            Column(modifier = Modifier.fillMaxSize().padding(20.dp)) {
                TextButton(onClick = onBack) { Text("← Back", color = Navy) }
                Text(title.uppercase(), style = MaterialTheme.typography.labelMedium, color = InkSoft)
                Spacer(Modifier.height(4.dp))
                Text("${state.documents.size} documents", style = MaterialTheme.typography.headlineMedium, color = Ink)

                // Error toast (doesn't block the list — cached data may still be showing)
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
                        items(state.documents) { doc ->
                            LedgerRow(
                                title = doc.title,
                                metaLine = "${doc.doc_date ?: doc.created_at.take(10)} · ${doc.hospital_name ?: "—"}",
                                category = doc.category,
                                tagLabel = "Open",
                                tagColor = Sage,
                                tagBg = SageBg,
                                onClick = {
                                    scope.launch {
                                        val dest = File(context.cacheDir.resolve("downloads").apply { mkdirs() }, doc.title)
                                        val file = viewModel.download(doc.id, dest)
                                        val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
                                        val intent = Intent(Intent.ACTION_VIEW).apply {
                                            setDataAndType(uri, doc.file_type ?: "*/*")
                                            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                                        }
                                        context.startActivity(Intent.createChooser(intent, "Open with"))
                                    }
                                }
                            )
                            Divider(color = PaperDeep, thickness = 1.dp)
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
}
