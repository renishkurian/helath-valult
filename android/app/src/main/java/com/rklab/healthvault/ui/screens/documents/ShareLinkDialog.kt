package com.rklab.healthvault.ui.screens.documents

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.unit.dp
import com.rklab.healthvault.data.model.DocumentOut
import com.rklab.healthvault.data.model.ShareLinkOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.theme.Navy
import com.rklab.healthvault.ui.theme.StampRed
import kotlinx.coroutines.launch

/**
 * Creates a read-only, expiring link for a document (e.g. to show a hospital
 * front desk your insurance card without handing over the app/account).
 * The link points at the Pi's public URL, so it only works while the Pi is
 * reachable from wherever it's opened — same as the rest of the app.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ShareLinkDialog(
    repository: HealthVaultRepository,
    doc: DocumentOut,
    onDismiss: () -> Unit
) {
    val scope = rememberCoroutineScope()
    val clipboard = LocalClipboardManager.current
    val context = LocalContext.current
    var link by remember { mutableStateOf<ShareLinkOut?>(null) }
    var expiresHours by remember { mutableStateOf(48) }
    var pin by remember { mutableStateOf("") }
    var creating by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    fun fullUrl(token: String): String {
        val base = repository.getServerUrl()?.trimEnd('/') ?: ""
        return "$base/s/$token"
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Share \"${doc.title}\"") },
        text = {
            Column {
                if (link == null) {
                    Text("Creates a read-only link — no login needed to view it.")
                    Spacer(Modifier.height(12.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        listOf(4 to "4h", 24 to "1 day", 168 to "1 week").forEach { (hrs, label) ->
                            FilterChip(
                                selected = expiresHours == hrs,
                                onClick = { expiresHours = hrs },
                                label = { Text(label) }
                            )
                        }
                    }
                    Spacer(Modifier.height(10.dp))
                    OutlinedTextField(
                        value = pin,
                        onValueChange = { if (it.length <= 8) pin = it.filter(Char::isDigit) },
                        label = { Text("Optional PIN") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                    if (error != null) {
                        Spacer(Modifier.height(10.dp))
                        Text(error!!, color = StampRed, style = MaterialTheme.typography.bodySmall)
                    }
                } else {
                    Text("Link created — expires in $expiresHours hour(s). Opens and downloads are logged (IP, browser, time) under Settings → Shared links.")
                    Spacer(Modifier.height(10.dp))
                    OutlinedTextField(
                        value = fullUrl(link!!.token),
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Link") },
                        modifier = Modifier.fillMaxWidth()
                    )
                    Spacer(Modifier.height(6.dp))
                    Text(
                        "Note: this only works from a device that can reach your Pi (e.g. same Wi-Fi, or your VPN).",
                        style = MaterialTheme.typography.bodySmall
                    )
                }
            }
        },
        confirmButton = {
            if (link == null) {
                TextButton(
                    onClick = {
                        creating = true
                        error = null
                        scope.launch {
                            try {
                                link = repository.createShareLink(doc.id, expiresHours, pin = pin.ifBlank { null })
                            } catch (e: Exception) {
                                error = e.message ?: "Couldn't create link."
                            } finally {
                                creating = false
                            }
                        }
                    },
                    enabled = !creating
                ) { Text(if (creating) "Creating…" else "Create link", color = Navy) }
            } else {
                TextButton(onClick = {
                    val url = fullUrl(link!!.token)
                    clipboard.setText(AnnotatedString(url))
                    val ctx = context
                    ctx.startActivity(android.content.Intent.createChooser(android.content.Intent(android.content.Intent.ACTION_SEND).apply {
                        type = "text/plain"
                        putExtra(android.content.Intent.EXTRA_TEXT, "Health Vault document: $url")
                    }, "Share via WhatsApp"))
                    onDismiss()
                }) { Text("Copy & WhatsApp", color = Navy) }
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Cancel") }
        }
    )
}
