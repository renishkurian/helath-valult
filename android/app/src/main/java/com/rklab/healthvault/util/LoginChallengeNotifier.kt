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
import com.rklab.healthvault.data.model.LoginChallengeOut

object LoginChallengeNotifier {
    fun show(context: Context, challenge: LoginChallengeOut) {
        val open = PendingIntent.getActivity(
            context,
            challenge.id.hashCode(),
            Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val where = challenge.ip?.takeIf { it.isNotBlank() } ?: "a browser"
        val builder = NotificationCompat.Builder(context, HealthVaultApp.LOGIN_CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_lock_idle_lock)
            .setContentTitle("Approve web login")
            .setContentText("Vault sign-in from $where")
            .setStyle(NotificationCompat.BigTextStyle().bigText(
                "Someone is signing in to Vault from $where. Open the app to allow or deny."
            ))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(open)

        if (ActivityCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS)
            == PackageManager.PERMISSION_GRANTED
        ) {
            NotificationManagerCompat.from(context).notify(challenge.id.hashCode(), builder.build())
        }
    }

    fun cancel(context: Context, challengeId: String) {
        NotificationManagerCompat.from(context).cancel(challengeId.hashCode())
    }
}
