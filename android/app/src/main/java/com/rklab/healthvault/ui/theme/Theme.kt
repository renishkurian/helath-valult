package com.rklab.healthvault.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val HealthVaultDark = darkColorScheme(
    primary = VaultGold,
    onPrimary = TextDark,
    secondary = Sage,
    onSecondary = TextDark,
    background = DarkBackground,
    onBackground = TextWhite,
    surface = CardSurface,
    onSurface = TextWhite,
    surfaceVariant = CardSurfaceRaised,
    onSurfaceVariant = TextGray,
    outline = CardOutline,
    error = StampRed,
    primaryContainer = VaultGoldSoft,
    onPrimaryContainer = VaultGold,
)

private val HealthVaultLight = lightColorScheme(
    primary = VaultGoldDeep,
    onPrimary = Color.White,
    secondary = Color(0xFF0F9F6E),
    onSecondary = Color.White,
    background = Color(0xFFF4F6FA),
    onBackground = Color(0xFF111827),
    surface = Color(0xFFFFFFFF),
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
