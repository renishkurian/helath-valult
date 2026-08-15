package com.rklab.healthvault.push

import android.app.Application
import android.util.Log
import com.google.firebase.FirebaseApp
import com.google.firebase.messaging.FirebaseMessaging
import com.rklab.healthvault.HealthVaultApp
import com.rklab.healthvault.data.model.DeviceTokenIn
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/**
 * Registers the FCM device token with the Vault API so Super Admin FCM can reach this phone.
 * Requires [android/app/google-services.json] from the same Firebase project as the server SA.
 */
object DevicePush {
    private const val TAG = "DevicePush"

    fun sync(app: Application) {
        val hv = app as? HealthVaultApp ?: return
        if (!hv.repository.isLoggedIn) return
        if (FirebaseApp.getApps(app).isEmpty()) {
            Log.w(TAG, "Firebase not configured — add google-services.json (see android/README.md)")
            return
        }
        FirebaseMessaging.getInstance().token
            .addOnSuccessListener { token ->
                if (token.isNullOrBlank()) return@addOnSuccessListener
                CoroutineScope(Dispatchers.IO).launch {
                    runCatching {
                        hv.repository.registerDevice(DeviceTokenIn(token = token, platform = "android"))
                    }.onFailure { Log.w(TAG, "registerDevice failed", it) }
                }
            }
            .addOnFailureListener { Log.w(TAG, "FCM token failed", it) }
    }
}
