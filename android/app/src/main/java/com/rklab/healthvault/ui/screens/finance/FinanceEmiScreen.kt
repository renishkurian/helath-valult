package com.rklab.healthvault.ui.screens.finance

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Add
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.rklab.healthvault.data.model.FinanceAccountOut
import com.rklab.healthvault.data.model.FinanceEmiIn
import com.rklab.healthvault.data.model.FinanceEmiOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.theme.*
import com.rklab.healthvault.util.EmiScheduler
import kotlinx.coroutines.launch
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private val emiDateFmt: DateTimeFormatter = DateTimeFormatter.ofPattern("dd MMM yyyy")
private val RECURRING_KINDS = listOf(
    "emi" to "EMI",
    "chitty" to "Chitty",
    "loan" to "Loan",
    "insurance" to "Insurance",
    "rent" to "Rent",
    "subscription" to "Subscription",
    "other" to "Other"
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FinanceEmiScreen(repository: HealthVaultRepository, onBack: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var filter by remember { mutableStateOf("pending") }
    var kindFilter by remember { mutableStateOf<String?>(null) }
    var items by remember { mutableStateOf<List<FinanceEmiOut>>(emptyList()) }
    var accounts by remember { mutableStateOf<List<FinanceAccountOut>>(emptyList()) }
    var adding by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    fun reload() {
        scope.launch {
            runCatching {
                accounts = repository.listFinanceAccounts()
                items = repository.listFinanceEmis()
                EmiScheduler.scheduleAll(context, items)
            }.onFailure { error = it.message }
        }
    }
    LaunchedEffect(Unit) { reload() }

    val visible = items.filter { emi ->
        val statusOk = when (filter) {
            "completed" -> emi.status == "completed"
            "pending" -> emi.status == "pending" || emi.status == "overdue"
            else -> true
        }
        val kindOk = kindFilter == null || emi.kind == kindFilter
        statusOk && kindOk
    }

    Box(Modifier.fillMaxSize().background(Paper)) {
        Column(Modifier.fillMaxSize()) {
            Row(
                Modifier.fillMaxWidth().padding(4.dp, 4.dp, 16.dp, 8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                IconButton(onClick = onBack) {
                    Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back", tint = Ink)
                }
                Text("Recurring", color = Ink, fontWeight = FontWeight.Bold, fontSize = 22.sp)
            }
            Row(
                Modifier.fillMaxWidth().padding(horizontal = 16.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                listOf("pending" to "Pending", "completed" to "Completed", "all" to "All").forEach { (key, label) ->
                    FilterChip(selected = filter == key, onClick = { filter = key }, label = { Text(label) })
                }
            }
            Row(
                Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                FilterChip(selected = kindFilter == null, onClick = { kindFilter = null }, label = { Text("All tags") })
            }
            RECURRING_KINDS.chunked(4).forEach { row ->
                Row(
                    Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 2.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    row.forEach { (key, label) ->
                        FilterChip(
                            selected = kindFilter == key,
                            onClick = { kindFilter = if (kindFilter == key) null else key },
                            label = { Text(label) }
                        )
                    }
                }
            }
            error?.let { Text(it, color = StampRed, modifier = Modifier.padding(16.dp)) }
            LazyColumn(Modifier.fillMaxSize().padding(top = 8.dp)) {
                items(visible, key = { it.id }) { emi ->
                    EmiRow(
                        emi = emi,
                        onPost = {
                            scope.launch {
                                runCatching { repository.postFinanceEmi(emi.id) }
                                    .onSuccess { reload() }
                                    .onFailure { error = it.message }
                            }
                        },
                        onPause = {
                            scope.launch {
                                runCatching { repository.pauseFinanceEmi(emi.id) }
                                    .onSuccess { reload() }
                                    .onFailure { error = it.message }
                            }
                        },
                        onDelete = {
                            scope.launch {
                                EmiScheduler.cancel(context, emi.id)
                                runCatching { repository.deleteFinanceEmi(emi.id) }
                                reload()
                            }
                        }
                    )
                    HorizontalDivider(color = LineColor)
                }
                if (visible.isEmpty()) {
                    item {
                        Text(
                            when (filter) {
                                "completed" -> "No completed payments in this view."
                                "pending" -> "No pending recurring payments. Tap + to set one up."
                                else -> "No recurring payments yet. Add EMI, chitty, loan, rent…"
                            },
                            color = InkSoft,
                            modifier = Modifier.padding(20.dp)
                        )
                    }
                }
                item { Spacer(Modifier.height(96.dp)) }
            }
        }
        FloatingActionButton(
            onClick = { adding = true },
            modifier = Modifier.align(Alignment.BottomEnd).padding(20.dp),
            containerColor = ExpenseRed,
            contentColor = Color.White,
            shape = CircleShape
        ) { Icon(Icons.Filled.Add, contentDescription = "Add recurring payment") }
    }

    if (adding) {
        EmiAddSheet(
            accounts = accounts,
            onDismiss = { adding = false },
            onSave = { body ->
                scope.launch {
                    runCatching { repository.createFinanceEmi(body) }
                        .onSuccess {
                            adding = false
                            reload()
                        }
                        .onFailure { error = it.message }
                }
            }
        )
    }
}

@Composable
private fun EmiRow(
    emi: FinanceEmiOut,
    onPost: () -> Unit,
    onPause: () -> Unit,
    onDelete: () -> Unit
) {
    val statusColor = when (emi.status) {
        "completed" -> Sage
        "overdue" -> ExpenseRed
        else -> IncomeBlue
    }
    Column(Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 14.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Column(Modifier.weight(1f).padding(end = 12.dp)) {
                Text(emi.name, color = Ink, fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
                Text(
                    "${emi.kind_label} · ${emi.account_name} · day ${emi.day_of_month}",
                    color = InkSoft,
                    style = MaterialTheme.typography.bodySmall
                )
            }
            Text(inr(emi.amount), color = ExpenseRed, fontWeight = FontWeight.Bold)
        }
        Spacer(Modifier.height(8.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(
                "${emi.paid_count} / ${emi.total_installments} paid",
                color = InkSoft,
                style = MaterialTheme.typography.bodySmall
            )
            Text(
                when (emi.status) {
                    "completed" -> "Completed"
                    "overdue" -> "Overdue · ${emi.next_due ?: ""}"
                    else -> "Next ${emi.next_due ?: "—"}"
                },
                color = statusColor,
                style = MaterialTheme.typography.bodySmall,
                fontWeight = FontWeight.SemiBold
            )
        }
        LinearProgressIndicator(
            progress = if (emi.total_installments == 0) 0f else emi.paid_count.toFloat() / emi.total_installments,
            modifier = Modifier.fillMaxWidth().padding(top = 8.dp).height(4.dp).clip(RoundedCornerShape(2.dp)),
            color = statusColor,
            trackColor = LineColor,
        )
        Row(Modifier.padding(top = 4.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (emi.status != "completed" && emi.active) {
                TextButton(onClick = onPost) { Text("Add this month", color = IncomeBlue) }
            }
            TextButton(onClick = onPause) {
                Text(if (emi.active && emi.status != "completed") "Pause" else "Resume", color = InkSoft)
            }
            TextButton(onClick = onDelete) { Text("Remove", color = StampRed) }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun EmiAddSheet(
    accounts: List<FinanceAccountOut>,
    onDismiss: () -> Unit,
    onSave: (FinanceEmiIn) -> Unit
) {
    var name by remember { mutableStateOf("") }
    var kind by remember { mutableStateOf("emi") }
    var amount by remember { mutableStateOf("") }
    var accountId by remember { mutableStateOf(accounts.firstOrNull()?.id) }
    var start by remember { mutableStateOf(LocalDate.now()) }
    var end by remember { mutableStateOf(LocalDate.now().plusMonths(12)) }
    var day by remember { mutableStateOf(LocalDate.now().dayOfMonth.toString()) }
    var notifyDays by remember { mutableStateOf(2) }
    var autoPost by remember { mutableStateOf(true) }
    var picking by remember { mutableStateOf<String?>(null) }
    val zone = ZoneId.systemDefault()
    val datePicker = rememberDatePickerState(
        initialSelectedDateMillis = start.atStartOfDay(zone).toInstant().toEpochMilli()
    )

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = PaperDeep
    ) {
        Column(
            Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(20.dp)
        ) {
            Text("Recurring payment", color = Ink, fontWeight = FontWeight.Bold, fontSize = 20.sp)
            Text("EMI, chitty, loan, rent, and the rest — posted on the due day with a reminder before.", color = InkSoft, style = MaterialTheme.typography.bodySmall)
            Spacer(Modifier.height(16.dp))
            Text("Tag", color = InkSoft, style = MaterialTheme.typography.labelMedium)
            RECURRING_KINDS.chunked(4).forEach { row ->
                Row(Modifier.fillMaxWidth().padding(top = 6.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    row.forEach { (key, label) ->
                        FilterChip(selected = kind == key, onClick = { kind = key }, label = { Text(label) })
                    }
                }
            }
            Spacer(Modifier.height(8.dp))
            OutlinedTextField(value = name, onValueChange = { name = it }, label = { Text("Name") }, modifier = Modifier.fillMaxWidth())
            Spacer(Modifier.height(8.dp))
            OutlinedTextField(
                value = amount,
                onValueChange = { amount = it.filter { ch -> ch.isDigit() || ch == '.' } },
                label = { Text("Monthly amount") },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(Modifier.height(12.dp))
            Text("Account", color = InkSoft, style = MaterialTheme.typography.labelMedium)
            accounts.chunked(3).forEach { row ->
                Row(Modifier.fillMaxWidth().padding(top = 6.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    row.forEach { a ->
                        val on = a.id == accountId
                        Box(
                            Modifier
                                .weight(1f)
                                .heightIn(min = 40.dp)
                                .clip(RoundedCornerShape(8.dp))
                                .border(1.dp, if (on) ExpenseRed else LineColor, RoundedCornerShape(8.dp))
                                .clickable { accountId = a.id }
                                .padding(8.dp),
                            contentAlignment = Alignment.Center
                        ) { Text(a.name, color = Ink) }
                    }
                    repeat(3 - row.size) { Spacer(Modifier.weight(1f)) }
                }
            }
            Spacer(Modifier.height(12.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                DateField("Start", start, Modifier.weight(1f)) { picking = "start" }
                DateField("End", end, Modifier.weight(1f)) { picking = "end" }
            }
            Spacer(Modifier.height(8.dp))
            OutlinedTextField(
                value = day,
                onValueChange = { day = it.filter { ch -> ch.isDigit() }.take(2) },
                label = { Text("Day of each month (1–31)") },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(Modifier.height(12.dp))
            Text("Remind me before due", color = InkSoft, style = MaterialTheme.typography.labelMedium)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 6.dp)) {
                listOf(0, 1, 2, 3, 7).forEach { n ->
                    FilterChip(
                        selected = notifyDays == n,
                        onClick = { notifyDays = n },
                        label = { Text(if (n == 0) "Off" else "$n d") }
                    )
                }
            }
            Row(
                Modifier.fillMaxWidth().padding(top = 8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text("Auto-add on due day", color = Ink, modifier = Modifier.weight(1f))
                Switch(checked = autoPost, onCheckedChange = { autoPost = it })
            }
            Spacer(Modifier.height(16.dp))
            Button(
                onClick = {
                    val acc = accountId ?: return@Button
                    val amt = amount.toDoubleOrNull() ?: 0.0
                    val n = name.trim()
                    if (n.isEmpty() || amt <= 0) return@Button
                    onSave(
                        FinanceEmiIn(
                            name = n,
                            kind = kind,
                            account_id = acc,
                            amount = amt,
                            start_date = start.toString(),
                            end_date = end.toString(),
                            day_of_month = day.toIntOrNull() ?: start.dayOfMonth,
                            auto_post = autoPost,
                            notify_days = notifyDays
                        )
                    )
                },
                modifier = Modifier.fillMaxWidth().height(48.dp),
                colors = ButtonDefaults.buttonColors(containerColor = ExpenseRed),
                shape = RoundedCornerShape(10.dp)
            ) { Text("Save", color = Color.White, fontWeight = FontWeight.Bold) }
            Spacer(Modifier.height(24.dp))
        }
    }

    if (picking != null) {
        DatePickerDialog(
            onDismissRequest = { picking = null },
            confirmButton = {
                TextButton(onClick = {
                    datePicker.selectedDateMillis?.let { ms ->
                        val d = Instant.ofEpochMilli(ms).atZone(zone).toLocalDate()
                        if (picking == "start") {
                            start = d
                            if (end.isBefore(d)) end = d.plusMonths(12)
                            if (day.isBlank()) day = d.dayOfMonth.toString()
                        } else {
                            end = d
                        }
                    }
                    picking = null
                }) { Text("OK") }
            },
            dismissButton = { TextButton(onClick = { picking = null }) { Text("Cancel") } }
        ) { DatePicker(state = datePicker) }
    }
}

@Composable
private fun DateField(label: String, value: LocalDate, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Column(modifier.clickable(onClick = onClick).padding(vertical = 4.dp)) {
        Text(label, color = InkSoft, style = MaterialTheme.typography.labelMedium)
        Text(value.format(emiDateFmt), color = Ink, fontWeight = FontWeight.Medium, modifier = Modifier.padding(top = 4.dp))
        HorizontalDivider(color = LineColor, modifier = Modifier.padding(top = 8.dp))
    }
}
