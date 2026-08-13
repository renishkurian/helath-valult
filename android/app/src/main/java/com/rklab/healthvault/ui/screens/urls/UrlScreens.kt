package com.rklab.healthvault.ui.screens.urls

import android.content.Intent
import android.graphics.Color as AndroidColor
import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Apps
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Link
import androidx.compose.material.icons.filled.OpenInNew
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Share
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.outlined.StarBorder
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.rklab.healthvault.data.model.UrlCategoryIn
import com.rklab.healthvault.data.model.UrlCategoryOut
import com.rklab.healthvault.data.model.UrlItemIn
import com.rklab.healthvault.data.model.UrlItemOut
import com.rklab.healthvault.data.model.UrlItemUpdate
import com.rklab.healthvault.data.model.UrlShareCreate
import com.rklab.healthvault.data.model.UrlShareOut
import com.rklab.healthvault.data.model.UrlTagIn
import com.rklab.healthvault.data.model.UrlTagOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.theme.*
import kotlinx.coroutines.launch
import java.net.URI

private fun hexColor(raw: String?, fallback: Color = Navy): Color {
    val value = raw?.trim().orEmpty()
    if (value.isBlank()) return fallback
    val hex = if (value.startsWith("#")) value else "#$value"
    return runCatching { Color(AndroidColor.parseColor(hex)) }.getOrDefault(fallback)
}

private fun hostOf(url: String): String = runCatching {
    val host = URI(url).host ?: url
    if (host.startsWith("www.")) host.drop(4) else host
}.getOrDefault(url)

