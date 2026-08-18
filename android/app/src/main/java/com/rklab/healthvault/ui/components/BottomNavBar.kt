package com.rklab.healthvault.ui.components

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AccountBalanceWallet
import androidx.compose.material.icons.filled.BarChart
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Call
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.Folder
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Inbox
import androidx.compose.material.icons.filled.Label
import androidx.compose.material.icons.filled.Link
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.MenuBook
import androidx.compose.material.icons.filled.MoreHoriz
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.People
import androidx.compose.material.icons.filled.Security
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Send
import androidx.compose.material.icons.filled.ShoppingCart
import androidx.compose.material.icons.filled.SmartToy
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.filled.VpnKey
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.unit.dp
import com.rklab.healthvault.ui.theme.HubDock
import com.rklab.healthvault.ui.theme.HubTextDim
import com.rklab.healthvault.ui.theme.VaultTeal
import com.rklab.healthvault.ui.theme.VaultTealSoft

enum class MainTab { HOME, DOCTORS, CARE, REMINDERS, FAMILY }

enum class PasswordTab { VAULT, GENERATOR, SEND, HEALTH }

enum class FinanceTab { HOME, TRANS, STATS, ACCOUNTS, MORE }

enum class LockerTab { LOCKER, EXPIRING }

enum class UrlTab { LINKS, FAVORITES, MANAGE }

enum class AiTab { ASK, PROVIDERS, LOGS }

enum class ExpenseTab { INBOX, INSIGHTS, LOG, SETTINGS }

enum class TrackerTab { LISTS, FRIENDS, CATALOG, TRASH }

private val navColors
    @Composable get() = NavigationBarItemDefaults.colors(
        selectedIconColor = VaultTeal,
        selectedTextColor = VaultTeal,
        unselectedIconColor = HubTextDim,
        unselectedTextColor = HubTextDim,
        indicatorColor = VaultTealSoft
    )

@Composable
fun TrackerBottomNav(current: TrackerTab, onSelect: (TrackerTab) -> Unit) {
    NavigationBar(containerColor = HubDock, tonalElevation = 0.dp) {
        NavigationBarItem(
            selected = current == TrackerTab.LISTS,
            onClick = { onSelect(TrackerTab.LISTS) },
            icon = { Icon(Icons.Filled.ShoppingCart, contentDescription = "Lists") },
            label = { Text("Lists") },
            colors = navColors
        )
        NavigationBarItem(
            selected = current == TrackerTab.FRIENDS,
            onClick = { onSelect(TrackerTab.FRIENDS) },
            icon = { Icon(Icons.Filled.People, contentDescription = "People") },
            label = { Text("People") },
            colors = navColors
        )
        NavigationBarItem(
            selected = current == TrackerTab.CATALOG,
            onClick = { onSelect(TrackerTab.CATALOG) },
            icon = { Icon(Icons.Filled.Star, contentDescription = "Quick add") },
            label = { Text("Chips") },
            colors = navColors
        )
        NavigationBarItem(
            selected = current == TrackerTab.TRASH,
            onClick = { onSelect(TrackerTab.TRASH) },
            icon = { Icon(Icons.Filled.Delete, contentDescription = "Trash") },
            label = { Text("Trash") },
            colors = navColors
        )
    }
}

@Composable
fun AiBottomNav(current: AiTab, onSelect: (AiTab) -> Unit) {
    NavigationBar(containerColor = HubDock, tonalElevation = 0.dp) {
        NavigationBarItem(
            selected = current == AiTab.ASK,
            onClick = { onSelect(AiTab.ASK) },
            icon = { Icon(Icons.Filled.SmartToy, contentDescription = "Ask AI") },
            label = { Text("Ask") },
            colors = navColors
        )
        NavigationBarItem(
            selected = current == AiTab.PROVIDERS,
            onClick = { onSelect(AiTab.PROVIDERS) },
            icon = { Icon(Icons.Filled.VpnKey, contentDescription = "Providers") },
            label = { Text("Keys") },
            colors = navColors
        )
        NavigationBarItem(
            selected = current == AiTab.LOGS,
            onClick = { onSelect(AiTab.LOGS) },
            icon = { Icon(Icons.Filled.MenuBook, contentDescription = "Usage logs") },
            label = { Text("Logs") },
            colors = navColors
        )
    }
}

