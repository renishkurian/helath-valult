package com.rklab.healthvault.data.sync

import android.content.Context
import androidx.work.*
import com.rklab.healthvault.HealthVaultApp

/**
 * Runs whenever the device has internet connectivity.
 * Responsibilities:
 *  1. Refresh people → cards + documents + reminders → update Room cache
 *  2. Drain the pending_uploads table: upload each queued file to the Pi,
 *     then delete the row on success. Failed rows stay for the next retry.
 */
class SyncWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {

    companion object {
        const val WORK_NAME = "healthvault_sync"

        /**
         * Enqueue a one-shot sync. If a sync is already queued/running we
         * KEEP it (no duplicates). WorkManager holds the work until the
         * CONNECTED constraint is satisfied, so this is safe to call any time.
         */
        fun enqueue(context: Context) {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()

            val request = OneTimeWorkRequestBuilder<SyncWorker>()
                .setConstraints(constraints)
                .build()

            WorkManager.getInstance(context)
                .enqueueUniqueWork(WORK_NAME, ExistingWorkPolicy.KEEP, request)
        }

        /**
         * Re-enqueue a sync immediately, replacing any waiting one.
         * Call this after queuing a pending upload so the worker runs ASAP.
         */
        fun enqueueNow(context: Context) {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()

            val request = OneTimeWorkRequestBuilder<SyncWorker>()
                .setConstraints(constraints)
                .build()

            WorkManager.getInstance(context)
                .enqueueUniqueWork(WORK_NAME, ExistingWorkPolicy.REPLACE, request)
        }
    }

    override suspend fun doWork(): Result {
        return try {
            val repository = (applicationContext as HealthVaultApp).repository
            repository.syncAll()
            Result.success()
        } catch (e: Exception) {
            // Retry with exponential back-off — WorkManager handles the schedule.
            Result.retry()
        }
    }
}
