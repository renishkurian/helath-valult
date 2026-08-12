package com.rklab.healthvault.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable

private val HealthVaultColors = lightColorScheme(
    primary = Navy,
    onPrimary = White,
    secondary = Sage,
    onSecondary = White,
    background = Paper,
    onBackground = Ink,
    surface = White,
    onSurface = Ink,
    surfaceVariant = PaperDeep,
    onSurfaceVariant = InkSoft,
    outline = LineColor,
    error = StampRed,
)

@Composable
fun HealthVaultTheme(
    darkTheme: Boolean = isSystemInDarkTheme(), // dark theme intentionally not designed yet — see README
    content: @Composable () -> Unit
) {
    MaterialTheme(
        colorScheme = HealthVaultColors,
        typography = HealthVaultTypography,
        content = content
    )
}
