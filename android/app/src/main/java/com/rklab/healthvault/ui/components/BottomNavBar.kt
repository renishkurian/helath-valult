package com.rklab.healthvault.ui.components

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.People
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import com.rklab.healthvault.ui.theme.InkSoft
import com.rklab.healthvault.ui.theme.Navy
import com.rklab.healthvault.ui.theme.White

enum class MainTab { HOME, SEARCH, REMINDERS, FAMILY }

@Composable
fun HealthVaultBottomNav(current: MainTab, onSelect: (MainTab) -> Unit) {
    NavigationBar(containerColor = White) {
        NavigationBarItem(
            selected = current == MainTab.HOME,
            onClick = { onSelect(MainTab.HOME) },
            icon = { Icon(Icons.Filled.Home, contentDescription = "Home") },
            label = { Text("Home") },
            colors = NavigationBarItemDefaults.colors(selectedIconColor = Navy, selectedTextColor = Navy, unselectedIconColor = InkSoft, unselectedTextColor = InkSoft, indicatorColor = White)
        )
        NavigationBarItem(
            selected = current == MainTab.SEARCH,
            onClick = { onSelect(MainTab.SEARCH) },
            icon = { Icon(Icons.Filled.Search, contentDescription = "Search") },
            label = { Text("Search") },
            colors = NavigationBarItemDefaults.colors(selectedIconColor = Navy, selectedTextColor = Navy, unselectedIconColor = InkSoft, unselectedTextColor = InkSoft, indicatorColor = White)
        )
        NavigationBarItem(
            selected = current == MainTab.REMINDERS,
            onClick = { onSelect(MainTab.REMINDERS) },
            icon = { Icon(Icons.Filled.Notifications, contentDescription = "Reminders") },
            label = { Text("Reminders") },
            colors = NavigationBarItemDefaults.colors(selectedIconColor = Navy, selectedTextColor = Navy, unselectedIconColor = InkSoft, unselectedTextColor = InkSoft, indicatorColor = White)
        )
        NavigationBarItem(
            selected = current == MainTab.FAMILY,
            onClick = { onSelect(MainTab.FAMILY) },
            icon = { Icon(Icons.Filled.People, contentDescription = "Family") },
            label = { Text("Family") },
            colors = NavigationBarItemDefaults.colors(selectedIconColor = Navy, selectedTextColor = Navy, unselectedIconColor = InkSoft, unselectedTextColor = InkSoft, indicatorColor = White)
        )
    }
}
