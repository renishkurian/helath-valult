package com.rklab.healthvault.ui.screens.reminders

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.rklab.healthvault.data.model.RepeatRule
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.theme.*
import com.rklab.healthvault.util.ReminderScheduler
import com.rklab.healthvault.util.ViewModelFactory
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

@Composable
fun RemindersScreen(repository: HealthVaultRepository, activePersonId: String?) {
    val viewModel: RemindersViewModel = viewModel(factory = ViewModelFactory(repository))
    val state by viewModel.state.collectAsState()
    val context = LocalContext.current
    var showAddDialog by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) { viewModel.load() }

    Box(modifier = Modifier.fillMaxSize().background(Paper)) {
        Column(modifier = Modifier.fillMaxSize().padding(20.dp)) {
            Text("REMINDERS", style = MaterialTheme.typography.labelMedium, color = InkSoft)
            Spacer(Modifier.height(4.dp))
            Text("Medicines & appointments", style = MaterialTheme.typography.headlineMedium, color = Ink)
            Spacer(Modifier.height(18.dp))

            if (state.loading) {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator(color = Navy) }
            } else if (state.reminders.isEmpty()) {
                Text("No reminders yet.", color = InkSoft)
            } else {
                LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp), contentPadding = PaddingValues(bottom = 90.dp)) {
                    items(state.reminders) { reminder ->
                        ReminderRow(
                            title = reminder.title,
                            description = reminder.description,
                            remindAt = reminder.remind_at,
                            repeatRule = reminder.repeat_rule,
                            onDelete = {
                                ReminderScheduler.cancel(context, reminder.id)
                                viewModel.deleteReminder(reminder.id)
                            },
                            onComplete = {
                                ReminderScheduler.cancel(context, reminder.id)
                                viewModel.completeReminder(reminder.id)
                            }
                        )
                    }
                }
            }
        }

        FloatingActionButton(
            onClick = { showAddDialog = true },
            containerColor = Navy, contentColor = White,
            modifier = Modifier.align(Alignment.BottomEnd).padding(20.dp)
        ) { Icon(Icons.Filled.Add, contentDescription = "Add reminder") }
    }

    if (showAddDialog && activePersonId != null) {
        AddReminderDialog(
            saving = state.saving,
            onDismiss = { showAddDialog = false },
            onConfirm = { title, description, remindAtIso, repeat ->
                viewModel.addReminder(activePersonId, title, description, remindAtIso, repeat) { created ->
                    ReminderScheduler.schedule(context, created.id, created.title, created.description, created.remind_at)
                    showAddDialog = false
                }
            }
        )
    }
}

@Composable
private fun ReminderRow(title: String, description: String?, remindAt: String, repeatRule: RepeatRule, onDelete: () -> Unit, onComplete: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .background(White)
            .padding(14.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Icon(Icons.Filled.Notifications, contentDescription = null, tint = Mustard)
        Spacer(Modifier.width(12.dp))
        Column(modifier = Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.titleMedium, color = Ink)
            Spacer(Modifier.height(2.dp))
            Text(
                buildString {
                    append(formatRemindAt(remindAt))
                    if (repeatRule != RepeatRule.NONE) append(" · ${repeatRule.name.lowercase()}")
                },
                style = MaterialTheme.typography.labelMedium,
                color = InkSoft
            )
            if (!description.isNullOrBlank()) {
                Spacer(Modifier.height(2.dp))
                Text(description, style = MaterialTheme.typography.bodySmall, color = InkSoft)
            }
        }
        IconButton(onClick = onComplete) {
            Icon(Icons.Filled.Check, contentDescription = "Mark done", tint = Sage)
        }
        IconButton(onClick = onDelete) {
            Icon(Icons.Filled.Delete, contentDescription = "Delete reminder", tint = StampRed)
        }
    }
}

private fun formatRemindAt(iso: String): String = try {
    LocalDateTime.parse(iso, DateTimeFormatter.ISO_DATE_TIME)
        .format(DateTimeFormatter.ofPattern("dd MMM, h:mm a"))
} catch (e: Exception) {
    iso
}

@Composable
private fun AddReminderDialog(
    saving: Boolean,
    onDismiss: () -> Unit,
    onConfirm: (String, String?, String, RepeatRule) -> Unit
) {
    var title by remember { mutableStateOf("") }
    var description by remember { mutableStateOf("") }
    var date by remember { mutableStateOf("") } // YYYY-MM-DD
    var time by remember { mutableStateOf("") } // HH:MM (24h)
    var repeatRule by remember { mutableStateOf(RepeatRule.NONE) }
    var repeatMenuOpen by remember { mutableStateOf(false) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Add reminder") },
        text = {
            Column {
                OutlinedTextField(value = title, onValueChange = { title = it }, label = { Text("Title, e.g. Take BP medicine") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                Spacer(Modifier.height(10.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    OutlinedTextField(value = date, onValueChange = { date = it }, label = { Text("Date") }, placeholder = { Text("YYYY-MM-DD") }, singleLine = true, modifier = Modifier.weight(1f))
                    OutlinedTextField(value = time, onValueChange = { time = it }, label = { Text("Time") }, placeholder = { Text("HH:MM") }, singleLine = true, modifier = Modifier.weight(1f))
                }
                Spacer(Modifier.height(10.dp))
                Box {
                    OutlinedTextField(
                        value = repeatRule.name.lowercase().replaceFirstChar { it.uppercase() },
                        onValueChange = {}, readOnly = true, label = { Text("Repeat") },
                        modifier = Modifier.fillMaxWidth().clickable { repeatMenuOpen = true }
                    )
                    DropdownMenu(expanded = repeatMenuOpen, onDismissRequest = { repeatMenuOpen = false }) {
                        RepeatRule.entries.forEach { r ->
                            DropdownMenuItem(text = { Text(r.name.lowercase().replaceFirstChar { it.uppercase() }) }, onClick = { repeatRule = r; repeatMenuOpen = false })
                        }
                    }
                }
                Spacer(Modifier.height(10.dp))
                OutlinedTextField(value = description, onValueChange = { description = it }, label = { Text("Notes (optional)") }, modifier = Modifier.fillMaxWidth())
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    val iso = "${date}T${if (time.length == 5) "$time:00" else time}"
                    onConfirm(title, description.ifBlank { null }, iso, repeatRule)
                },
                enabled = title.isNotBlank() && date.isNotBlank() && time.isNotBlank() && !saving
            ) { Text(if (saving) "Saving…" else "Save", color = Navy) }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel", color = InkSoft) } }
    )
}
