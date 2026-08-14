package com.rklab.healthvault.ui.screens.shell

import android.provider.Settings
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AccountBalanceWallet
import androidx.compose.material.icons.outlined.Apps
import androidx.compose.material.icons.outlined.ChevronRight
import androidx.compose.material.icons.outlined.Description
import androidx.compose.material.icons.outlined.Favorite
import androidx.compose.material.icons.outlined.Link
import androidx.compose.material.icons.outlined.Lock
import androidx.compose.material.icons.outlined.Person
import androidx.compose.material.icons.outlined.QrCodeScanner
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material.icons.outlined.SmartToy
import androidx.compose.material.icons.outlined.Star
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.viewmodel.compose.viewModel
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.theme.HubAmber
import com.rklab.healthvault.ui.theme.HubBg
import com.rklab.healthvault.ui.theme.HubDock
import com.rklab.healthvault.ui.theme.HubGlass
import com.rklab.healthvault.ui.theme.HubGlassHi
import com.rklab.healthvault.ui.theme.HubRose
import com.rklab.healthvault.ui.theme.HubSky
import com.rklab.healthvault.ui.theme.HubSlate
import com.rklab.healthvault.ui.theme.HubStroke
import com.rklab.healthvault.ui.theme.HubTeal
import com.rklab.healthvault.ui.theme.HubText
import com.rklab.healthvault.ui.theme.HubTextDim
import com.rklab.healthvault.ui.theme.HubTextFaint
import com.rklab.healthvault.ui.theme.HubViolet
import com.rklab.healthvault.ui.theme.MonoFont
import com.rklab.healthvault.ui.theme.VaultGold
import com.rklab.healthvault.util.ViewModelFactory

private val TileShape = RoundedCornerShape(24.dp)
private val HeroShape = RoundedCornerShape(28.dp)
private val IconShape = RoundedCornerShape(13.dp)
private val ArrowShape = RoundedCornerShape(9.dp)
private val SettingsShape = RoundedCornerShape(14.dp)
private val DockShape = RoundedCornerShape(24.dp)
private val ChipShape = RoundedCornerShape(20.dp)

