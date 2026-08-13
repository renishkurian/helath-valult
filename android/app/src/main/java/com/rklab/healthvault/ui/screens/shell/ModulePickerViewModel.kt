package com.rklab.healthvault.ui.screens.shell

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.rklab.healthvault.data.model.VaultHealthOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.temporal.ChronoUnit
import java.util.Calendar

data class HubUiState(
    val greeting: String = greetingForHour(),
    val vaultTitle: String = "Your Vault",
    val score: Int = 0,
    val scoreLabel: String = "checking",
    val heroSubtitle: String = "Loading vault status…",
    val online: Boolean = true,
    val alertCount: Int = 0,
    val recordCount: Int = 0,
    val healthSyncLabel: String = "Records, cards, care & reminders",
    val nextReminderLabel: String = "No reminders yet",
    val loginCount: Int = 0,
    val weakCount: Int = 0,
    val monthSpendLabel: String = "No spend this month",
    val financeFooter: String = "SMS auto-tag",
    val lockerCount: Int = 0,
    val lockerExpiring: Int = 0,
    val urlCount: Int = 0,
    val urlFavorites: Int = 0
)

class ModulePickerViewModel(private val repository: HealthVaultRepository) : ViewModel() {

    private val _state = MutableStateFlow(HubUiState())
    val state: StateFlow<HubUiState> = _state

    fun refresh() {
        viewModelScope.launch {
            val online = runCatching { repository.connectivityObserver.isConnected.first() }.getOrDefault(true)
            try {
                coroutineScope {
                    val userDef = async { runCatching { repository.me() }.getOrNull() }
                    val docsDef = async { runCatching { repository.listDocuments() }.getOrDefault(emptyList()) }
                    val healthDef = async { runCatching { repository.vaultHealth() }.getOrNull() }
                    val financeDef = async { runCatching { repository.financeSummary() }.getOrNull() }
                    val lockerDef = async { runCatching { repository.lockerSummary() }.getOrNull() }
                    val urlsDef = async { runCatching { repository.urlSummary() }.getOrNull() }
                    val remindersDef = async {
                        runCatching { repository.listReminders(upcomingOnly = true) }.getOrDefault(emptyList())
                    }

                    val user = userDef.await()
                    val docs = docsDef.await()
                    val health = healthDef.await()
                    val finance = financeDef.await()
                    val locker = lockerDef.await()
                    val urls = urlsDef.await()
                    val reminders = remindersDef.await().sortedBy { it.remind_at }

                    val firstName = user?.full_name?.trim()?.substringBefore(" ")?.takeIf { it.isNotBlank() }
                    val weak = health?.weak?.distinctBy { it.item_id }?.size ?: 0
                    val reused = health?.reused?.distinctBy { it.item_id }?.size ?: 0
                    val pendingSms = finance?.pending_messages ?: 0
                    val alerts = weak + reused + pendingSms
                    val latestDoc = docs.maxByOrNull { it.created_at }
                    val score = computeScore(health, online)

                    _state.value = HubUiState(
                        greeting = greetingForHour(),
                        vaultTitle = firstName?.let { possessiveVault(it) } ?: "Your Vault",
                        score = score,
                        scoreLabel = scoreLabel(score),
                        heroSubtitle = heroSubtitle(online, weak),
                        online = online,
                        alertCount = alerts,
                        recordCount = docs.size,
                        healthSyncLabel = healthSyncLabel(online, latestDoc?.created_at),
                        nextReminderLabel = nextReminderLabel(reminders.firstOrNull()?.remind_at),
                        loginCount = health?.total_logins ?: 0,
                        weakCount = weak,
                        monthSpendLabel = monthSpendLabel(finance?.expense ?: 0.0),
                        financeFooter = if (pendingSms > 0) "$pendingSms SMS to review" else "SMS auto-tag",
                        lockerCount = locker?.total ?: 0,
                        lockerExpiring = locker?.expiring ?: 0,
                        urlCount = urls?.total ?: 0,
                        urlFavorites = urls?.favorites ?: 0
                    )
                }
            } catch (_: Exception) {
                _state.value = _state.value.copy(
                    greeting = greetingForHour(),
                    heroSubtitle = if (online) "Couldn't refresh status." else "Pi is unreachable.",
                    online = online,
                    scoreLabel = if (online) "unknown" else "offline"
                )
            }
        }
    }
}

