package com.rklab.healthvault.ui.screens.expense

import android.content.Intent
import android.net.Uri
import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.text.input.PasswordVisualTransformation
import com.rklab.healthvault.data.model.ExpenseAnalyserInsightsOut
import com.rklab.healthvault.data.model.ExpenseAnalyserItemOut
import com.rklab.healthvault.data.model.ExpenseAnalyserPostIn
import com.rklab.healthvault.data.model.ExpenseAnalyserSlice
import com.rklab.healthvault.data.model.ExpenseAnalyserStatusOut
import com.rklab.healthvault.data.model.ExpenseAnalyserSyncLogOut
import com.rklab.healthvault.data.model.FinanceAccountOut
import com.rklab.healthvault.data.model.FinanceCategoryOut
import com.rklab.healthvault.data.model.ShopPdfPasswordIn
import com.rklab.healthvault.data.model.ShopPdfPasswordOut
import com.rklab.healthvault.data.model.ShopStatementPdfOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.screens.finance.ExpenseRed
import com.rklab.healthvault.ui.screens.finance.IncomeBlue
import com.rklab.healthvault.ui.screens.finance.inr
import com.rklab.healthvault.ui.theme.HubBg
import com.rklab.healthvault.ui.theme.HubGlass
import com.rklab.healthvault.ui.theme.HubMint
import com.rklab.healthvault.ui.theme.Ink
import com.rklab.healthvault.ui.theme.InkSoft
import com.rklab.healthvault.ui.theme.LineColor
import com.rklab.healthvault.ui.theme.Navy
import com.rklab.healthvault.ui.theme.Sage
import com.rklab.healthvault.ui.theme.StampRed
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import retrofit2.HttpException

private val CardShape = RoundedCornerShape(16.dp)
private const val OPEN_STATUSES = "pending,missed,matched,corrected"

private fun errMessage(t: Throwable): String = when (t) {
    is HttpException -> {
        val body = runCatching { t.response()?.errorBody()?.string() }.getOrNull().orEmpty()
        Regex("\"detail\"\\s*:\\s*\"([^\"]+)\"").find(body)?.groupValues?.getOrNull(1)
            ?: t.message()
            ?: "Request failed"
    }
    else -> t.message ?: "Something went wrong"
}

private fun labelize(value: String?): String =
    (value ?: "").replace('_', ' ').replaceFirstChar { it.uppercase() }.ifBlank { "—" }

private fun itemTitle(item: ExpenseAnalyserItemOut): String =
    item.payee?.takeIf { it.isNotBlank() }
        ?: item.subject?.takeIf { it.isNotBlank() }
        ?: "Untitled"

private fun dayPart(iso: String?): String = iso?.replace('T', ' ')?.take(10).orEmpty()

private fun adminUrl(repository: HealthVaultRepository, path: String): String {
    val base = repository.getServerUrl()?.trimEnd('/') ?: return ""
    return "$base$path"
}

