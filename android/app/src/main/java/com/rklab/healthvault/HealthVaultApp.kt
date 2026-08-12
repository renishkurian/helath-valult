package com.rklab.healthvault

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build
import com.rklab.healthvault.data.ServerConfigManager
import com.rklab.healthvault.data.TokenManager
import com.rklab.healthvault.data.remote.RetrofitClient
import com.rklab.healthvault.data.repository.HealthVaultRepository

class HealthVaultApp : Application() {

    lateinit var repository: HealthVaultRepository
        private set

    override fun onCreate() {
        super.onCreate()
        val tokenManager = TokenManager(this)
        val serverConfig = ServerConfigManager(this)
        val api = RetrofitClient.create(tokenManager, serverConfig)
        repository = HealthVaultRepository(api, tokenManager, serverConfig)
        createReminderNotificationChannel()
    }

    private fun createReminderNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                REMINDER_CHANNEL_ID,
                "Health reminders",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Medicine, appointment, and card-expiry reminders"
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }
    }

    companion object {
        const val REMINDER_CHANNEL_ID = "reminders"
    }
}
