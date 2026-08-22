package com.rklab.healthvault.ui.screens.finance

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.PhotoCamera
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import com.rklab.healthvault.data.model.*
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.theme.*
import com.rklab.healthvault.util.FileUtil
import kotlinx.coroutines.launch
import java.io.File
import java.time.Instant
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

private enum class EntrySheet { None, Account, ToAccount, Category, Method }

private val dateRowFmt: DateTimeFormatter =
    DateTimeFormatter.ofPattern("dd/MM/yy (EEE) h:mm a", Locale.US)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FinanceAddScreen(
    repository: HealthVaultRepository,
    onDone: () -> Unit,
    onBack: () -> Unit = onDone,
    prefillAccountId: String? = null,
    txnId: String? = null
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var accounts by remember { mutableStateOf<List<FinanceAccountOut>>(emptyList()) }
    var categories by remember { mutableStateOf<List<FinanceCategoryOut>>(emptyList()) }
    var txnType by remember { mutableStateOf("expense") }
    var accountId by remember { mutableStateOf(prefillAccountId) }
    var toAccountId by remember { mutableStateOf<String?>(null) }
    var categoryId by remember { mutableStateOf<String?>(null) }
    var amount by remember { mutableStateOf("") }
    var payee by remember { mutableStateOf("") }
    var description by remember { mutableStateOf("") }
    var paymentMethod by remember { mutableStateOf<String?>(null) }
    var whenAt by remember { mutableStateOf(LocalDateTime.now().withSecond(0).withNano(0)) }
    var error by remember { mutableStateOf<String?>(null) }
    var saving by remember { mutableStateOf(false) }
    var sheet by remember { mutableStateOf(EntrySheet.None) }
    var showDate by remember { mutableStateOf(false) }
    var showTime by remember { mutableStateOf(false) }
    val zone = ZoneId.systemDefault()
    val datePicker = rememberDatePickerState(
        initialSelectedDateMillis = whenAt.atZone(zone).toInstant().toEpochMilli()
    )
    val timePicker = rememberTimePickerState(
        initialHour = whenAt.hour,
        initialMinute = whenAt.minute,
        is24Hour = false
    )
    var receiptFile by remember { mutableStateOf<File?>(null) }
    var captureFile by remember { mutableStateOf<File?>(null) }
    val accent = if (txnType == "income") IncomeBlue else ExpenseRed

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

    fun reloadCats() {
        scope.launch {
            categories = repository.listFinanceCategories(accountId)
        }
    }

    LaunchedEffect(Unit) {
        scope.launch {
            accounts = repository.listFinanceAccounts()
            if (!txnId.isNullOrBlank()) {
                runCatching { repository.getFinanceTransaction(txnId) }.onSuccess { t ->
                    txnType = t.txn_type
                    accountId = t.account_id
                    toAccountId = t.to_account_id
                    categoryId = t.category_id
                    amount = if (t.amount == t.amount.toLong().toDouble()) t.amount.toLong().toString() else t.amount.toString()
                    payee = t.payee.orEmpty()
                    description = t.description.orEmpty()
                    paymentMethod = t.payment_method
                    val date = runCatching { LocalDate.parse(t.txn_date) }.getOrNull() ?: LocalDate.now()
                    val time = runCatching {
                        LocalTime.parse((t.txn_time ?: "12:00").take(5))
                    }.getOrDefault(LocalTime.now().withSecond(0).withNano(0))
                    whenAt = LocalDateTime.of(date, time)
                }.onFailure { error = it.message }
            } else {
                if (accountId == null) accountId = accounts.firstOrNull()?.id
                toAccountId = accounts.firstOrNull { it.id != accountId }?.id
            }
            categories = repository.listFinanceCategories(accountId)
            if (txnId.isNullOrBlank()) {
                categoryId = categories.firstOrNull { it.kind == txnType && it.parent_id == null }?.id
            }
        }
    }
    LaunchedEffect(accountId) { reloadCats() }

    val account = accounts.firstOrNull { it.id == accountId }
    val noDefaultCategories = account?.no_default_categories == true
    val visibleCats = categories.filter {
        it.kind == txnType && (it.account_id == accountId || (!noDefaultCategories && it.account_id == null))
    }
    LaunchedEffect(txnType, categories, accountId) {
        if (visibleCats.isEmpty()) return@LaunchedEffect
        if (visibleCats.none { it.id == categoryId }) {
            categoryId = visibleCats.firstOrNull { it.parent_id == null }?.id
        }
    }

    val toAccount = accounts.firstOrNull { it.id == toAccountId }
    val category = categories.firstOrNull { it.id == categoryId }
    val categoryLabel = when {
        category == null -> "Select"
        !category.parent_name.isNullOrBlank() -> "${category.parent_name} › ${category.name}"
        else -> category.name
    }

    Column(Modifier.fillMaxSize().background(HubBg)) {
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            IconButton(onClick = onBack) {
                Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back", tint = Ink)
            }
            Text(
                if (txnId.isNullOrBlank()) txnType.replaceFirstChar { it.uppercase() } else "Edit ${txnType}",
                color = Ink,
                fontWeight = FontWeight.Bold,
                fontSize = 20.sp,
                modifier = Modifier.weight(1f)
            )
        }
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 16.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            listOf("income" to "Income", "expense" to "Expense", "transfer" to "Transfer").forEach { (key, label) ->
                val on = txnType == key
                Box(
                    Modifier
                        .weight(1f)
                        .height(40.dp)
                        .clip(RoundedCornerShape(8.dp))
                        .border(1.dp, if (on) accent else LineColor, RoundedCornerShape(8.dp))
                        .background(if (on) accent.copy(alpha = 0.12f) else Color.Transparent)
                        .clickable { txnType = key },
                    contentAlignment = Alignment.Center
                ) {
                    Text(label, color = if (on) accent else Ink, fontWeight = FontWeight.SemiBold)
                }
            }
        }
        Spacer(Modifier.height(8.dp))
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) {
            EntryField(label = "Date", value = whenAt.format(dateRowFmt), active = showDate || showTime) {
                showDate = true
            }
            EntryField(label = "Account", value = account?.name ?: "Select", active = sheet == EntrySheet.Account) {
                sheet = EntrySheet.Account
            }
            if (txnType == "transfer") {
                EntryField(label = "To account", value = toAccount?.name ?: "Select", active = sheet == EntrySheet.ToAccount) {
                    sheet = EntrySheet.ToAccount
                }
            } else {
                EntryField(label = "Category", value = categoryLabel, active = sheet == EntrySheet.Category) {
                    sheet = EntrySheet.Category
                }
            }
            EntryInput(label = "Amount", value = amount, onValueChange = { amount = it.filter { ch -> ch.isDigit() || ch == '.' } }, keyboard = KeyboardType.Decimal)
            EntryField(label = "Paid by", value = methodLabel(paymentMethod) ?: "Select", active = sheet == EntrySheet.Method) {
                sheet = EntrySheet.Method
            }
            EntryInput(label = "Note", value = payee, onValueChange = { payee = it })
            EntryInput(
                label = "Description",
                value = description,
                onValueChange = { description = it },
                trailing = {
                    IconButton(onClick = {
                        if (ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
                            launchCamera()
                        } else {
                            cameraPermLauncher.launch(Manifest.permission.CAMERA)
                        }
                    }) {
                        Icon(
                            Icons.Filled.PhotoCamera,
                            contentDescription = "Receipt photo",
                            tint = if (receiptFile != null) accent else InkSoft
                        )
                    }
                }
            )
            if (receiptFile != null) {
                Text(
                    "Photo attached · tap to remove",
                    color = InkSoft,
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.padding(horizontal = 20.dp, vertical = 6.dp).clickable { receiptFile = null }
                )
            }
            TextButton(onClick = { galleryLauncher.launch("image/*") }, modifier = Modifier.padding(horizontal = 8.dp)) {
                Text("Choose from gallery", color = InkSoft)
            }
            error?.let { Text(it, color = StampRed, modifier = Modifier.padding(20.dp, 8.dp)) }
            Spacer(Modifier.height(12.dp))
            Button(
                onClick = {
                    val acc = accountId ?: return@Button
                    val amt = amount.toDoubleOrNull() ?: 0.0
                    if (amt <= 0) { error = "Enter an amount"; return@Button }
                    if (txnType == "transfer" && (toAccountId == null || toAccountId == acc)) {
                        error = "Pick a different account to transfer to"
                        return@Button
                    }
                    saving = true
                    scope.launch {
                        runCatching {
                            val body = FinanceTxnIn(
                                account_id = acc,
                                to_account_id = if (txnType == "transfer") toAccountId else null,
                                category_id = if (txnType == "transfer") null else categoryId,
                                txn_type = txnType,
                                amount = amt,
                                txn_date = whenAt.toLocalDate().toString(),
                                txn_time = whenAt.toLocalTime().format(DateTimeFormatter.ofPattern("HH:mm")),
                                payee = payee.ifBlank { null },
                                description = description.ifBlank { null },
                                payment_method = paymentMethod
                            )
                            val saved = if (!txnId.isNullOrBlank()) {
                                repository.updateFinanceTransaction(txnId, body)
                            } else {
                                repository.createFinanceTransaction(body)
                            }
                            receiptFile?.let { repository.uploadFinanceImage(saved.id, it) }
                        }.onSuccess { onDone() }.onFailure { error = it.message }
                        saving = false
                    }
                },
                enabled = !saving,
                modifier = Modifier.fillMaxWidth().padding(20.dp).height(48.dp),
                shape = RoundedCornerShape(10.dp),
                colors = ButtonDefaults.buttonColors(containerColor = accent)
            ) { Text(if (saving) "Saving…" else if (txnId.isNullOrBlank()) "Save" else "Update", color = Color.White, fontWeight = FontWeight.Bold) }
        }
    }

    if (showDate) {
        DatePickerDialog(
            onDismissRequest = { showDate = false },
            confirmButton = {
                TextButton(onClick = {
                    datePicker.selectedDateMillis?.let { ms ->
                        val d = Instant.ofEpochMilli(ms).atZone(zone).toLocalDate()
                        whenAt = LocalDateTime.of(d, whenAt.toLocalTime())
                    }
                    showDate = false
                    showTime = true
                }) { Text("Next") }
            },
            dismissButton = { TextButton(onClick = { showDate = false }) { Text("Cancel") } }
        ) { DatePicker(state = datePicker) }
    }
    if (showTime) {
        AlertDialog(
            onDismissRequest = { showTime = false },
            confirmButton = {
                TextButton(onClick = {
                    whenAt = LocalDateTime.of(whenAt.toLocalDate(), LocalTime.of(timePicker.hour, timePicker.minute))
                    showTime = false
                }) { Text("OK") }
            },
            dismissButton = { TextButton(onClick = { showTime = false }) { Text("Skip") } },
            title = { Text("Time") },
            text = { TimePicker(state = timePicker) }
        )
    }

    if (sheet == EntrySheet.Account || sheet == EntrySheet.ToAccount) {
        val pickingTo = sheet == EntrySheet.ToAccount
        AccountPickerSheet(
            title = if (pickingTo) "To account" else "Accounts",
            accounts = accounts,
            selectedId = if (pickingTo) toAccountId else accountId,
            onSelect = {
                if (pickingTo) toAccountId = it else accountId = it
                sheet = EntrySheet.None
            },
            onAdd = { name, type, noDefault ->
                scope.launch {
                    runCatching {
                        repository.createFinanceAccount(
                            FinanceAccountIn(name, type, no_default_categories = noDefault)
                        )
                    }
                        .onSuccess { created ->
                            accounts = repository.listFinanceAccounts()
                            if (pickingTo) toAccountId = created.id else accountId = created.id
                        }
                }
            },
            onClose = { sheet = EntrySheet.None }
        )
    }
    if (sheet == EntrySheet.Category) {
        CategoryPickerSheet(
            categories = visibleCats,
            selectedId = categoryId,
            accent = accent,
            onSelect = { categoryId = it; sheet = EntrySheet.None },
            onAdd = { name, parentId ->
                scope.launch {
                    runCatching {
                        repository.createFinanceCategory(
                            FinanceCategoryIn(
                                name = name,
                                kind = txnType,
                                account_id = accountId.takeIf { noDefaultCategories },
                                parent_id = parentId
                            )
                        )
                    }.onSuccess { created ->
                        categories = repository.listFinanceCategories(accountId)
                        categoryId = created.id
                    }
                }
            },
            onClose = { sheet = EntrySheet.None }
        )
    }
    if (sheet == EntrySheet.Method) {
        MethodPickerSheet(
            selected = paymentMethod,
            onSelect = { paymentMethod = it; sheet = EntrySheet.None },
            onClose = { sheet = EntrySheet.None }
        )
    }
}

