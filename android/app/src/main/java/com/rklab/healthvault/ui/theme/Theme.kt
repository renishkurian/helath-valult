package com.rklab.healthvault.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable

private val HealthVaultColors = darkColorScheme(
    primary = Navy,
    onPrimary = TextWhite,
    secondary = Sage,
    onSecondary = TextWhite,
    background = DarkBackground,
    onBackground = TextWhite,
    surface = CardSurface,
    onSurface = TextWhite,
    surfaceVariant = CardSurface,
    onSurfaceVariant = TextGray,
    outline = CardOutline,
    error = StampRed,
)

@Composable
fun HealthVaultTheme(
    darkTheme: Boolean = true, // Force dark theme for the new UI overhaul

    content: @Composable () -> Unit
) {
    MaterialTheme(
        colorScheme = HealthVaultColors,
        typography = HealthVaultTypography,
        content = content
    )
}
