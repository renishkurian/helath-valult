package com.rklab.healthvault.ui.screens.finance

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.BitmapFactory
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
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
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Image
import androidx.compose.material.icons.filled.PhotoCamera
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import com.rklab.healthvault.data.model.*
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.theme.*
import com.rklab.healthvault.util.FileUtil
import kotlinx.coroutines.launch
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import java.io.File
import java.time.LocalDate
import java.time.YearMonth
import java.time.format.DateTimeFormatter
import java.util.Locale

private val ExpenseRed = Color(0xFFFF6B7A)
private val IncomeBlue = Color(0xFF5B9CFF)
private val monthFmt: DateTimeFormatter = DateTimeFormatter.ofPattern("yyyy-MM")
private val monthLabelFmt: DateTimeFormatter = DateTimeFormatter.ofPattern("MMM yyyy")

private val PAY_METHODS = listOf(
    "upi" to "UPI",
    "debit_card" to "Debit card",
    "credit_card" to "Credit card",
    "atm" to "ATM cash",
    "netbanking" to "Net banking",
    "cash" to "Cash",
    "other" to "Other"
)

private fun methodLabel(key: String?): String? =
    PAY_METHODS.firstOrNull { it.first == key }?.second ?: key?.replace('_', ' ')

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
    var month by remember { mutableStateOf(YearMonth.now()) }
    val monthKey = month.format(monthFmt)
    var summary by remember { mutableStateOf<FinanceSummaryOut?>(null) }
    var items by remember { mutableStateOf<List<FinanceTxnOut>>(emptyList()) }
    var error by remember { mutableStateOf<String?>(null) }
    var photoTxn by remember { mutableStateOf<FinanceTxnOut?>(null) }

    fun reload() {
        scope.launch {
            runCatching {
                summary = repository.financeSummary(monthKey)
                items = repository.listFinanceTransactions(monthKey)
            }.onFailure { error = it.message }
        }
    }
    LaunchedEffect(monthKey) {
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
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("‹", color = InkSoft, modifier = Modifier.clickable { month = month.minusMonths(1) }.padding(end = 8.dp), fontWeight = FontWeight.Bold)
                        Text(month.format(monthLabelFmt), style = MaterialTheme.typography.headlineMedium, color = Ink, fontWeight = FontWeight.Bold)
                        Text("›", color = InkSoft, modifier = Modifier.clickable { month = month.plusMonths(1) }.padding(start = 8.dp), fontWeight = FontWeight.Bold)
                    }
                }
                IconButton(onClick = onOpenModules) {
                    Icon(Icons.Filled.Apps, contentDescription = "Modules", tint = InkSoft)
                }
            }
            IncomingSmsBanner(onChanged = { reload() })
            summary?.let { s ->
                Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    SummaryChip("Opening", inr(s.opening), Ink, Modifier.weight(1f))
                    SummaryChip("Income", inr(s.income), IncomeBlue, Modifier.weight(1f))
                    SummaryChip("Expenses", inr(s.expense), ExpenseRed, Modifier.weight(1f))
                    SummaryChip("Total", inr(s.closing), Ink, Modifier.weight(1f))
                }
                Text(
                    "Last month ${inr(s.prev_income)} in · ${inr(s.prev_expense)} out carried into this month.",
                    color = InkSoft,
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.padding(horizontal = 20.dp, vertical = 8.dp)
                )
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
                            Text(
                                buildString {
                                    append(t.account_name)
                                    methodLabel(t.payment_method)?.let { append(" · "); append(it) }
                                    if (!t.description.isNullOrBlank() && !t.payee.isNullOrBlank()) {
                                        append(" · "); append(t.description)
                                    }
                                },
                                color = InkSoft,
                                style = MaterialTheme.typography.bodySmall
                            )
                        }
                        Column(horizontalAlignment = Alignment.End) {
                            Text(
                                inr(t.amount),
                                color = when (t.txn_type) { "income" -> IncomeBlue; "expense" -> ExpenseRed; else -> Ink },
                                fontWeight = FontWeight.Bold
                            )
                            if (t.has_image) {
                                Text(
                                    "Photo",
                                    color = IncomeBlue,
                                    style = MaterialTheme.typography.labelSmall,
                                    modifier = Modifier.clickable { photoTxn = t }
                                )
                            }
                        }
                    }
                    HorizontalDivider(color = LineColor)
                }
            }
        }
        photoTxn?.let { txn ->
            FinancePhotoDialog(repository, txn) { photoTxn = null }
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
    var categories by remember { mutableStateOf<List<FinanceCategoryOut>>(emptyList()) }
    var name by remember { mutableStateOf("") }
    var accountType by remember { mutableStateOf("bank") }
    var catName by remember { mutableStateOf("") }
    var catKind by remember { mutableStateOf("expense") }
    var catScope by remember { mutableStateOf<String?>(null) }
    fun reload() {
        scope.launch {
            runCatching {
                summary = repository.financeSummary()
                accounts = repository.listFinanceAccounts()
                categories = repository.listFinanceCategories()
            }
        }
    }
    LaunchedEffect(Unit) { reload() }
    val scopedCats = categories.filter { if (catScope == null) it.account_id == null else it.account_id == catScope }
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
                Row(
                    Modifier.fillMaxWidth().clickable { catScope = a.id }.padding(vertical = 10.dp),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Column {
                        Text(a.name, color = Ink, fontWeight = FontWeight.SemiBold)
                        Text(a.account_type.replace('_', ' '), color = InkSoft, style = MaterialTheme.typography.bodySmall)
                    }
                    Text(inr(a.balance), color = if (a.is_liability || a.balance < 0) ExpenseRed else IncomeBlue, fontWeight = FontWeight.Bold)
                }
                HorizontalDivider(color = LineColor)
            }
            item {
                Spacer(Modifier.height(18.dp))
                Text("Categories", color = Ink, fontWeight = FontWeight.Bold)
                Text(
                    "General ones apply to every account. Account ones only show for Home, Personal, and so on.",
                    color = InkSoft,
                    style = MaterialTheme.typography.bodySmall
                )
                Spacer(Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                    FilterChip(
                        selected = catScope == null,
                        onClick = { catScope = null },
                        label = { Text("All accounts") }
                    )
                }
                accounts.chunked(3).forEach { row ->
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth().padding(top = 6.dp)) {
                        row.forEach { a ->
                            FilterChip(
                                selected = catScope == a.id,
                                onClick = { catScope = a.id },
                                label = { Text(a.name) },
                                modifier = Modifier.weight(1f)
                            )
                        }
                        repeat(3 - row.size) { Spacer(Modifier.weight(1f)) }
                    }
                }
                Spacer(Modifier.height(8.dp))
                scopedCats.forEach { c ->
                    Text(
                        "${c.name}  ·  ${c.kind}${if (c.account_name != null) "  ·  ${c.account_name}" else "  ·  general"}",
                        color = Ink,
                        modifier = Modifier.padding(vertical = 6.dp)
                    )
                }
                if (scopedCats.isEmpty()) {
                    Text("No categories in this scope yet.", color = InkSoft, style = MaterialTheme.typography.bodySmall)
                }
            }
        }
        OutlinedTextField(value = name, onValueChange = { name = it }, label = { Text("New account (Home, Personal…)") }, modifier = Modifier.fillMaxWidth())
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 6.dp)) {
            listOf("cash" to "Cash", "bank" to "Bank", "credit_card" to "Card", "wallet" to "Wallet").forEach { (key, label) ->
                FilterChip(selected = accountType == key, onClick = { accountType = key }, label = { Text(label) })
            }
        }
        Spacer(Modifier.height(8.dp))
        Button(
            onClick = {
                val n = name.trim(); if (n.isEmpty()) return@Button
                scope.launch {
                    runCatching { repository.createFinanceAccount(FinanceAccountIn(n, accountType)) }
                    name = ""
                    reload()
                }
            },
            colors = ButtonDefaults.buttonColors(containerColor = Navy)
        ) { Text("Save account") }
        Spacer(Modifier.height(12.dp))
        OutlinedTextField(
            value = catName,
            onValueChange = { catName = it },
            label = { Text(if (catScope == null) "New general category" else "New category for this account") },
            modifier = Modifier.fillMaxWidth()
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 6.dp)) {
            FilterChip(selected = catKind == "expense", onClick = { catKind = "expense" }, label = { Text("Expense") })
            FilterChip(selected = catKind == "income", onClick = { catKind = "income" }, label = { Text("Income") })
        }
        Spacer(Modifier.height(8.dp))
        Button(
            onClick = {
                val n = catName.trim(); if (n.isEmpty()) return@Button
                scope.launch {
                    runCatching { repository.createFinanceCategory(FinanceCategoryIn(n, catKind, catScope)) }
                    catName = ""
                    categories = repository.listFinanceCategories()
                }
            },
            colors = ButtonDefaults.buttonColors(containerColor = Navy)
        ) { Text("Save category") }
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
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var accounts by remember { mutableStateOf<List<FinanceAccountOut>>(emptyList()) }
    var categories by remember { mutableStateOf<List<FinanceCategoryOut>>(emptyList()) }
    var txnType by remember { mutableStateOf("expense") }
    var accountId by remember { mutableStateOf<String?>(null) }
    var categoryId by remember { mutableStateOf<String?>(null) }
    var amount by remember { mutableStateOf("") }
    var payee by remember { mutableStateOf("") }
    var description by remember { mutableStateOf("") }
    var paymentMethod by remember { mutableStateOf("other") }
    var error by remember { mutableStateOf<String?>(null) }
    var receiptFile by remember { mutableStateOf<File?>(null) }
    var captureFile by remember { mutableStateOf<File?>(null) }
    val galleryLauncher = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        val copied = FileUtil.copyUriToCacheFile(context, uri, "fn_${System.currentTimeMillis()}")
        receiptFile = FileUtil.enhanceImageFile(copied)
    }
    val cameraLauncher = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { ok ->
        if (ok) {
            captureFile?.let { file ->
                if (file.exists() && file.length() > 0) receiptFile = FileUtil.enhanceImageFile(file)
            }
        }
        captureFile = null
    }
    fun launchCamera() {
        val file = FileUtil.newCaptureFile(context)
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
        captureFile = file
        cameraLauncher.launch(uri)
    }
    val cameraPermLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) launchCamera()
    }
    LaunchedEffect(Unit) {
        scope.launch {
            accounts = repository.listFinanceAccounts()
            categories = repository.listFinanceCategories()
            accountId = accounts.firstOrNull()?.id
            categoryId = categories.firstOrNull { it.kind == txnType }?.id
        }
    }
    val visibleCats = categories.filter {
        it.kind == txnType && (it.account_id == null || it.account_id == accountId)
    }
    LaunchedEffect(txnType, categories, accountId) {
        if (visibleCats.none { it.id == categoryId }) {
            categoryId = visibleCats.firstOrNull()?.id
        }
    }
    LaunchedEffect(paymentMethod, accounts, categories, txnType) {
        val want = when (paymentMethod) {
            "credit_card" -> "credit_card"
            "cash" -> "cash"
            "upi", "debit_card", "netbanking", "atm" -> "bank"
            else -> null
        }
        want?.let { type -> accounts.firstOrNull { it.account_type == type }?.id?.let { accountId = it } }
        if (paymentMethod == "atm" && txnType == "expense") {
            categories.firstOrNull { it.name == "ATM / cash" }?.id?.let { categoryId = it }
        }
    }
    Column(Modifier.fillMaxSize().background(Paper).verticalScroll(rememberScrollState()).padding(20.dp)) {
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
            visibleCats.chunked(3).forEach { row ->
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                    row.forEach { c ->
                        FilterChip(
                            selected = categoryId == c.id,
                            onClick = { categoryId = c.id },
                            label = { Text(if (c.account_name != null) "${c.name}" else c.name) },
                            modifier = Modifier.weight(1f)
                        )
                    }
                    repeat(3 - row.size) { Spacer(Modifier.weight(1f)) }
                }
            }
        }
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(value = amount, onValueChange = { amount = it }, label = { Text("Amount") }, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(8.dp))
        Text("Paid by", color = InkSoft, style = MaterialTheme.typography.labelMedium)
        PAY_METHODS.chunked(3).forEach { row ->
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth().padding(top = 6.dp)) {
                row.forEach { (key, label) ->
                    FilterChip(selected = paymentMethod == key, onClick = { paymentMethod = key }, label = { Text(label) }, modifier = Modifier.weight(1f))
                }
                repeat(3 - row.size) { Spacer(Modifier.weight(1f)) }
            }
        }
        OutlinedTextField(value = payee, onValueChange = { payee = it }, label = { Text("Note") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(value = description, onValueChange = { description = it }, label = { Text("Description") }, modifier = Modifier.fillMaxWidth(), minLines = 2)
        Spacer(Modifier.height(10.dp))
        Text("Photo / receipt", color = InkSoft, style = MaterialTheme.typography.labelMedium)
        Text(receiptFile?.name ?: "Optional bill, receipt, or screenshot", color = InkSoft, style = MaterialTheme.typography.bodySmall)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 8.dp)) {
            OutlinedButton(onClick = {
                if (ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
                    launchCamera()
                } else {
                    cameraPermLauncher.launch(Manifest.permission.CAMERA)
                }
            }) {
                Icon(Icons.Filled.PhotoCamera, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(6.dp))
                Text("Camera")
            }
            OutlinedButton(onClick = { galleryLauncher.launch("image/*") }) {
                Icon(Icons.Filled.Image, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(6.dp))
                Text("Gallery")
            }
            if (receiptFile != null) {
                TextButton(onClick = { receiptFile = null }) { Text("Remove") }
            }
        }
        error?.let { Text(it, color = StampRed, modifier = Modifier.padding(top = 8.dp)) }
        Spacer(Modifier.height(16.dp))
        Button(
            onClick = {
                val acc = accountId ?: return@Button
                val amt = amount.toDoubleOrNull() ?: 0.0
                if (amt <= 0) { error = "Enter an amount"; return@Button }
                scope.launch {
                    runCatching {
                        val created = repository.createFinanceTransaction(
                            FinanceTxnIn(
                                account_id = acc,
                                to_account_id = if (txnType == "transfer") accounts.firstOrNull { it.id != acc }?.id else null,
                                category_id = if (txnType == "transfer") null else categoryId,
                                txn_type = txnType,
                                amount = amt,
                                txn_date = LocalDate.now().toString(),
                                payee = payee.ifBlank { null },
                                description = description.ifBlank { null },
                                payment_method = paymentMethod.takeIf { it != "other" }
                            )
                        )
                        receiptFile?.let { repository.uploadFinanceImage(created.id, it) }
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
                    Text("${m.direction} · ${methodLabel(m.payment_method) ?: "—"} · ${m.suggested_category ?: "—"}", color = InkSoft, style = MaterialTheme.typography.bodySmall)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        TextButton(onClick = { scope.launch { runCatching { repository.acceptFinanceMessage(m.id) }; reload() } }) { Text("Accept") }
                    }
                }
                HorizontalDivider(color = LineColor)
            }
        }
    }
}

@Composable
private fun FinancePhotoDialog(
    repository: HealthVaultRepository,
    txn: FinanceTxnOut,
    onDismiss: () -> Unit
) {
    val context = LocalContext.current
    var bitmap by remember { mutableStateOf<android.graphics.Bitmap?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(txn.id) {
        runCatching {
            val dest = File(context.cacheDir, "fn_${txn.id}.jpg")
            repository.downloadFinanceImage(txn.id, dest)
            BitmapFactory.decodeFile(dest.absolutePath)
        }.onSuccess { bitmap = it }.onFailure { error = it.message }
    }
    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = {
            TextButton(onClick = onDismiss) {
                Icon(Icons.Filled.Close, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(4.dp))
                Text("Close")
            }
        },
        title = { Text(txn.payee ?: txn.description ?: "Photo") },
        text = {
            when {
                bitmap != null -> Image(
                    bitmap = bitmap!!.asImageBitmap(),
                    contentDescription = "Receipt",
                    modifier = Modifier.fillMaxWidth().heightIn(max = 420.dp),
                    contentScale = ContentScale.Fit
                )
                error != null -> Text(error ?: "", color = StampRed)
                else -> CircularProgressIndicator()
            }
        }
    )
}
