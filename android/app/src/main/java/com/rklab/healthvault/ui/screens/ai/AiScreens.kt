package com.rklab.healthvault.ui.screens.ai

import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Bolt
import androidx.compose.material.icons.filled.Chat
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.SmartToy
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.foundation.horizontalScroll
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
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
import com.rklab.healthvault.data.model.AiChatMessageOut
import com.rklab.healthvault.data.model.AiChatThreadOut
import com.rklab.healthvault.data.model.AiProviderIn
import com.rklab.healthvault.data.model.AiProviderOut
import com.rklab.healthvault.data.model.AiStatusOut
import com.rklab.healthvault.data.model.AiUsageLogOut
import com.rklab.healthvault.data.model.AiUsageSummaryOut
import com.rklab.healthvault.data.model.AiVaultAction
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.google.gson.Gson
import com.rklab.healthvault.ui.theme.HubBg
import com.rklab.healthvault.ui.theme.HubGlass
import com.rklab.healthvault.ui.theme.HubSlate
import com.rklab.healthvault.ui.theme.Ink
import com.rklab.healthvault.ui.theme.InkSoft
import com.rklab.healthvault.ui.theme.LineColor
import com.rklab.healthvault.ui.theme.Navy
import com.rklab.healthvault.ui.theme.Sage
import com.rklab.healthvault.ui.theme.StampRed
import com.rklab.healthvault.ui.theme.VaultGold
import kotlinx.coroutines.launch
import retrofit2.HttpException

private val BubbleUser = VaultGold.copy(alpha = 0.18f)
private val BubbleAi = HubGlass
private val vaultActionGson = Gson()
private val vaultActionRegex = Regex(
    """```vault-action\s*(\{[\s\S]*?\})\s*```""",
    setOf(RegexOption.IGNORE_CASE)
)

private data class SplitVaultContent(
    val text: String,
    val action: AiVaultAction?
)

private fun splitVaultAction(content: String): SplitVaultContent {
    val match = vaultActionRegex.find(content) ?: return SplitVaultContent(content, null)
    val raw = match.groupValues.getOrNull(1).orEmpty()
    val action = runCatching { vaultActionGson.fromJson(raw, AiVaultAction::class.java) }.getOrNull()
    val cleaned = content.replace(match.value, "").trim()
    return when (action?.type) {
        "create_shop_list" -> if (!action.items.isNullOrEmpty()) SplitVaultContent(cleaned, action)
            else SplitVaultContent(content, null)
        "create_diary_entry" -> if (!action.title.isNullOrBlank()) SplitVaultContent(cleaned, action)
            else SplitVaultContent(content, null)
        else -> SplitVaultContent(content, null)
    }
}

private val ProviderKinds = listOf(
    "openai" to "ChatGPT / OpenAI",
    "anthropic" to "Claude / Anthropic",
    "openrouter" to "OpenRouter",
    "kimi" to "Kimi / Moonshot",
    "groq" to "Groq",
    "ollama" to "Ollama (local)",
    "custom" to "Custom OpenAI-compatible"
)

private fun errMessage(t: Throwable): String = when (t) {
    is HttpException -> {
        val body = runCatching { t.response()?.errorBody()?.string() }.getOrNull().orEmpty()
        Regex("\"detail\"\\s*:\\s*\"([^\"]+)\"").find(body)?.groupValues?.getOrNull(1)
            ?: t.message()
            ?: "Request failed"
    }
    else -> t.message ?: "Something went wrong"
}

private fun fmtTokens(n: Int?): String =
    if (n == null) "—" else "%,d".format(n)

private fun fmtWhen(iso: String): String {
    val clean = iso.replace('T', ' ').take(19)
    return clean.ifBlank { iso }
}