@Composable
fun ExpenseAnalyserInboxScreen(
    repository: HealthVaultRepository,
    onOpenModules: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var status by remember { mutableStateOf<ExpenseAnalyserStatusOut?>(null) }
    var items by remember { mutableStateOf<List<ExpenseAnalyserItemOut>>(emptyList()) }
    var accounts by remember { mutableStateOf<List<FinanceAccountOut>>(emptyList()) }
    var categories by remember { mutableStateOf<List<FinanceCategoryOut>>(emptyList()) }
    var filter by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf<String?>(null) }

    fun reload() {
        scope.launch {
            runCatching {
                status = repository.expenseAnalyserStatus()
                items = repository.listExpenseAnalyserItems(
                    status = filter,
                    statuses = if (filter == null) OPEN_STATUSES else null
                )
                if (accounts.isEmpty()) accounts = repository.listFinanceAccounts()
                if (categories.isEmpty()) categories = repository.listFinanceCategories()
            }.onFailure {
                Toast.makeText(context, errMessage(it), Toast.LENGTH_SHORT).show()
            }
        }
    }

    LaunchedEffect(filter) { reload() }
    LaunchedEffect(status?.syncing, status?.retagging) {
        if (status?.syncing == true || status?.retagging == true) {
            delay(4000)
            reload()
        }
    }

    Column(
        Modifier
            .fillMaxSize()
            .background(HubBg)
            .padding(horizontal = 16.dp, vertical = 12.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = onOpenModules) { Text("Modules", color = InkSoft) }
            Spacer(Modifier.weight(1f))
            TextButton(
                onClick = {
                    scope.launch {
                        busy = true
                        runCatching { repository.syncExpenseAnalyser() }
                            .onSuccess { out ->
                                message = if (out.error.isNullOrBlank()) {
                                    "Synced · ${out.created} new"
                                } else out.error
                                reload()
                            }
                            .onFailure {
                                Toast.makeText(context, errMessage(it), Toast.LENGTH_LONG).show()
                            }
                        busy = false
                    }
                },
                enabled = status?.connected == true && status?.syncing != true && !busy
            ) { Text(if (status?.syncing == true) "Syncing…" else "Sync", color = InkSoft) }
        }
        Text("Expense Analyser", style = MaterialTheme.typography.headlineMedium, color = Ink, fontWeight = FontWeight.Bold)
        Text("Bank alerts from Gmail — post to Money Manager when ready.", color = InkSoft, style = MaterialTheme.typography.bodySmall)
        Spacer(Modifier.height(12.dp))
        val st = status
        if (st != null) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                StatBox("Pending", "${st.pending + st.corrected}", Modifier.weight(1f), HubMint)
                StatBox("Matched", "${st.matched}", Modifier.weight(1f))
                StatBox("Missed", "${st.missed}", Modifier.weight(1f))
                StatBox("Posted", "${st.posted}", Modifier.weight(1f))
            }
        }
        if (status?.connected != true) {
            Spacer(Modifier.height(12.dp))
            Box(
                Modifier
                    .fillMaxWidth()
                    .clip(CardShape)
                    .background(HubGlass)
                    .border(1.dp, LineColor, CardShape)
                    .padding(16.dp)
            ) {
                Column {
                    Text("Connect Gmail to start", color = Ink, fontWeight = FontWeight.SemiBold)
                    Text(
                        "Gmail OAuth runs on the website. Connect once under Gmail & sync, then sync and post here.",
                        color = InkSoft,
                        style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier.padding(top = 4.dp, bottom = 10.dp)
                    )
                    Button(
                        onClick = {
                            val url = adminUrl(repository, "/admin/expense-analyser/settings")
                            if (url.isNotBlank()) {
                                context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
                            }
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = Navy)
                    ) { Text("Open website settings") }
                }
            }
        }
        if (status?.syncing == true || status?.retagging == true) {
            Spacer(Modifier.height(8.dp))
            Text(
                if (status?.retagging == true) "AI re-tag is running on the server…" else "Gmail sync is running…",
                color = HubMint,
                style = MaterialTheme.typography.bodySmall
            )
        }
        status?.last_error?.takeIf { status?.last_ok == false }?.let {
            Text("Last sync error: $it", color = StampRed, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 6.dp))
        }
        message?.let { Text(it, color = Sage, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 6.dp)) }
        Spacer(Modifier.height(10.dp))
        Row(
            Modifier.horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            listOf(null to "Open", "pending" to "Pending", "missed" to "Missed", "matched" to "Matched", "posted" to "Posted")
                .forEach { (key, label) ->
                    FilterChip(selected = filter == key, onClick = { filter = key }, label = { Text(label) })
                }
        }
        Spacer(Modifier.height(8.dp))
        if (items.isEmpty()) {
            Text("No items yet. Connect Gmail and sync, or widen the search query in Settings.", color = InkSoft)
        } else {
            LazyColumn(
                verticalArrangement = Arrangement.spacedBy(10.dp),
                contentPadding = PaddingValues(bottom = 24.dp)
            ) {
                items(items, key = { it.id }) { item ->
                    InboxCard(
                        item = item,
                        accounts = accounts,
                        categories = categories,
                        onPost = { accountId, categoryId ->
                            scope.launch {
                                runCatching {
                                    repository.postExpenseAnalyserItem(
                                        item.id,
                                        ExpenseAnalyserPostIn(account_id = accountId, category_id = categoryId)
                                    )
                                }.onSuccess {
                                    Toast.makeText(context, "Posted to Money Manager", Toast.LENGTH_SHORT).show()
                                    reload()
                                }.onFailure {
                                    Toast.makeText(context, errMessage(it), Toast.LENGTH_LONG).show()
                                }
                            }
                        },
                        onIgnore = {
                            scope.launch {
                                runCatching { repository.ignoreExpenseAnalyserItem(item.id) }
                                    .onSuccess { reload() }
                                    .onFailure { Toast.makeText(context, errMessage(it), Toast.LENGTH_SHORT).show() }
                            }
                        }
                    )
                }
            }
        }
    }
}

