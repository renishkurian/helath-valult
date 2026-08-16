package com.rklab.healthvault.ui.screens.care

import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.rklab.healthvault.data.model.*
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.theme.*
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

private enum class CareTab { ICE, MEDS, VAX, VISITS, MORE }

@Composable
fun CareScreen(repository: HealthVaultRepository) {
    var personId by remember { mutableStateOf<String?>(null) }
    var people by remember { mutableStateOf<List<PersonOut>>(emptyList()) }
    var tab by remember { mutableStateOf(CareTab.ICE) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(Unit) {
        people = runCatching { repository.listPeople() }.getOrDefault(emptyList())
        personId = repository.activePersonFlow().first() ?: people.firstOrNull()?.id
    }

    Column(Modifier.fillMaxSize().background(HubBg).padding(20.dp)) {
        Text("CARE", style = MaterialTheme.typography.labelMedium, color = VaultGold)
        Spacer(Modifier.height(4.dp))
        Text("Health, not only files", style = MaterialTheme.typography.headlineMedium, color = Ink)
        Spacer(Modifier.height(12.dp))
        ScrollableTabRow(selectedTabIndex = tab.ordinal, containerColor = Paper, edgePadding = 0.dp) {
            CareTab.entries.forEach { t ->
                Tab(selected = tab == t, onClick = { tab = t }, text = { Text(t.name) })
            }
        }
        Spacer(Modifier.height(12.dp))
        val pid = personId
        if (pid == null) {
            Text("Add a family member first.", color = InkSoft)
            return@Column
        }
        when (tab) {
            CareTab.ICE -> IceSection(repository, people.firstOrNull { it.id == pid }, onSaved = {
                scope.launch { people = repository.listPeople() }
            })
            CareTab.MEDS -> MedsSection(repository, pid)
            CareTab.VAX -> VaxSection(repository, pid)
            CareTab.VISITS -> VisitsSection(repository, pid)
            CareTab.MORE -> MoreSection(repository, pid)
        }
    }
}

@Composable
private fun IceSection(repository: HealthVaultRepository, person: PersonOut?, onSaved: () -> Unit) {
    if (person == null) return
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    var allergies by remember(person.id) { mutableStateOf(person.allergies.orEmpty()) }
    var conditions by remember(person.id) { mutableStateOf(person.conditions.orEmpty()) }
    var emName by remember(person.id) { mutableStateOf(person.emergency_name.orEmpty()) }
    var emPhone by remember(person.id) { mutableStateOf(person.emergency_phone.orEmpty()) }
    var abha by remember(person.id) { mutableStateOf(person.abha_id.orEmpty()) }
    var ayushman by remember(person.id) { mutableStateOf(person.ayushman_id.orEmpty()) }
    var msg by remember { mutableStateOf<String?>(null) }
    val iceUrl = person.ice_token?.let { repository.getServerUrl()?.trimEnd('/') + "/ice/$it" }

    Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text(person.name, color = Ink, style = MaterialTheme.typography.titleMedium)
        if (iceUrl != null) {
            Text(iceUrl, color = InkSoft, style = MaterialTheme.typography.bodySmall)
            Button(onClick = {
                context.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply {
                    type = "text/plain"
                    putExtra(Intent.EXTRA_TEXT, "ICE card for ${person.name}: $iceUrl")
                }, "Share ICE card"))
            }, colors = ButtonDefaults.buttonColors(containerColor = Navy)) { Text("Share ICE / WhatsApp", color = TextDark) }
        }
        OutlinedTextField(allergies, { allergies = it }, label = { Text("Allergies") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(conditions, { conditions = it }, label = { Text("Conditions") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(emName, { emName = it }, label = { Text("Emergency contact") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(emPhone, { emPhone = it }, label = { Text("Emergency phone") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(abha, { abha = it }, label = { Text("ABHA ID") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(ayushman, { ayushman = it }, label = { Text("Ayushman ID") }, modifier = Modifier.fillMaxWidth())
        Button(onClick = {
            scope.launch {
                runCatching {
                    repository.updatePerson(person.id, PersonUpdate(allergies, conditions, emName, emPhone, abha, ayushman))
                    repository.enableIce(person.id)
                    msg = "Saved"
                    onSaved()
                }.onFailure { msg = it.message }
            }
        }, colors = ButtonDefaults.buttonColors(containerColor = Navy)) { Text("Save ICE card", color = TextDark) }
        if (msg != null) Text(msg!!, color = Sage)
        Spacer(Modifier.height(40.dp))
    }
}

@Composable
private fun MedsSection(repository: HealthVaultRepository, personId: String) {
    val scope = rememberCoroutineScope()
    var items by remember { mutableStateOf<List<MedicineOut>>(emptyList()) }
    var name by remember { mutableStateOf("") }
    var dose by remember { mutableStateOf("") }
    var remaining by remember { mutableStateOf("") }
    LaunchedEffect(personId) { items = runCatching { repository.listMedicines(personId) }.getOrDefault(emptyList()) }
    Column {
        items.forEach { m ->
            Text("${m.name}  ·  ${m.dose ?: ""}  ·  left ${m.remaining ?: "—"}", color = Ink, modifier = Modifier.padding(vertical = 6.dp))
        }
        OutlinedTextField(name, { name = it }, label = { Text("Medicine") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(dose, { dose = it }, label = { Text("Dose") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(remaining, { remaining = it }, label = { Text("Remaining count") }, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(8.dp))
        Button(onClick = {
            scope.launch {
                repository.addMedicine(MedicineIn(personId, name, dose.ifBlank { null }, remaining = remaining.toIntOrNull()))
                items = repository.listMedicines(personId)
                name = ""; dose = ""; remaining = ""
            }
        }, enabled = name.isNotBlank() && !repository.isViewer, colors = ButtonDefaults.buttonColors(containerColor = Navy)) {
            Text("Add medicine", color = TextDark)
        }
    }
}

@Composable
private fun VaxSection(repository: HealthVaultRepository, personId: String) {
    val scope = rememberCoroutineScope()
    var items by remember { mutableStateOf<List<VaccinationOut>>(emptyList()) }
    var name by remember { mutableStateOf("") }
    var due by remember { mutableStateOf("") }
    LaunchedEffect(personId) { items = runCatching { repository.listVaccinations(personId) }.getOrDefault(emptyList()) }
    Column {
        items.forEach { v ->
            Text("${v.vaccine_name}  ·  next ${v.next_due ?: "—"}" + if (v.overdue) "  OVERDUE" else "", color = if (v.overdue) StampRed else Ink, modifier = Modifier.padding(vertical = 6.dp))
        }
        OutlinedTextField(name, { name = it }, label = { Text("Vaccine") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(due, { due = it }, label = { Text("Next due YYYY-MM-DD") }, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(8.dp))
        Button(onClick = {
            scope.launch {
                repository.addVaccination(VaccinationIn(personId, name, next_due = due.ifBlank { null }))
                items = repository.listVaccinations(personId)
                name = ""; due = ""
            }
        }, enabled = name.isNotBlank() && !repository.isViewer, colors = ButtonDefaults.buttonColors(containerColor = Navy)) {
            Text("Add vaccination", color = TextDark)
        }
    }
}

@Composable
private fun VisitsSection(repository: HealthVaultRepository, personId: String) {
    val scope = rememberCoroutineScope()
    var visits by remember { mutableStateOf<List<VisitOut>>(emptyList()) }
    var claims by remember { mutableStateOf<List<ClaimOut>>(emptyList()) }
    var spend by remember { mutableStateOf<SpendOut?>(null) }
    var hospital by remember { mutableStateOf("") }
    var reason by remember { mutableStateOf("") }
    var insurer by remember { mutableStateOf("") }
    var amount by remember { mutableStateOf("") }
    LaunchedEffect(personId) {
        visits = runCatching { repository.listVisits(personId) }.getOrDefault(emptyList())
        claims = runCatching { repository.listClaims(personId) }.getOrDefault(emptyList())
        spend = runCatching { repository.yearlySpend(personId) }.getOrNull()
    }
    Column(Modifier.verticalScroll(rememberScrollState())) {
        if (spend != null) Text("This year: bills ${spend!!.bills} + claims ${spend!!.claims} = ${spend!!.total}", color = InkSoft)
        Spacer(Modifier.height(8.dp))
        Text("VISITS", style = MaterialTheme.typography.labelMedium, color = VaultGold)
        visits.forEach { Text("${it.visit_date ?: ""}  ${it.hospital_name ?: ""}  ${it.reason ?: ""}", color = Ink, modifier = Modifier.padding(vertical = 4.dp)) }
        OutlinedTextField(hospital, { hospital = it }, label = { Text("Hospital") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(reason, { reason = it }, label = { Text("Reason") }, modifier = Modifier.fillMaxWidth())
        Button(onClick = {
            scope.launch {
                repository.addVisit(VisitIn(personId, hospital.ifBlank { null }, reason = reason.ifBlank { null }))
                visits = repository.listVisits(personId)
            }
        }, enabled = !repository.isViewer, colors = ButtonDefaults.buttonColors(containerColor = Navy)) { Text("Add visit", color = TextDark) }
        Spacer(Modifier.height(16.dp))
        Text("CLAIMS", style = MaterialTheme.typography.labelMedium, color = VaultGold)
        claims.forEach { Text("${it.insurer ?: "—"}  ${it.amount ?: ""}  ${it.status}", color = Ink, modifier = Modifier.padding(vertical = 4.dp)) }
        OutlinedTextField(insurer, { insurer = it }, label = { Text("Insurer") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(amount, { amount = it }, label = { Text("Amount") }, modifier = Modifier.fillMaxWidth())
        Button(onClick = {
            scope.launch {
                repository.addClaim(ClaimIn(personId, insurer = insurer.ifBlank { null }, amount = amount.ifBlank { null }))
                claims = repository.listClaims(personId)
                spend = runCatching { repository.yearlySpend(personId) }.getOrNull()
            }
        }, enabled = !repository.isViewer, colors = ButtonDefaults.buttonColors(containerColor = Navy)) { Text("Add claim", color = TextDark) }
        Spacer(Modifier.height(40.dp))
    }
}

@Composable
private fun MoreSection(repository: HealthVaultRepository, personId: String) {
    val scope = rememberCoroutineScope()
    var doctors by remember { mutableStateOf<List<DoctorOut>>(emptyList()) }
    var growth by remember { mutableStateOf<List<GrowthOut>>(emptyList()) }
    var timeline by remember { mutableStateOf<List<TimelineItem>>(emptyList()) }
    var alerts by remember { mutableStateOf<List<LabAlert>>(emptyList()) }
    var height by remember { mutableStateOf("") }
    var weight by remember { mutableStateOf("") }
    var measured by remember { mutableStateOf("") }
    LaunchedEffect(personId) {
        doctors = runCatching { repository.listDoctors() }.getOrDefault(emptyList())
        growth = runCatching { repository.listGrowth(personId) }.getOrDefault(emptyList())
        timeline = runCatching { repository.timeline(personId) }.getOrDefault(emptyList())
        alerts = runCatching { repository.labAlerts(personId) }.getOrDefault(emptyList())
    }
    Column(Modifier.verticalScroll(rememberScrollState())) {
        alerts.forEach { Text(it.message, color = Mustard, modifier = Modifier.padding(vertical = 4.dp)) }
        Text("DOCTORS", style = MaterialTheme.typography.labelMedium, color = VaultGold)
        doctors.forEach {
            Text("${it.name}  ${it.specialty ?: ""}  ${it.phone ?: ""}", color = Ink, modifier = Modifier.padding(vertical = 4.dp))
        }
        Text("Use the Doctors tab for call & WhatsApp cards.", color = InkSoft, style = MaterialTheme.typography.bodySmall)
        Spacer(Modifier.height(12.dp))
        Text("GROWTH", style = MaterialTheme.typography.labelMedium, color = VaultGold)
        growth.forEach { Text("${it.measured_at}  ${it.height_cm ?: "—"} cm  ${it.weight_kg ?: "—"} kg", color = Ink, modifier = Modifier.padding(vertical = 4.dp)) }
        OutlinedTextField(measured, { measured = it }, label = { Text("Date YYYY-MM-DD") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(height, { height = it }, label = { Text("Height cm") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(weight, { weight = it }, label = { Text("Weight kg") }, modifier = Modifier.fillMaxWidth())
        Button(onClick = {
            scope.launch {
                repository.addGrowth(GrowthIn(personId, measured, height.ifBlank { null }, weight.ifBlank { null }))
                growth = repository.listGrowth(personId)
            }
        }, enabled = measured.isNotBlank() && !repository.isViewer, colors = ButtonDefaults.buttonColors(containerColor = Navy)) { Text("Add reading", color = TextDark) }
        Spacer(Modifier.height(12.dp))
        Text("TIMELINE", style = MaterialTheme.typography.labelMedium, color = VaultGold)
        timeline.take(20).forEach {
            Text("${it.at.take(10)}  ${it.kind}  ${it.title}", color = Ink, modifier = Modifier.padding(vertical = 3.dp))
        }
        Spacer(Modifier.height(40.dp))
    }
}
