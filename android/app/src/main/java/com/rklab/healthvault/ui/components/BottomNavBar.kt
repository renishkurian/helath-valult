package com.rklab.healthvault.ui.components

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.Security
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.People
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Send
import androidx.compose.material.icons.filled.VpnKey
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.rklab.healthvault.ui.theme.InkSoft
import com.rklab.healthvault.ui.theme.Navy
import com.rklab.healthvault.ui.theme.White

enum class MainTab { HOME, SEARCH, CARE, REMINDERS, FAMILY }

enum class PasswordTab { VAULT, GENERATOR, SEND, HEALTH }

private val navColors
    @Composable get() = NavigationBarItemDefaults.colors(
        selectedIconColor = Navy,
        selectedTextColor = Navy,
        unselectedIconColor = InkSoft,
        unselectedTextColor = InkSoft,
        indicatorColor = Color(0x335B8CFF)
    )

@Composable
fun PasswordVaultBottomNav(current: PasswordTab, onSelect: (PasswordTab) -> Unit) {
    NavigationBar(containerColor = White, tonalElevation = 0.dp) {
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
fun HealthVaultBottomNav(current: MainTab, onSelect: (MainTab) -> Unit) {
    NavigationBar(containerColor = White, tonalElevation = 0.dp) {
        NavigationBarItem(
            selected = current == MainTab.HOME,
            onClick = { onSelect(MainTab.HOME) },
            icon = { Icon(Icons.Filled.Home, contentDescription = "Home") },
            label = { Text("Home") },
            colors = navColors
        )
        NavigationBarItem(
            selected = current == MainTab.SEARCH,
            onClick = { onSelect(MainTab.SEARCH) },
            icon = { Icon(Icons.Filled.Search, contentDescription = "Search") },
            label = { Text("Search") },
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