@Composable
private fun StatBox(label: String, value: String, modifier: Modifier = Modifier, accent: Color = Ink) {
    Column(
        modifier
            .clip(CardShape)
            .background(HubGlass)
            .border(1.dp, LineColor, CardShape)
            .padding(10.dp)
    ) {
        Text(label, color = InkSoft, fontSize = 11.sp)
        Text(value, color = accent, fontWeight = FontWeight.Bold, fontSize = 18.sp)
    }
}

@Composable
private fun InboxCard(
    item: ExpenseAnalyserItemOut,
    accounts: List<FinanceAccountOut>,
    categories: List<FinanceCategoryOut>,
    onPost: (accountId: String?, categoryId: String?) -> Unit,
    onIgnore: () -> Unit
) {
    val kind = if (item.direction == "credit") "income" else "expense"
    val parents = categories.filter { it.parent_id == null && it.kind == kind }
    var accountId by remember(item.id, accounts) { mutableStateOf(accounts.firstOrNull()?.id) }
    var categoryId by remember(item.id) {
        mutableStateOf(parents.firstOrNull { it.name.equals(item.suggested_category?.substringBefore(" / "), true) }?.id)
    }
    var accountOpen by remember { mutableStateOf(false) }
    var categoryOpen by remember { mutableStateOf(false) }
    val amountColor = if (item.direction == "credit") IncomeBlue else ExpenseRed
    val canPost = item.status !in listOf("posted", "ignored") && item.kind != "bill"

    Column(
        Modifier
            .fillMaxWidth()
            .clip(CardShape)
            .background(HubGlass)
            .border(1.dp, LineColor, CardShape)
            .padding(14.dp)
    ) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Badge(labelize(item.kind))
                Badge(labelize(item.status), accent = statusColor(item.status))
                item.payment_method?.takeIf { it.isNotBlank() }?.let { Badge(labelize(it)) }
            }
            Text(
                listOfNotNull(item.txn_date, dayPart(item.received_at).takeIf { it.isNotBlank() && it != item.txn_date }?.let { "mail $it" })
                    .joinToString(" · "),
                color = InkSoft,
                style = MaterialTheme.typography.bodySmall
            )
        }
        Spacer(Modifier.height(8.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Column(Modifier.weight(1f).padding(end = 8.dp)) {
                Text(itemTitle(item), color = Ink, fontWeight = FontWeight.SemiBold, maxLines = 2, overflow = TextOverflow.Ellipsis)
                item.from_addr?.takeIf { it.isNotBlank() }?.let {
                    Text(it, color = InkSoft, style = MaterialTheme.typography.bodySmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
                item.suggested_category?.takeIf { it.isNotBlank() }?.let {
                    Text("Suggested: $it", color = InkSoft, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 2.dp))
                }
                item.raw_snippet?.takeIf { it.isNotBlank() }?.let {
                    Text(it, color = InkSoft, style = MaterialTheme.typography.bodySmall, maxLines = 3, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 6.dp))
                }
            }
            Column(horizontalAlignment = Alignment.End) {
                item.amount?.let {
                    Text(
                        "${if (item.direction == "credit") "+" else "−"}${inr(it)}",
                        color = amountColor,
                        fontWeight = FontWeight.Bold,
                        fontSize = 18.sp
                    )
                }
                if (!item.match_txn_id.isNullOrBlank()) {
                    Text("Ledger match", color = Sage, style = MaterialTheme.typography.bodySmall)
                }
            }
        }
        if (canPost) {
            Spacer(Modifier.height(10.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                Box {
                    OutlinedButton(onClick = { accountOpen = true }) {
                        Text(accounts.firstOrNull { it.id == accountId }?.name ?: "Account", maxLines = 1)
                    }
                    DropdownMenu(expanded = accountOpen, onDismissRequest = { accountOpen = false }) {
                        accounts.forEach { a ->
                            DropdownMenuItem(text = { Text(a.name) }, onClick = { accountId = a.id; accountOpen = false })
                        }
                    }
                }
                Box {
                    OutlinedButton(onClick = { categoryOpen = true }) {
                        Text(parents.firstOrNull { it.id == categoryId }?.name ?: "Category", maxLines = 1)
                    }
                    DropdownMenu(expanded = categoryOpen, onDismissRequest = { categoryOpen = false }) {
                        DropdownMenuItem(text = { Text("None") }, onClick = { categoryId = null; categoryOpen = false })
                        parents.forEach { c ->
                            DropdownMenuItem(text = { Text(c.name) }, onClick = { categoryId = c.id; categoryOpen = false })
                        }
                    }
                }
            }
            Spacer(Modifier.height(8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(
                    onClick = { onPost(accountId, categoryId) },
                    colors = ButtonDefaults.buttonColors(containerColor = Navy),
                    enabled = item.amount != null && item.amount > 0
                ) { Text("Post") }
                TextButton(onClick = onIgnore) { Text("Ignore", color = InkSoft) }
            }
        } else if (item.kind == "bill") {
            Text("Statement header — review bill lines separately.", color = InkSoft, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 8.dp))
        }
    }
}

