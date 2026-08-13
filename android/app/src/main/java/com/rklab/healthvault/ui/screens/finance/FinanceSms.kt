package com.rklab.healthvault.ui.screens.finance

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.ContentResolver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.provider.Telephony
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.rklab.healthvault.HealthVaultApp
import com.rklab.healthvault.MainActivity
import com.rklab.healthvault.data.model.FinanceMessageIn
import com.rklab.healthvault.data.model.FinanceMessageOut
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import java.security.MessageDigest

object FinanceSmsLooks {
    private val finance = Regex(
        """(?:rs\.?|inr|₹|debited|credited|upi|neft|imps|rtgs|spent|paid to|avl\s*bal|a/c|account|withdrawn|deposited|sent\s+rs)""",
        RegexOption.IGNORE_CASE
    )
    private val otp = Regex(
        """\b(otp|one[\s-]?time\s+password|verification code|do not share)\b""",
        RegexOption.IGNORE_CASE
    )
    private val money = Regex("""(?:rs\.?|inr|₹|debited|credited)""", RegexOption.IGNORE_CASE)

    fun isFinance(body: String): Boolean {
        val text = body.trim()
        if (text.length < 20) return false
        if (otp.containsMatchIn(text) && !money.containsMatchIn(text)) return false
        return finance.containsMatchIn(text)
    }
}

object FinanceSmsPrefs {
    private const val PREF = "finance_sms"
    private const val KEY_ON = "enabled"
    private const val KEY_SCAN = "last_scan_ms"
    private const val KEY_SEEN = "seen_hashes"

    fun isEnabled(context: Context): Boolean =
        context.getSharedPreferences(PREF, Context.MODE_PRIVATE).getBoolean(KEY_ON, false)

    fun setEnabled(context: Context, on: Boolean) {
        context.getSharedPreferences(PREF, Context.MODE_PRIVATE).edit().putBoolean(KEY_ON, on).apply()
    }

    fun lastScanMs(context: Context): Long =
        context.getSharedPreferences(PREF, Context.MODE_PRIVATE).getLong(KEY_SCAN, 0L)

    fun setLastScanMs(context: Context, ms: Long) {
        context.getSharedPreferences(PREF, Context.MODE_PRIVATE).edit().putLong(KEY_SCAN, ms).apply()
    }

    fun seen(context: Context, hash: String): Boolean {
        val raw = context.getSharedPreferences(PREF, Context.MODE_PRIVATE).getString(KEY_SEEN, "") ?: ""
        return raw.split('\n').contains(hash)
    }

    fun markSeen(context: Context, hash: String) {
        val prefs = context.getSharedPreferences(PREF, Context.MODE_PRIVATE)
        val raw = prefs.getString(KEY_SEEN, "") ?: ""
        val next = (listOf(hash) + raw.split('\n').filter { it.isNotBlank() }).distinct().take(400)
        prefs.edit().putString(KEY_SEEN, next.joinToString("\n")).apply()
    }

    fun hash(body: String): String {
        val norm = body.lowercase().replace(Regex("""\s+"""), " ").trim()
        val bytes = MessageDigest.getInstance("SHA-256").digest(norm.toByteArray())
        return bytes.joinToString("") { "%02x".format(it) }.take(32)
    }

    fun hasSmsPermission(context: Context): Boolean {
        val read = ContextCompat.checkSelfPermission(context, Manifest.permission.READ_SMS) ==
            PackageManager.PERMISSION_GRANTED
        val receive = ContextCompat.checkSelfPermission(context, Manifest.permission.RECEIVE_SMS) ==
            PackageManager.PERMISSION_GRANTED
        return read && receive
    }
}

object FinanceSmsIngestor {
    const val CHANNEL_ID = "finance_sms"

