package com.rklab.healthvault.ui.theme

import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color

/**
 * Clinical Health Vault palette — matches mobile mockup:
 * obsidian surfaces, teal monitor-pulse primary, brass for time-sensitive.
 */
val DarkBackground = Color(0xFF0C0F14)
val CardSurface = Color(0xFF151923)
val CardSurfaceRaised = Color(0xFF1D2330)
val CardSurfaceHigh = Color(0xFF262E3D)
val CardOutline = Color(0x14FFFFFF)
val CardOutlineSoft = Color(0x0DFFFFFF)

val TextWhite = Color(0xFFEDEFF4)
val TextGray = Color(0xFF9AA2B4)
val TextMuted = Color(0xFF5C6478)
val TextDark = Color(0xFF06231D)

/** Teal pulse — primary CTA / active nav. */
val VaultTeal = Color(0xFF3FE0C5)
val VaultTealDeep = Color(0xFF25AE99)
val VaultTealSoft = Color(0x243FE0C5)
val VaultTealLine = Color(0x523FE0C5)

/** Brass — expiry, lab trends, time-sensitive. */
val VaultBrass = Color(0xFFD4A657)
val VaultBrassDeep = Color(0xFFC29B54)
val VaultBrassSoft = Color(0x24D4A657)
val VaultBrassLine = Color(0x52D4A657)

/** Legacy aliases — call sites still say VaultGold / Navy. */
val VaultGold = VaultBrass
val VaultGoldDeep = VaultBrassDeep
val VaultGoldSoft = VaultBrassSoft
val VaultGoldLine = VaultBrassLine

/** Primary action color (teal). */
val Navy = VaultTeal
val NavyDeep = Color(0xFF080B12)

val GradientPrimary = Brush.linearGradient(
    colors = listOf(Color(0xFF5EEAD4), VaultTeal, VaultTealDeep)
)
val GradientBrass = Brush.linearGradient(
    colors = listOf(Color(0xFFE8C87A), VaultBrass, VaultBrassDeep)
)

val Paper = DarkBackground
val PaperDeep = CardSurfaceRaised
val LineColor = CardOutline
val White = CardSurface
val Ink = TextWhite
val InkSoft = TextGray

val StampRed = Color(0xFFE8615C)
val StampRedSoft = Color(0x24E8615C)
val Sage = Color(0xFF6FCF8E)
val SageBg = Color(0x216FCF8E)
val Mustard = VaultBrass
val MustardBg = VaultBrassSoft
val PurpleAccent = Color(0xFF9C8CF0)
val BlueAccent = Color(0xFF5FA8D3)
val PinkAccent = Color(0xFFE091D0)

val CatHospitalCard = VaultTeal
val CatPrescription = PurpleAccent
val CatLabReport = VaultBrass
val CatInsurance = BlueAccent
val CatVaccination = Sage
val CatBill = StampRed
val CatMedicine = PurpleAccent
val CatOther = TextGray

/** Hub / module-picker — same clinical base. */
val HubBg = DarkBackground
val HubGlass = Color(0x0BFFFFFF)
val HubGlassHi = Color(0x14FFFFFF)
val HubStroke = CardOutline
val HubText = TextWhite
val HubTextDim = TextGray
val HubTextFaint = TextMuted
val HubViolet = PurpleAccent
val HubTeal = VaultTeal
val HubRose = StampRed
val HubAmber = VaultBrass
val HubSky = BlueAccent
val HubSlate = TextGray
val HubMint = Color(0xFF5EEAD4)
val HubDock = Color(0xE6151923)
