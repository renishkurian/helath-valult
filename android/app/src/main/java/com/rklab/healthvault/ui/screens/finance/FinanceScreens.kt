package com.rklab.healthvault.ui.screens.finance

import android.Manifest
import android.content.Intent
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Apps
import androidx.compose.material.icons.filled.Close
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
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.rklab.healthvault.data.model.*
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.theme.*
import kotlinx.coroutines.launch
import java.io.File
import java.time.LocalDate
import java.time.YearMonth
import java.time.format.DateTimeFormatter
import java.util.Locale

internal val ExpenseRed = Color(0xFFFF6B7A)
internal val IncomeBlue = Color(0xFF5B9CFF)
internal val monthFmt: DateTimeFormatter = DateTimeFormatter.ofPattern("yyyy-MM")
internal val monthLabelFmt: DateTimeFormatter = DateTimeFormatter.ofPattern("MMM yyyy")

internal val PAY_METHODS = listOf(
    "upi" to "UPI",
    "debit_card" to "Debit card",
    "credit_card" to "Credit card",
    "atm" to "ATM cash",
    "netbanking" to "Net banking",
    "cash" to "Cash",
    "other" to "Other"
)

internal fun methodLabel(key: String?): String? =
    PAY_METHODS.firstOrNull { it.first == key }?.second ?: key?.replace('_', ' ')

internal fun inr(n: Double): String {
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
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text(t.payee ?: t.description ?: "—", color = Ink, fontWeight = FontWeight.SemiBold)
                                if (t.has_image) {
                                    Text(" · ", color = InkSoft, fontWeight = FontWeight.SemiBold)
                                    Text(
                                        "photo",
                                        color = IncomeBlue,
                                        fontWeight = FontWeight.SemiBold,
                                        modifier = Modifier.clickable { photoTxn = t }
                                    )
                                }
                            }
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
fun FinanceMoreScreen(
    repository: HealthVaultRepository,
    onOpenModules: () -> Unit,
    onOpenInbox: () -> Unit,
    onOpenEmi: () -> Unit = {}
) {
    Column(Modifier.fillMaxSize().background(Paper).padding(20.dp)) {
        Text("Settings", style = MaterialTheme.typography.headlineMedium, color = Ink, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(20.dp))
        IncomingSmsToggle()
        Spacer(Modifier.height(8.dp))
        MoreRow("Recurring payments", "EMI, chitty, loan, rent — auto-add and due alerts") { onOpenEmi() }
        MoreRow("AI & SMS inbox", "Review pending tags or paste a message") { onOpenInbox() }
        MoreRow("Switch module", "Health / Passwords / Money") { onOpenModules() }
    }
}

private fun openAppDetails(context: android.content.Context) {
    context.startActivity(
        Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
            data = Uri.fromParts("package", context.packageName, null)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
    )
}

@Composable
private fun SmsRestrictedHelp(onDismiss: () -> Unit, onOpenSettings: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("SMS was blocked") },
        text = {
            Text(
                "Sideloaded apps cannot turn SMS on from the toggle. On the next screen:\n\n" +
                    "1. Tap the ⋮ menu (top right)\n" +
                    "2. Tap Allow restricted settings\n" +
                    "3. Open Permissions → SMS → Allow\n" +
                    "4. Come back here and turn Incoming SMS on again."
            )
        },
        confirmButton = {
            TextButton(onClick = onOpenSettings) { Text("Open app settings") }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Close") }
        }
    )
}

@Composable
private fun IncomingSmsToggle() {
    val context = LocalContext.current
    var enabled by remember {
        mutableStateOf(FinanceSmsPrefs.isEnabled(context) && FinanceSmsPrefs.hasSmsPermission(context))
    }
    var showHelp by remember { mutableStateOf(false) }
    val launcher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { grants ->
        val ok = grants[Manifest.permission.READ_SMS] == true &&
            grants[Manifest.permission.RECEIVE_SMS] == true
        FinanceSmsPrefs.setEnabled(context, ok)
        enabled = ok
        if (ok) FinanceSmsIngestor.scanInbox(context) else showHelp = true
    }
    val perms = buildList {
        add(Manifest.permission.READ_SMS)
        add(Manifest.permission.RECEIVE_SMS)
        if (Build.VERSION.SDK_INT >= 33) add(Manifest.permission.POST_NOTIFICATIONS)
    }
    if (showHelp) {
        SmsRestrictedHelp(
            onDismiss = { showHelp = false },
            onOpenSettings = {
                showHelp = false
                openAppDetails(context)
            }
        )
    }
    Row(
        Modifier.fillMaxWidth().padding(vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(Modifier.weight(1f).padding(end = 12.dp)) {
            Text("Incoming SMS", color = Ink, fontWeight = FontWeight.SemiBold)
            Text(
                "Bank and UPI alerts are tagged as they arrive. Sideloaded builds need Allow restricted settings first.",
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
    var showHelp by remember { mutableStateOf(false) }
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
        } else {
            showHelp = true
        }
    }
    val perms = buildList {
        add(Manifest.permission.READ_SMS)
        add(Manifest.permission.RECEIVE_SMS)
        if (Build.VERSION.SDK_INT >= 33) add(Manifest.permission.POST_NOTIFICATIONS)
    }
    if (showHelp) {
        SmsRestrictedHelp(
            onDismiss = { showHelp = false },
            onOpenSettings = {
                showHelp = false
                openAppDetails(context)
            }
        )
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
internal fun FinancePhotoDialog(
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
    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(usePlatformDefaultWidth = false, dismissOnBackPress = true, dismissOnClickOutside = true)
    ) {
        Box(
            Modifier
                .fillMaxSize()
                .background(Color.Black.copy(alpha = 0.88f))
                .clickable(
                    indication = null,
                    interactionSource = remember { MutableInteractionSource() },
                    onClick = onDismiss
                )
        ) {
            IconButton(
                onClick = onDismiss,
                modifier = Modifier.align(Alignment.TopEnd).padding(8.dp)
            ) {
                Icon(Icons.Filled.Close, contentDescription = "Close", tint = Color.White)
            }
            Box(Modifier.fillMaxSize().padding(20.dp), contentAlignment = Alignment.Center) {
                when {
                    bitmap != null -> Image(
                        bitmap = bitmap!!.asImageBitmap(),
                        contentDescription = "Receipt",
                        modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)),
                        contentScale = ContentScale.Fit
                    )
                    error != null -> Text(error ?: "", color = StampRed)
                    else -> CircularProgressIndicator(color = IncomeBlue)
                }
            }
        }
    }
}
