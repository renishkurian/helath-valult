package com.rklab.healthvault.ui.screens.shell

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.rklab.healthvault.ui.theme.*

@Composable
fun ModulePickerScreen(
    onHealth: () -> Unit,
    onPasswords: () -> Unit,
    onSettings: () -> Unit
) {
    Column(
        modifier = Modifier.fillMaxSize().background(Paper).padding(24.dp)
    ) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    Modifier.size(40.dp).clip(RoundedCornerShape(12.dp)).background(GradientPrimary),
                    contentAlignment = Alignment.Center
                ) {
                    Text("V", color = TextWhite, fontWeight = FontWeight.Bold)
                }
                Spacer(Modifier.width(12.dp))
                Column {
                    Text("Vault", style = MaterialTheme.typography.headlineMedium, color = Ink)
                    Text("Choose a module", style = MaterialTheme.typography.bodySmall, color = InkSoft)
                }
            }
            IconButton(onClick = onSettings) {
                Icon(Icons.Filled.Settings, contentDescription = "Settings", tint = InkSoft)
            }
        }
        Spacer(Modifier.height(32.dp))
        ModuleTile(
            title = "Health Vault",
            subtitle = "Records, cards, care, and reminders",
            well = listOf(Color(0xFF1A332C), Color(0xFF123028)),
            iconTint = Sage,
            icon = { Icon(Icons.Filled.Favorite, contentDescription = null, tint = Sage, modifier = Modifier.size(26.dp)) },
            onClick = onHealth
        )
        Spacer(Modifier.height(14.dp))
        ModuleTile(
            title = "Password Vault",
            subtitle = "Logins, notes, cards, generator, and Send",
            well = listOf(Color(0xFF1A2744), Color(0xFF151B2E)),
            iconTint = Navy,
            icon = { Icon(Icons.Filled.Lock, contentDescription = null, tint = Navy, modifier = Modifier.size(26.dp)) },
            onClick = onPasswords
        )
    }
}

@Composable
private fun ModuleTile(
    title: String,
    subtitle: String,
    well: List<Color>,
    iconTint: Color,
    icon: @Composable () -> Unit,
    onClick: () -> Unit
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(22.dp))
            .background(White)
            .clickable(onClick = onClick)
            .padding(18.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            modifier = Modifier
                .size(56.dp)
                .clip(RoundedCornerShape(16.dp))
                .background(Brush.linearGradient(well)),
            contentAlignment = Alignment.Center
        ) { icon() }
        Spacer(Modifier.width(16.dp))
        Column(Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.titleLarge, color = Ink, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(4.dp))
            Text(subtitle, style = MaterialTheme.typography.bodySmall, color = InkSoft)
        }
        Icon(Icons.Filled.ChevronRight, contentDescription = null, tint = iconTint)
    }
}