@Composable
fun ModulePickerScreen(
    repository: HealthVaultRepository,
    onHealth: () -> Unit,
    onPasswords: () -> Unit,
    onFinance: () -> Unit,
    onAi: () -> Unit,
    onLocker: () -> Unit,
    onUrls: () -> Unit,
    onSettings: () -> Unit,
    onScanQr: () -> Unit = {},
    onVaultHealth: () -> Unit = {}
) {
    val viewModel: ModulePickerViewModel = viewModel(factory = ViewModelFactory(repository))
    val state by viewModel.state.collectAsState()
    val lifecycleOwner = LocalLifecycleOwner.current
    val reduceMotion = rememberReducedMotion()

    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) viewModel.refresh()
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(HubBg)
    ) {
        AmbientMesh(reduceMotion = reduceMotion)
        Column(
            modifier = Modifier
                .fillMaxSize()
                .statusBarsPadding()
                .verticalScroll(rememberScrollState())
                .padding(start = 20.dp, end = 20.dp, top = 8.dp, bottom = 120.dp)
        ) {
            HubTopBar(
                greeting = state.greeting,
                title = state.vaultTitle,
                onScanQr = onScanQr,
                onSettings = onSettings
            )
            Spacer(Modifier.height(22.dp))
            VaultHealthHero(
                state = state,
                onClick = onVaultHealth
            )
            Spacer(Modifier.height(16.dp))
            Text(
                "MODULES",
                color = VaultGold,
                fontFamily = MonoFont,
                fontSize = 10.5.sp,
                fontWeight = FontWeight.Medium,
                letterSpacing = 1.2.sp,
                modifier = Modifier.padding(start = 2.dp, bottom = 10.dp)
            )
            HubTile(
                glow = HubTeal,
                onClick = onHealth,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(156.dp),
                contentDescription = "Open Health Vault, ${state.recordCount} records"
            ) {
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.Top
                ) {
                    TileIcon(Icons.Outlined.Favorite, HubTeal)
                    Text(
                        "${state.recordCount} records",
                        color = HubTeal,
                        fontFamily = MonoFont,
                        fontSize = 9.sp,
                        modifier = Modifier
                            .clip(ChipShape)
                            .background(HubTeal.copy(alpha = 0.12f))
                            .border(1.dp, HubTeal.copy(alpha = 0.25f), ChipShape)
                            .padding(horizontal = 8.dp, vertical = 3.dp)
                    )
                }
                Column {
                    Text("Health Vault", color = HubText, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
                    Spacer(Modifier.height(3.dp))
                    Text(
                        state.healthSyncLabel,
                        color = HubTextDim,
                        fontSize = 11.5.sp,
                        lineHeight = 16.sp,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis
                    )
                }
                TileFooter(
                    stat = state.nextReminderLabel,
                    accentStat = reminderAccent(state.nextReminderLabel)
                )
            }
            Spacer(Modifier.height(12.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                HubTile(
                    glow = HubViolet,
                    onClick = onPasswords,
                    modifier = Modifier
                        .weight(1f)
                        .height(168.dp),
                    contentDescription = "Open Password Vault, ${state.loginCount} logins"
                ) {
                    TileIcon(Icons.Outlined.Lock, HubViolet)
                    Column {
                        Text("Password\nVault", color = HubText, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, lineHeight = 20.sp)
                        Spacer(Modifier.height(3.dp))
                        Text(
                            passwordDesc(state.loginCount, state.weakCount),
                            color = HubTextDim,
                            fontSize = 11.5.sp,
                            lineHeight = 16.sp,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis
                        )
                    }
                    TileFooter(stat = "Generator")
                }
                HubTile(
                    glow = HubRose,
                    onClick = onFinance,
                    modifier = Modifier
                        .weight(1f)
                        .height(168.dp),
                    contentDescription = "Open Money Manager, ${state.monthSpendLabel}"
                ) {
                    TileIcon(Icons.Outlined.AccountBalanceWallet, HubRose)
                    Column {
                        Text("Money\nManager", color = HubText, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, lineHeight = 20.sp)
                        Spacer(Modifier.height(3.dp))
                        Text(
                            state.monthSpendLabel,
                            color = HubTextDim,
                            fontSize = 11.5.sp,
                            lineHeight = 16.sp,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis
                        )
                    }
                    TileFooter(stat = state.financeFooter)
                }
            }
            Spacer(Modifier.height(12.dp))
            HubTile(
                glow = HubSlate,
                onClick = onAi,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(132.dp),
                contentDescription = "Open Ask AI"
            ) {
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.Top
                ) {
                    TileIcon(Icons.Outlined.SmartToy, HubSlate)
                    Text(
                        "Chat · Keys · Logs",
                        color = HubSlate,
                        fontFamily = MonoFont,
                        fontSize = 9.sp,
                        modifier = Modifier
                            .clip(ChipShape)
                            .background(HubSlate.copy(alpha = 0.12f))
                            .border(1.dp, HubSlate.copy(alpha = 0.25f), ChipShape)
                            .padding(horizontal = 8.dp, vertical = 3.dp)
                    )
                }
                Column {
                    Text("Ask AI", color = HubText, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
                    Spacer(Modifier.height(3.dp))
                    Text(
                        "Chat across vault modules, manage providers, and review usage",
                        color = HubTextDim,
                        fontSize = 11.5.sp,
                        lineHeight = 16.sp,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis
                    )
                }
            }
            Spacer(Modifier.height(12.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                HubTile(
                    glow = HubAmber,
                    onClick = onLocker,
                    modifier = Modifier
                        .weight(1f)
                        .height(156.dp),
                    contentDescription = "Open Document Vault, ${state.lockerCount} documents"
                ) {
                    TileIcon(Icons.Outlined.Description, HubAmber)
                    Column {
                        Text("Document\nVault", color = HubText, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, lineHeight = 20.sp)
                        Spacer(Modifier.height(3.dp))
                        Text(
                            if (state.lockerExpiring > 0) "${state.lockerExpiring} expiring soon"
                            else "${state.lockerCount} docs",
                            color = HubTextDim,
                            fontSize = 11.5.sp,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis
                        )
                    }
                    TileFooter(stat = "IDs & papers")
                }
                HubTile(
                    glow = HubSky,
                    onClick = onUrls,
                    modifier = Modifier
                        .weight(1f)
                        .height(156.dp),
                    contentDescription = "Open URL Vault, ${state.urlCount} links"
                ) {
                    TileIcon(Icons.Outlined.Link, HubSky)
                    Column {
                        Text("URL\nVault", color = HubText, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, lineHeight = 20.sp)
                        Spacer(Modifier.height(3.dp))
                        Text(
                            if (state.urlCount == 0) "Save links & previews"
                            else "${state.urlCount} links",
                            color = HubTextDim,
                            fontSize = 11.5.sp,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis
                        )
                    }
                    TileFooter(stat = if (state.urlFavorites > 0) "${state.urlFavorites} favorites" else "Categories & tags")
                }
            }
        }
        HubDock(
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .navigationBarsPadding()
                .padding(bottom = 22.dp),
            onHome = {},
            onHealth = onVaultHealth,
            onProfile = onSettings
        )
    }
}

@Composable
private fun HubTopBar(greeting: String, title: String, onScanQr: () -> Unit, onSettings: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(top = 8.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(Modifier.padding(start = 2.dp)) {
            Text(
                greeting,
                color = VaultGold,
                fontFamily = MonoFont,
                fontSize = 10.5.sp,
                letterSpacing = 1.4.sp,
                fontWeight = FontWeight.Medium
            )
            Spacer(Modifier.height(4.dp))
            Text(
                title,
                color = HubText,
                fontSize = 22.sp,
                fontWeight = FontWeight.SemiBold,
                letterSpacing = (-0.2).sp
            )
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Box(
                modifier = Modifier
                    .size(48.dp)
                    .clip(SettingsShape)
                    .background(HubGlass)
                    .border(1.dp, HubStroke, SettingsShape)
                    .clickable(role = Role.Button, onClick = onScanQr)
                    .semantics { contentDescription = "Scan web login QR" },
                contentAlignment = Alignment.Center
            ) {
                Icon(Icons.Outlined.QrCodeScanner, contentDescription = null, tint = HubTextDim, modifier = Modifier.size(18.dp))
            }
            Box(
                modifier = Modifier
                    .size(48.dp)
                    .clip(SettingsShape)
                    .background(HubGlass)
                    .border(1.dp, HubStroke, SettingsShape)
                    .clickable(role = Role.Button, onClick = onSettings)
                    .semantics { contentDescription = "Settings" },
                contentAlignment = Alignment.Center
            ) {
                Icon(Icons.Outlined.Settings, contentDescription = null, tint = HubTextDim, modifier = Modifier.size(18.dp))
            }
        }
    }
}

@Composable
private fun VaultHealthHero(state: HubUiState, onClick: () -> Unit) {
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val scale by animateFloatAsState(if (pressed) 0.98f else 1f, tween(150), label = "hero")
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .graphicsLayer { scaleX = scale; scaleY = scale }
            .clip(HeroShape)
            .background(
                Brush.linearGradient(
                    colors = listOf(HubViolet.copy(alpha = 0.14f), Color.White.copy(alpha = 0.03f))
                )
            )
            .border(1.dp, HubStroke, HeroShape)
            .clickable(
                interactionSource = interaction,
                indication = null,
                role = Role.Button,
                onClick = onClick
            )
            .semantics {
                contentDescription = "Vault health ${state.score}, ${state.scoreLabel}. ${state.heroSubtitle}"
            }
            .padding(22.dp)
    ) {
        Box(
            modifier = Modifier
                .align(Alignment.TopEnd)
                .offset(x = 36.dp, y = (-48).dp)
                .size(180.dp)
                .background(
                    Brush.radialGradient(listOf(HubViolet.copy(alpha = 0.35f), Color.Transparent))
                )
        )
        Row(verticalAlignment = Alignment.CenterVertically) {
            ScoreRing(score = state.score)
            Spacer(Modifier.width(18.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    "Vault health: ${state.scoreLabel}",
                    color = HubText,
                    fontSize = 16.sp,
                    fontWeight = FontWeight.SemiBold
                )
                Spacer(Modifier.height(4.dp))
                Text(
                    state.heroSubtitle,
                    color = HubTextDim,
                    fontSize = 12.sp,
                    lineHeight = 17.sp,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis
                )
                Spacer(Modifier.height(10.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    StatusChip(
                        label = if (state.online) "Pi online" else "Pi offline",
                        dot = if (state.online) HubTeal else HubRose
                    )
                    if (state.alertCount > 0) {
                        StatusChip(
                            label = "${state.alertCount} alert${if (state.alertCount == 1) "" else "s"}",
                            dot = HubAmber
                        )
                    } else {
                        StatusChip(label = "all clear", dot = HubTeal)
                    }
                }
            }
        }
    }
}

@Composable
private fun ScoreRing(score: Int) {
    Box(modifier = Modifier.size(76.dp), contentAlignment = Alignment.Center) {
        Canvas(Modifier.fillMaxSize()) {
            val stroke = 6.dp.toPx()
            val glow = 10.dp.toPx()
            drawCircle(
                color = Color.White.copy(alpha = 0.08f),
                style = Stroke(width = stroke)
            )
            val sweep = 360f * (score.coerceIn(0, 100) / 100f)
            drawArc(
                color = HubTeal.copy(alpha = 0.35f),
                startAngle = -90f,
                sweepAngle = sweep,
                useCenter = false,
                style = Stroke(width = glow, cap = StrokeCap.Round)
            )
            drawArc(
                color = HubTeal,
                startAngle = -90f,
                sweepAngle = sweep,
                useCenter = false,
                style = Stroke(width = stroke, cap = StrokeCap.Round)
            )
        }
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(score.toString(), color = HubText, fontSize = 18.sp, fontWeight = FontWeight.Bold, letterSpacing = (-0.3).sp)
            Text("score", color = HubTextFaint, fontSize = 9.sp, modifier = Modifier.offset(y = (-2).dp))
        }
    }
}

