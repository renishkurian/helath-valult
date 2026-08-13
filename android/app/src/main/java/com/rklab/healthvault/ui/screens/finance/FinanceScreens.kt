package com.rklab.healthvault.ui.screens.finance

import android.Manifest
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Apps
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.rklab.healthvault.data.model.*
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.theme.*
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

private val ExpenseRed = Color(0xFFFF6B7A)
private val IncomeBlue = Color(0xFF5B9CFF)
private val monthFmt: DateTimeFormatter = DateTimeFormatter.ofPattern("yyyy-MM")

private fun inr(n: Double): String {
    val sign = if (n < 0) "-" else ""
    val abs = kotlin.math.abs(n)
    val raw = String.format(Locale.US, "%.2f", abs)
    val parts = raw.split(".")
    val whole = parts[0]
    val frac = parts.getOrElse(1) { "00" }
    val body = if (whole.length <= 3) whole else {
        val last3 = whole.takeLast(3)
        var rest = whole.dropLast(3)
        val chunks = mutableListOf<String>()
        while (rest.isNotEmpty()) {
            chunks.add(0, rest.takeLast(2))
            rest = rest.dropLast(2)
        }
        (chunks + last3).joinToString(",")
    }
    return "${sign}₹ $body.$frac"
}

@Composable
fun FinanceTransScreen(
    repository: HealthVaultRepository,
    onAdd: () -> Unit,
    onOpenModules: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val month = remember { LocalDate.now().format(monthFmt) }
    var summary by remember { mutableStateOf<FinanceSummaryOut?>(null) }
    var items by remember { mutableStateOf<List<FinanceTxnOut>>(emptyList()) }
    var error by remember { mutableStateOf<String?>(null) }

    fun reload() {
        scope.launch {
            runCatching {
                summary = repository.financeSummary(month)
                items = repository.listFinanceTransactions(month)
            }.onFailure { error = it.message }
        }
    }
    LaunchedEffect(Unit) {
        reload()
        FinanceSmsIngestor.scanInbox(context)
    }

    Box(Modifier.fillMaxSize().background(Paper)) {
        Column(Modifier.fillMaxSize()) {
            Row(
                Modifier.fillMaxWidth().padding(20.dp, 16.dp, 8.dp, 8.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text("MONEY MANAGER", style = MaterialTheme.typography.labelMedium, color = InkSoft)
                    Text("Daily", style = MaterialTheme.typography.headlineMedium, color = Ink, fontWeight = FontWeight.Bold)
                }
                IconButton(onClick = onOpenModules) {
                    Icon(Icons.Filled.Apps, contentDescription = "Modules", tint = InkSoft)
                }
            }
            IncomingSmsBanner(onChanged = { reload() })
            summary?.let { s ->
                Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    SummaryChip("Income", inr(s.income), IncomeBlue, Modifier.weight(1f))
                    SummaryChip("Expenses", inr(s.expense), ExpenseRed, Modifier.weight(1f))
                    SummaryChip("Total", inr(s.total), Ink, Modifier.weight(1f))
                }
            }
            error?.let { Text(it, color = StampRed, modifier = Modifier.padding(16.dp)) }
            LazyColumn(Modifier.fillMaxSize().padding(16.dp)) {
                items(items, key = { it.id }) { t ->
                    Row(
                        Modifier.fillMaxWidth().padding(vertical = 10.dp),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Column(Modifier.weight(1f)) {
                            Text(t.category_name ?: t.txn_type, color = InkSoft, style = MaterialTheme.typography.labelMedium)
                            Text(t.payee ?: t.description ?: "—", color = Ink, fontWeight = FontWeight.SemiBold)
                            Text(t.account_name, color = InkSoft, style = MaterialTheme.typography.bodySmall)
                        }
                        Text(
                            inr(t.amount),
                            color = when (t.txn_type) { "income" -> IncomeBlue; "expense" -> ExpenseRed; else -> Ink },
                            fontWeight = FontWeight.Bold
                        )
                    }
                    HorizontalDivider(color = LineColor)
                }
            }
        }
        FloatingActionButton(
            onClick = onAdd,
            modifier = Modifier.align(Alignment.BottomEnd).padding(20.dp),
            containerColor = ExpenseRed,
            contentColor = Color.White,
            shape = CircleShape
        ) { Icon(Icons.Filled.Add, contentDescription = "Add") }
    }
}

@Composable
private fun SummaryChip(label: String, value: String, color: Color, modifier: Modifier = Modifier) {
    Column(
        modifier.clip(RoundedCornerShape(14.dp)).background(White).padding(12.dp)
    ) {
        Text(label.uppercase(), color = InkSoft, style = MaterialTheme.typography.labelSmall)
        Spacer(Modifier.height(4.dp))
        Text(value, color = color, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyLarge)
    }
}

