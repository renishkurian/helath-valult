package com.rklab.healthvault.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val HealthVaultDark = darkColorScheme(
    primary = VaultTeal,
    onPrimary = TextDark,
    secondary = VaultBrass,
    onSecondary = Color(0xFF1C1406),
    background = DarkBackground,
    onBackground = TextWhite,
    surface = CardSurface,
    onSurface = TextWhite,
    surfaceVariant = CardSurfaceRaised,
    onSurfaceVariant = TextGray,
    outline = CardOutline,
    error = StampRed,
    primaryContainer = VaultTealSoft,
    onPrimaryContainer = VaultTeal,
    secondaryContainer = VaultBrassSoft,
    onSecondaryContainer = VaultBrass,
)

private val HealthVaultLight = lightColorScheme(
    primary = VaultTealDeep,
    onPrimary = Color.White,
    secondary = VaultBrassDeep,
    onSecondary = Color.White,
    background = Color(0xFFF4F6FA),
    onBackground = Color(0xFF111827),
    surface = Color.White,
    onSurface = Color(0xFF111827),
    surfaceVariant = Color(0xFFEEF2F7),
    onSurfaceVariant = Color(0xFF5B6577),
    outline = Color(0xFFD7DEE8),
    error = StampRed,
)

@Composable
fun HealthVaultTheme(
    darkTheme: Boolean = true,
    largeText: Boolean = false,
    content: @Composable () -> Unit
) {
    val typography = if (largeText) HealthVaultTypographyLarge else HealthVaultTypography
    MaterialTheme(
        colorScheme = if (darkTheme) HealthVaultDark else HealthVaultLight,
        typography = typography,
        content = content
    )
}
