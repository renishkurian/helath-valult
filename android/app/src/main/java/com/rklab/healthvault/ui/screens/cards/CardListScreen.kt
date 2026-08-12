package com.rklab.healthvault.ui.screens.cards

import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.components.HealthIdCard
import com.rklab.healthvault.ui.theme.*
import com.rklab.healthvault.util.ViewModelFactory

@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
fun CardListScreen(
    repository: HealthVaultRepository,
    personId: String,
    personName: String,
    onBack: () -> Unit
) {
    val viewModel: CardsViewModel = viewModel(factory = ViewModelFactory(repository))
    val state by viewModel.state.collectAsState()
    var showAddSheet by remember { mutableStateOf(false) }

    LaunchedEffect(personId) { viewModel.load(personId) }

    Box(modifier = Modifier.fillMaxSize().background(Paper)) {
        Column(modifier = Modifier.fillMaxSize().padding(20.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                TextButton(onClick = onBack) { Text("← Back", color = Navy) }
            }
            Text("$personName'S CARDS".uppercase(), style = MaterialTheme.typography.labelMedium, color = InkSoft)
            Spacer(Modifier.height(4.dp))
            Text("Hospital ID cards", style = MaterialTheme.typography.headlineMedium, color = Ink)
            Spacer(Modifier.height(18.dp))

            if (state.loading) {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator(color = Navy) }
            } else if (state.cards.isEmpty()) {
                Text("No cards yet for $personName. Add one with the button below.", color = InkSoft)
            } else {
                LazyColumn(verticalArrangement = Arrangement.spacedBy(20.dp), contentPadding = PaddingValues(bottom = 90.dp)) {
                    items(state.cards) { card ->
                        Box(
                            modifier = Modifier.combinedClickable(
                                onClick = {},
                                onLongClick = { viewModel.deleteCard(personId, card.id) }
                            )
                        ) {
                            HealthIdCard(card = card, patientName = personName, modifier = Modifier.fillMaxWidth())
                        }
                    }
                }
            }
        }

        FloatingActionButton(
            onClick = { showAddSheet = true },
            containerColor = Navy, contentColor = White,
            modifier = Modifier.align(Alignment.BottomEnd).padding(20.dp)
        ) { Icon(Icons.Filled.Add, contentDescription = "Add card") }
    }

    if (showAddSheet) {
        AddCardSheet(
            saving = state.saving,
            onDismiss = { showAddSheet = false },
            onConfirm = { hospital, ward, bg, from, till, pid, notes ->
                viewModel.addCard(personId, hospital, ward, bg, from, till, pid, notes) { showAddSheet = false }
            }
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AddCardSheet(
    saving: Boolean,
    onDismiss: () -> Unit,
    onConfirm: (String, String?, String?, String?, String?, String?, String?) -> Unit
) {
    var hospital by remember { mutableStateOf("") }
    var ward by remember { mutableStateOf("") }
    var bloodGroup by remember { mutableStateOf("") }
    var validFrom by remember { mutableStateOf("") }
    var validTill by remember { mutableStateOf("") }
    var patientId by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }

    ModalBottomSheet(onDismissRequest = onDismiss, containerColor = Paper) {
        Column(modifier = Modifier.fillMaxWidth().padding(20.dp).padding(bottom = 24.dp)) {
            Text("Add hospital card", style = MaterialTheme.typography.headlineMedium, color = Ink)
            Spacer(Modifier.height(16.dp))

            LabeledField("Hospital name*", hospital) { hospital = it }
            Spacer(Modifier.height(10.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Box(Modifier.weight(1f)) { LabeledField("Ward", ward) { ward = it } }
                Box(Modifier.weight(1f)) { LabeledField("Blood group", bloodGroup) { bloodGroup = it } }
            }
            Spacer(Modifier.height(10.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Box(Modifier.weight(1f)) { LabeledField("Valid from (YYYY-MM-DD)", validFrom) { validFrom = it } }
                Box(Modifier.weight(1f)) { LabeledField("Valid till (YYYY-MM-DD)", validTill) { validTill = it } }
            }
            Spacer(Modifier.height(10.dp))
            LabeledField("Patient ID number", patientId, keyboardType = KeyboardType.Text) { patientId = it }
            Text("Stored encrypted", style = MaterialTheme.typography.labelSmall, color = Sage)
            Spacer(Modifier.height(10.dp))
            LabeledField("Notes", notes) { notes = it }

            Spacer(Modifier.height(20.dp))
            Button(
                onClick = {
                    onConfirm(
                        hospital, ward.ifBlank { null }, bloodGroup.ifBlank { null },
                        validFrom.ifBlank { null }, validTill.ifBlank { null },
                        patientId.ifBlank { null }, notes.ifBlank { null }
                    )
                },
                enabled = hospital.isNotBlank() && !saving,
                modifier = Modifier.fillMaxWidth().height(48.dp),
                colors = ButtonDefaults.buttonColors(containerColor = Navy)
            ) {
                Text(if (saving) "Saving…" else "Save card", color = White)
            }
        }
    }
}

@Composable
private fun LabeledField(
    label: String,
    value: String,
    keyboardType: KeyboardType = KeyboardType.Text,
    onChange: (String) -> Unit
) {
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        label = { Text(label) },
        singleLine = true,
        modifier = Modifier.fillMaxWidth()
    )
}
