package com.rklab.healthvault.ui.screens.finance

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowLeft
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.BarChart
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.rklab.healthvault.data.model.FinanceAccountIn
import com.rklab.healthvault.data.model.FinanceAccountOut
import com.rklab.healthvault.data.model.FinanceSummaryOut
import com.rklab.healthvault.data.model.FinanceTxnOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.theme.*
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.YearMonth
import java.time.format.DateTimeFormatter
import java.time.format.TextStyle
import java.util.Locale

private val rangeFmt: DateTimeFormatter = DateTimeFormatter.ofPattern("dd.MM.yy")

@Composable
fun FinanceAccountsScreen(
    repository: HealthVaultRepository,
    onOpenAccount: (String) -> Unit
) {
    val scope = rememberCoroutineScope()
    var summary by remember { mutableStateOf<FinanceSummaryOut?>(null) }
    var accounts by remember { mutableStateOf<List<FinanceAccountOut>>(emptyList()) }
    var adding by remember { mutableStateOf(false) }
    var newName by remember { mutableStateOf("") }
    var newType by remember { mutableStateOf("bank") }

    fun reload() {
        scope.launch {
            runCatching {
                summary = repository.financeSummary()
                accounts = repository.listFinanceAccounts().filter { !it.archived }
            }
        }
    }
    LaunchedEffect(Unit) { reload() }

    Column(Modifier.fillMaxSize().background(HubBg)) {
        Row(
            Modifier.fillMaxWidth().padding(20.dp, 16.dp, 8.dp, 8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text("Accounts", style = MaterialTheme.typography.headlineMedium, color = Ink, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
            IconButton(onClick = { adding = true }) {
                Icon(Icons.Filled.Add, contentDescription = "Add account", tint = Ink)
            }
        }
        summary?.let { s ->
            Row(Modifier.fillMaxWidth().padding(horizontal = 20.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                Column(horizontalAlignment = Alignment.Start) {
                    Text("Assets", color = InkSoft, style = MaterialTheme.typography.labelMedium)
                    Text(inr(s.assets), color = IncomeBlue, fontWeight = FontWeight.Bold, fontSize = 16.sp)
                }
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("Liabilities", color = InkSoft, style = MaterialTheme.typography.labelMedium)
                    Text(inr(s.liabilities), color = ExpenseRed, fontWeight = FontWeight.Bold, fontSize = 16.sp)
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text("Total", color = InkSoft, style = MaterialTheme.typography.labelMedium)
                    Text(inr(s.net), color = Ink, fontWeight = FontWeight.Bold, fontSize = 16.sp)
                }
            }
        }
        Spacer(Modifier.height(12.dp))
        HorizontalDivider(color = LineColor)
        LazyColumn(Modifier.fillMaxSize()) {
            items(accounts, key = { it.id }) { a ->
                AccountRow(a) { onOpenAccount(a.id) }
                HorizontalDivider(color = LineColor)
            }
            if (accounts.isEmpty()) {
                item {
                    Text("No accounts yet. Tap + to add Cash, Home, Card…", color = InkSoft, modifier = Modifier.padding(20.dp))
                }
            }
            item { Spacer(Modifier.height(80.dp)) }
        }
    }

    if (adding) {
        AlertDialog(
            onDismissRequest = { adding = false },
            confirmButton = {
                TextButton(onClick = {
                    val n = newName.trim()
                    if (n.isEmpty()) return@TextButton
                    scope.launch {
                        runCatching { repository.createFinanceAccount(FinanceAccountIn(n, newType)) }
                        newName = ""
                        adding = false
                        reload()
                    }
                }) { Text("Save") }
            },
            dismissButton = { TextButton(onClick = { adding = false }) { Text("Cancel") } },
            title = { Text("New account") },
            text = {
                Column {
                    OutlinedTextField(value = newName, onValueChange = { newName = it }, label = { Text("Name") }, modifier = Modifier.fillMaxWidth())
                    Spacer(Modifier.height(8.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        listOf("cash" to "Cash", "bank" to "Bank", "credit_card" to "Card", "loan" to "Loan", "wallet" to "Wallet").forEach { (k, l) ->
                            FilterChip(selected = newType == k, onClick = { newType = k }, label = { Text(l) })
                        }
                    }
                }
            }
        )
    }
}

@Composable
private fun AccountRow(a: FinanceAccountOut, onClick: () -> Unit) {
    val amountColor = if (a.is_liability || a.balance < 0) ExpenseRed else IncomeBlue
    Column(
        Modifier.fillMaxWidth().clickable(onClick = onClick).padding(horizontal = 20.dp, vertical = 14.dp)
    ) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f).padding(end = 12.dp)) {
                Text(a.name, color = Ink, fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
                Text(a.account_type.replace('_', ' '), color = InkSoft, style = MaterialTheme.typography.bodySmall)
            }
            Text(inr(a.balance), color = amountColor, fontWeight = FontWeight.Bold)
        }
        val limit = a.credit_limit
        if (a.account_type == "credit_card" && limit != null) {
            Spacer(Modifier.height(6.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("Credit limit  ${inr(limit)}", color = InkSoft, style = MaterialTheme.typography.bodySmall)
                Text("Outstanding  ${inr(a.balance)}", color = ExpenseRed, style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

@Composable
fun FinanceAccountDetailScreen(
    repository: HealthVaultRepository,
    accountId: String,
    onBack: () -> Unit,
    onAdd: (String) -> Unit
) {
    val scope = rememberCoroutineScope()
    var month by remember { mutableStateOf(YearMonth.now()) }
    var account by remember { mutableStateOf<FinanceAccountOut?>(null) }
    var txns by remember { mutableStateOf<List<FinanceTxnOut>>(emptyList()) }
    var photoTxn by remember { mutableStateOf<FinanceTxnOut?>(null) }
    val monthKey = month.format(monthFmt)

    fun reload() {
        scope.launch {
            runCatching {
                account = repository.listFinanceAccounts().firstOrNull { it.id == accountId }
                txns = repository.listFinanceTransactions(yearMonth = monthKey, accountId = accountId)
                    .sortedWith(compareBy({ it.txn_date }, { it.txn_time ?: "" }, { it.created_at }))
            }
        }
    }
    LaunchedEffect(accountId, monthKey) { reload() }

    val deposit = txns.filter { isDeposit(it, accountId) }.sumOf { it.amount }
    val withdrawal = txns.filter { !isDeposit(it, accountId) }.sumOf { it.amount }
    val total = deposit - withdrawal
    val grouped = txns.groupBy { it.txn_date }.toSortedMap(compareByDescending { it })
    val start = month.atDay(1)
    val end = month.atEndOfMonth()

    Box(Modifier.fillMaxSize().background(HubBg)) {
        Column(Modifier.fillMaxSize()) {
            Row(
                Modifier.fillMaxWidth().padding(4.dp, 4.dp, 8.dp, 0.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                IconButton(onClick = onBack) {
                    Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back", tint = Ink)
                }
                Text(account?.name ?: "Account", color = Ink, fontWeight = FontWeight.Bold, fontSize = 20.sp, modifier = Modifier.weight(1f))
                MonthYearNav(month) { month = it }
            }
            Row(
                Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(Modifier.weight(1f)) {
                    Text("Statement", color = InkSoft, style = MaterialTheme.typography.labelMedium)
                    Text("${start.format(rangeFmt)} ~ ${end.format(rangeFmt)}", color = InkSoft, style = MaterialTheme.typography.bodySmall)
                }
                Icon(Icons.Filled.BarChart, contentDescription = null, tint = InkSoft, modifier = Modifier.size(20.dp).padding(end = 12.dp))
                Icon(Icons.Filled.Edit, contentDescription = null, tint = InkSoft, modifier = Modifier.size(20.dp))
            }
            Row(
                Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                StatementStat("Deposit", inr(deposit), IncomeBlue)
                StatementStat("Withdrawal", inr(withdrawal), ExpenseRed)
                StatementStat("Total", inr(total), Ink)
                StatementStat("Balance", inr(account?.balance ?: 0.0), if ((account?.balance ?: 0.0) < 0 || account?.is_liability == true) ExpenseRed else IncomeBlue)
            }
            HorizontalDivider(color = LineColor)
            LazyColumn(Modifier.fillMaxSize()) {
                grouped.forEach { (date, dayTxns) ->
                    val d = runCatching { LocalDate.parse(date) }.getOrNull()
                    val dayIn = dayTxns.filter { isDeposit(it, accountId) }.sumOf { it.amount }
                    val dayOut = dayTxns.filter { !isDeposit(it, accountId) }.sumOf { it.amount }
                    item(key = "h-$date") {
                        Row(
                            Modifier.fillMaxWidth().background(PaperDeep).padding(horizontal = 16.dp, vertical = 8.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            if (d != null) {
                                Text(d.dayOfMonth.toString().padStart(2, '0'), color = Ink, fontWeight = FontWeight.Bold)
                                Spacer(Modifier.width(8.dp))
                                Box(
                                    Modifier.clip(RoundedCornerShape(4.dp)).background(ExpenseRed.copy(alpha = 0.2f)).padding(horizontal = 6.dp, vertical = 2.dp)
                                ) {
                                    Text(d.dayOfWeek.getDisplayName(TextStyle.SHORT, Locale.US), color = ExpenseRed, style = MaterialTheme.typography.labelSmall)
                                }
                                Spacer(Modifier.width(8.dp))
                                Text(d.format(DateTimeFormatter.ofPattern("MM.yyyy")), color = InkSoft, style = MaterialTheme.typography.bodySmall)
                            } else {
                                Text(date, color = Ink)
                            }
                            Spacer(Modifier.weight(1f))
                            Text(inr(dayIn), color = IncomeBlue, style = MaterialTheme.typography.bodySmall)
                            Spacer(Modifier.width(10.dp))
                            Text(inr(dayOut), color = ExpenseRed, style = MaterialTheme.typography.bodySmall)
                        }
                    }
                    items(dayTxns, key = { it.id }) { t ->
                        val depositRow = isDeposit(t, accountId)
                        Row(
                            Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Column(Modifier.weight(1f).padding(end = 12.dp)) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Text(t.payee ?: t.description ?: t.category_name ?: t.txn_type, color = Ink, fontWeight = FontWeight.Medium)
                                    if (t.has_image) {
                                        Text(" · ", color = InkSoft, fontWeight = FontWeight.Medium)
                                        Text(
                                            "photo",
                                            color = IncomeBlue,
                                            fontWeight = FontWeight.Medium,
                                            modifier = Modifier.clickable { photoTxn = t }
                                        )
                                    }
                                }
                                Text(
                                    buildString {
                                        append(t.category_name ?: t.txn_type)
                                        if (!t.description.isNullOrBlank() && !t.payee.isNullOrBlank()) {
                                            append(" · "); append(t.description)
                                        }
                                    },
                                    color = InkSoft,
                                    style = MaterialTheme.typography.bodySmall
                                )
                            }
                            Text(inr(t.amount), color = if (depositRow) IncomeBlue else ExpenseRed, fontWeight = FontWeight.Bold)
                        }
                        HorizontalDivider(color = LineColor)
                    }
                }
                if (txns.isEmpty()) {
                    item {
                        Text("No entries this month.", color = InkSoft, modifier = Modifier.padding(20.dp))
                    }
                }
                item { Spacer(Modifier.height(96.dp)) }
            }
        }
        photoTxn?.let { txn ->
            FinancePhotoDialog(repository, txn) { photoTxn = null }
        }
        FloatingActionButton(
            onClick = { onAdd(accountId) },
            modifier = Modifier.align(Alignment.BottomEnd).padding(20.dp),
            containerColor = ExpenseRed,
            contentColor = Color.White,
            shape = CircleShape
        ) { Icon(Icons.Filled.Add, contentDescription = "Add") }
    }
}

@Composable
private fun MonthYearNav(month: YearMonth, onChange: (YearMonth) -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(
            "‹‹",
            color = InkSoft,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.clickable { onChange(month.minusYears(1)) }.padding(6.dp)
        )
        IconButton(onClick = { onChange(month.minusMonths(1)) }, modifier = Modifier.size(32.dp)) {
            Icon(Icons.AutoMirrored.Filled.KeyboardArrowLeft, contentDescription = "Previous month", tint = InkSoft)
        }
        Text(month.format(monthLabelFmt), color = Ink, fontWeight = FontWeight.SemiBold)
        IconButton(onClick = { onChange(month.plusMonths(1)) }, modifier = Modifier.size(32.dp)) {
            Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, contentDescription = "Next month", tint = InkSoft)
        }
        Text(
            "››",
            color = InkSoft,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.clickable { onChange(month.plusYears(1)) }.padding(6.dp)
        )
    }
}

@Composable
private fun StatementStat(label: String, value: String, color: Color) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(label, color = InkSoft, style = MaterialTheme.typography.labelSmall)
        Text(value, color = color, fontWeight = FontWeight.Bold, fontSize = 13.sp)
    }
}

private fun isDeposit(t: FinanceTxnOut, accountId: String): Boolean {
    return when (t.txn_type) {
        "income" -> true
        "transfer" -> t.to_account_id == accountId
        else -> false
    }
}
