package com.rklab.healthvault.ui.screens.doctors

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Call
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.LocalHospital
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.rklab.healthvault.data.model.DoctorIn
import com.rklab.healthvault.data.model.DoctorOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.theme.*
import kotlinx.coroutines.launch

private val WaGreen = Color(0xFF25D366)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DoctorsScreen(repository: HealthVaultRepository) {
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    var doctors by remember { mutableStateOf<List<DoctorOut>>(emptyList()) }
    val hospitals by repository.getAllHospitals().collectAsState(initial = emptyList())
    var loading by remember { mutableStateOf(true) }
    var showAdd by remember { mutableStateOf(false) }
    var filterHospital by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        doctors = runCatching { repository.listDoctors() }.getOrDefault(emptyList())
        loading = false
    }

    val visible = remember(doctors, filterHospital) {
        if (filterHospital.isNullOrBlank()) doctors
        else doctors.filter { it.hospital_name.equals(filterHospital, ignoreCase = true) }
    }

    Box(modifier = Modifier.fillMaxSize().background(HubBg)) {
        Column(modifier = Modifier.fillMaxSize().padding(20.dp)) {
            Text("DOCTORS", style = MaterialTheme.typography.labelMedium, color = VaultGold)
            Spacer(Modifier.height(4.dp))
            Text("Call & WhatsApp", style = MaterialTheme.typography.headlineMedium, color = Ink)
            Text("Each doctor belongs to a hospital", color = InkSoft, style = MaterialTheme.typography.bodyMedium)
            Spacer(Modifier.height(14.dp))

            if (hospitals.isNotEmpty()) {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState())
                ) {
                    FilterChip(
                        selected = filterHospital == null,
                        onClick = { filterHospital = null },
                        label = { Text("All") }
                    )
                    hospitals.forEach { h ->
                        FilterChip(
                            selected = filterHospital.equals(h, ignoreCase = true),
                            onClick = { filterHospital = h },
                            label = { Text(h, maxLines = 1) }
                        )
                    }
                }
                Spacer(Modifier.height(12.dp))
            }

            when {
                loading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = Navy)
                }
                visible.isEmpty() -> Text(
                    if (filterHospital != null) "No doctors for this hospital." else "No doctors yet. Tap + to add one.",
                    color = InkSoft
                )
                else -> LazyColumn(
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                    contentPadding = PaddingValues(bottom = 96.dp)
                ) {
                    items(visible, key = { it.id }) { doc ->
                        DoctorBizCard(
                            doctor = doc,
                            onCall = {
                                val digits = phoneDigits(doc.phone)
                                if (digits.isNotEmpty()) {
                                    context.startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:$digits")))
                                }
                            },
                            onWhatsApp = {
                                val digits = phoneDigits(doc.phone)
                                if (digits.isNotEmpty()) {
                                    context.startActivity(
                                        Intent(Intent.ACTION_VIEW, Uri.parse("https://wa.me/$digits"))
                                    )
                                }
                            },
                            onDelete = {
                                scope.launch {
                                    runCatching { repository.deleteDoctor(doc.id) }
                                    doctors = runCatching { repository.listDoctors() }.getOrDefault(emptyList())
                                }
                            },
                            canEdit = !repository.isViewer
                        )
                    }
                }
            }
        }

        if (!repository.isViewer) {
            FloatingActionButton(
                onClick = { showAdd = true },
                containerColor = Navy,
                contentColor = TextDark,
                modifier = Modifier.align(Alignment.BottomEnd).padding(20.dp)
            ) { Icon(Icons.Filled.Add, contentDescription = "Add doctor") }
        }
    }

    if (showAdd) {
        AddDoctorDialog(
            hospitals = hospitals,
            onDismiss = { showAdd = false },
            onSave = { name, specialty, hospital, phone, notes ->
                scope.launch {
                    runCatching {
                        repository.addDoctor(
                            DoctorIn(
                                name = name,
                                specialty = specialty.ifBlank { null },
                                hospital_name = hospital,
                                phone = phone,
                                notes = notes.ifBlank { null }
                            )
                        )
                    }
                    doctors = runCatching { repository.listDoctors() }.getOrDefault(emptyList())
                    showAdd = false
                }
            }
        )
    }
}

