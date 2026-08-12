package com.rklab.healthvault.ui.theme

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Brush

// Dark Theme Colors
val DarkBackground = Color(0xFF0F121E)
val CardSurface = Color(0xFF1D2235)
val CardOutline = Color(0xFF2C324B)

// Ink (Text)
val TextWhite = Color(0xFFFFFFFF)
val TextGray = Color(0xFF8A96AC)
val TextDark = Color(0xFF21281F) // For light buttons if any

// Branding / Gradients
val PurpleAccent = Color(0xFF8A6A9C)
val BlueAccent = Color(0xFF5B6CFA)
val GradientPrimary = Brush.linearGradient(
    colors = listOf(Color(0xFF6B83FF), Color(0xFFA57DFF))
)

// Legacy mappings for compatibility (can keep these mapped to new colors so existing screens don't break immediately)
val Paper = DarkBackground
val PaperDeep = CardSurface
val LineColor = CardOutline
val White = CardSurface
val Ink = TextWhite
val InkSoft = TextGray
val Navy = Color(0xFF5B6CFA) // Blueish
val NavyDeep = Color(0xFF1E313F)
val StampRed = Color(0xFFD25050)
val Sage = Color(0xFF32C68A) // Neon green for verified
val SageBg = Color(0xFF1A332C)
val Mustard = Color(0xFFFFB347)
val MustardBg = Color(0xFF332814)

// Document category colors
val CatHospitalCard = Color(0xFF3A589F)
val CatPrescription = Color(0xFF389B73)
val CatLabReport = Color(0xFF7A4AA6)
val CatInsurance = Mustard
val CatVaccination = Sage
val CatBill = StampRed
val CatMedicine = Mustard
val CatOther = TextGray
