package com.rklab.healthvault.ui.screens.finance

import androidx.compose.foundation.background
import androidx.compose.foundation.border
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
import com.rklab.healthvault.data.model.FinanceReportRow
import com.rklab.healthvault.data.model.FinanceSummaryOut
import com.rklab.healthvault.data.model.FinanceTxnOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.theme.*
import kotlinx.coroutines.launch
import java.time.YearMonth

@Composable
fun FinanceHomeScreen(
    repository: HealthVaultRepository,
    onAdd: () -> Unit,
    onOpenModules: () -> Unit,
    onSeeAll: () -> Unit,
    onEdit: (String) -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var month by remember { mutableStateOf(YearMonth.now()) }
    val monthKey = month.format(monthFmt)
    var summary by remember { mutableStateOf<FinanceSummaryOut?>(null) }
    var items by remember { mutableStateOf<List<FinanceTxnOut>>(emptyList()) }
    var topRow by remember { mutableStateOf<FinanceReportRow?>(null) }
    var error by remember { mutableStateOf<String?>(null) }

    fun reload() {
        scope.launch {
            runCatching {
                summary = repository.financeSummary(monthKey)
                items = repository.listFinanceTransactions(monthKey)
                topRow = repository.financeReports(monthKey, "expense").rows.firstOrNull()
            }.onFailure { error = it.message }
        }
    }
    LaunchedEffect(monthKey) {
        reload()
        FinanceSmsIngestor.scanInbox(context)
    }

    val expenses = items.filter { it.txn_type == "expense" }
    val highest = expenses.maxByOrNull { it.amount }
    val recent = items.take(8)

    Box(Modifier.fillMaxSize().background(HubBg)) {
        Column(Modifier.fillMaxSize()) {
            Row(
                Modifier.fillMaxWidth().padding(20.dp, 16.dp, 8.dp, 8.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(Modifier.weight(1f)) {
                    Text("MONEY MANAGER", style = MaterialTheme.typography.labelMedium, color = VaultGold)
                    Text("Home", style = MaterialTheme.typography.headlineMedium, color = Ink, fontWeight = FontWeight.Bold)
                    Text("Track every rupee. Understand every expense.", color = InkSoft, style = MaterialTheme.typography.bodySmall)
                }
                IconButton(onClick = onOpenModules) {
                    Icon(Icons.Filled.Apps, contentDescription = "Modules", tint = InkSoft)
                }
            }
            IncomingSmsBanner(onChanged = { reload() })
            error?.let { Text(it, color = StampRed, modifier = Modifier.padding(16.dp)) }
            LazyColumn(
                Modifier.fillMaxSize(),
                contentPadding = PaddingValues(16.dp, 4.dp, 16.dp, 96.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                item {
                    Row(
                        Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.Center,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text("‹", color = InkSoft, modifier = Modifier.clickable { month = month.minusMonths(1) }.padding(8.dp), fontWeight = FontWeight.Bold)
                        Text(month.format(monthLabelFmt), color = Ink, fontWeight = FontWeight.SemiBold)
                        Text("›", color = InkSoft, modifier = Modifier.clickable { month = month.plusMonths(1) }.padding(8.dp), fontWeight = FontWeight.Bold)
                    }
                }
                summary?.let { s ->
                    item {
                        Column(
                            Modifier
                                .fillMaxWidth()
                                .clip(RoundedCornerShape(22.dp))
                                .background(Color(0xFF0E2E38))
                                .border(1.dp, VaultTealLine, RoundedCornerShape(22.dp))
                                .padding(20.dp)
                        ) {
                            Text("TOTAL BALANCE", color = Color(0xB3F4FFFC), style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold)
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text(inr(s.net), color = Color.White, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.headlineMedium)
                                Spacer(Modifier.width(10.dp))
                                Text(
                                    "ACTIVE",
                                    color = VaultTeal,
                                    fontWeight = FontWeight.Bold,
                                    style = MaterialTheme.typography.labelSmall,
                                    modifier = Modifier
                                        .clip(RoundedCornerShape(99.dp))
                                        .background(VaultTealSoft)
                                        .padding(horizontal = 8.dp, vertical = 4.dp)
                                )
                            }
                            Text(
                                "Net this month ${inr(s.total)} · opening ${inr(s.opening)}",
                                color = if (s.total >= 0) Sage else ExpenseRed,
                                style = MaterialTheme.typography.bodySmall,
                                fontWeight = FontWeight.SemiBold
                            )
                        }
                    }
                    item {
                        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            DashSplitCard(
                                label = "Income",
                                value = inr(s.income),
                                valueColor = Sage,
                                tint = SageBg,
                                modifier = Modifier.weight(1f)
                            )
                            DashSplitCard(
                                label = "Expenses",
                                value = inr(s.expense),
                                valueColor = ExpenseRed,
                                tint = StampRedSoft,
                                modifier = Modifier.weight(1f)
                            )
                        }
                    }
                    item {
                        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            DashSplitCard(
                                label = "Top category",
                                value = topRow?.name ?: "No spend yet",
                                meta = topRow?.let { "${inr(it.amount)} · ${it.pct.toInt()}% of spend" },
                                modifier = Modifier.weight(1f)
                            )
                            DashSplitCard(
                                label = "Highest spend",
                                value = highest?.payee ?: highest?.category_name ?: "Nothing posted",
                                meta = highest?.let { inr(it.amount) },
                                valueColor = if (highest != null) ExpenseRed else Ink,
                                modifier = Modifier.weight(1f)
                            )
                        }
                    }
                    item {
                        Column(
                            Modifier
                                .fillMaxWidth()
                                .clip(RoundedCornerShape(18.dp))
                                .background(Color(0xFF16343C))
                                .border(1.dp, VaultTealLine, RoundedCornerShape(18.dp))
                                .padding(16.dp)
                        ) {
                            Text("SMART INSIGHT", color = VaultTeal, style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold)
                            Spacer(Modifier.height(6.dp))
                            Text(financeInsight(s, topRow, highest), color = Color(0xE0F4FFFC), style = MaterialTheme.typography.bodyMedium)
                        }
                    }
                }
                item {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                        Text("Recent", color = Ink, fontWeight = FontWeight.SemiBold)
                        Text("See all", color = VaultTeal, style = MaterialTheme.typography.bodySmall, modifier = Modifier.clickable(onClick = onSeeAll))
                    }
                }
                if (recent.isEmpty()) {
                    item {
                        Text("Nothing this month yet. Tap + to log the first entry.", color = InkSoft, style = MaterialTheme.typography.bodySmall)
                    }
                } else {
                    items(recent, key = { it.id }) { t ->
                        FinanceTxnCard(txn = t, onClick = { onEdit(t.id) })
                    }
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
private fun DashSplitCard(
    label: String,
    value: String,
    modifier: Modifier = Modifier,
    meta: String? = null,
    valueColor: Color = Ink,
    tint: Color = HubGlass
) {
    Column(
        modifier
            .clip(RoundedCornerShape(18.dp))
            .background(tint)
            .border(1.dp, HubStroke, RoundedCornerShape(18.dp))
            .padding(14.dp)
    ) {
        Text(label.uppercase(), color = InkSoft, style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(6.dp))
        Text(value, color = valueColor, fontWeight = FontWeight.Bold)
        if (meta != null) {
            Spacer(Modifier.height(4.dp))
            Text(meta, color = InkSoft, style = MaterialTheme.typography.bodySmall)
        }
    }
}
