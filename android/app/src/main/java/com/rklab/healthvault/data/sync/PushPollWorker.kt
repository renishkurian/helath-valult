package com.rklab.healthvault.data.sync

import android.content.Context
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.rklab.healthvault.HealthVaultApp
import com.rklab.healthvault.util.LoginChallengeNotifier
import com.rklab.healthvault.util.VaultSendRequestNotifier
import java.util.concurrent.TimeUnit

/**
 * Background fallback when FCM is delayed or unavailable: poll pending Send
 * access requests and web-login challenges while the user is signed in.
 */
class PushPollWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {

    companion object {
        const val WORK_NAME = "vault_push_poll"

        fun enqueue(context: Context) {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()
            val request = PeriodicWorkRequestBuilder<PushPollWorker>(15, TimeUnit.MINUTES)
                .setConstraints(constraints)
                .build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                WORK_NAME,
                ExistingPeriodicWorkPolicy.KEEP,
                request
            )
        }

        fun cancel(context: Context) {
            WorkManager.getInstance(context).cancelUniqueWork(WORK_NAME)
        }
    }

    override suspend fun doWork(): Result {
        val app = applicationContext as? HealthVaultApp ?: return Result.success()
        if (!app.repository.isLoggedIn) return Result.success()
        return try {
            runCatching {
                app.repository.listVaultSendRequests("pending").forEach { req ->
                    VaultSendRequestNotifier.show(app, req)
                }
            }
            runCatching {
                app.repository.pendingLoginChallenges().forEach { challenge ->
                    LoginChallengeNotifier.show(app, challenge)
                }
            }
            Result.success()
        } catch (_: Exception) {
            Result.retry()
        }
    }
}