@Composable
private fun StatusChip(label: String, dot: Color) {
    Row(
        modifier = Modifier
            .clip(ChipShape)
            .background(Color.White.copy(alpha = 0.05f))
            .border(1.dp, HubStroke, ChipShape)
            .padding(horizontal = 7.dp, vertical = 3.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(Modifier.size(5.dp).clip(CircleShape).background(dot))
        Spacer(Modifier.width(4.dp))
        Text(label, color = HubTextDim, fontFamily = MonoFont, fontSize = 9.sp)
    }
}

@Composable
private fun HubTile(
    glow: Color,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    contentDescription: String,
    content: @Composable androidx.compose.foundation.layout.ColumnScope.() -> Unit
) {
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val scale by animateFloatAsState(if (pressed) 0.97f else 1f, tween(150), label = "tile")
    Box(
        modifier = modifier
            .graphicsLayer { scaleX = scale; scaleY = scale }
            .clip(TileShape)
            .background(if (pressed) HubGlassHi else HubGlass)
            .border(1.dp, HubStroke, TileShape)
            .clickable(
                interactionSource = interaction,
                indication = null,
                role = Role.Button,
                onClick = onClick
            )
            .semantics { this.contentDescription = contentDescription }
    ) {
        Box(
            modifier = Modifier
                .align(Alignment.TopEnd)
                .offset(x = 20.dp, y = (-30).dp)
                .size(120.dp)
                .background(Brush.radialGradient(listOf(glow.copy(alpha = 0.50f), Color.Transparent)))
        )
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(18.dp),
            verticalArrangement = Arrangement.SpaceBetween,
            content = content
        )
    }
}