@Composable
private fun Badge(text: String, accent: Color = InkSoft) {
    Text(
        text,
        color = accent,
        fontSize = 10.sp,
        fontWeight = FontWeight.Medium,
        modifier = Modifier
            .clip(RoundedCornerShape(8.dp))
            .background(accent.copy(alpha = 0.14f))
            .padding(horizontal = 8.dp, vertical = 3.dp)
    )
}

private fun statusColor(status: String): Color = when (status) {
    "missed" -> Color(0xFFF0C36A)
    "matched" -> Sage
    "posted" -> HubMint
    "corrected" -> Color(0xFF7FA6FF)
    else -> InkSoft
}

@Composable
fun ExpenseAnalyserInsightsScreen(repository: HealthVaultRepository, onOpenModules: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var report by remember { mutableStateOf<ExpenseAnalyserInsightsOut?>(null) }

    fun load(month: String? = null) {
        scope.launch {
            runCatching { report = repository.expenseAnalyserInsights(month) }
                .onFailure { Toast.makeText(context, errMessage(it), Toast.LENGTH_SHORT).show() }
        }
    }
    LaunchedEffect(Unit) { load() }

    Column(
        Modifier
            .fillMaxSize()
            .background(HubBg)
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp, vertical = 12.dp)
    ) {
        TextButton(onClick = onOpenModules) { Text("Modules", color = InkSoft) }
        Text("Insights", style = MaterialTheme.typography.headlineMedium, color = Ink, fontWeight = FontWeight.Bold)
        val r = report
        if (r == null) {
            Text("Loading…", color = InkSoft)
        } else {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
            TextButton(onClick = { load(r.prev) }) { Text("←", color = InkSoft) }
            Text(r.label, color = Ink, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
            TextButton(onClick = { load(r.next) }) { Text("→", color = InkSoft) }
        }
        Text("${r.item_count} items this month", color = InkSoft, style = MaterialTheme.typography.bodySmall)
        Spacer(Modifier.height(12.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            StatBox("Spent", inr(r.debit_total), Modifier.weight(1f), ExpenseRed)
            StatBox("Credits", inr(r.credit_total), Modifier.weight(1f), IncomeBlue)
        }
        Spacer(Modifier.height(16.dp))
        SliceSection("By category", r.by_category)
        SliceSection("Top payees", r.top_payees)
        SliceSection("By method", r.by_method)
        if (r.by_day.isNotEmpty()) {
            Text("By day", color = Ink, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 8.dp, bottom = 8.dp))
            r.by_day.forEach { day ->
                Column(Modifier.padding(bottom = 6.dp)) {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text(day.label, color = InkSoft, style = MaterialTheme.typography.bodySmall)
                        Text(inr(day.amount), color = Ink, style = MaterialTheme.typography.bodySmall)
                    }
                    LinearProgressIndicator(
                        progress = (day.pct / 100.0).toFloat().coerceIn(0f, 1f),
                        modifier = Modifier.fillMaxWidth().height(6.dp).clip(RoundedCornerShape(4.dp)),
                        color = HubMint,
                        trackColor = LineColor
                    )
                }
            }
        }
        Spacer(Modifier.height(24.dp))
        }
    }
}

