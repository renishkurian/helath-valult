package com.rklab.healthvault.util

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import androidx.core.app.ActivityCompat
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.work.*
import com.rklab.healthvault.HealthVaultApp
import java.time.Duration
import java.time.Instant
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.concurrent.TimeUnit

/**
 * Schedules a one-off WorkManager job that fires a local notification at
 * `remindAtIso`. This relies on the app/device being alive around that time
 * (WorkManager, not exact AlarmManager) — good enough for "take your
 * medicine at 9am" style reminders. If you need alarm-clock-grade precision
 * even when Doze kicks in, swap this for AlarmManager.setExactAndAllowWhileIdle.
 */
object ReminderScheduler {

    fun schedule(context: Context, reminderId: String, title: String, description: String?, remindAtIso: String) {
        val remindAt = try {
            LocalDateTime.parse(remindAtIso, DateTimeFormatter.ISO_DATE_TIME)
                .atZone(ZoneId.systemDefault()).toInstant()
        } catch (e: Exception) {
            return
        }
        val delay = Duration.between(Instant.now(), remindAt).toMillis()
        if (delay <= 0) return

        val data = Data.Builder()
            .putString("title", title)
            .putString("description", description ?: "")
            .putString("reminderId", reminderId)
            .build()

        val request = OneTimeWorkRequestBuilder<ReminderWorker>()
            .setInitialDelay(delay, TimeUnit.MILLISECONDS)
            .setInputData(data)
            .addTag("reminder_$reminderId")
            .build()

        WorkManager.getInstance(context).enqueueUniqueWork(
            "reminder_$reminderId",
            ExistingWorkPolicy.REPLACE,
            request
        )
    }

    fun cancel(context: Context, reminderId: String) {
        WorkManager.getInstance(context).cancelUniqueWork("reminder_$reminderId")
    }
}

class ReminderWorker(context: Context, params: WorkerParameters) : Worker(context, params) {
    override fun doWork(): Result {
        val title = inputData.getString("title") ?: "Health Vault reminder"
        val description = inputData.getString("description").orEmpty()
        val reminderId = inputData.getString("reminderId") ?: return Result.success()

        val builder = NotificationCompat.Builder(applicationContext, HealthVaultApp.REMINDER_CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_popup_reminder)
            .setContentTitle(title)
            .setContentText(description)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)

        if (ActivityCompat.checkSelfPermission(applicationContext, Manifest.permission.POST_NOTIFICATIONS)
            == PackageManager.PERMISSION_GRANTED
        ) {
            NotificationManagerCompat.from(applicationContext).notify(reminderId.hashCode(), builder.build())
        }
        return Result.success()
    }
}
