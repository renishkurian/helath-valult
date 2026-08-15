package com.rklab.healthvault.push

import android.util.Log
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import com.rklab.healthvault.HealthVaultApp
import com.rklab.healthvault.data.model.VaultSendRequestOut
import com.rklab.healthvault.util.LoginChallengeNotifier
import com.rklab.healthvault.util.VaultSendRequestNotifier
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class VaultFirebaseMessagingService : FirebaseMessagingService() {
    override fun onNewToken(token: String) {
        DevicePush.sync(application)
    }

    override fun onMessageReceived(message: RemoteMessage) {
        val type = message.data["type"].orEmpty()
        val app = application as? HealthVaultApp ?: return
        when (type) {
            "vault_send_request" -> {
                val id = message.data["id"].orEmpty()
                if (id.isBlank()) return
                CoroutineScope(Dispatchers.IO).launch {
                    val req = runCatching {
                        app.repository.listVaultSendRequests("pending").firstOrNull { it.id == id }
                    }.getOrNull() ?: VaultSendRequestOut(
                        id = id,
                        send_id = message.data["send_id"].orEmpty(),
                        send_name = message.notification?.body
                            ?.substringAfter("asked for access to “")
                            ?.substringBefore("”")
                            ?.takeIf { it.isNotBlank() }
                            ?: "shared link",
                        status = "pending"
                    )
                    VaultSendRequestNotifier.show(app, req)
                }
            }
            "login_challenge" -> {
                val id = message.data["id"].orEmpty()
                if (id.isBlank()) return
                CoroutineScope(Dispatchers.IO).launch {
                    runCatching {
                        app.repository.pendingLoginChallenges().firstOrNull { it.id == id }
                    }.getOrNull()?.let { LoginChallengeNotifier.show(app, it) }
                }
            }
            else -> {
                if (type.isNotBlank()) Log.d("VaultFCM", "Unhandled push type=$type")
            }
        }
    }
}