@Composable
private fun SliceSection(title: String, rows: List<ExpenseAnalyserSlice>) {
    if (rows.isEmpty()) return
    Text(title, color = Ink, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 8.dp, bottom = 4.dp))
    rows.take(8).forEach { row ->
        Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), horizontalArrangement = Arrangement.SpaceBetween) {
            Text("${row.name}  ·  ${row.count}", color = Ink, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(inr(row.amount), color = Ink, fontWeight = FontWeight.SemiBold)
        }
        HorizontalDivider(color = LineColor)
    }
}

@Composable
fun ExpenseAnalyserSyncLogScreen(repository: HealthVaultRepository, onOpenModules: () -> Unit) {
    val context = LocalContext.current
    var logs by remember { mutableStateOf<List<ExpenseAnalyserSyncLogOut>>(emptyList()) }
    LaunchedEffect(Unit) {
        runCatching { logs = repository.listExpenseAnalyserSyncLogs() }
            .onFailure { Toast.makeText(context, errMessage(it), Toast.LENGTH_SHORT).show() }
    }
    Column(
        Modifier
            .fillMaxSize()
            .background(HubBg)
            .padding(horizontal = 16.dp, vertical = 12.dp)
    ) {
        TextButton(onClick = onOpenModules) { Text("Modules", color = InkSoft) }
        Text("Sync log", style = MaterialTheme.typography.headlineMedium, color = Ink, fontWeight = FontWeight.Bold)
        Text("Each Gmail pull — manual, daily, or after connect.", color = InkSoft, style = MaterialTheme.typography.bodySmall)
        Spacer(Modifier.height(12.dp))
        if (logs.isEmpty()) {
            Text("No syncs yet.", color = InkSoft)
        } else {
            LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp), contentPadding = PaddingValues(bottom = 24.dp)) {
                items(logs, key = { it.id }) { log ->
                    Column(
                        Modifier
                            .fillMaxWidth()
                            .clip(CardShape)
                            .background(HubGlass)
                            .border(1.dp, LineColor, CardShape)
                            .padding(14.dp)
                    ) {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Text(labelize(log.trigger), color = Ink, fontWeight = FontWeight.SemiBold)
                            Text(if (log.ok) "OK" else "Failed", color = if (log.ok) Sage else StampRed, fontWeight = FontWeight.SemiBold)
                        }
                        Text(log.finished_at.replace('T', ' ').take(19), color = InkSoft, style = MaterialTheme.typography.bodySmall)
                        Text(
                            "Fetched ${log.fetched} · created ${log.created} · skipped ${log.skipped} · matched ${log.matched} · missed ${log.missed}",
                            color = InkSoft,
                            style = MaterialTheme.typography.bodySmall,
                            modifier = Modifier.padding(top = 4.dp)
                        )
                        log.error?.takeIf { it.isNotBlank() }?.let {
                            Text(it, color = StampRed, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 4.dp))
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun ExpenseAnalyserSettingsScreen(repository: HealthVaultRepository, onOpenModules: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var status by remember { mutableStateOf<ExpenseAnalyserStatusOut?>(null) }
    var query by remember { mutableStateOf("") }
    var hourOpen by remember { mutableStateOf(false) }
    var passwords by remember { mutableStateOf<List<ShopPdfPasswordOut>>(emptyList()) }
    var mailPdfs by remember { mutableStateOf<List<ShopStatementPdfOut>>(emptyList()) }
    var bankLabel by remember { mutableStateOf("") }
    var bankPassword by remember { mutableStateOf("") }
    var bankLast4 by remember { mutableStateOf("") }
    var bankIsCard by remember { mutableStateOf(false) }

    fun reload() {
        scope.launch {
            runCatching { repository.expenseAnalyserStatus() }
                .onSuccess {
                    status = it
                    query = it.sync_query.orEmpty()
                }
                .onFailure { Toast.makeText(context, errMessage(it), Toast.LENGTH_SHORT).show() }
            runCatching { repository.listShopPdfPasswords() }
                .onSuccess { passwords = it }
            runCatching { repository.listExpenseAnalyserMailPdfs() }
                .onSuccess { mailPdfs = it.filter { p -> p.status == "needs_password" || p.status == "failed" } }
        }
    }
    LaunchedEffect(Unit) { reload() }

    Column(
        Modifier
            .fillMaxSize()
            .background(HubBg)
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp, vertical = 12.dp)
    ) {
        TextButton(onClick = onOpenModules) { Text("Modules", color = InkSoft) }
        Text("Gmail & sync", style = MaterialTheme.typography.headlineMedium, color = Ink, fontWeight = FontWeight.Bold)
        Text("Read-only Gmail for bank alerts. Posting to Money Manager stays a separate step.", color = InkSoft, style = MaterialTheme.typography.bodySmall)
        Spacer(Modifier.height(16.dp))
        val st = status
        Box(
            Modifier
                .fillMaxWidth()
                .clip(CardShape)
                .background(HubGlass)
                .border(1.dp, LineColor, CardShape)
                .padding(16.dp)
        ) {
            Column {
                Text("Gmail", color = Ink, fontWeight = FontWeight.SemiBold)
                if (st?.connected == true) {
                    Text("Connected as ${st.email ?: "Gmail account"}", color = Sage, modifier = Modifier.padding(top = 6.dp))
                    st.last_sync_at?.let {
                        Text("Last sync ${it.replace('T', ' ').take(19)}", color = InkSoft, style = MaterialTheme.typography.bodySmall)
                    }
                    Spacer(Modifier.height(10.dp))
                    Row(
                        Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Button(
                            onClick = {
                                scope.launch {
                                    runCatching { repository.syncExpenseAnalyser() }
                                        .onSuccess {
                                            Toast.makeText(context, "Synced · ${it.created} new", Toast.LENGTH_SHORT).show()
                                            reload()
                                        }
                                        .onFailure { Toast.makeText(context, errMessage(it), Toast.LENGTH_LONG).show() }
                                }
                            },
                            colors = ButtonDefaults.buttonColors(containerColor = Navy),
                            enabled = st.syncing != true
                        ) { Text(if (st.syncing) "Syncing…" else "Sync now") }
                        OutlinedButton(
                            onClick = {
                                scope.launch {
                                    runCatching { repository.importExpenseAnalyserPdfs() }
                                        .onSuccess {
                                            Toast.makeText(context, "Loading PDFs from Gmail…", Toast.LENGTH_SHORT).show()
                                            reload()
                                        }
                                        .onFailure { Toast.makeText(context, errMessage(it), Toast.LENGTH_LONG).show() }
                                }
                            },
                            enabled = st.syncing != true
                        ) { Text("Load PDFs") }
                        OutlinedButton(onClick = {
                            scope.launch {
                                runCatching { repository.disconnectExpenseAnalyser() }
                                    .onSuccess { reload() }
                                    .onFailure { Toast.makeText(context, errMessage(it), Toast.LENGTH_SHORT).show() }
                            }
                        }) { Text("Disconnect") }
                    }
                } else {
                    Text(
                        if (st?.server_oauth == true) "Connect your mailbox on the website with read-only access."
                        else "Super Admin must configure the Google OAuth client first.",
                        color = InkSoft,
                        style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier.padding(top = 6.dp, bottom = 10.dp)
                    )
                    Button(
                        onClick = {
                            val url = adminUrl(repository, "/admin/expense-analyser/settings")
                            if (url.isNotBlank()) context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = Navy)
                    ) { Text("Open website to connect") }
                }
            }
        }
        Spacer(Modifier.height(12.dp))
        Box(
            Modifier
                .fillMaxWidth()
                .clip(CardShape)
                .background(HubGlass)
                .border(1.dp, LineColor, CardShape)
                .padding(16.dp)
        ) {
            Column {
                Text("Daily auto-sync", color = Ink, fontWeight = FontWeight.SemiBold)
                Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(top = 8.dp)) {
                    Text("Sync Gmail once a day", color = Ink, modifier = Modifier.weight(1f))
                    Switch(
                        checked = st?.enabled == true,
                        onCheckedChange = { on ->
                            scope.launch {
                                runCatching { repository.saveExpenseAnalyserSchedule(on, st?.hour ?: 6) }
                                    .onSuccess { status = it }
                                    .onFailure { Toast.makeText(context, errMessage(it), Toast.LENGTH_SHORT).show() }
                            }
                        },
                        enabled = st?.connected == true
                    )
                }
                Text("Preferred hour (server local time)", color = InkSoft, style = MaterialTheme.typography.bodySmall)
                Box {
                    OutlinedButton(onClick = { hourOpen = true }, enabled = st?.connected == true, modifier = Modifier.padding(top = 6.dp)) {
                        Text("%02d:00".format(st?.hour ?: 6))
                    }
                    DropdownMenu(expanded = hourOpen, onDismissRequest = { hourOpen = false }) {
                        (0..23).forEach { h ->
                            DropdownMenuItem(
                                text = { Text("%02d:00".format(h)) },
                                onClick = {
                                    hourOpen = false
                                    scope.launch {
                                        runCatching { repository.saveExpenseAnalyserSchedule(st?.enabled == true, h) }
                                            .onSuccess { status = it }
                                            .onFailure { Toast.makeText(context, errMessage(it), Toast.LENGTH_SHORT).show() }
                                    }
                                }
                            )
                        }
                    }
                }
            }
        }
        Spacer(Modifier.height(12.dp))
        Box(
            Modifier
                .fillMaxWidth()
                .clip(CardShape)
                .background(HubGlass)
                .border(1.dp, LineColor, CardShape)
                .padding(16.dp)
        ) {
            Column {
                Text("Gmail search", color = Ink, fontWeight = FontWeight.SemiBold)
                OutlinedTextField(
                    value = query,
                    onValueChange = { query = it },
                    modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                    minLines = 3,
                    label = { Text("Query") }
                )
                Button(
                    onClick = {
                        scope.launch {
                            runCatching { repository.saveExpenseAnalyserQuery(query.ifBlank { null }) }
                                .onSuccess {
                                    status = it
                                    Toast.makeText(context, "Query saved", Toast.LENGTH_SHORT).show()
                                }
                                .onFailure { Toast.makeText(context, errMessage(it), Toast.LENGTH_SHORT).show() }
                        }
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = Navy),
                    modifier = Modifier.padding(top = 8.dp)
                ) { Text("Save query") }
            }
        }
        Spacer(Modifier.height(12.dp))
        Box(
            Modifier
                .fillMaxWidth()
                .clip(CardShape)
                .background(HubGlass)
                .border(1.dp, LineColor, CardShape)
                .padding(16.dp)
        ) {
            Column {
                Text("Bank PDF passwords", color = Ink, fontWeight = FontWeight.SemiBold)
                Text(
                    "Add each bank and the password printed on the statement so Gmail PDFs unlock automatically.",
                    color = InkSoft,
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.padding(top = 6.dp, bottom = 8.dp)
                )
                passwords.forEach { row ->
                    Row(
                        Modifier.fillMaxWidth().padding(vertical = 4.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column(Modifier.weight(1f)) {
                            Text(row.identifier, color = Ink)
                            Text(
                                listOfNotNull(
                                    row.account_type.replace('_', ' '),
                                    row.last_4_digits
                                ).joinToString(" · "),
                                color = InkSoft,
                                style = MaterialTheme.typography.bodySmall
                            )
                        }
                        TextButton(onClick = {
                            scope.launch {
                                runCatching { repository.deleteShopPdfPassword(row.id) }
                                    .onSuccess { reload() }
                                    .onFailure { Toast.makeText(context, errMessage(it), Toast.LENGTH_SHORT).show() }
                            }
                        }) { Text("Remove", color = StampRed) }
                    }
                }
                OutlinedTextField(
                    value = bankLabel,
                    onValueChange = { bankLabel = it },
                    modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                    label = { Text("Bank / label") },
                    placeholder = { Text("HDFC 4521") },
                    singleLine = true
                )
                OutlinedTextField(
                    value = bankPassword,
                    onValueChange = { bankPassword = it },
                    modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                    label = { Text("PDF password") },
                    singleLine = true,
                    visualTransformation = PasswordVisualTransformation()
                )
                OutlinedTextField(
                    value = bankLast4,
                    onValueChange = { bankLast4 = it.take(8) },
                    modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                    label = { Text("Last 4 (optional)") },
                    singleLine = true
                )
                Row(
                    Modifier.padding(top = 8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("Credit card", color = Ink, modifier = Modifier.weight(1f))
                    Switch(checked = bankIsCard, onCheckedChange = { bankIsCard = it })
                }
                Button(
                    onClick = {
                        if (bankLabel.isBlank() || bankPassword.isBlank()) {
                            Toast.makeText(context, "Bank name and password are required", Toast.LENGTH_SHORT).show()
                            return@Button
                        }
                        scope.launch {
                            runCatching {
                                repository.saveShopPdfPassword(
                                    ShopPdfPasswordIn(
                                        identifier = bankLabel.trim(),
                                        password = bankPassword,
                                        account_type = if (bankIsCard) "credit_card" else "bank",
                                        last_4_digits = bankLast4.trim().ifBlank { null }
                                    )
                                )
                            }.onSuccess {
                                bankLabel = ""
                                bankPassword = ""
                                bankLast4 = ""
                                bankIsCard = false
                                Toast.makeText(context, "Bank password saved", Toast.LENGTH_SHORT).show()
                                reload()
                            }.onFailure { Toast.makeText(context, errMessage(it), Toast.LENGTH_LONG).show() }
                        }
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = Navy),
                    modifier = Modifier.padding(top = 8.dp)
                ) { Text("Save bank") }
                mailPdfs.takeIf { it.isNotEmpty() }?.let { locked ->
                    Text(
                        "${locked.size} Gmail PDF(s) still need a password or failed to parse.",
                        color = InkSoft,
                        style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier.padding(top = 10.dp)
                    )
                }
            }
        }
        Spacer(Modifier.height(12.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = {
                scope.launch {
                    runCatching { repository.reconcileExpenseAnalyser() }
                        .onSuccess { Toast.makeText(context, "Re-matched ${it.updated}", Toast.LENGTH_SHORT).show() }
                        .onFailure { Toast.makeText(context, errMessage(it), Toast.LENGTH_SHORT).show() }
                }
            }) { Text("Re-match ledger") }
            OutlinedButton(onClick = {
                scope.launch {
                    runCatching { repository.retagExpenseAnalyser() }
                        .onSuccess { Toast.makeText(context, "AI re-tag started", Toast.LENGTH_SHORT).show() }
                        .onFailure { Toast.makeText(context, errMessage(it), Toast.LENGTH_SHORT).show() }
                }
            }) { Text("AI re-tag") }
        }
        Spacer(Modifier.height(8.dp))
        TextButton(onClick = {
            scope.launch {
                runCatching { repository.clearExpenseAnalyser() }
                    .onSuccess {
                        Toast.makeText(context, "Cleared ${it.deleted} items", Toast.LENGTH_SHORT).show()
                        reload()
                    }
                    .onFailure { Toast.makeText(context, errMessage(it), Toast.LENGTH_SHORT).show() }
            }
        }) { Text("Clear inbox", color = StampRed) }
        Spacer(Modifier.height(32.dp))
    }
}
