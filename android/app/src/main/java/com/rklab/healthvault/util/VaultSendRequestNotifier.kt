package com.rklab.healthvault.util

import android.Manifest
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import androidx.core.app.ActivityCompat
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.rklab.healthvault.HealthVaultApp
import com.rklab.healthvault.MainActivity
import com.rklab.healthvault.data.model.VaultSendRequestOut

object VaultSendRequestNotifier {
    fun show(context: Context, req: VaultSendRequestOut) {
        val open = PendingIntent.getActivity(
            context,
            req.id.hashCode(),
            Intent(context, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP)
                .putExtra(MainActivity.EXTRA_OPEN_VAULT_SENDS, true),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val who = req.name?.takeIf { it.isNotBlank() }
            ?: req.email?.takeIf { it.isNotBlank() }
            ?: req.ip?.takeIf { it.isNotBlank() }
            ?: "Someone"
        val builder = NotificationCompat.Builder(context, HealthVaultApp.SEND_REQUEST_CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("Send access request")
            .setContentText("$who asked for “${req.send_name}”")
            .setStyle(
                NotificationCompat.BigTextStyle().bigText(
                    buildString {
                        append("$who asked for access to “${req.send_name}”.")
                        req.ip?.takeIf { it.isNotBlank() }?.let { append(" IP: $it.") }
                        if (req.has_photo) append(" Includes a photo.")
                        if (!req.latitude.isNullOrBlank() && !req.longitude.isNullOrBlank()) {
                            append(" Location shared.")
                        }
                        append(" Open Send to review.")
                    }
                )
            )
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(open)

        if (ActivityCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS)
            == PackageManager.PERMISSION_GRANTED
        ) {
            NotificationManagerCompat.from(context).notify(req.id.hashCode(), builder.build())
        }
    }
}