private fun addedOn(iso: String): String {
    val day = iso.take(10)
    if (day.length < 10) return iso
    val y = day.take(4)
    val m = day.substring(5, 7)
    val d = day.substring(8, 10)
    val months = listOf("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    val month = months.getOrNull(m.toIntOrNull()?.minus(1) ?: -1) ?: m
    return "$d $month $y"
}

private fun shareUrl(context: android.content.Context, title: String, url: String) {
    val send = Intent(Intent.ACTION_SEND).apply {
        type = "text/plain"
        putExtra(Intent.EXTRA_SUBJECT, title)
        putExtra(Intent.EXTRA_TEXT, "$title\n$url")
    }
    context.startActivity(Intent.createChooser(send, "Share link"))
}

@Composable
fun UrlListScreen(
    repository: HealthVaultRepository,
    onOpenItem: (String) -> Unit,
    onAdd: (String?) -> Unit,
    onOpenModules: () -> Unit,
    favoritesOnly: Boolean = false
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var query by remember { mutableStateOf("") }
    var categoryId by remember { mutableStateOf<String?>(null) }
    var tagId by remember { mutableStateOf<String?>(null) }
    var items by remember { mutableStateOf<List<UrlItemOut>>(emptyList()) }
    var categories by remember { mutableStateOf<List<UrlCategoryOut>>(emptyList()) }
    var tags by remember { mutableStateOf<List<UrlTagOut>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }

    fun reload() {
        scope.launch {
            loading = true
            error = null
            runCatching {
                val summary = repository.urlSummary()
                categories = summary.categories
                tags = summary.tags
                items = repository.listUrlItems(
                    q = query.ifBlank { null },
                    categoryId = categoryId,
                    tagId = tagId,
                    favorite = favoritesOnly
                )
            }.onFailure { error = it.message ?: "Could not load links" }
            loading = false
        }
    }
    LaunchedEffect(query, categoryId, tagId, favoritesOnly) { reload() }

    Box(Modifier.fillMaxSize().background(Paper)) {
        Column(Modifier.fillMaxSize()) {
            Row(
                Modifier.fillMaxWidth().padding(20.dp, 16.dp, 8.dp, 0.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text("URL VAULT", style = MaterialTheme.typography.labelMedium, color = InkSoft)
                    Text(
                        if (favoritesOnly) "Favorites" else "Links",
                        style = MaterialTheme.typography.headlineMedium,
                        color = Ink,
                        fontWeight = FontWeight.Bold
                    )
                }
                IconButton(onClick = onOpenModules) {
                    Icon(Icons.Filled.Apps, contentDescription = "Modules", tint = InkSoft)
                }
            }
            OutlinedTextField(
                value = query,
                onValueChange = { query = it },
                placeholder = { Text("Search title or URL") },
                leadingIcon = { Icon(Icons.Filled.Search, contentDescription = null) },
                singleLine = true,
                shape = RoundedCornerShape(16.dp),
                modifier = Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 8.dp)
            )
            LazyRow(
                contentPadding = PaddingValues(horizontal = 20.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                item {
                    FilterChip(selected = categoryId == null, onClick = { categoryId = null }, label = { Text("All") })
                }
                items(categories, key = { it.id }) { c ->
                    FilterChip(
                        selected = categoryId == c.id,
                        onClick = { categoryId = if (categoryId == c.id) null else c.id },
                        label = { Text("${c.name} ${c.count}") },
                        leadingIcon = {
                            Box(Modifier.size(8.dp).clip(CircleShape).background(hexColor(c.color)))
                        }
                    )
                }
            }
            if (tags.isNotEmpty()) {
                LazyRow(
                    contentPadding = PaddingValues(horizontal = 20.dp, vertical = 8.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    items(tags, key = { it.id }) { t ->
                        FilterChip(
                            selected = tagId == t.id,
                            onClick = { tagId = if (tagId == t.id) null else t.id },
                            label = { Text(t.name) }
                        )
                    }
                }
            }
            when {
                loading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = Navy)
                }
                error != null -> Text(error!!, color = StampRed, modifier = Modifier.padding(20.dp))
                items.isEmpty() -> Text(
                    "No links yet. Save a URL and we’ll fetch a preview when the site allows it.",
                    color = InkSoft,
                    modifier = Modifier.padding(20.dp)
                )
                else -> LazyColumn(
                    contentPadding = PaddingValues(20.dp, 12.dp, 20.dp, 88.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    items(items, key = { it.id }) { item ->
                        UrlCard(
                            item = item,
                            onOpen = { onOpenItem(item.id) },
                            onShare = { shareUrl(context, item.title, item.url) }
                        )
                    }
                }
            }
        }
        FloatingActionButton(
            onClick = { onAdd(categoryId) },
            modifier = Modifier.align(Alignment.BottomEnd).padding(20.dp),
            containerColor = Navy
        ) {
            Icon(Icons.Filled.Add, contentDescription = "Add link", tint = Color.White)
        }
    }
}

@Composable
private fun UrlCard(item: UrlItemOut, onOpen: () -> Unit, onShare: () -> Unit) {
    Surface(
        shape = RoundedCornerShape(16.dp),
        color = White,
        modifier = Modifier.fillMaxWidth().clickable(onClick = onOpen)
    ) {
        Column {
            if (!item.og_image.isNullOrBlank()) {
                AsyncImage(
                    model = item.og_image,
                    contentDescription = null,
                    contentScale = ContentScale.Crop,
                    modifier = Modifier.fillMaxWidth().height(120.dp)
                )
            }
            Row(Modifier.padding(14.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                if (item.og_image.isNullOrBlank()) {
                    Box(
                        Modifier.size(44.dp).clip(RoundedCornerShape(12.dp))
                            .background(hexColor(item.category_color).copy(alpha = 0.2f)),
                        contentAlignment = Alignment.Center
                    ) {
                        if (!item.favicon_url.isNullOrBlank()) {
                            AsyncImage(
                                model = item.favicon_url,
                                contentDescription = null,
                                modifier = Modifier.size(22.dp)
                            )
                        } else {
                            Icon(Icons.Filled.Link, contentDescription = null, tint = hexColor(item.category_color))
                        }
                    }
                }
                Column(Modifier.weight(1f)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        if (item.favorite) {
                            Icon(Icons.Filled.Star, contentDescription = "Favorite", tint = Mustard, modifier = Modifier.size(14.dp))
                            Spacer(Modifier.width(4.dp))
                        }
                        Text(
                            item.og_site_name ?: hostOf(item.url),
                            color = InkSoft,
                            style = MaterialTheme.typography.labelSmall,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                            modifier = Modifier.weight(1f)
                        )
                        Text(addedOn(item.created_at), color = InkSoft, style = MaterialTheme.typography.labelSmall)
                    }
                    Spacer(Modifier.height(4.dp))
                    Text(item.title, color = Ink, fontWeight = FontWeight.SemiBold, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    if (!item.og_description.isNullOrBlank()) {
                        Text(
                            item.og_description!!,
                            color = InkSoft,
                            style = MaterialTheme.typography.bodySmall,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis,
                            modifier = Modifier.padding(top = 4.dp)
                        )
                    }
                    Row(
                        Modifier.padding(top = 8.dp).horizontalScroll(rememberScrollState()),
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        item.category_name?.let { name ->
                            AssistChip(
                                onClick = {},
                                enabled = false,
                                label = { Text(name) },
                                colors = AssistChipDefaults.assistChipColors(
                                    disabledContainerColor = hexColor(item.category_color).copy(alpha = 0.16f),
                                    disabledLabelColor = hexColor(item.category_color)
                                )
                            )
                        }
                        item.tags.forEach { tag ->
                            AssistChip(onClick = {}, enabled = false, label = { Text(tag.name) })
                        }
                    }
                }
                IconButton(onClick = onShare, modifier = Modifier.semantics { contentDescription = "Share ${item.title}" }) {
                    Icon(Icons.Filled.Share, contentDescription = null, tint = InkSoft)
                }
            }
        }
    }
}

@Composable
fun UrlAddScreen(
    repository: HealthVaultRepository,
    defaultCategoryId: String?,
    onDone: () -> Unit,
    onBack: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var url by remember { mutableStateOf("") }
    var title by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }
    var favorite by remember { mutableStateOf(false) }
    var categoryId by remember { mutableStateOf(defaultCategoryId) }
    var selectedTags by remember { mutableStateOf(setOf<String>()) }
    var categories by remember { mutableStateOf<List<UrlCategoryOut>>(emptyList()) }
    var tags by remember { mutableStateOf<List<UrlTagOut>>(emptyList()) }
    var saving by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        runCatching {
            val summary = repository.urlSummary()
            categories = summary.categories
            tags = summary.tags
        }
    }

    Column(Modifier.fillMaxSize().background(Paper).verticalScroll(rememberScrollState()).padding(20.dp)) {
        TextButton(onClick = onBack) { Text("← URL Vault", color = Navy) }
        Text("Add link", style = MaterialTheme.typography.headlineMedium, color = Ink, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(16.dp))
        OutlinedTextField(
            url, { url = it }, label = { Text("URL") },
            modifier = Modifier.fillMaxWidth(), singleLine = true
        )
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(
            title, { title = it }, label = { Text("Title (optional)") },
            modifier = Modifier.fillMaxWidth(), singleLine = true
        )
        Spacer(Modifier.height(12.dp))
        Text("Category", color = InkSoft, style = MaterialTheme.typography.labelMedium)
        Spacer(Modifier.height(6.dp))
        LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            item { FilterChip(selected = categoryId == null, onClick = { categoryId = null }, label = { Text("None") }) }
            items(categories, key = { it.id }) { c ->
                FilterChip(
                    selected = categoryId == c.id,
                    onClick = { categoryId = c.id },
                    label = { Text(c.name) }
                )
            }
        }
        if (tags.isNotEmpty()) {
            Spacer(Modifier.height(12.dp))
            Text("Tags", color = InkSoft, style = MaterialTheme.typography.labelMedium)
            Spacer(Modifier.height(6.dp))
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                items(tags, key = { it.id }) { t ->
                    FilterChip(
                        selected = t.id in selectedTags,
                        onClick = {
                            selectedTags = if (t.id in selectedTags) selectedTags - t.id else selectedTags + t.id
                        },
                        label = { Text(t.name) }
                    )
                }
            }
        }
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(notes, { notes = it }, label = { Text("Notes") }, modifier = Modifier.fillMaxWidth(), minLines = 2)
        Spacer(Modifier.height(8.dp))
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.clickable { favorite = !favorite }.padding(vertical = 4.dp)) {
            Checkbox(favorite, { favorite = it })
            Text("Favorite", color = Ink)
        }
        Spacer(Modifier.height(16.dp))
        Button(
            onClick = {
                if (url.isBlank()) {
                    Toast.makeText(context, "URL is required", Toast.LENGTH_SHORT).show()
                    return@Button
                }
                saving = true
                scope.launch {
                    runCatching {
                        repository.createUrlItem(
                            UrlItemIn(
                                url = url.trim(),
                                title = title.trim().ifBlank { null },
                                category_id = categoryId,
                                tag_ids = selectedTags.toList(),
                                notes = notes.trim().ifBlank { null },
                                favorite = favorite,
                                fetch_preview = true
                            )
                        )
                    }.onSuccess { onDone() }
                        .onFailure { Toast.makeText(context, it.message ?: "Could not save", Toast.LENGTH_LONG).show() }
                    saving = false
                }
            },
            enabled = !saving,
            modifier = Modifier.fillMaxWidth(),
            colors = ButtonDefaults.buttonColors(containerColor = Navy)
        ) {
            Text(if (saving) "Saving…" else "Save link")
        }
        Text(
            "We’ll try to pull a preview image and description from the page.",
            color = InkSoft,
            style = MaterialTheme.typography.bodySmall,
            modifier = Modifier.padding(top = 10.dp)
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun UrlItemScreen(
    repository: HealthVaultRepository,
    itemId: String,
    onBack: () -> Unit
) {
    val context = LocalContext.current
    val uriHandler = LocalUriHandler.current
    val clipboard = LocalClipboardManager.current
    val scope = rememberCoroutineScope()
    var item by remember { mutableStateOf<UrlItemOut?>(null) }
    var categories by remember { mutableStateOf<List<UrlCategoryOut>>(emptyList()) }
    var tags by remember { mutableStateOf<List<UrlTagOut>>(emptyList()) }
    var shares by remember { mutableStateOf<List<UrlShareOut>>(emptyList()) }
    var title by remember { mutableStateOf("") }
    var url by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }
    var categoryId by remember { mutableStateOf<String?>(null) }
    var selectedTags by remember { mutableStateOf(setOf<String>()) }
    var error by remember { mutableStateOf<String?>(null) }
    var saving by remember { mutableStateOf(false) }
    var shareHours by remember { mutableStateOf(168) }
    var shareDialog by remember { mutableStateOf<UrlShareOut?>(null) }

    fun reload() {
        scope.launch {
            runCatching {
                val loaded = repository.getUrlItem(itemId)
                item = loaded
                title = loaded.title
                url = loaded.url
                notes = loaded.notes.orEmpty()
                categoryId = loaded.category_id
                selectedTags = loaded.tags.map { it.id }.toSet()
                val summary = repository.urlSummary()
                categories = summary.categories
                tags = summary.tags
                shares = repository.listUrlShares(itemId)
            }.onFailure { error = it.message }
        }
    }
    LaunchedEffect(itemId) { reload() }

    Column(Modifier.fillMaxSize().background(Paper).verticalScroll(rememberScrollState()).padding(20.dp)) {
        TextButton(onClick = onBack) { Text("← URL Vault", color = Navy) }
        val current = item
        if (error != null) Text(error!!, color = StampRed)
        else if (current == null) Box(Modifier.fillMaxWidth().height(120.dp), contentAlignment = Alignment.Center) {
            CircularProgressIndicator(color = Navy)
        } else {
            if (!current.og_image.isNullOrBlank()) {
                AsyncImage(
                    model = current.og_image,
                    contentDescription = null,
                    contentScale = ContentScale.Crop,
                    modifier = Modifier.fillMaxWidth().height(160.dp).clip(RoundedCornerShape(16.dp))
                )
                Spacer(Modifier.height(12.dp))
            }
            Text(current.og_site_name ?: hostOf(current.url), style = MaterialTheme.typography.labelMedium, color = InkSoft)
            Text(current.title, style = MaterialTheme.typography.headlineMedium, color = Ink, fontWeight = FontWeight.Bold)
            Text("Added ${addedOn(current.created_at)}", color = InkSoft, style = MaterialTheme.typography.bodySmall)
            Spacer(Modifier.height(12.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = { runCatching { uriHandler.openUri(current.url) } }, colors = ButtonDefaults.buttonColors(containerColor = Navy)) {
                    Icon(Icons.Filled.OpenInNew, contentDescription = null, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("Open")
                }
                OutlinedButton(onClick = { shareUrl(context, current.title, current.url) }) {
                    Icon(Icons.Filled.Share, contentDescription = null, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("Share")
                }
                IconButton(onClick = {
                    scope.launch {
                        runCatching { repository.toggleUrlFavorite(itemId) }
                            .onSuccess { reload() }
                            .onFailure { Toast.makeText(context, it.message, Toast.LENGTH_SHORT).show() }
                    }
                }) {
                    Icon(
                        if (current.favorite) Icons.Filled.Star else Icons.Outlined.StarBorder,
                        contentDescription = if (current.favorite) "Unfavorite" else "Favorite",
                        tint = if (current.favorite) Mustard else InkSoft
                    )
                }
            }
            Spacer(Modifier.height(18.dp))
            OutlinedTextField(url, { url = it }, label = { Text("URL") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
            Spacer(Modifier.height(8.dp))
            OutlinedTextField(title, { title = it }, label = { Text("Title") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
            Spacer(Modifier.height(8.dp))
            OutlinedTextField(notes, { notes = it }, label = { Text("Notes") }, modifier = Modifier.fillMaxWidth(), minLines = 2)
            Spacer(Modifier.height(12.dp))
            Text("Category", color = InkSoft, style = MaterialTheme.typography.labelMedium)
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 6.dp)) {
                item { FilterChip(selected = categoryId == null, onClick = { categoryId = null }, label = { Text("None") }) }
                items(categories, key = { it.id }) { c ->
                    FilterChip(selected = categoryId == c.id, onClick = { categoryId = c.id }, label = { Text(c.name) })
                }
            }
            if (tags.isNotEmpty()) {
                Spacer(Modifier.height(12.dp))
                Text("Tags", color = InkSoft, style = MaterialTheme.typography.labelMedium)
                LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 6.dp)) {
                    items(tags, key = { it.id }) { t ->
                        FilterChip(
                            selected = t.id in selectedTags,
                            onClick = {
                                selectedTags = if (t.id in selectedTags) selectedTags - t.id else selectedTags + t.id
                            },
                            label = { Text(t.name) }
                        )
                    }
                }
            }
            Spacer(Modifier.height(16.dp))
            Button(
                onClick = {
                    saving = true
                    scope.launch {
                        runCatching {
                            repository.updateUrlItem(
                                itemId,
                                UrlItemUpdate(
                                    url = url.trim(),
                                    title = title.trim(),
                                    category_id = categoryId,
                                    tag_ids = selectedTags.toList(),
                                    notes = notes.trim().ifBlank { null },
                                    favorite = current.favorite,
                                    fetch_preview = false
                                )
                            )
                        }.onSuccess {
                            Toast.makeText(context, "Saved", Toast.LENGTH_SHORT).show()
                            reload()
                        }.onFailure { Toast.makeText(context, it.message, Toast.LENGTH_LONG).show() }
                        saving = false
                    }
                },
                enabled = !saving,
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.buttonColors(containerColor = Navy)
            ) { Text(if (saving) "Saving…" else "Save changes") }
            TextButton(onClick = {
                scope.launch {
                    runCatching { repository.refreshUrlPreview(itemId) }
                        .onSuccess { reload() }
                        .onFailure { Toast.makeText(context, it.message, Toast.LENGTH_SHORT).show() }
                }
            }) { Text("Refresh preview") }

            Spacer(Modifier.height(12.dp))
            Text("Share link", fontWeight = FontWeight.SemiBold, color = Ink)
            Text("Create an expiring public preview page — no login needed.", color = InkSoft, style = MaterialTheme.typography.bodySmall)
            Row(Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf(24 to "1 day", 168 to "1 week", 720 to "30d").forEach { (hrs, label) ->
                    FilterChip(selected = shareHours == hrs, onClick = { shareHours = hrs }, label = { Text(label) })
                }
            }
            Button(
                onClick = {
                    scope.launch {
                        runCatching { repository.createUrlShare(itemId, UrlShareCreate(expires_in_hours = shareHours)) }
                            .onSuccess { created ->
                                shareDialog = created
                                shares = repository.listUrlShares(itemId)
                            }
                            .onFailure { Toast.makeText(context, it.message, Toast.LENGTH_SHORT).show() }
                    }
                },
                modifier = Modifier.padding(top = 8.dp),
                colors = ButtonDefaults.buttonColors(containerColor = Navy)
            ) { Text("Create share link") }
            shares.filter { !it.revoked }.forEach { s ->
                Surface(shape = RoundedCornerShape(12.dp), color = PaperDeep, modifier = Modifier.fillMaxWidth().padding(top = 8.dp)) {
                    Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text("/u/${s.token.take(12)}…", color = Ink, style = MaterialTheme.typography.bodySmall)
                            Text("${s.view_count} views · expires ${addedOn(s.expires_at)}", color = InkSoft, style = MaterialTheme.typography.labelSmall)
                        }
                        TextButton(onClick = {
                            scope.launch {
                                runCatching { repository.revokeUrlShare(s.id) }
                                    .onSuccess { reload() }
                            }
                        }) { Text("Revoke", color = StampRed) }
                    }
                }
            }

            Spacer(Modifier.height(20.dp))
            OutlinedButton(
                onClick = {
                    scope.launch {
                        runCatching { repository.deleteUrlItem(itemId) }
                            .onSuccess { onBack() }
                            .onFailure { Toast.makeText(context, it.message, Toast.LENGTH_SHORT).show() }
                    }
                },
                colors = ButtonDefaults.outlinedButtonColors(contentColor = StampRed)
            ) {
                Icon(Icons.Filled.Delete, contentDescription = null)
                Spacer(Modifier.width(6.dp))
                Text("Delete link")
            }
        }
    }

    shareDialog?.let { created ->
        val full = "${repository.getServerUrl()?.trimEnd('/')}/u/${created.token}"
        AlertDialog(
            onDismissRequest = { shareDialog = null },
            title = { Text("Share link ready") },
            text = {
                Column {
                    Text("Anyone with this link can open the preview until it expires.")
                    Spacer(Modifier.height(10.dp))
                    Text(full, color = Navy, style = MaterialTheme.typography.bodySmall)
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    clipboard.setText(AnnotatedString(full))
                    shareDialog = null
                    Toast.makeText(context, "Copied", Toast.LENGTH_SHORT).show()
                }) { Text("Copy") }
            },
            dismissButton = { TextButton(onClick = { shareDialog = null }) { Text("Close") } }
        )
    }
}