@Composable
fun AiAskScreen(
    repository: HealthVaultRepository,
    onOpenModules: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var status by remember { mutableStateOf<AiStatusOut?>(null) }
    var threads by remember { mutableStateOf<List<AiChatThreadOut>>(emptyList()) }
    var threadId by remember { mutableStateOf<String?>(null) }
    var title by remember { mutableStateOf("New chat") }
    var messages by remember { mutableStateOf<List<AiChatMessageOut>>(emptyList()) }
    var draft by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var showThreads by remember { mutableStateOf(false) }
    val listState = rememberLazyListState()

    fun reloadThreads() {
        scope.launch {
            runCatching { repository.listAiChatThreads() }
                .onSuccess { threads = it }
        }
    }

    fun openThread(id: String?) {
        scope.launch {
            if (id == null) {
                threadId = null
                title = "New chat"
                messages = emptyList()
                showThreads = false
                return@launch
            }
            runCatching { repository.getAiChatThread(id) }
                .onSuccess {
                    threadId = it.id
                    title = it.title
                    messages = it.messages
                    showThreads = false
                }
                .onFailure {
                    error = errMessage(it)
                    Toast.makeText(context, error, Toast.LENGTH_SHORT).show()
                }
        }
    }

    fun send(text: String) {
        val msg = text.trim()
        if (msg.isEmpty() || busy) return
        if (status?.has_default != true) {
            Toast.makeText(context, "Add a provider first", Toast.LENGTH_SHORT).show()
            return
        }
        busy = true
        error = null
        messages = messages + AiChatMessageOut(id = "local-u", role = "user", content = msg)
        draft = ""
        scope.launch {
            runCatching { repository.aiChat(msg, threadId) }
                .onSuccess {
                    threadId = it.thread_id
                    title = it.title
                    messages = it.messages
                    reloadThreads()
                }
                .onFailure {
                    error = errMessage(it)
                    messages = messages.dropLast(1)
                    Toast.makeText(context, error, Toast.LENGTH_LONG).show()
                }
            busy = false
        }
    }

    LaunchedEffect(Unit) {
        runCatching { repository.aiStatus() }.onSuccess { status = it }
        reloadThreads()
    }
    LaunchedEffect(messages.size) {
        if (messages.isNotEmpty()) listState.animateScrollToItem(messages.lastIndex)
    }

    Scaffold(
        containerColor = HubBg,
        floatingActionButton = {
            FloatingActionButton(
                onClick = { openThread(null) },
                containerColor = VaultGold,
                contentColor = Color(0xFF18130A)
            ) {
                Icon(Icons.Filled.Add, contentDescription = "New chat")
            }
        }
    ) { pad ->
        Column(
            Modifier
                .fillMaxSize()
                .padding(pad)
                .padding(horizontal = 16.dp, vertical = 12.dp)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                TextButton(onClick = onOpenModules) { Text("Modules", color = InkSoft) }
                Spacer(Modifier.weight(1f))
                TextButton(
                    onClick = {
                        scope.launch {
                            runCatching { repository.testAiConnection() }
                                .onSuccess {
                                    Toast.makeText(
                                        context,
                                        "Connected · ${it.name ?: "default"} · ${it.sample}",
                                        Toast.LENGTH_LONG
                                    ).show()
                                }
                                .onFailure {
                                    Toast.makeText(context, errMessage(it), Toast.LENGTH_LONG).show()
                                }
                        }
                    },
                    enabled = status?.has_default == true
                ) { Text("Test", color = InkSoft) }
                TextButton(onClick = { showThreads = !showThreads }) {
                    Text(if (showThreads) "Hide chats" else "Chats", color = InkSoft)
                }
            }
            Text("Ask AI", style = MaterialTheme.typography.headlineMedium, color = Ink, fontWeight = FontWeight.Bold)
            Text(title, color = InkSoft, style = MaterialTheme.typography.bodySmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
            status?.let { s ->
                Text(
                    if (s.has_default) "Using ${s.default_name} · ${s.default_kind ?: ""}"
                    else "No default provider — add one under Providers",
                    color = if (s.has_default) Sage else StampRed,
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.padding(top = 4.dp)
                )
            }
            if (showThreads) {
                Spacer(Modifier.height(8.dp))
                Column(
                    Modifier
                        .fillMaxWidth()
                        .heightIn(max = 180.dp)
                        .clip(RoundedCornerShape(14.dp))
                        .background(HubGlass)
                        .border(1.dp, LineColor, RoundedCornerShape(14.dp))
                        .padding(8.dp)
                ) {
                    if (threads.isEmpty()) {
                        Text("No chats yet", color = InkSoft, modifier = Modifier.padding(8.dp))
                    } else {
                        LazyColumn {
                            items(threads, key = { it.id }) { t ->
                                Row(
                                    Modifier
                                        .fillMaxWidth()
                                        .clip(RoundedCornerShape(10.dp))
                                        .background(if (t.id == threadId) VaultGold.copy(alpha = 0.12f) else Color.Transparent)
                                        .clickable { openThread(t.id) }
                                        .padding(10.dp),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Icon(Icons.Filled.Chat, null, tint = HubSlate, modifier = Modifier.size(18.dp))
                                    Column(Modifier.padding(start = 8.dp).weight(1f)) {
                                        Text(t.title, color = Ink, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                        t.preview?.let {
                                            Text(it, color = InkSoft, style = MaterialTheme.typography.bodySmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                        }
                                    }
                                    IconButton(onClick = {
                                        scope.launch {
                                            runCatching { repository.deleteAiChatThread(t.id) }
                                            if (threadId == t.id) openThread(null)
                                            reloadThreads()
                                        }
                                    }) {
                                        Icon(Icons.Filled.Delete, contentDescription = "Delete", tint = StampRed)
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Spacer(Modifier.height(8.dp))
            LazyColumn(
                state = listState,
                modifier = Modifier.weight(1f).fillMaxWidth(),
                contentPadding = PaddingValues(bottom = 12.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                if (messages.isEmpty()) {
                    item {
                        Column(
                            Modifier.fillMaxWidth().padding(top = 32.dp),
                            horizontalAlignment = Alignment.CenterHorizontally
                        ) {
                            Icon(Icons.Filled.SmartToy, null, tint = HubSlate, modifier = Modifier.size(40.dp))
                            Spacer(Modifier.height(12.dp))
                            Text("Ask anything in this vault", color = Ink, fontWeight = FontWeight.SemiBold)
                            Text(
                                "Reports, shopping lists, diary notes — total charges and save to Digital Diary.",
                                color = InkSoft,
                                style = MaterialTheme.typography.bodySmall,
                                modifier = Modifier.padding(top = 4.dp, start = 24.dp, end = 24.dp)
                            )
                            Spacer(Modifier.height(16.dp))
                            listOf(
                                "Summarise health reports by hospital",
                                "Create a shopping list with onion and rice",
                                "Cake 1200, decor 800 — total and add to diary"
                            ).forEach { hint ->
                                Text(
                                    hint,
                                    color = Ink,
                                    modifier = Modifier
                                        .padding(vertical = 4.dp)
                                        .clip(RoundedCornerShape(20.dp))
                                        .border(1.dp, LineColor, RoundedCornerShape(20.dp))
                                        .clickable { send(hint) }
                                        .padding(horizontal = 14.dp, vertical = 10.dp)
                                )
                            }
                        }
                    }
                }
                items(messages, key = { it.id + it.role + it.content.take(24) }) { m ->
                    val mine = m.role == "user"
                    val split = if (mine) SplitVaultContent(m.content, null) else splitVaultAction(m.content)
                    Column(
                        Modifier.fillMaxWidth(),
                        horizontalAlignment = if (mine) Alignment.End else Alignment.Start
                    ) {
                        Text(
                            split.text,
                            color = Ink,
                            modifier = Modifier
                                .widthIn(max = 320.dp)
                                .clip(RoundedCornerShape(16.dp))
                                .background(if (mine) BubbleUser else BubbleAi)
                                .border(1.dp, if (mine) VaultGold.copy(alpha = 0.35f) else LineColor, RoundedCornerShape(16.dp))
                                .padding(12.dp)
                        )
                        split.action?.let { action ->
                            Spacer(Modifier.height(8.dp))
                            VaultActionCard(
                                action = action,
                                repository = repository,
                                onApplied = { /* stay on thread */ }
                            )
                        }
                    }
                }
                if (busy) {
                    item {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Start) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(22.dp).padding(8.dp),
                                color = VaultGold,
                                strokeWidth = 2.dp
                            )
                        }
                    }
                }
            }

            Row(
                Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(22.dp))
                    .border(1.dp, LineColor, RoundedCornerShape(22.dp))
                    .background(HubGlass)
                    .padding(6.dp),
                verticalAlignment = Alignment.Bottom
            ) {
                OutlinedTextField(
                    value = draft,
                    onValueChange = { draft = it },
                    modifier = Modifier.weight(1f),
                    placeholder = { Text("Ask about hospital, shop list, diary…") },
                    enabled = !busy && status?.has_default == true,
                    maxLines = 5
                )
                IconButton(
                    onClick = { send(draft) },
                    enabled = !busy && draft.isNotBlank() && status?.has_default == true
                ) {
                    Icon(Icons.AutoMirrored.Filled.Send, contentDescription = "Send", tint = VaultGold)
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AiProvidersScreen(
    repository: HealthVaultRepository,
    onOpenModules: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var providers by remember { mutableStateOf<List<AiProviderOut>>(emptyList()) }
    var status by remember { mutableStateOf<AiStatusOut?>(null) }
    var name by remember { mutableStateOf("") }
    var kind by remember { mutableStateOf("openrouter") }
    var apiKey by remember { mutableStateOf("") }
    var model by remember { mutableStateOf("") }
    var baseUrl by remember { mutableStateOf("") }
    var isDefault by remember { mutableStateOf(true) }
    var kindOpen by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var testMsg by remember { mutableStateOf<String?>(null) }

    fun reload() {
        scope.launch {
            runCatching {
                status = repository.aiStatus()
                providers = repository.listAiProviders()
            }.onFailure {
                Toast.makeText(context, errMessage(it), Toast.LENGTH_SHORT).show()
            }
        }
    }

    LaunchedEffect(Unit) { reload() }

    Column(
        Modifier
            .fillMaxSize()
            .background(HubBg)
            .verticalScroll(rememberScrollState())
            .padding(16.dp)
    ) {
        TextButton(onClick = onOpenModules) { Text("Modules", color = InkSoft) }
        Text("AI providers", style = MaterialTheme.typography.headlineMedium, color = Ink, fontWeight = FontWeight.Bold)
        Text("Shared keys for Ask AI, Money Manager SMS, and Expense Analyser.", color = InkSoft, style = MaterialTheme.typography.bodySmall)
        Spacer(Modifier.height(12.dp))
        status?.let { s ->
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                StatChip("${s.count} saved", Modifier.weight(1f))
                StatChip(s.default_name ?: "No default", Modifier.weight(1f))
            }
        }
        Spacer(Modifier.height(10.dp))
        Button(
            onClick = {
                busy = true
                scope.launch {
                    runCatching { repository.testAiConnection() }
                        .onSuccess {
                            testMsg = "Connected · ${it.name ?: "default"} · ${it.sample}"
                            Toast.makeText(context, testMsg, Toast.LENGTH_LONG).show()
                        }
                        .onFailure {
                            testMsg = errMessage(it)
                            Toast.makeText(context, testMsg, Toast.LENGTH_LONG).show()
                        }
                    busy = false
                    reload()
                }
            },
            enabled = !busy && status?.has_default == true,
            colors = ButtonDefaults.buttonColors(containerColor = Navy),
            modifier = Modifier.fillMaxWidth()
        ) {
            Icon(Icons.Filled.Bolt, null, modifier = Modifier.size(18.dp))
            Text("  Test connection", modifier = Modifier.padding(start = 4.dp))
        }
        testMsg?.let {
            Text(it, color = InkSoft, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 6.dp))
        }

        Spacer(Modifier.height(16.dp))
        Text("Add provider", color = Ink, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(value = name, onValueChange = { name = it }, label = { Text("Label") }, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(8.dp))
        ExposedDropdownMenuBox(expanded = kindOpen, onExpandedChange = { kindOpen = it }) {
            OutlinedTextField(
                value = ProviderKinds.firstOrNull { it.first == kind }?.second ?: kind,
                onValueChange = {},
                readOnly = true,
                label = { Text("Provider") },
                trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(kindOpen) },
                modifier = Modifier.menuAnchor().fillMaxWidth()
            )
            ExposedDropdownMenu(expanded = kindOpen, onDismissRequest = { kindOpen = false }) {
                ProviderKinds.forEach { (key, label) ->
                    DropdownMenuItem(text = { Text(label) }, onClick = { kind = key; kindOpen = false })
                }
            }
        }
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(value = apiKey, onValueChange = { apiKey = it }, label = { Text("API key") }, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(value = model, onValueChange = { model = it }, label = { Text("Model") }, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(value = baseUrl, onValueChange = { baseUrl = it }, label = { Text("Base URL (optional)") }, modifier = Modifier.fillMaxWidth())
        Row(verticalAlignment = Alignment.CenterVertically) {
            Checkbox(checked = isDefault, onCheckedChange = { isDefault = it })
            Text("Use as default", color = Ink)
        }
        Button(
            onClick = {
                if (name.isBlank()) {
                    Toast.makeText(context, "Label required", Toast.LENGTH_SHORT).show()
                    return@Button
                }
                busy = true
                scope.launch {
                    runCatching {
                        repository.createAiProvider(
                            AiProviderIn(
                                name = name.trim(),
                                kind = kind,
                                api_key = apiKey.ifBlank { null },
                                model = model.ifBlank { null },
                                base_url = baseUrl.ifBlank { null },
                                is_default = isDefault
                            )
                        )
                    }.onSuccess {
                        name = ""; apiKey = ""; model = ""; baseUrl = ""
                        Toast.makeText(context, "Provider saved", Toast.LENGTH_SHORT).show()
                        reload()
                    }.onFailure {
                        Toast.makeText(context, errMessage(it), Toast.LENGTH_LONG).show()
                    }
                    busy = false
                }
            },
            enabled = !busy,
            colors = ButtonDefaults.buttonColors(containerColor = VaultGold, contentColor = Color(0xFF18130A)),
            modifier = Modifier.fillMaxWidth()
        ) { Text("Save provider") }

        Spacer(Modifier.height(20.dp))
        Text("Saved", color = Ink, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(8.dp))
        providers.forEach { p ->
            Column(
                Modifier
                    .fillMaxWidth()
                    .padding(vertical = 8.dp)
                    .clip(RoundedCornerShape(14.dp))
                    .border(1.dp, LineColor, RoundedCornerShape(14.dp))
                    .background(HubGlass)
                    .padding(12.dp)
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(p.name, color = Ink, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                    if (p.is_default) {
                        Text("Default", color = VaultGold, style = MaterialTheme.typography.labelSmall)
                    }
                }
                Text("${p.kind} · ${p.model ?: "default model"}", color = InkSoft, style = MaterialTheme.typography.bodySmall)
                Text(if (p.has_key) "Key saved" else "No key", color = if (p.has_key) Sage else InkSoft, style = MaterialTheme.typography.bodySmall)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    TextButton(onClick = {
                        scope.launch {
                            runCatching { repository.testAiProvider(p.id) }
                                .onSuccess {
                                    val sample = (it["sample"] as? String) ?: "ok"
                                    Toast.makeText(context, "Test ok: $sample", Toast.LENGTH_LONG).show()
                                    reload()
                                }
                                .onFailure { Toast.makeText(context, errMessage(it), Toast.LENGTH_LONG).show() }
                        }
                    }) { Text("Test") }
                    TextButton(onClick = {
                        scope.launch {
                            runCatching { repository.deleteAiProvider(p.id) }
                                .onSuccess { reload() }
                                .onFailure { Toast.makeText(context, errMessage(it), Toast.LENGTH_SHORT).show() }
                        }
                    }) { Text("Remove", color = StampRed) }
                }
            }
        }
        if (providers.isEmpty()) {
            Text("No providers yet. Add one above.", color = InkSoft, modifier = Modifier.padding(vertical = 12.dp))
        }
        Spacer(Modifier.height(40.dp))
    }
}

@Composable
private fun StatChip(text: String, modifier: Modifier = Modifier) {
    Box(
        modifier
            .clip(RoundedCornerShape(12.dp))
            .background(HubGlass)
            .border(1.dp, LineColor, RoundedCornerShape(12.dp))
            .padding(12.dp)
    ) {
        Text(text, color = Ink, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
    }
}

@Composable
private fun VaultActionCard(
    action: AiVaultAction,
    repository: HealthVaultRepository,
    onApplied: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var busy by remember { mutableStateOf(false) }
    var doneUrl by remember { mutableStateOf<String?>(null) }
    var doneLabel by remember { mutableStateOf<String?>(null) }
    var dismissed by remember { mutableStateOf(false) }
    if (dismissed) return

    val isDiary = action.type == "create_diary_entry"
    val heading = if (isDiary) "Proposed diary entry" else "Proposed shopping list"
    val title = if (isDiary) action.title.orEmpty() else action.name.orEmpty()
    val cta = if (isDiary) "Save to diary" else "Create list"

    Column(
        Modifier
            .widthIn(max = 320.dp)
            .clip(RoundedCornerShape(14.dp))
            .border(1.dp, VaultGold.copy(alpha = 0.35f), RoundedCornerShape(14.dp))
            .background(HubGlass)
            .padding(12.dp)
    ) {
        Text(heading, color = VaultGold, style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.SemiBold)
        Text(title, color = Ink, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 4.dp))
        if (isDiary) {
            val meta = listOfNotNull(action.entry_date, action.category).joinToString(" · ")
            if (meta.isNotBlank()) {
                Text(meta, color = InkSoft, style = MaterialTheme.typography.bodySmall)
            }
            action.charges.orEmpty().take(8).forEach { c ->
                val label = c.label ?: c.name ?: ""
                Text(
                    "• $label${c.amount?.let { " · ₹ $it" } ?: ""}",
                    color = InkSoft,
                    style = MaterialTheme.typography.bodySmall
                )
            }
            if (action.charges.isNullOrEmpty() && !action.body.isNullOrBlank()) {
                Text(action.body.take(160), color = InkSoft, style = MaterialTheme.typography.bodySmall)
            }
        } else {
            action.items.orEmpty().take(8).forEach { item ->
                val meta = listOfNotNull(
                    item.quantity?.takeIf { it != 1.0 }?.toString(),
                    item.unit
                ).joinToString(" ")
                Text(
                    "• ${item.name}${if (meta.isNotBlank()) " $meta" else ""}",
                    color = InkSoft,
                    style = MaterialTheme.typography.bodySmall
                )
            }
            val extra = (action.items?.size ?: 0) - 8
            if (extra > 0) Text("+$extra more", color = InkSoft, style = MaterialTheme.typography.labelSmall)
        }
        Spacer(Modifier.height(8.dp))
        if (doneUrl != null) {
            Text(
                "Saved: ${doneLabel ?: title}",
                color = Sage,
                style = MaterialTheme.typography.bodySmall
            )
        } else {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(
                    onClick = {
                        busy = true
                        scope.launch {
                            try {
                                if (isDiary) {
                                    val res = repository.applyAiDiaryEntry(action)
                                    doneUrl = res.url
                                    doneLabel = res.title
                                } else {
                                    val res = repository.applyAiShopList(action)
                                    doneUrl = res.url
                                    doneLabel = res.name
                                }
                                Toast.makeText(context, "Saved", Toast.LENGTH_SHORT).show()
                                onApplied()
                            } catch (t: Throwable) {
                                Toast.makeText(context, errMessage(t), Toast.LENGTH_LONG).show()
                            }
                            busy = false
                        }
                    },
                    enabled = !busy,
                    colors = ButtonDefaults.buttonColors(containerColor = VaultGold, contentColor = Color(0xFF18130A)),
                    contentPadding = PaddingValues(horizontal = 12.dp, vertical = 6.dp)
                ) { Text(if (busy) "…" else cta) }
                TextButton(onClick = { dismissed = true }, enabled = !busy) {
                    Text("Dismiss", color = InkSoft)
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun AiUsageLogsScreen(
    repository: HealthVaultRepository,
    onOpenModules: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var logs by remember { mutableStateOf<List<AiUsageLogOut>>(emptyList()) }
    var summary by remember { mutableStateOf<AiUsageSummaryOut?>(null) }
    var filter by remember { mutableStateOf<String?>(null) }
    val filters = listOf(
        null to "All",
        "ask_ai" to "Ask AI",
        "finance_sms" to "SMS",
        "expense_analyser" to "Mail",
        "catalog_translate" to "Catalog",
        "connection_test" to "Connection",
        "provider_test" to "Provider"
    )

    fun reload(client: String?) {
        scope.launch {
            runCatching {
                summary = repository.aiUsageSummary()
                logs = repository.listAiUsage(client)
            }.onFailure {
                Toast.makeText(context, errMessage(it), Toast.LENGTH_SHORT).show()
            }
        }
    }

    LaunchedEffect(Unit) { reload(null) }

    Column(
        Modifier
            .fillMaxSize()
            .background(HubBg)
            .padding(16.dp)
    ) {
        TextButton(onClick = onOpenModules) { Text("Modules", color = InkSoft) }
        Text("Usage logs", style = MaterialTheme.typography.headlineMedium, color = Ink, fontWeight = FontWeight.Bold)
        Text("Client, model, request/response tokens, and time for every AI call.", color = InkSoft, style = MaterialTheme.typography.bodySmall)
        Spacer(Modifier.height(12.dp))
        summary?.let { s ->
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                StatChip("${s.calls} calls", Modifier.weight(1f))
                StatChip(fmtTokens(s.prompt_tokens) + " in", Modifier.weight(1f))
                StatChip(fmtTokens(s.completion_tokens) + " out", Modifier.weight(1f))
            }
            Text(
                "Last ${s.days} days · ${s.ok} ok · ${s.failed} failed · total ${fmtTokens(s.total_tokens)}",
                color = InkSoft,
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.padding(top = 8.dp)
            )
        }
        Spacer(Modifier.height(10.dp))
        FlowRow(
            horizontalArrangement = Arrangement.spacedBy(6.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            filters.forEach { (key, label) ->
                FilterChip(
                    selected = filter == key,
                    onClick = {
                        filter = key
                        reload(key)
                    },
                    label = { Text(label) }
                )
            }
        }
        Spacer(Modifier.height(8.dp))
        LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            if (logs.isEmpty()) {
                item {
                    Text("No usage yet. Ask a question or run Test connection.", color = InkSoft, modifier = Modifier.padding(24.dp))
                }
            }
            items(logs, key = { it.id }) { row ->
                Column(
                    Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(12.dp))
                        .border(1.dp, LineColor, RoundedCornerShape(12.dp))
                        .background(HubGlass)
                        .padding(12.dp)
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(row.client_label, color = Ink, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                        Text(
                            if (row.ok) "ok" else "failed",
                            color = if (row.ok) Sage else StampRed,
                            style = MaterialTheme.typography.labelSmall
                        )
                    }
                    Text(fmtWhen(row.created_at), color = InkSoft, style = MaterialTheme.typography.bodySmall)
                    Text(
                        listOfNotNull(row.provider_name, row.provider_kind, row.model).joinToString(" · ").ifBlank { "—" },
                        color = InkSoft,
                        style = MaterialTheme.typography.bodySmall
                    )
                    Text(
                        "req ${fmtTokens(row.prompt_tokens)} · resp ${fmtTokens(row.completion_tokens)} · total ${fmtTokens(row.total_tokens)}" +
                            (row.latency_ms?.let { " · ${it}ms" } ?: ""),
                        color = Ink,
                        style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier.padding(top = 4.dp)
                    )
                    if (!row.ok && !row.error.isNullOrBlank()) {
                        Text(row.error!!, color = StampRed, style = MaterialTheme.typography.bodySmall)
                    }
                    if (!row.request_text.isNullOrBlank()) {
                        Text("Request", color = InkSoft, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(top = 8.dp))
                        Text(row.request_text!!, color = Ink, style = MaterialTheme.typography.bodySmall)
                    }
                    if (!row.response_text.isNullOrBlank()) {
                        Text("Response", color = InkSoft, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(top = 6.dp))
                        Text(row.response_text!!, color = Ink, style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
            item { Spacer(Modifier.height(48.dp)) }
        }
    }
}
