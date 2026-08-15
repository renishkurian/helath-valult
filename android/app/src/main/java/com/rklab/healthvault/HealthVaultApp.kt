package com.rklab.healthvault

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build
import com.rklab.healthvault.data.ServerConfigManager
import com.rklab.healthvault.data.TokenManager
import com.rklab.healthvault.data.local.AppDatabase
import com.rklab.healthvault.data.remote.RetrofitClient
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.data.sync.ConnectivityObserver
import com.rklab.healthvault.data.sync.SyncWorker

class HealthVaultApp : Application() {

    lateinit var repository: HealthVaultRepository
        private set

    @Volatile var pendingQuickAdd: Boolean = false
    @Volatile var pendingOpenCare: Boolean = false
    @Volatile var pendingOpenVaultSends: Boolean = false

    override fun onCreate() {
        super.onCreate()

        val tokenManager = TokenManager(this)
        val serverConfig = ServerConfigManager(this)
        val api = RetrofitClient.create(tokenManager, serverConfig)
        val db = AppDatabase.getInstance(this)
        val connectivity = ConnectivityObserver(this)

        repository = HealthVaultRepository(
            api = api,
            tokenManager = tokenManager,
            serverConfig = serverConfig,
            db = db,
            connectivityObserver = connectivity,
            appContext = this
        )

        // Enqueue a background sync now; WorkManager will hold it until
        // connectivity is available, then run it automatically.
        if (tokenManager.getAccessToken() != null) {
            SyncWorker.enqueue(this)
            com.rklab.healthvault.util.ReminderScheduler.rescheduleAll(this)
            com.rklab.healthvault.util.EmiScheduler.rescheduleAll(this)
        }

        createReminderNotificationChannel()
        createEmiNotificationChannel()
        createLoginNotificationChannel()
        createSendRequestNotificationChannel()
        com.rklab.healthvault.ui.screens.finance.FinanceSmsIngestor.ensureChannel(this)
        if (tokenManager.getAccessToken() != null) {
            com.rklab.healthvault.ui.screens.finance.FinanceSmsIngestor.scanInbox(this)
        }
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

    private fun createEmiNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                EMI_CHANNEL_ID,
                "Recurring payments",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Alerts when an EMI, chitty, loan, or other recurring payment is due"
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }
    }

    private fun createLoginNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                LOGIN_CHANNEL_ID,
                "Web login requests",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Approve or deny a sign-in to the Vault website"
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }
    }

    private fun createSendRequestNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                SEND_REQUEST_CHANNEL_ID,
                "Send access requests",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Someone requested access to a shared password link"
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }
    }

    companion object {
        const val REMINDER_CHANNEL_ID = "reminders"
        const val EMI_CHANNEL_ID = "emi"
        const val LOGIN_CHANNEL_ID = "login_challenge"
        const val SEND_REQUEST_CHANNEL_ID = "vault_send_request"
    }
}
