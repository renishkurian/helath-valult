package com.rklab.healthvault.ui.theme

import androidx.compose.material3.Typography
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

// Using system font families out of the box so the project builds with zero
// extra assets. For exact parity with the original design mockup (Roboto
// Slab / IBM Plex Sans / IBM Plex Mono), download the .ttf files and drop
// them into res/font/, then point these at Font(R.font.xxx) instead —
// see README "Fonts" section for the exact steps and file names expected.
val DisplayFont = FontFamily.Serif      // stands in for Roboto Slab
val BodyFont = FontFamily.SansSerif     // stands in for IBM Plex Sans
val MonoFont = FontFamily.Monospace     // stands in for IBM Plex Mono

val HealthVaultTypography = Typography(
    headlineLarge = TextStyle(fontFamily = DisplayFont, fontWeight = FontWeight.Bold, fontSize = 26.sp, lineHeight = 30.sp),
    headlineMedium = TextStyle(fontFamily = DisplayFont, fontWeight = FontWeight.Bold, fontSize = 20.sp, lineHeight = 24.sp),
    titleLarge = TextStyle(fontFamily = DisplayFont, fontWeight = FontWeight.SemiBold, fontSize = 18.sp, lineHeight = 22.sp),
    titleMedium = TextStyle(fontFamily = BodyFont, fontWeight = FontWeight.SemiBold, fontSize = 15.sp, lineHeight = 20.sp),
    bodyLarge = TextStyle(fontFamily = BodyFont, fontWeight = FontWeight.Normal, fontSize = 15.sp, lineHeight = 21.sp),
    bodyMedium = TextStyle(fontFamily = BodyFont, fontWeight = FontWeight.Normal, fontSize = 13.5.sp, lineHeight = 19.sp),
    bodySmall = TextStyle(fontFamily = BodyFont, fontWeight = FontWeight.Normal, fontSize = 12.sp, lineHeight = 16.sp),
    labelLarge = TextStyle(fontFamily = MonoFont, fontWeight = FontWeight.Medium, fontSize = 12.sp, letterSpacing = 0.5.sp),
    labelMedium = TextStyle(fontFamily = MonoFont, fontWeight = FontWeight.Normal, fontSize = 11.sp, letterSpacing = 1.2.sp),
    labelSmall = TextStyle(fontFamily = MonoFont, fontWeight = FontWeight.Normal, fontSize = 9.5.sp, letterSpacing = 0.8.sp),
)
