package com.rklab.healthvault.ui.theme

import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color

/** Surfaces — aligned with backend vault.css (--v-bg / --v-surface). */
val DarkBackground = Color(0xFF0A0C11)
val CardSurface = Color(0xFF13161E)
val CardSurfaceRaised = Color(0xFF181C26)
val CardOutline = Color(0x14FFFFFF)

val TextWhite = Color(0xFFEEF1F6)
val TextGray = Color(0xFFA8B0BF)
val TextDark = Color(0xFF18130A)

/** Brand gold — primary CTA on the website. */
val VaultGold = Color(0xFFD9B978)
val VaultGoldDeep = Color(0xFFC29B54)
val VaultGoldSoft = Color(0x21D9B978)
val VaultGoldLine = Color(0x52D9B978)
val GradientPrimary = Brush.linearGradient(
    colors = listOf(Color(0xFFEBD6A6), VaultGold, VaultGoldDeep)
)

val Paper = DarkBackground
val PaperDeep = CardSurfaceRaised
val LineColor = CardOutline
val White = CardSurface
val Ink = TextWhite
val InkSoft = TextGray
/** Primary action color (gold), kept as Navy for existing call sites. */
val Navy = VaultGold
val NavyDeep = Color(0xFF080B12)
val StampRed = Color(0xFFFF8095)
val Sage = Color(0xFF4ADE9B)
val SageBg = Color(0x214ADE9B)
val Mustard = Color(0xFFF0C36A)
val MustardBg = Color(0x24F0C36A)
val PurpleAccent = Color(0xFFC0A8FF)
val BlueAccent = Color(0xFF7FA6FF)

val CatHospitalCard = BlueAccent
val CatPrescription = Sage
val CatLabReport = PurpleAccent
val CatInsurance = Mustard
val CatVaccination = Sage
val CatBill = StampRed
val CatMedicine = Mustard
val CatOther = TextGray

/** Hub / module-picker tokens — match vault redesign glass hub. */
val HubBg = Color(0xFF060714)
val HubGlass = Color(0x0BFFFFFF)
val HubGlassHi = Color(0x14FFFFFF)
val HubStroke = Color(0x17FFFFFF)
val HubText = Color(0xFFF4F5FB)
val HubTextDim = Color(0xFF9AA1B8)
val HubTextFaint = Color(0xFF5C6379)
val HubViolet = Color(0xFF8B7CF7)
val HubTeal = Color(0xFF2DD9B8)
val HubRose = Color(0xFFF2618A)
val HubAmber = Color(0xFFF5B862)
val HubSky = Color(0xFF38BDF8)
val HubDock = Color(0xE0141620)