internal fun greetingForHour(hour: Int = Calendar.getInstance().get(Calendar.HOUR_OF_DAY)): String = when {
    hour < 12 -> "GOOD MORNING"
    hour < 17 -> "GOOD AFTERNOON"
    else -> "GOOD EVENING"
}

private fun possessiveVault(name: String): String =
    if (name.endsWith("s", ignoreCase = true)) "$name' Vault" else "$name's Vault"

private fun computeScore(health: VaultHealthOut?, online: Boolean): Int {
    if (health == null) return if (online) 80 else 62
    if (health.total_logins <= 0) return if (online) 100 else 88
    val weak = health.weak.distinctBy { it.item_id }.size
    val reused = health.reused.distinctBy { it.item_id }.size
    val old = health.old.distinctBy { it.item_id }.size
    val noTotp = health.no_totp.distinctBy { it.item_id }.size
    var score = 100
    score -= (weak * 10).coerceAtMost(35)
    score -= (reused * 8).coerceAtMost(25)
    score -= (old * 3).coerceAtMost(15)
    score -= noTotp.coerceAtMost(10)
    if (!online) score -= 8
    return score.coerceIn(0, 100)
}

private fun scoreLabel(score: Int): String = when {
    score >= 85 -> "strong"
    score >= 65 -> "okay"
    else -> "at risk"
}

private fun heroSubtitle(online: Boolean, weak: Int): String {
    val sync = if (online) "All modules synced." else "Pi is unreachable."
    val flag = when {
        weak == 1 -> " One weak login flagged."
        weak > 1 -> " $weak weak logins flagged."
        online -> " No weak logins."
        else -> ""
    }
    return sync + flag
}

private fun healthSyncLabel(online: Boolean, createdAt: String?): String {
    val base = "Records, cards, care & reminders"
    if (!online) return "$base — offline"
    val ago = createdAt?.let { relativeAgo(it) } ?: return base
    return "$base — synced $ago"
}

private fun nextReminderLabel(remindAt: String?): String {
    if (remindAt.isNullOrBlank()) return "No reminders yet"
    val date = parseToLocalDate(remindAt) ?: return "Upcoming reminder set"
    val days = ChronoUnit.DAYS.between(LocalDate.now(), date)
    return when {
        days < 0 -> "Next reminder overdue"
        days == 0L -> "Next reminder today"
        days == 1L -> "Next reminder in 1 day"
        else -> "Next reminder in $days days"
    }
}

private fun monthSpendLabel(expense: Double): String {
    if (expense <= 0.0) return "No spend this month"
    return "${inrCompact(expense)} tracked this month"
}

internal fun inrCompact(amount: Double): String {
    val abs = kotlin.math.abs(amount)
    return when {
        abs >= 100_000 -> {
            val lakhs = abs / 100_000.0
            val body = if (lakhs >= 10) "%.0f".format(lakhs) else "%.1f".format(lakhs).trimEnd('0').trimEnd('.')
            "₹${body}L"
        }
        abs >= 1_000 -> {
            val thousands = abs / 1_000.0
            val body = if (thousands >= 10) "%.0f".format(thousands) else "%.1f".format(thousands).trimEnd('0').trimEnd('.')
            "₹${body}K"
        }
        else -> "₹%.0f".format(abs)
    }
}

private fun relativeAgo(iso: String): String? {
    val instant = parseToInstant(iso) ?: return null
    val hours = Duration.between(instant, Instant.now()).toHours()
    return when {
        hours < 1 -> "just now"
        hours < 24 -> "${hours}h ago"
        else -> "${hours / 24}d ago"
    }
}

private fun parseToInstant(iso: String): Instant? =
    runCatching { Instant.parse(iso) }.getOrNull()
        ?: runCatching { LocalDateTime.parse(iso).atZone(ZoneId.systemDefault()).toInstant() }.getOrNull()
        ?: runCatching { LocalDate.parse(iso.take(10)).atStartOfDay(ZoneId.systemDefault()).toInstant() }.getOrNull()

private fun parseToLocalDate(iso: String): LocalDate? =
    runCatching { Instant.parse(iso).atZone(ZoneId.systemDefault()).toLocalDate() }.getOrNull()
        ?: runCatching { LocalDateTime.parse(iso).toLocalDate() }.getOrNull()
        ?: runCatching { LocalDate.parse(iso.take(10)) }.getOrNull()