@Composable
private fun TileIcon(icon: ImageVector, tint: Color) {
    Box(
        modifier = Modifier
            .size(44.dp)
            .clip(IconShape)
            .background(tint.copy(alpha = 0.14f))
            .border(1.dp, HubStroke, IconShape),
        contentAlignment = Alignment.Center
    ) {
        Icon(icon, contentDescription = null, tint = tint, modifier = Modifier.size(20.dp))
    }
}

@Composable
private fun TileFooter(stat: String, accentStat: String? = null) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        if (accentStat != null && stat.contains(accentStat)) {
            val prefix = stat.substringBefore(accentStat).trimEnd()
            Row {
                Text("$prefix ", color = HubTextFaint, fontFamily = MonoFont, fontSize = 10.5.sp)
                Text(accentStat, color = HubText, fontFamily = MonoFont, fontSize = 10.5.sp, fontWeight = FontWeight.Medium)
            }
        } else {
            Text(stat, color = HubTextFaint, fontFamily = MonoFont, fontSize = 10.5.sp)
        }
        Box(
            modifier = Modifier
                .size(26.dp)
                .clip(ArrowShape)
                .background(Color.White.copy(alpha = 0.06f)),
            contentAlignment = Alignment.Center
        ) {
            Icon(Icons.Outlined.ChevronRight, contentDescription = null, tint = HubTextDim, modifier = Modifier.size(14.dp))
        }
    }
}