@Composable
fun FinanceStatsScreen(repository: HealthVaultRepository) {
    val scope = rememberCoroutineScope()
    val month = remember { LocalDate.now().format(monthFmt) }
    var kind by remember { mutableStateOf("expense") }
    var report by remember { mutableStateOf<FinanceReportOut?>(null) }
    LaunchedEffect(kind) {
        scope.launch { runCatching { report = repository.financeReports(month, kind) } }
    }
    Column(Modifier.fillMaxSize().background(Paper).padding(20.dp)) {
        Text("Stats", style = MaterialTheme.typography.headlineMedium, color = Ink, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(12.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(selected = kind == "income", onClick = { kind = "income" }, label = { Text("Income") })
            FilterChip(selected = kind == "expense", onClick = { kind = "expense" }, label = { Text("Expenses") })
        }
        Spacer(Modifier.height(16.dp))
        Text(inr(report?.total ?: 0.0), color = if (kind == "income") IncomeBlue else ExpenseRed, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(16.dp))
        LazyColumn {
            items(report?.rows ?: emptyList()) { row ->
                Row(Modifier.fillMaxWidth().padding(vertical = 10.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text("${row.pct.toInt()}%  ${row.name}", color = Ink)
                    Text(inr(row.amount), color = Ink, fontWeight = FontWeight.SemiBold)
                }
                HorizontalDivider(color = LineColor)
            }
        }
    }
}

@Composable
fun FinanceAccountsScreen(repository: HealthVaultRepository) {
    val scope = rememberCoroutineScope()
    var summary by remember { mutableStateOf<FinanceSummaryOut?>(null) }
    var accounts by remember { mutableStateOf<List<FinanceAccountOut>>(emptyList()) }
    var name by remember { mutableStateOf("") }
    LaunchedEffect(Unit) {
        scope.launch {
            runCatching {
                summary = repository.financeSummary()
                accounts = repository.listFinanceAccounts()
            }
        }
    }
    Column(Modifier.fillMaxSize().background(Paper).padding(20.dp)) {
        Text("Accounts", style = MaterialTheme.typography.headlineMedium, color = Ink, fontWeight = FontWeight.Bold)
        summary?.let { s ->
            Spacer(Modifier.height(12.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                SummaryChip("Assets", inr(s.assets), IncomeBlue, Modifier.weight(1f))
                SummaryChip("Liabilities", inr(s.liabilities), ExpenseRed, Modifier.weight(1f))
            }
            Spacer(Modifier.height(8.dp))
            Text("Total  ${inr(s.net)}", color = Ink, fontWeight = FontWeight.Bold)
        }
        Spacer(Modifier.height(16.dp))
        LazyColumn(Modifier.weight(1f)) {
            items(accounts, key = { it.id }) { a ->
                Row(Modifier.fillMaxWidth().padding(vertical = 10.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                    Column {
                        Text(a.name, color = Ink, fontWeight = FontWeight.SemiBold)
                        Text(a.account_type.replace('_', ' '), color = InkSoft, style = MaterialTheme.typography.bodySmall)
                    }
                    Text(inr(a.balance), color = if (a.is_liability || a.balance < 0) ExpenseRed else IncomeBlue, fontWeight = FontWeight.Bold)
                }
                HorizontalDivider(color = LineColor)
            }
        }
        OutlinedTextField(value = name, onValueChange = { name = it }, label = { Text("New account") }, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(8.dp))
        Button(
            onClick = {
                val n = name.trim(); if (n.isEmpty()) return@Button
                scope.launch {
                    runCatching { repository.createFinanceAccount(FinanceAccountIn(n)) }
                    name = ""
                    accounts = repository.listFinanceAccounts()
                    summary = repository.financeSummary()
                }
            },
            colors = ButtonDefaults.buttonColors(containerColor = Navy)
        ) { Text("Save account") }
    }
}

@Composable
fun FinanceMoreScreen(
    repository: HealthVaultRepository,
    onOpenModules: () -> Unit,
    onOpenInbox: () -> Unit
) {
    Column(Modifier.fillMaxSize().background(Paper).padding(20.dp)) {
        Text("Settings", style = MaterialTheme.typography.headlineMedium, color = Ink, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(20.dp))
        IncomingSmsToggle()
        Spacer(Modifier.height(8.dp))
        MoreRow("AI & SMS inbox", "Review pending tags or paste a message") { onOpenInbox() }
        MoreRow("Switch module", "Health / Passwords / Money") { onOpenModules() }
    }
}

@Composable
private fun IncomingSmsToggle() {
    val context = LocalContext.current
    var enabled by remember {
        mutableStateOf(FinanceSmsPrefs.isEnabled(context) && FinanceSmsPrefs.hasSmsPermission(context))
    }
    val launcher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { grants ->
        val ok = grants[Manifest.permission.READ_SMS] == true &&
            grants[Manifest.permission.RECEIVE_SMS] == true
        FinanceSmsPrefs.setEnabled(context, ok)
        enabled = ok
        if (ok) FinanceSmsIngestor.scanInbox(context)
    }
    val perms = buildList {
        add(Manifest.permission.READ_SMS)
        add(Manifest.permission.RECEIVE_SMS)
        if (Build.VERSION.SDK_INT >= 33) add(Manifest.permission.POST_NOTIFICATIONS)
    }
    Row(
        Modifier.fillMaxWidth().padding(vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(Modifier.weight(1f).padding(end = 12.dp)) {
            Text("Incoming SMS", color = Ink, fontWeight = FontWeight.SemiBold)
            Text(
                "Bank and UPI alerts are tagged as they arrive. Keep the app unrestricted in battery settings.",
                color = InkSoft,
                style = MaterialTheme.typography.bodySmall
            )
        }
        Switch(
            checked = enabled,
            onCheckedChange = { on ->
                if (on) {
                    if (FinanceSmsPrefs.hasSmsPermission(context)) {
                        FinanceSmsPrefs.setEnabled(context, true)
                        enabled = true
                        FinanceSmsIngestor.scanInbox(context)
                    } else {
                        launcher.launch(perms.toTypedArray())
                    }
                } else {
                    FinanceSmsPrefs.setEnabled(context, false)
                    enabled = false
                }
            }
        )
    }
}

@Composable
private fun IncomingSmsBanner(onChanged: () -> Unit) {
    val context = LocalContext.current
    var enabled by remember {
        mutableStateOf(FinanceSmsPrefs.isEnabled(context) && FinanceSmsPrefs.hasSmsPermission(context))
    }
    if (enabled) return
    val launcher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { grants ->
        val ok = grants[Manifest.permission.READ_SMS] == true &&
            grants[Manifest.permission.RECEIVE_SMS] == true
        FinanceSmsPrefs.setEnabled(context, ok)
        enabled = ok
        if (ok) {
            FinanceSmsIngestor.scanInbox(context)
            onChanged()
        }
    }
    val perms = buildList {
        add(Manifest.permission.READ_SMS)
        add(Manifest.permission.RECEIVE_SMS)
        if (Build.VERSION.SDK_INT >= 33) add(Manifest.permission.POST_NOTIFICATIONS)
    }
    Row(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 4.dp)
            .clip(RoundedCornerShape(14.dp))
            .background(White)
            .clickable { launcher.launch(perms.toTypedArray()) }
            .padding(14.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(Modifier.weight(1f)) {
            Text("Read incoming SMS", color = Ink, fontWeight = FontWeight.SemiBold)
            Text("Allow SMS so bank alerts tag themselves", color = InkSoft, style = MaterialTheme.typography.bodySmall)
        }
        Text("Allow", color = IncomeBlue, fontWeight = FontWeight.Bold)
    }
}

@Composable
private fun MoreRow(title: String, subtitle: String, onClick: () -> Unit) {
    Column(Modifier.fillMaxWidth().clickable(onClick = onClick).padding(vertical = 14.dp)) {
        Text(title, color = Ink, fontWeight = FontWeight.SemiBold)
        Text(subtitle, color = InkSoft, style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
fun FinanceAddScreen(repository: HealthVaultRepository, onDone: () -> Unit) {
    val scope = rememberCoroutineScope()
    var accounts by remember { mutableStateOf<List<FinanceAccountOut>>(emptyList()) }
    var categories by remember { mutableStateOf<List<FinanceCategoryOut>>(emptyList()) }
    var txnType by remember { mutableStateOf("expense") }
    var accountId by remember { mutableStateOf<String?>(null) }
    var categoryId by remember { mutableStateOf<String?>(null) }
    var amount by remember { mutableStateOf("") }
    var payee by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) {
        scope.launch {
            accounts = repository.listFinanceAccounts()
            categories = repository.listFinanceCategories()
            accountId = accounts.firstOrNull()?.id
            categoryId = categories.firstOrNull { it.kind == txnType }?.id
        }
    }
    LaunchedEffect(txnType, categories) {
        categoryId = categories.firstOrNull { it.kind == txnType }?.id
    }
    Column(Modifier.fillMaxSize().background(Paper).padding(20.dp)) {
        Text(txnType.replaceFirstChar { it.uppercase() }, style = MaterialTheme.typography.headlineMedium, color = Ink, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(12.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("income", "expense", "transfer").forEach { t ->
                FilterChip(selected = txnType == t, onClick = { txnType = t }, label = { Text(t.replaceFirstChar { it.uppercase() }) })
            }
        }
        Spacer(Modifier.height(12.dp))
        accounts.chunked(3).forEach { row ->
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                row.forEach { a ->
                    FilterChip(selected = accountId == a.id, onClick = { accountId = a.id }, label = { Text(a.name) }, modifier = Modifier.weight(1f))
                }
                repeat(3 - row.size) { Spacer(Modifier.weight(1f)) }
            }
        }
        Spacer(Modifier.height(8.dp))
        if (txnType != "transfer") {
            categories.filter { it.kind == txnType }.chunked(3).forEach { row ->
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                    row.forEach { c ->
                        FilterChip(selected = categoryId == c.id, onClick = { categoryId = c.id }, label = { Text(c.name) }, modifier = Modifier.weight(1f))
                    }
                    repeat(3 - row.size) { Spacer(Modifier.weight(1f)) }
                }
            }
        }
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(value = amount, onValueChange = { amount = it }, label = { Text("Amount") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(value = payee, onValueChange = { payee = it }, label = { Text("Note") }, modifier = Modifier.fillMaxWidth())
        error?.let { Text(it, color = StampRed, modifier = Modifier.padding(top = 8.dp)) }
        Spacer(Modifier.height(16.dp))
        Button(
            onClick = {
                val acc = accountId ?: return@Button
                val amt = amount.toDoubleOrNull() ?: 0.0
                if (amt <= 0) { error = "Enter an amount"; return@Button }
                scope.launch {
                    runCatching {
                        repository.createFinanceTransaction(
                            FinanceTxnIn(
                                account_id = acc,
                                to_account_id = if (txnType == "transfer") accounts.firstOrNull { it.id != acc }?.id else null,
                                category_id = if (txnType == "transfer") null else categoryId,
                                txn_type = txnType,
                                amount = amt,
                                txn_date = LocalDate.now().toString(),
                                payee = payee.ifBlank { null }
                            )
                        )
                    }.onSuccess { onDone() }.onFailure { error = it.message }
                }
            },
            colors = ButtonDefaults.buttonColors(containerColor = if (txnType == "income") IncomeBlue else ExpenseRed)
        ) { Text("Save") }
    }
}

@Composable
fun FinanceInboxScreen(repository: HealthVaultRepository, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    var text by remember { mutableStateOf("") }
    var messages by remember { mutableStateOf<List<FinanceMessageOut>>(emptyList()) }
    var error by remember { mutableStateOf<String?>(null) }
    fun reload() { scope.launch { runCatching { messages = repository.listFinanceMessages() } } }
    LaunchedEffect(Unit) { reload() }
    Column(Modifier.fillMaxSize().background(Paper).padding(20.dp)) {
        TextButton(onClick = onBack) { Text("← More", color = InkSoft) }
        Text("AI & SMS", style = MaterialTheme.typography.headlineMedium, color = Ink, fontWeight = FontWeight.Bold)
        Text(
            "Incoming bank SMS is tagged automatically when SMS is allowed. Paste here only if a message was missed.",
            color = InkSoft,
            style = MaterialTheme.typography.bodySmall
        )
        Spacer(Modifier.height(8.dp))
        IncomingSmsToggle()
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(value = text, onValueChange = { text = it }, label = { Text("Paste bank / UPI message") }, modifier = Modifier.fillMaxWidth(), minLines = 4)
        Spacer(Modifier.height(8.dp))
        Button(onClick = {
            scope.launch {
                runCatching { repository.ingestFinanceMessages(FinanceMessageIn(text)) }
                    .onSuccess { text = ""; reload() }
                    .onFailure { error = it.message }
            }
        }, colors = ButtonDefaults.buttonColors(containerColor = Navy)) { Text("Read & tag") }
        error?.let { Text(it, color = StampRed) }
        Spacer(Modifier.height(12.dp))
        LazyColumn {
            items(messages, key = { it.id }) { m ->
                Column(Modifier.fillMaxWidth().padding(vertical = 10.dp)) {
                    Text("${m.payee ?: m.suggested_category}  ${m.amount?.let { inr(it) } ?: ""}", color = Ink, fontWeight = FontWeight.SemiBold)
                    Text("${m.direction} · ${m.suggested_category ?: "—"}", color = InkSoft, style = MaterialTheme.typography.bodySmall)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        TextButton(onClick = { scope.launch { runCatching { repository.acceptFinanceMessage(m.id) }; reload() } }) { Text("Accept") }
                    }
                }
                HorizontalDivider(color = LineColor)
            }
        }
    }
}
