package com.rklab.healthvault.ui.screens.login

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
import com.rklab.healthvault.data.model.LoginChallengeOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.theme.Sage
import com.rklab.healthvault.ui.theme.StampRed
import com.rklab.healthvault.util.LoginChallengeNotifier
import kotlinx.coroutines.launch

@Composable
fun LoginChallengeDialog(
    repository: HealthVaultRepository,
    challenge: LoginChallengeOut,
    onDone: () -> Unit
) {
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val where = challenge.ip?.takeIf { it.isNotBlank() } ?: "unknown IP"
    val agent = challenge.user_agent?.take(80).orEmpty()

    AlertDialog(
        onDismissRequest = { },
        title = { Text("Web login request") },
        text = {
            Column {
                Text("Allow this browser to open your vault?")
                Spacer(Modifier.height(8.dp))
                Text("From $where", style = MaterialTheme.typography.bodySmall)
                if (agent.isNotBlank()) {
                    Text(agent, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
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
                        runCatching { repository.approveLoginChallenge(challenge.id) }
                            .onSuccess {
                                LoginChallengeNotifier.cancel(context, challenge.id)
                                onDone()
                            }
                            .onFailure {
                                error = "Could not allow this sign-in. Try again."
                                busy = false
                            }
                    }
                }
            ) { Text("Allow", color = Sage) }
        },
        dismissButton = {
            TextButton(
                enabled = !busy,
                onClick = {
                    busy = true
                    scope.launch {
                        runCatching { repository.denyLoginChallenge(challenge.id) }
                            .onSuccess {
                                LoginChallengeNotifier.cancel(context, challenge.id)
                                onDone()
                            }
                            .onFailure {
                                error = "Could not deny this sign-in. Try again."
                                busy = false
                            }
                    }
                }
            ) { Text("Deny", color = StampRed) }
        }
    )
}