@Composable
private fun HubDock(
    modifier: Modifier = Modifier,
    onHome: () -> Unit,
    onHealth: () -> Unit,
    onProfile: () -> Unit
) {
    Row(
        modifier = modifier
            .clip(DockShape)
            .background(HubDock)
            .border(1.dp, Color.White.copy(alpha = 0.10f), DockShape)
            .padding(horizontal = 22.dp, vertical = 6.dp),
        horizontalArrangement = Arrangement.spacedBy(34.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        DockIcon(Icons.Outlined.Apps, "Modules", selected = true, onClick = onHome)
        DockIcon(Icons.Outlined.Star, "Vault health", selected = false, onClick = onHealth)
        DockIcon(Icons.Outlined.Person, "Settings", selected = false, onClick = onProfile)
    }
}

@Composable
private fun DockIcon(icon: ImageVector, label: String, selected: Boolean, onClick: () -> Unit) {
    Box(
        modifier = Modifier
            .size(48.dp)
            .clip(RoundedCornerShape(14.dp))
            .clickable(role = Role.Button, onClick = onClick)
            .semantics { contentDescription = label },
        contentAlignment = Alignment.Center
    ) {
        Icon(
            icon,
            contentDescription = null,
            tint = if (selected) HubText else HubTextFaint,
            modifier = Modifier.size(19.dp)
        )
    }
}

@Composable
private fun AmbientMesh(reduceMotion: Boolean) {
    val transition = rememberInfiniteTransition(label = "mesh")
    val d1 by transition.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(16_000, easing = FastOutSlowInEasing), RepeatMode.Reverse),
        label = "d1"
    )
    val d2 by transition.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(20_000, easing = FastOutSlowInEasing), RepeatMode.Reverse),
        label = "d2"
    )
    val d3 by transition.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(18_000, easing = FastOutSlowInEasing), RepeatMode.Reverse),
        label = "d3"
    )
    val drift1 = if (reduceMotion) 0f else d1
    val drift2 = if (reduceMotion) 0.4f else d2
    val drift3 = if (reduceMotion) 0.2f else d3

    Canvas(Modifier.fillMaxSize()) {
        val r1 = 160.dp.toPx()
        val r2 = 140.dp.toPx()
        val r3 = 150.dp.toPx()
        val c1 = Offset(-50.dp.toPx() + 30.dp.toPx() * drift1, -70.dp.toPx() + 25.dp.toPx() * drift1)
        val c2 = Offset(size.width + 40.dp.toPx() - 25.dp.toPx() * drift2, 160.dp.toPx() + 20.dp.toPx() * drift2)
        val c3 = Offset(40.dp.toPx() + 20.dp.toPx() * drift3, size.height - 40.dp.toPx() - 20.dp.toPx() * drift3)
        drawCircle(Brush.radialGradient(listOf(HubViolet.copy(alpha = 0.45f), Color.Transparent), c1, r1), r1, c1)
        drawCircle(Brush.radialGradient(listOf(HubTeal.copy(alpha = 0.28f), Color.Transparent), c2, r2), r2, c2)
        drawCircle(Brush.radialGradient(listOf(HubRose.copy(alpha = 0.24f), Color.Transparent), c3, r3), r3, c3)
    }
}

@Composable
private fun rememberReducedMotion(): Boolean {
    val context = LocalContext.current
    return remember {
        runCatching {
            Settings.Global.getFloat(context.contentResolver, Settings.Global.ANIMATOR_DURATION_SCALE, 1f) == 0f
        }.getOrDefault(false)
    }
}

private fun passwordDesc(logins: Int, weak: Int): String = when {
    logins == 0 -> "No logins yet"
    weak == 0 -> "$logins logins · all strong"
    else -> "$logins logins · $weak weak"
}

private fun reminderAccent(label: String): String? = when {
    label.startsWith("Next reminder ") -> label.removePrefix("Next reminder ").trim()
    else -> null
}