@Composable
fun ExpenseAnalyserBottomNav(current: ExpenseTab, onSelect: (ExpenseTab) -> Unit) {
    NavigationBar(containerColor = HubDock, tonalElevation = 0.dp) {
        NavigationBarItem(
            selected = current == ExpenseTab.INBOX,
            onClick = { onSelect(ExpenseTab.INBOX) },
            icon = { Icon(Icons.Filled.Inbox, contentDescription = "Inbox") },
            label = { Text("Inbox") },
            colors = navColors
        )
        NavigationBarItem(
            selected = current == ExpenseTab.INSIGHTS,
            onClick = { onSelect(ExpenseTab.INSIGHTS) },
            icon = { Icon(Icons.Filled.BarChart, contentDescription = "Insights") },
            label = { Text("Insights") },
            colors = navColors
        )
        NavigationBarItem(
            selected = current == ExpenseTab.LOG,
            onClick = { onSelect(ExpenseTab.LOG) },
            icon = { Icon(Icons.Filled.History, contentDescription = "Sync log") },
            label = { Text("Log") },
            colors = navColors
        )
        NavigationBarItem(
            selected = current == ExpenseTab.SETTINGS,
            onClick = { onSelect(ExpenseTab.SETTINGS) },
            icon = { Icon(Icons.Filled.Settings, contentDescription = "Gmail & sync") },
            label = { Text("Gmail") },
            colors = navColors
        )
    }
}

@Composable
fun PasswordVaultBottomNav(current: PasswordTab, onSelect: (PasswordTab) -> Unit) {
    NavigationBar(containerColor = HubDock, tonalElevation = 0.dp) {
        NavigationBarItem(
            selected = current == PasswordTab.VAULT,
            onClick = { onSelect(PasswordTab.VAULT) },
            icon = { Icon(Icons.Filled.Lock, contentDescription = "Vault") },
            label = { Text("Vault") },
            colors = navColors
        )
        NavigationBarItem(
            selected = current == PasswordTab.GENERATOR,
            onClick = { onSelect(PasswordTab.GENERATOR) },
            icon = { Icon(Icons.Filled.VpnKey, contentDescription = "Generator") },
            label = { Text("Generate") },
            colors = navColors
        )
        NavigationBarItem(
            selected = current == PasswordTab.SEND,
            onClick = { onSelect(PasswordTab.SEND) },
            icon = { Icon(Icons.Filled.Send, contentDescription = "Send") },
            label = { Text("Send") },
            colors = navColors
        )
        NavigationBarItem(
            selected = current == PasswordTab.HEALTH,
            onClick = { onSelect(PasswordTab.HEALTH) },
            icon = { Icon(Icons.Filled.Security, contentDescription = "Health") },
            label = { Text("Health") },
            colors = navColors
        )
    }
}

@Composable
fun FinanceBottomNav(current: FinanceTab, onSelect: (FinanceTab) -> Unit) {
    NavigationBar(containerColor = HubDock, tonalElevation = 0.dp) {
        NavigationBarItem(
            selected = current == FinanceTab.HOME,
            onClick = { onSelect(FinanceTab.HOME) },
            icon = { Icon(Icons.Filled.Home, contentDescription = "Home") },
            label = { Text("Home") },
            colors = navColors
        )
        NavigationBarItem(
            selected = current == FinanceTab.TRANS,
            onClick = { onSelect(FinanceTab.TRANS) },
            icon = { Icon(Icons.Filled.History, contentDescription = "History") },
            label = { Text("History") },
            colors = navColors
        )
        NavigationBarItem(
            selected = current == FinanceTab.STATS,
            onClick = { onSelect(FinanceTab.STATS) },
            icon = { Icon(Icons.Filled.BarChart, contentDescription = "Insight") },
            label = { Text("Insight") },
            colors = navColors
        )
        NavigationBarItem(
            selected = current == FinanceTab.ACCOUNTS,
            onClick = { onSelect(FinanceTab.ACCOUNTS) },
            icon = { Icon(Icons.Filled.AccountBalanceWallet, contentDescription = "Accounts") },
            label = { Text("Accounts") },
            colors = navColors
        )
        NavigationBarItem(
            selected = current == FinanceTab.MORE,
            onClick = { onSelect(FinanceTab.MORE) },
            icon = { Icon(Icons.Filled.MoreHoriz, contentDescription = "More") },
            label = { Text("More") },
            colors = navColors
        )
    }
}

