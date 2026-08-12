package com.rklab.healthvault.ui.screens.documents

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.rklab.healthvault.data.model.DocCategory
import com.rklab.healthvault.data.model.DocumentUpdate
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.components.docCategoryColor
import com.rklab.healthvault.ui.theme.*
import com.rklab.healthvault.util.ViewModelFactory
import kotlinx.coroutines.launch

@Composable
fun EditDocumentScreen(
    repository: HealthVaultRepository,
    docId: String,
    onDone: () -> Unit,
    onBack: () -> Unit
) {
    val viewModel: DocumentsViewModel = viewModel(factory = ViewModelFactory(repository))
    val state by viewModel.state.collectAsState()
    val scope = rememberCoroutineScope()

    var initialized by remember { mutableStateOf(false) }
    var category by remember { mutableStateOf(DocCategory.OTHER) }
    var customCategory by remember { mutableStateOf("") }
    var title by remember { mutableStateOf("") }
    var hospitalName by remember { mutableStateOf("") }
    var docDate by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }

    var categoryMenuOpen by remember { mutableStateOf(false) }
    var saving by remember { mutableStateOf(false) }
    var loadError by remember { mutableStateOf<String?>(null) }
    var saveError by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(docId) {
        val doc = state.documents.find { it.id == docId }
        if (doc != null) {
            category = doc.category
            customCategory = doc.custom_category ?: ""
            title = doc.title
            hospitalName = doc.hospital_name ?: ""
            docDate = doc.doc_date ?: ""
            notes = doc.notes ?: ""
            initialized = true
        } else {
            loadError = "Document not found."
        }
    }

    Box(modifier = Modifier.fillMaxSize().background(Paper)) {
        if (loadError != null) {
            Column(modifier = Modifier.align(androidx.compose.ui.Alignment.Center).padding(20.dp)) {
                Text(loadError!!, color = StampRed)
                Spacer(Modifier.height(16.dp))
                Button(onClick = onBack) { Text("Go Back") }
            }
            return@Box
        }

        if (!initialized) {
            CircularProgressIndicator(modifier = Modifier.align(androidx.compose.ui.Alignment.Center), color = Navy)
            return@Box
        }

        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(20.dp)
                .verticalScroll(rememberScrollState())
        ) {
            TextButton(onClick = onBack) { Text("← Back", color = Navy) }
            Text("EDIT DOCUMENT", style = MaterialTheme.typography.labelMedium, color = InkSoft)
            Spacer(Modifier.height(4.dp))
            Text("Edit details", style = MaterialTheme.typography.headlineMedium, color = Ink)
            Spacer(Modifier.height(20.dp))

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

            OutlinedTextField(
                value = hospitalName,
                onValueChange = { hospitalName = it },
                label = { Text("Hospital / clinic (optional)") },
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(Modifier.height(10.dp))

            OutlinedTextField(
                value = docDate,
                onValueChange = { docDate = it },
                label = { Text("Date (optional)") },
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(Modifier.height(10.dp))
            OutlinedTextField(value = notes, onValueChange = { notes = it }, label = { Text("Notes (optional, stored encrypted)") }, modifier = Modifier.fillMaxWidth())

            if (saveError != null) {
                Spacer(Modifier.height(10.dp))
                Text(saveError!!, color = StampRed, style = MaterialTheme.typography.bodySmall)
            }

            Spacer(Modifier.height(20.dp))
            Button(
                onClick = {
                    saving = true
                    saveError = null
                    scope.launch {
                        try {
                            val update = DocumentUpdate(
                                title = title.ifBlank { null },
                                category = category,
                                custom_category = customCategory.ifBlank { null },
                                hospital_name = hospitalName.ifBlank { null },
                                doc_date = docDate.ifBlank { null },
                                notes = notes.ifBlank { null }
                            )
                            repository.updateDocument(docId, update)
                            // Reload list from local db to reflect changes instantly on the previous screen
                            viewModel.load(null, null, null)
                            onDone()
                        } catch (e: Exception) {
                            saveError = e.message ?: "Failed to update document"
                        } finally {
                            saving = false
                        }
                    }
                },
                enabled = !saving && title.isNotBlank(),
                modifier = Modifier.fillMaxWidth().height(52.dp),
                shape = RoundedCornerShape(14.dp),
                colors = ButtonDefaults.buttonColors(containerColor = docCategoryColor(category))
            ) {
                if (saving) {
                    CircularProgressIndicator(modifier = Modifier.size(20.dp), color = White, strokeWidth = 2.dp)
                    Spacer(Modifier.width(8.dp))
                }
                Text(
                    if (saving) "Saving…" else "Save Changes",
                    color = White,
                    fontWeight = FontWeight.SemiBold
                )
            }
            Spacer(Modifier.height(40.dp))
        }
    }
}

private fun categoryLabel(cat: DocCategory): String =
    cat.name.lowercase().split("_").joinToString(" ") { it.replaceFirstChar(Char::uppercase) }