@Composable
private fun EntryField(label: String, value: String, active: Boolean, onClick: () -> Unit) {
    Column(
        Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(horizontal = 20.dp, vertical = 12.dp)
    ) {
        Text(label, color = InkSoft, style = MaterialTheme.typography.labelMedium)
        Spacer(Modifier.height(4.dp))
        Text(value, color = Ink, fontWeight = FontWeight.Medium, fontSize = 16.sp)
    }
    HorizontalDivider(color = if (active) ExpenseRed else LineColor, thickness = if (active) 2.dp else 1.dp)
}

@Composable
private fun EntryInput(
    label: String,
    value: String,
    onValueChange: (String) -> Unit,
    keyboard: KeyboardType = KeyboardType.Text,
    trailing: @Composable (() -> Unit)? = null
) {
    Row(
        Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(Modifier.weight(1f)) {
            Text(label, color = InkSoft, style = MaterialTheme.typography.labelMedium)
            Spacer(Modifier.height(4.dp))
            BasicTextField(
                value = value,
                onValueChange = onValueChange,
                textStyle = TextStyle(color = Ink, fontSize = 16.sp, fontWeight = FontWeight.Medium),
                cursorBrush = SolidColor(Ink),
                singleLine = keyboard != KeyboardType.Text || label != "Description",
                keyboardOptions = KeyboardOptions(keyboardType = keyboard),
                modifier = Modifier.fillMaxWidth()
            )
        }
        trailing?.invoke()
    }
    HorizontalDivider(color = LineColor)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AccountPickerSheet(
    title: String,
    accounts: List<FinanceAccountOut>,
    selectedId: String?,
    onSelect: (String) -> Unit,
    onAdd: (String, String, Boolean) -> Unit,
    onClose: () -> Unit
) {
    var adding by remember { mutableStateOf(false) }
    var newName by remember { mutableStateOf("") }
    var newType by remember { mutableStateOf("bank") }
    var noDefaultCategories by remember { mutableStateOf(false) }
    ModalBottomSheet(
        onDismissRequest = onClose,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = PaperDeep,
        dragHandle = null
    ) {
        SheetHeader(title, onClose, onAdd = { adding = true })
        accounts.chunked(3).forEach { row ->
            Row(
                Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 4.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                row.forEach { a ->
                    val on = a.id == selectedId
                    Box(
                        Modifier
                            .weight(1f)
                            .heightIn(min = 48.dp)
                            .clip(RoundedCornerShape(8.dp))
                            .border(1.dp, if (on) ExpenseRed else LineColor, RoundedCornerShape(8.dp))
                            .background(if (on) ExpenseRed.copy(alpha = 0.14f) else Color.Transparent)
                            .clickable { onSelect(a.id) }
                            .padding(10.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(a.name, color = Ink, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    }
                }
                repeat(3 - row.size) { Spacer(Modifier.weight(1f)) }
            }
        }
        Spacer(Modifier.height(24.dp))
        if (adding) {
            AlertDialog(
                onDismissRequest = { adding = false },
                confirmButton = {
                    TextButton(onClick = {
                        val n = newName.trim()
                        if (n.isNotEmpty()) {
                            onAdd(n, newType, noDefaultCategories)
                            adding = false
                            newName = ""
                            noDefaultCategories = false
                        }
                    }) { Text("Save") }
                },
                dismissButton = { TextButton(onClick = { adding = false }) { Text("Cancel") } },
                title = { Text("New account") },
                text = {
                    Column {
                        OutlinedTextField(value = newName, onValueChange = { newName = it }, label = { Text("Name") })
                        Spacer(Modifier.height(8.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            listOf("cash" to "Cash", "bank" to "Bank", "credit_card" to "Card", "wallet" to "Wallet").forEach { (k, l) ->
                                FilterChip(selected = newType == k, onClick = { newType = k }, label = { Text(l) })
                            }
                        }
                        Spacer(Modifier.height(8.dp))
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Checkbox(checked = noDefaultCategories, onCheckedChange = { noDefaultCategories = it })
                            Text("No default categories", color = InkSoft, style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun CategoryPickerSheet(
    categories: List<FinanceCategoryOut>,
    selectedId: String?,
    accent: Color,
    onSelect: (String) -> Unit,
    onAdd: (String, String?) -> Unit,
    onClose: () -> Unit
) {
    val parents = categories.filter { it.parent_id == null }
    val selected = categories.firstOrNull { it.id == selectedId }
    var parentId by remember {
        mutableStateOf(selected?.parent_id ?: selected?.id ?: parents.firstOrNull()?.id)
    }
    var addingMode by remember { mutableStateOf<String?>(null) } // parent | child
    var newName by remember { mutableStateOf("") }
    LaunchedEffect(selectedId, categories) {
        val cur = categories.firstOrNull { it.id == selectedId }
        parentId = cur?.parent_id ?: cur?.id ?: parents.firstOrNull()?.id
    }
    val children = categories.filter { it.parent_id == parentId }
    ModalBottomSheet(
        onDismissRequest = onClose,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = PaperDeep,
        dragHandle = null
    ) {
        SheetHeader("Category", onClose, onAdd = { addingMode = "parent"; newName = "" })
        Row(Modifier.fillMaxWidth().heightIn(min = 280.dp, max = 420.dp)) {
            Column(
                Modifier.weight(1f).fillMaxHeight().background(HubBg)
            ) {
                parents.forEach { p ->
                    val on = p.id == parentId
                    val kids = categories.filter { it.parent_id == p.id }
                    Row(
                        Modifier
                            .fillMaxWidth()
                            .background(if (on) accent else Color.Transparent)
                            .clickable {
                                parentId = p.id
                                if (kids.isEmpty()) onSelect(p.id)
                            }
                            .padding(14.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(p.name, color = if (on) Color.White else Ink, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                        Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, contentDescription = null, tint = if (on) Color.White else InkSoft, modifier = Modifier.size(18.dp))
                    }
                }
                Text(
                    "+ Category",
                    color = accent,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.clickable { addingMode = "parent"; newName = "" }.padding(14.dp)
                )
            }
            Column(Modifier.weight(1f).fillMaxHeight().background(PaperDeep)) {
                val parent = parents.firstOrNull { it.id == parentId }
                if (parent != null) {
                    val onParent = selectedId == parent.id
                    Text(
                        parent.name,
                        color = if (onParent) accent else Ink,
                        fontWeight = FontWeight.SemiBold,
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable { onSelect(parent.id) }
                            .padding(14.dp)
                    )
                    HorizontalDivider(color = LineColor)
                }
                children.forEach { c ->
                    val on = c.id == selectedId
                    Text(
                        c.name,
                        color = if (on) accent else Ink,
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(if (on) accent.copy(alpha = 0.12f) else Color.Transparent)
                            .clickable { onSelect(c.id) }
                            .padding(14.dp)
                    )
                }
                Text(
                    "+ Subcategory",
                    color = accent,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier
                        .clickable(enabled = parentId != null) {
                            addingMode = "child"
                            newName = ""
                        }
                        .padding(14.dp)
                )
            }
        }
        if (addingMode != null) {
            val forChild = addingMode == "child"
            AlertDialog(
                onDismissRequest = { addingMode = null },
                confirmButton = {
                    TextButton(onClick = {
                        val n = newName.trim()
                        if (n.isNotEmpty()) {
                            onAdd(n, if (forChild) parentId else null)
                            addingMode = null
                            newName = ""
                        }
                    }) { Text("Save") }
                },
                dismissButton = { TextButton(onClick = { addingMode = null }) { Text("Cancel") } },
                title = { Text(if (forChild) "New subcategory" else "New category") },
                text = {
                    OutlinedTextField(value = newName, onValueChange = { newName = it }, label = { Text("Name") })
                }
            )
        }
        Spacer(Modifier.height(16.dp))
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MethodPickerSheet(
    selected: String?,
    onSelect: (String) -> Unit,
    onClose: () -> Unit
) {
    ModalBottomSheet(
        onDismissRequest = onClose,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = PaperDeep,
        dragHandle = null
    ) {
        SheetHeader("Paid by", onClose)
        PAY_METHODS.chunked(3).forEach { row ->
            Row(
                Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 4.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                row.forEach { (key, label) ->
                    val on = key == selected
                    Box(
                        Modifier
                            .weight(1f)
                            .heightIn(min = 44.dp)
                            .clip(RoundedCornerShape(8.dp))
                            .border(1.dp, if (on) ExpenseRed else LineColor, RoundedCornerShape(8.dp))
                            .clickable { onSelect(key) }
                            .padding(10.dp),
                        contentAlignment = Alignment.Center
                    ) { Text(label, color = Ink) }
                }
                repeat(3 - row.size) { Spacer(Modifier.weight(1f)) }
            }
        }
        Spacer(Modifier.height(24.dp))
    }
}

@Composable
private fun SheetHeader(title: String, onClose: () -> Unit, onAdd: (() -> Unit)? = null) {
    Row(
        Modifier.fillMaxWidth().padding(12.dp, 8.dp, 4.dp, 8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(title, color = Ink, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
        if (onAdd != null) {
            IconButton(onClick = onAdd) {
                Icon(Icons.Filled.Edit, contentDescription = "Add", tint = InkSoft)
            }
        }
        IconButton(onClick = onClose) {
            Icon(Icons.Filled.Close, contentDescription = "Close", tint = InkSoft)
        }
    }
}