@Composable
fun LockerBottomNav(current: LockerTab, onSelect: (LockerTab) -> Unit) {
    NavigationBar(containerColor = HubDock, tonalElevation = 0.dp) {
        NavigationBarItem(
            selected = current == LockerTab.LOCKER,
            onClick = { onSelect(LockerTab.LOCKER) },
            icon = { Icon(Icons.Filled.Folder, contentDescription = "Locker") },
            label = { Text("Locker") },
            colors = navColors
        )
        NavigationBarItem(
            selected = current == LockerTab.EXPIRING,
            onClick = { onSelect(LockerTab.EXPIRING) },
            icon = { Icon(Icons.Filled.Warning, contentDescription = "Expiring") },
            label = { Text("Expiring") },
            colors = navColors
        )
    }
}

@Composable
fun UrlBottomNav(current: UrlTab, onSelect: (UrlTab) -> Unit) {
    NavigationBar(containerColor = HubDock, tonalElevation = 0.dp) {
        NavigationBarItem(
            selected = current == UrlTab.LINKS,
            onClick = { onSelect(UrlTab.LINKS) },
            icon = { Icon(Icons.Filled.Link, contentDescription = "Links") },
            label = { Text("Links") },
            colors = navColors
        )
        NavigationBarItem(
            selected = current == UrlTab.FAVORITES,
            onClick = { onSelect(UrlTab.FAVORITES) },
            icon = { Icon(Icons.Filled.Star, contentDescription = "Favorites") },
            label = { Text("Favorites") },
            colors = navColors
        )
        NavigationBarItem(
            selected = current == UrlTab.MANAGE,
            onClick = { onSelect(UrlTab.MANAGE) },
            icon = { Icon(Icons.Filled.Label, contentDescription = "Manage") },
            label = { Text("Manage") },
            colors = navColors
        )
    }
}

@Composable
fun HealthVaultBottomNav(current: MainTab, onSelect: (MainTab) -> Unit) {
    NavigationBar(containerColor = HubDock, tonalElevation = 0.dp) {
        NavigationBarItem(
            selected = current == MainTab.HOME,
            onClick = { onSelect(MainTab.HOME) },
            icon = { Icon(Icons.Filled.Home, contentDescription = "Home") },
            label = { Text("Home") },
            colors = navColors
        )
        NavigationBarItem(
            selected = current == MainTab.DOCTORS,
            onClick = { onSelect(MainTab.DOCTORS) },
            icon = { Icon(Icons.Filled.Call, contentDescription = "Doctors") },
            label = { Text("Doctors") },
            colors = navColors
        )
        NavigationBarItem(
            selected = current == MainTab.CARE,
            onClick = { onSelect(MainTab.CARE) },
            icon = { Icon(Icons.Filled.Favorite, contentDescription = "Care") },
            label = { Text("Care") },
            colors = navColors
        )
        NavigationBarItem(
            selected = current == MainTab.REMINDERS,
            onClick = { onSelect(MainTab.REMINDERS) },
            icon = { Icon(Icons.Filled.Notifications, contentDescription = "Reminders") },
            label = { Text("Reminders") },
            colors = navColors
        )
        NavigationBarItem(
            selected = current == MainTab.FAMILY,
            onClick = { onSelect(MainTab.FAMILY) },
            icon = { Icon(Icons.Filled.People, contentDescription = "Family") },
            label = { Text("Family") },
            colors = navColors
        )
    }
}
