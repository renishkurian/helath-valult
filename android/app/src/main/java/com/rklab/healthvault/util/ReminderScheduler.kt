package com.rklab.healthvault.util

import android.Manifest
import android.app.AlarmManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.ActivityCompat
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.rklab.healthvault.HealthVaultApp
import com.rklab.healthvault.data.model.RepeatRule
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import java.time.Instant
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/**
 * Fires reminder notifications via AlarmManager (not by polling the API).
 * Recurring reminders reschedule themselves when they fire.
 */
object ReminderScheduler {

    fun schedule(
        context: Context,
        reminderId: String,
        title: String,
        description: String?,
        remindAtIso: String,
        repeatRule: RepeatRule = RepeatRule.NONE
    ) {
        val remindAt = parseIso(remindAtIso) ?: return
        var whenMs = remindAt.toEpochMilli()
        if (whenMs <= System.currentTimeMillis()) {
            val next = nextOccurrence(remindAt, repeatRule) ?: return
            whenMs = next.toEpochMilli()
        }

        val intent = Intent(context, ReminderReceiver::class.java).apply {
            putExtra("title", title)
            putExtra("description", description ?: "")
            putExtra("reminderId", reminderId)
            putExtra("repeatRule", repeatRule.name)
            putExtra("remindAtIso", remindAtIso)
        }
        val pi = PendingIntent.getBroadcast(
            context, reminderId.hashCode(), intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val am = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && !am.canScheduleExactAlarms()) {
            am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, whenMs, pi)
        } else {
            am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, whenMs, pi)
        }
    }

    fun cancel(context: Context, reminderId: String) {
        val intent = Intent(context, ReminderReceiver::class.java)
        val pi = PendingIntent.getBroadcast(
            context, reminderId.hashCode(), intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        (context.getSystemService(Context.ALARM_SERVICE) as AlarmManager).cancel(pi)
    }

    fun rescheduleAll(context: Context) {
        val app = context.applicationContext as? HealthVaultApp ?: return
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val reminders = app.repository.listReminders(upcomingOnly = true)
                reminders.filter { it.is_active }.forEach { r ->
                    schedule(context, r.id, r.title, r.description, r.remind_at, r.repeat_rule)
                }
            } catch (_: Exception) { }
        }
    }

    fun nextOccurrence(from: Instant, rule: RepeatRule): Instant? {
        val days = when (rule) {
            RepeatRule.DAILY -> 1L
            RepeatRule.WEEKLY -> 7L
            RepeatRule.MONTHLY -> 30L
            RepeatRule.YEARLY -> 365L
            RepeatRule.NONE -> return null
        }
        return from.plusSeconds(days * 86400)
    }

    private fun parseIso(iso: String): Instant? {
        val cleaned = iso.trim().replace(' ', 'T')
        return try {
            Instant.parse(cleaned)
        } catch (_: Exception) {
            val patterns = listOf(
                DateTimeFormatter.ISO_DATE_TIME,
                DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss"),
                DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm"),
                DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSS"),
            )
            for (fmt in patterns) {
                try {
                    return LocalDateTime.parse(cleaned, fmt).atZone(ZoneId.systemDefault()).toInstant()
                } catch (_: Exception) {
                    // try next
                }
            }
            null
        }
    }
}

class ReminderReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val title = intent.getStringExtra("title") ?: "Vault Hub reminder"
        val description = intent.getStringExtra("description").orEmpty()
        val reminderId = intent.getStringExtra("reminderId") ?: return
        val repeatName = intent.getStringExtra("repeatRule") ?: RepeatRule.NONE.name
        val repeat = runCatching { RepeatRule.valueOf(repeatName) }.getOrDefault(RepeatRule.NONE)

        val builder = NotificationCompat.Builder(context, HealthVaultApp.REMINDER_CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_popup_reminder)
            .setContentTitle(title)
            .setContentText(description)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)

        if (ActivityCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS)
            == PackageManager.PERMISSION_GRANTED
        ) {
            NotificationManagerCompat.from(context).notify(reminderId.hashCode(), builder.build())
        }

        if (repeat != RepeatRule.NONE) {
            val from = ReminderScheduler.nextOccurrence(Instant.now(), repeat) ?: return
            val iso = LocalDateTime.ofInstant(from, ZoneId.systemDefault())
                .format(DateTimeFormatter.ISO_DATE_TIME)
            ReminderScheduler.schedule(context, reminderId, title, description, iso, repeat)
        }
    }
}

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED) {
            ReminderScheduler.rescheduleAll(context)
            EmiScheduler.rescheduleAll(context)
            com.rklab.healthvault.ui.screens.finance.FinanceSmsIngestor.scanInbox(context)
        }
    }
}