@Composable
fun UrlManageScreen(
    repository: HealthVaultRepository,
    onOpenModules: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var categories by remember { mutableStateOf<List<UrlCategoryOut>>(emptyList()) }
    var tags by remember { mutableStateOf<List<UrlTagOut>>(emptyList()) }
    var newCat by remember { mutableStateOf("") }
    var newTag by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }

    fun reload() {
        scope.launch {
            runCatching {
                val summary = repository.urlSummary()
                categories = summary.categories
                tags = summary.tags
            }.onFailure { error = it.message }
        }
    }
    LaunchedEffect(Unit) { reload() }

    Column(Modifier.fillMaxSize().background(Paper)) {
        Row(
            Modifier.fillMaxWidth().padding(20.dp, 16.dp, 8.dp, 0.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column {
                Text("URL VAULT", style = MaterialTheme.typography.labelMedium, color = InkSoft)
                Text("Manage", style = MaterialTheme.typography.headlineMedium, color = Ink, fontWeight = FontWeight.Bold)
            }
            IconButton(onClick = onOpenModules) {
                Icon(Icons.Filled.Apps, contentDescription = "Modules", tint = InkSoft)
            }
        }
        if (error != null) Text(error!!, color = StampRed, modifier = Modifier.padding(20.dp))
        LazyColumn(
            contentPadding = PaddingValues(20.dp, 8.dp, 20.dp, 88.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            item {
                Text("Categories", fontWeight = FontWeight.SemiBold, color = Ink)
                Text("Adult, Instagram, News, Songs — rename or add your own.", color = InkSoft, style = MaterialTheme.typography.bodySmall)
            }
            items(categories, key = { it.id }) { cat ->
                ManageRow(
                    name = cat.name,
                    count = cat.count,
                    color = hexColor(cat.color),
                    onSave = { name ->
                        scope.launch {
                            runCatching { repository.updateUrlCategory(cat.id, UrlCategoryIn(name = name, color = cat.color)) }
                                .onSuccess { reload() }
                                .onFailure { Toast.makeText(context, it.message, Toast.LENGTH_SHORT).show() }
                        }
                    },
                    onDelete = {
                        scope.launch {
                            runCatching { repository.deleteUrlCategory(cat.id) }
                                .onSuccess { reload() }
                                .onFailure { Toast.makeText(context, it.message, Toast.LENGTH_SHORT).show() }
                        }
                    }
                )
            }
            item {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(
                        newCat, { newCat = it }, label = { Text("New category") },
                        modifier = Modifier.weight(1f), singleLine = true
                    )
                    Button(
                        onClick = {
                            val name = newCat.trim()
                            if (name.isBlank()) return@Button
                            scope.launch {
                                runCatching { repository.createUrlCategory(UrlCategoryIn(name = name)) }
                                    .onSuccess { newCat = ""; reload() }
                                    .onFailure { Toast.makeText(context, it.message, Toast.LENGTH_SHORT).show() }
                            }
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = Navy)
                    ) { Text("Add") }
                }
            }
            item {
                Spacer(Modifier.height(8.dp))
                Text("Tags", fontWeight = FontWeight.SemiBold, color = Ink)
            }
            items(tags, key = { it.id }) { tag ->
                ManageRow(
                    name = tag.name,
                    count = tag.count,
                    color = hexColor(tag.color, PurpleAccent),
                    onSave = { name ->
                        scope.launch {
                            runCatching { repository.updateUrlTag(tag.id, UrlTagIn(name = name, color = tag.color)) }
                                .onSuccess { reload() }
                                .onFailure { Toast.makeText(context, it.message, Toast.LENGTH_SHORT).show() }
                        }
                    },
                    onDelete = {
                        scope.launch {
                            runCatching { repository.deleteUrlTag(tag.id) }
                                .onSuccess { reload() }
                                .onFailure { Toast.makeText(context, it.message, Toast.LENGTH_SHORT).show() }
                        }
                    }
                )
            }
            item {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(
                        newTag, { newTag = it }, label = { Text("New tag") },
                        modifier = Modifier.weight(1f), singleLine = true
                    )
                    Button(
                        onClick = {
                            val name = newTag.trim()
                            if (name.isBlank()) return@Button
                            scope.launch {
                                runCatching { repository.createUrlTag(UrlTagIn(name = name)) }
                                    .onSuccess { newTag = ""; reload() }
                                    .onFailure { Toast.makeText(context, it.message, Toast.LENGTH_SHORT).show() }
                            }
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = Navy)
                    ) { Text("Add") }
                }
            }
        }
    }
}

@Composable
private fun ManageRow(
    name: String,
    count: Int,
    color: Color,
    onSave: (String) -> Unit,
    onDelete: () -> Unit
) {
    var value by remember(name) { mutableStateOf(name) }
    Surface(shape = RoundedCornerShape(14.dp), color = White, modifier = Modifier.fillMaxWidth()) {
        Row(
            Modifier.padding(10.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Box(Modifier.size(12.dp).clip(CircleShape).background(color).border(1.dp, HubStroke, CircleShape))
            OutlinedTextField(
                value, { value = it }, modifier = Modifier.weight(1f), singleLine = true
            )
            Text("$count", color = InkSoft, style = MaterialTheme.typography.labelSmall)
            TextButton(onClick = { if (value.isNotBlank()) onSave(value.trim()) }, enabled = value.isNotBlank() && value != name) {
                Text("Save")
            }
            IconButton(onClick = onDelete) {
                Icon(Icons.Filled.Delete, contentDescription = "Delete $name", tint = StampRed)
            }
        }
    }
}
