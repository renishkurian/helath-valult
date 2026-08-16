package com.rklab.healthvault.push

import android.util.Log
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import com.rklab.healthvault.HealthVaultApp
import com.rklab.healthvault.data.model.LoginChallengeOut
import com.rklab.healthvault.data.model.VaultSendRequestOut
import com.rklab.healthvault.util.LoginChallengeNotifier
import com.rklab.healthvault.util.VaultSendRequestNotifier
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

/**
 * Handles FCM data messages. The server sends data-only payloads so this runs
 * even when the app is backgrounded (notification+data would skip it).
 */
class VaultFirebaseMessagingService : FirebaseMessagingService() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onNewToken(token: String) {
        DevicePush.sync(application)
    }

    override fun onMessageReceived(message: RemoteMessage) {
        val data = message.data
        val type = data["type"].orEmpty()
        val app = application as? HealthVaultApp ?: return
        when (type) {
            "vault_send_request" -> {
                val id = data["id"].orEmpty()
                if (id.isBlank()) return
                scope.launch {
                    val req = runCatching {
                        app.repository.listVaultSendRequests("pending").firstOrNull { it.id == id }
                    }.getOrNull() ?: VaultSendRequestOut(
                        id = id,
                        send_id = data["send_id"].orEmpty(),
                        send_name = data["send_name"]
                            ?.takeIf { it.isNotBlank() }
                            ?: data["body"]
                                ?.substringAfter("asked for access to “")
                                ?.substringBefore("”")
                                ?.takeIf { it.isNotBlank() }
                            ?: "shared link",
                        item_id = data["item_id"]?.takeIf { it.isNotBlank() },
                        name = data["name"]?.takeIf { it.isNotBlank() },
                        email = data["email"]?.takeIf { it.isNotBlank() },
                        ip = data["ip"]?.takeIf { it.isNotBlank() },
                        has_photo = data["has_photo"] == "1" || data["has_photo"] == "true",
                        status = "pending",
                    )
                    VaultSendRequestNotifier.show(app, req)
                }
            }
            "login_challenge" -> {
                val id = data["id"].orEmpty()
                if (id.isBlank()) return
                scope.launch {
                    val challenge = runCatching {
                        app.repository.pendingLoginChallenges().firstOrNull { it.id == id }
                    }.getOrNull() ?: LoginChallengeOut(
                        id = id,
                        ip = data["ip"]?.takeIf { it.isNotBlank() },
                        status = "pending",
                    )
                    LoginChallengeNotifier.show(app, challenge)
                }
            }
            "reminder_schedule" -> {
                val id = data["id"].orEmpty()
                if (id.isBlank()) return
                val title = data["title"].orEmpty().ifBlank { "Vault reminder" }
                val body = data["body"].orEmpty()
                val remindAt = data["remind_at"].orEmpty()
                if (remindAt.isBlank()) return
                val repeat = runCatching {
                    com.rklab.healthvault.data.model.RepeatRule.valueOf(
                        data["repeat_rule"].orEmpty().uppercase().ifBlank { "NONE" }
                    )
                }.getOrDefault(com.rklab.healthvault.data.model.RepeatRule.NONE)
                // Schedule local alarm — do not show a tray notification until the due time.
                com.rklab.healthvault.util.ReminderScheduler.schedule(
                    app, id, title, body, remindAt, repeat
                )
            }
            "reminder_cancel" -> {
                val id = data["id"].orEmpty()
                if (id.isNotBlank()) {
                    com.rklab.healthvault.util.ReminderScheduler.cancel(app, id)
                }
            }
            "reminder_due" -> {
                val title = data["title"].orEmpty().ifBlank { "Vault reminder" }
                val body = data["body"].orEmpty()
                GenericPushNotifier.show(app, title, body)
                val id = data["id"].orEmpty()
                val remindAt = data["remind_at"].orEmpty()
                val repeat = runCatching {
                    com.rklab.healthvault.data.model.RepeatRule.valueOf(
                        data["repeat_rule"].orEmpty().uppercase().ifBlank { "NONE" }
                    )
                }.getOrDefault(com.rklab.healthvault.data.model.RepeatRule.NONE)
                if (id.isNotBlank() && remindAt.isNotBlank() && repeat != com.rklab.healthvault.data.model.RepeatRule.NONE) {
                    com.rklab.healthvault.util.ReminderScheduler.schedule(
                        app, id, title, body, remindAt, repeat
                    )
                } else if (id.isNotBlank() && repeat == com.rklab.healthvault.data.model.RepeatRule.NONE) {
                    com.rklab.healthvault.util.ReminderScheduler.cancel(app, id)
                }
            }
            else -> {
                // Generic / reminder-style data pushes: show title+body if present.
                val title = data["title"].orEmpty().ifBlank {
                    message.notification?.title.orEmpty()
                }
                val body = data["body"].orEmpty().ifBlank {
                    message.notification?.body.orEmpty()
                }
                if (title.isNotBlank() || body.isNotBlank()) {
                    GenericPushNotifier.show(app, title.ifBlank { "Vault Hub" }, body)
                } else if (type.isNotBlank()) {
                    Log.d("VaultFCM", "Unhandled push type=$type")
                }
            }
        }
    }
}
