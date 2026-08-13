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
import com.rklab.healthvault.data.model.FinanceEmiOut
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.ZoneId

/**
 * Alerts a few days before a recurring payment due date, and again on the due morning.
 */
object EmiScheduler {

    fun scheduleAll(context: Context, emis: List<FinanceEmiOut>) {
        emis.filter { it.active && it.status != "completed" && !it.next_due.isNullOrBlank() }
            .forEach { schedule(context, it) }
    }

    fun schedule(context: Context, emi: FinanceEmiOut) {
        val due = runCatching { LocalDate.parse(emi.next_due) }.getOrNull() ?: return
        val notifyDays = emi.notify_days.coerceIn(0, 14)
        if (notifyDays > 0) {
            setAlarm(
                context,
                requestCode(emi.id, upcoming = true),
                at = due.minusDays(notifyDays.toLong()),
                title = "${emi.kind_label} due in $notifyDays day${if (notifyDays == 1) "" else "s"}",
                text = "${emi.name} · ${formatInr(emi.amount)} on ${emi.next_due}"
            )
        }
        setAlarm(
            context,
            requestCode(emi.id, upcoming = false),
            at = due,
            title = "${emi.kind_label} due today",
            text = "${emi.name} · ${formatInr(emi.amount)}"
        )
    }

    fun cancel(context: Context, emiId: String) {
        cancelOne(context, requestCode(emiId, true))
        cancelOne(context, requestCode(emiId, false))
    }

    fun rescheduleAll(context: Context) {
        val app = context.applicationContext as? HealthVaultApp ?: return
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val emis = app.repository.listFinanceEmis()
                scheduleAll(context, emis)
            } catch (_: Exception) { }
        }
    }

    private fun setAlarm(context: Context, requestCode: Int, at: LocalDate, title: String, text: String) {
        val whenMs = LocalDateTime.of(at, LocalTime.of(9, 0))
            .atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
        if (whenMs <= System.currentTimeMillis()) return
        val intent = Intent(context, EmiReceiver::class.java).apply {
            putExtra("title", title)
            putExtra("text", text)
            putExtra("code", requestCode)
        }
        val pi = PendingIntent.getBroadcast(
            context, requestCode, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val am = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && !am.canScheduleExactAlarms()) {
            am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, whenMs, pi)
        } else {
            am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, whenMs, pi)
        }
    }

    private fun cancelOne(context: Context, requestCode: Int) {
        val intent = Intent(context, EmiReceiver::class.java)
        val pi = PendingIntent.getBroadcast(
            context, requestCode, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        (context.getSystemService(Context.ALARM_SERVICE) as AlarmManager).cancel(pi)
    }

    private fun requestCode(emiId: String, upcoming: Boolean): Int {
        val base = emiId.hashCode() and 0x7fff_ffff
        return if (upcoming) base else base xor 0x4000_0000
    }

    private fun formatInr(n: Double): String {
        val abs = kotlin.math.abs(n)
        return "₹ ${"%,.0f".format(abs)}"
    }
}

class EmiReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val title = intent.getStringExtra("title") ?: "Recurring payment"
        val text = intent.getStringExtra("text").orEmpty()
        val code = intent.getIntExtra("code", title.hashCode())
        val builder = NotificationCompat.Builder(context, HealthVaultApp.EMI_CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_popup_reminder)
            .setContentTitle(title)
            .setContentText(text)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
        if (ActivityCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS)
            == PackageManager.PERMISSION_GRANTED
        ) {
            NotificationManagerCompat.from(context).notify(code, builder.build())
        }
    }
}