    fun ensureChannel(context: Context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Money SMS",
                NotificationManager.IMPORTANCE_DEFAULT
            ).apply { description = "Bank and UPI messages tagged into Money Manager" }
            context.getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
    }

    suspend fun ingestNow(context: Context, bodies: List<String>): Boolean {
        val app = context.applicationContext as? HealthVaultApp ?: return false
        if (!FinanceSmsPrefs.isEnabled(context)) return false
        if (!app.repository.isLoggedIn) return false
        val fresh = bodies.map { it.trim() }.filter { it.isNotBlank() && FinanceSmsLooks.isFinance(it) }
            .filter { !FinanceSmsPrefs.seen(context, FinanceSmsPrefs.hash(it)) }
        if (fresh.isEmpty()) return true
        return runCatching {
            val out = app.repository.ingestFinanceMessages(
                FinanceMessageIn(text = fresh.joinToString("\n\n"), auto_accept = true)
            )
            fresh.forEach { FinanceSmsPrefs.markSeen(context, FinanceSmsPrefs.hash(it)) }
            notify(context, out)
            true
        }.getOrElse {
            Log.w("FinanceSms", "ingest failed", it)
            false
        }
    }

    fun ingestIncoming(context: Context, bodies: List<String>) {
        CoroutineScope(Dispatchers.IO).launch { ingestNow(context, bodies) }
    }

    fun scanInbox(context: Context) {
        if (!FinanceSmsPrefs.isEnabled(context)) return
        if (!FinanceSmsPrefs.hasSmsPermission(context)) return
        CoroutineScope(Dispatchers.IO).launch {
            val since = FinanceSmsPrefs.lastScanMs(context).let {
                if (it > 0) it else System.currentTimeMillis() - 7L * 24 * 60 * 60 * 1000
            }
            val bodies = readInbox(context.contentResolver, since)
            val ok = if (bodies.isNotEmpty()) ingestNow(context, bodies) else true
            if (ok) FinanceSmsPrefs.setLastScanMs(context, System.currentTimeMillis())
        }
    }

    private fun readInbox(resolver: ContentResolver, sinceMs: Long): List<String> {
        val out = mutableListOf<String>()
        val cursor = resolver.query(
            Telephony.Sms.Inbox.CONTENT_URI,
            arrayOf(Telephony.Sms.BODY, Telephony.Sms.DATE),
            "${Telephony.Sms.DATE} > ?",
            arrayOf(sinceMs.toString()),
            "${Telephony.Sms.DATE} DESC"
        ) ?: return out
        cursor.use {
            val bodyIdx = it.getColumnIndex(Telephony.Sms.BODY)
            if (bodyIdx < 0) return out
            while (it.moveToNext()) {
                val body = it.getString(bodyIdx) ?: continue
                if (FinanceSmsLooks.isFinance(body)) out.add(body)
                if (out.size >= 40) break
            }
        }
        return out
    }

    private fun notify(context: Context, messages: List<FinanceMessageOut>) {
        if (messages.isEmpty()) return
        ensureChannel(context)
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS)
            != PackageManager.PERMISSION_GRANTED && Build.VERSION.SDK_INT >= 33
        ) return
        val accepted = messages.count { it.status == "accepted" }
        val pending = messages.count { it.status == "pending" }
        val first = messages.first()
        val title = when {
            accepted > 0 -> "Money Manager tagged a ${first.direction}"
            else -> "Money Manager needs a review"
        }
        val text = buildString {
            first.amount?.let { append("₹${"%.2f".format(it)} ") }
            append(first.payee ?: first.suggested_category ?: first.direction)
            if (accepted + pending > 1) append(" · ${accepted + pending} messages")
        }
        val open = PendingIntent.getActivity(
            context, 44,
            Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val notif = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(title)
            .setContentText(text)
            .setContentIntent(open)
            .setAutoCancel(true)
            .build()
        NotificationManagerCompat.from(context).notify(first.id.hashCode(), notif)
    }
}

class FinanceSmsReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Telephony.Sms.Intents.SMS_RECEIVED_ACTION) return
        if (!FinanceSmsPrefs.isEnabled(context)) return
        val parts = Telephony.Sms.Intents.getMessagesFromIntent(intent) ?: return
        val body = parts.joinToString("") { it.messageBody ?: "" }
        val pending = goAsync()
        CoroutineScope(Dispatchers.IO).launch {
            try {
                FinanceSmsIngestor.ingestNow(context, listOf(body))
            } finally {
                pending.finish()
            }
        }
    }
}