@Composable
private fun DoctorBizCard(
    doctor: DoctorOut,
    onCall: () -> Unit,
    onWhatsApp: () -> Unit,
    onDelete: () -> Unit,
    canEdit: Boolean
) {
    val hasPhone = phoneDigits(doctor.phone).isNotEmpty()
    Card(
        shape = RoundedCornerShape(18.dp),
        colors = CardDefaults.cardColors(containerColor = HubDock),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(Modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Box(
                    modifier = Modifier
                        .size(48.dp)
                        .clip(RoundedCornerShape(14.dp))
                        .background(Sage),
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        (doctor.name.firstOrNull()?.uppercaseChar() ?: '?').toString(),
                        color = TextDark,
                        fontWeight = FontWeight.Bold,
                        style = MaterialTheme.typography.titleMedium
                    )
                }
                Column(modifier = Modifier.weight(1f)) {
                    Text(doctor.name, color = Ink, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.titleMedium)
                    Text(doctor.specialty ?: "Doctor", color = InkSoft, style = MaterialTheme.typography.bodySmall)
                }
                if (canEdit) {
                    IconButton(onClick = onDelete) {
                        Icon(Icons.Filled.Delete, contentDescription = "Remove", tint = InkSoft)
                    }
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Icon(Icons.Filled.LocalHospital, contentDescription = null, tint = InkSoft, modifier = Modifier.size(16.dp))
                Text(doctor.hospital_name ?: "—", color = InkSoft, style = MaterialTheme.typography.bodyMedium)
            }
            if (!doctor.phone.isNullOrBlank()) {
                Text(doctor.phone!!, color = VaultGold, style = MaterialTheme.typography.bodyLarge, fontWeight = FontWeight.Medium)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                Button(
                    onClick = onCall,
                    enabled = hasPhone,
                    colors = ButtonDefaults.buttonColors(containerColor = Sage, contentColor = TextDark),
                    modifier = Modifier.weight(1f).height(48.dp)
                ) {
                    Icon(Icons.Filled.Call, contentDescription = null, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("Call")
                }
                Button(
                    onClick = onWhatsApp,
                    enabled = hasPhone,
                    colors = ButtonDefaults.buttonColors(containerColor = WaGreen, contentColor = Color.White),
                    modifier = Modifier.weight(1f).height(48.dp)
                ) {
                    Text("WhatsApp")
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AddDoctorDialog(
    hospitals: List<String>,
    onDismiss: () -> Unit,
    onSave: (name: String, specialty: String, hospital: String, phone: String, notes: String) -> Unit
) {
    var name by remember { mutableStateOf("") }
    var specialty by remember { mutableStateOf("") }
    var hospital by remember { mutableStateOf(hospitals.firstOrNull().orEmpty()) }
    var hospitalOther by remember { mutableStateOf("") }
    var phone by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }
    var hospitalExpanded by remember { mutableStateOf(false) }

    LaunchedEffect(hospitals) {
        if (hospital.isBlank() && hospitals.isNotEmpty()) hospital = hospitals.first()
    }

    val resolvedHospital = if (hospitals.isEmpty()) hospitalOther.trim() else hospital.trim()
    val canSave = name.isNotBlank() && resolvedHospital.isNotBlank() && phone.isNotBlank()

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Add doctor") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedTextField(name, { name = it }, label = { Text("Name") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(specialty, { specialty = it }, label = { Text("Specialty") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                if (hospitals.isEmpty()) {
                    OutlinedTextField(
                        hospitalOther, { hospitalOther = it },
                        label = { Text("Hospital") }, singleLine = true, modifier = Modifier.fillMaxWidth()
                    )
                } else {
                    ExposedDropdownMenuBox(expanded = hospitalExpanded, onExpandedChange = { hospitalExpanded = it }) {
                        OutlinedTextField(
                            value = hospital,
                            onValueChange = {},
                            readOnly = true,
                            label = { Text("Hospital") },
                            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = hospitalExpanded) },
                            modifier = Modifier.menuAnchor().fillMaxWidth()
                        )
                        ExposedDropdownMenu(expanded = hospitalExpanded, onDismissRequest = { hospitalExpanded = false }) {
                            hospitals.forEach { h ->
                                DropdownMenuItem(
                                    text = { Text(h) },
                                    onClick = { hospital = h; hospitalExpanded = false }
                                )
                            }
                        }
                    }
                }
                OutlinedTextField(phone, { phone = it }, label = { Text("Phone") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(notes, { notes = it }, label = { Text("Notes") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            }
        },
        confirmButton = {
            TextButton(onClick = { onSave(name.trim(), specialty.trim(), resolvedHospital, phone.trim(), notes.trim()) }, enabled = canSave) {
                Text("Save")
            }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } }
    )
}

private fun phoneDigits(phone: String?): String =
    phone?.filter { it.isDigit() }.orEmpty()
