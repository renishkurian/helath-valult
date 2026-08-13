package com.rklab.healthvault.ui.screens.family
import androidx.compose.foundation.clickable
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.rklab.healthvault.data.model.PersonOut
import com.rklab.healthvault.data.model.Relation
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.theme.*
import com.rklab.healthvault.util.ViewModelFactory
import androidx.compose.foundation.rememberScrollState

@Composable
fun FamilyScreen(repository: HealthVaultRepository, onOpenPerson: (PersonOut) -> Unit) {
    val viewModel: FamilyViewModel = viewModel(factory = ViewModelFactory(repository))
    val state by viewModel.state.collectAsState()
    var showAddDialog by remember { mutableStateOf(false) }
    var showInviteDialog by remember { mutableStateOf(false) }
    val isViewer = repository.isViewer

    LaunchedEffect(Unit) { viewModel.load() }

    Box(modifier = Modifier.fillMaxSize().background(Paper)) {
        Column(modifier = Modifier.fillMaxSize().padding(20.dp)) {
            Text("FAMILY", style = MaterialTheme.typography.labelMedium, color = InkSoft)
            Spacer(Modifier.height(4.dp))
            Text("Who you're managing", style = MaterialTheme.typography.headlineMedium, color = Ink)
            if (!isViewer) {
                Spacer(Modifier.height(8.dp))
                OutlinedButton(onClick = { showInviteDialog = true }) {
                    Text("Invite viewer (spouse login)", color = Navy)
                }
            }
            Spacer(Modifier.height(18.dp))

            if (state.loading) {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = Navy)
                }
            } else {
                LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    items(state.people) { person ->
                        PersonRow(
                            person = person,
                            onClick = { onOpenPerson(person) },
                            onDelete = if (!isViewer && person.relation != Relation.SELF) {
                                { viewModel.removeMember(person.id) }
                            } else null
                        )
                    }
                }
            }
        }

        if (!isViewer) {
        FloatingActionButton(
            onClick = { showAddDialog = true },
            containerColor = Navy,
            contentColor = White,
            modifier = Modifier.align(Alignment.BottomEnd).padding(20.dp)
        ) {
            Icon(Icons.Filled.Add, contentDescription = "Add family member")
        }
        }
    }

    if (showInviteDialog) {
        InviteViewerDialog(
            saving = state.saving,
            error = state.error,
            onDismiss = { showInviteDialog = false },
            onConfirm = { email, password, name ->
                viewModel.inviteViewer(email, password, name) { showInviteDialog = false }
            }
        )
    }

    if (showAddDialog) {
        AddFamilyMemberDialog(
            saving = state.saving,
            onDismiss = { showAddDialog = false },
            onConfirm = { name, relation, dob, bg ->
                viewModel.addMember(name, relation, dob, bg) { showAddDialog = false }
            }
        )
    }
}

@Composable
private fun PersonRow(person: PersonOut, onClick: () -> Unit, onDelete: (() -> Unit)?) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .background(White)
            .padding(16.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            modifier = Modifier.size(46.dp).clip(CircleShape).background(PaperDeep),
            contentAlignment = Alignment.Center
        ) {
            Text(person.avatar_initials ?: "?", style = MaterialTheme.typography.titleMedium, color = Ink)
        }
        Spacer(Modifier.width(14.dp))
        Column(modifier = Modifier.weight(1f)) {
            Text(person.name, style = MaterialTheme.typography.titleMedium, color = Ink)
            Text(
                person.relation.name.lowercase().replaceFirstChar { it.uppercase() },
                style = MaterialTheme.typography.bodySmall,
                color = InkSoft
            )
        }
        TextButton(onClick = onClick) { Text("Open", color = Navy) }
        if (onDelete != null) {
            IconButton(onClick = onDelete) {
                Icon(Icons.Filled.Delete, contentDescription = "Remove", tint = StampRed)
            }
        }
    }
}

@Composable
private fun AddFamilyMemberDialog(
    saving: Boolean,
    onDismiss: () -> Unit,
    onConfirm: (String, Relation, String?, String?) -> Unit
) {
    var name by remember { mutableStateOf("") }
    var relation by remember { mutableStateOf(Relation.SPOUSE) }
    var bloodGroup by remember { mutableStateOf("") }
    var dob by remember { mutableStateOf("") }
    var expanded by remember { mutableStateOf(false) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Add family member") },
        text = {
            Column {
                OutlinedTextField(
                    value = name, onValueChange = { name = it },
                    label = { Text("Name") }, singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
                Spacer(Modifier.height(10.dp))
                Box {
                    OutlinedTextField(
                        value = relation.name.lowercase().replaceFirstChar { it.uppercase() },
                        onValueChange = {}, readOnly = true,
                        label = { Text("Relation") },
                        modifier = Modifier.fillMaxWidth().clickableNoRipple { expanded = true }
                    )
                    DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                        listOf(Relation.SPOUSE, Relation.CHILD, Relation.PARENT, Relation.OTHER).forEach { r ->
                            DropdownMenuItem(
                                text = { Text(r.name.lowercase().replaceFirstChar { it.uppercase() }) },
                                onClick = { relation = r; expanded = false }
                            )
                        }
                    }
                }
                Spacer(Modifier.height(10.dp))
                com.rklab.healthvault.ui.components.DatePickerField(
                    label = "Date of Birth (optional)",
                    value = dob,
                    onValueChange = { dob = it },
                    modifier = Modifier.fillMaxWidth()
                )
                Spacer(Modifier.height(10.dp))
                OutlinedTextField(
                    value = bloodGroup, onValueChange = { bloodGroup = it },
                    label = { Text("Blood group (optional)") }, singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
            }
        },
        confirmButton = {
            TextButton(
                onClick = { onConfirm(name, relation, dob.ifBlank { null }, bloodGroup.ifBlank { null }) },
                enabled = name.isNotBlank() && !saving
            ) { Text(if (saving) "Adding…" else "Add", color = Navy) }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel", color = InkSoft) } }
    )
}

@Composable
private fun InviteViewerDialog(
    saving: Boolean,
    error: String?,
    onDismiss: () -> Unit,
    onConfirm: (String, String, String) -> Unit
) {
    var name by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Invite viewer") },
        text = {
            Column {
                Text("Creates a view-only login — they can see the vault but not change it.", style = MaterialTheme.typography.bodySmall, color = InkSoft)
                Spacer(Modifier.height(10.dp))
                OutlinedTextField(value = name, onValueChange = { name = it }, label = { Text("Name") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(value = email, onValueChange = { email = it }, label = { Text("Email") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(value = password, onValueChange = { password = it }, label = { Text("Password (8+ chars)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                if (error != null) {
                    Spacer(Modifier.height(8.dp))
                    Text(error, color = StampRed, style = MaterialTheme.typography.bodySmall)
                }
            }
        },
        confirmButton = {
            TextButton(
                onClick = { onConfirm(email, password, name) },
                enabled = email.isNotBlank() && password.length >= 8 && name.isNotBlank() && !saving
            ) { Text(if (saving) "Inviting…" else "Invite", color = Navy) }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel", color = InkSoft) } }
    )
}

private fun Modifier.clickableNoRipple(onClick: () -> Unit): Modifier =
    this.clickable(onClick = onClick)
