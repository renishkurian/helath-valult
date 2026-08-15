package com.rklab.healthvault.ui.screens.passwords

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.rklab.healthvault.data.model.VaultSendRequestOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.theme.StampRed
import com.rklab.healthvault.ui.theme.VaultGold
import com.rklab.healthvault.util.VaultSendRequestNotifier
import kotlinx.coroutines.launch

@Composable
fun VaultSendRequestDialog(
    repository: HealthVaultRepository,
    request: VaultSendRequestOut,
    onOpenSend: () -> Unit,
    onDone: () -> Unit
) {
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val who = listOfNotNull(request.name, request.email, request.ip)
        .firstOrNull { it.isNotBlank() } ?: "Someone"

    AlertDialog(
        onDismissRequest = { },
        title = { Text("Send access request") },
        text = {
            Column {
                Text("$who asked for access to “${request.send_name}”.")
                Spacer(Modifier.height(8.dp))
                Text(
                    listOfNotNull(request.ip, request.created_at.take(16)).joinToString(" · "),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                if (request.has_photo) {
                    Text("Includes a photo.", style = MaterialTheme.typography.bodySmall)
                }
                if (error != null) {
                    Spacer(Modifier.height(8.dp))
                    Text(error!!, color = StampRed, style = MaterialTheme.typography.bodySmall)
                }
            }
        },
        confirmButton = {
            TextButton(
                enabled = !busy,
                onClick = {
                    busy = true
                    scope.launch {
                        runCatching { repository.grantVaultSendRequest(request.id) }
                            .onSuccess {
                                VaultSendRequestNotifier.cancel(context, request.id)
                                onOpenSend()
                                onDone()
                            }
                            .onFailure {
                                error = "Could not grant access. Try again."
                                busy = false
                            }
                    }
                }
            ) { Text("Grant access", color = VaultGold) }
        },
        dismissButton = {
            TextButton(
                enabled = !busy,
                onClick = {
                    busy = true
                    scope.launch {
                        runCatching { repository.dismissVaultSendRequest(request.id) }
                            .onSuccess {
                                VaultSendRequestNotifier.cancel(context, request.id)
                                onDone()
                            }
                            .onFailure {
                                error = "Could not dismiss. Try again."
                                busy = false
                            }
                    }
                }
            ) { Text("Dismiss", color = StampRed) }
        }
    )
}
