package com.rklab.healthvault.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.rklab.healthvault.ui.screens.lock.EcgDivider
import com.rklab.healthvault.ui.theme.*
import kotlin.math.min

@Composable
fun ExpiryPulseCard(
    count: Int,
    subtitle: String,
    modifier: Modifier = Modifier,
    progress: Float = 0.72f
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .background(CardSurface, RoundedCornerShape(20.dp))
            .border(1.dp, CardOutline, RoundedCornerShape(20.dp))
            .padding(16.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(modifier = Modifier.size(76.dp), contentAlignment = Alignment.Center) {
                Canvas(modifier = Modifier.fillMaxSize()) {
                    val stroke = 6.dp.toPx()
                    val r = (min(size.width, size.height) - stroke) / 2f
                    val topLeft = Offset(size.width / 2f - r, size.height / 2f - r)
                    val arcSize = Size(r * 2, r * 2)
                    drawArc(
                        color = CardSurfaceHigh,
                        startAngle = -90f,
                        sweepAngle = 360f,
                        useCenter = false,
                        topLeft = topLeft,
                        size = arcSize,
                        style = Stroke(width = stroke, cap = StrokeCap.Round)
                    )
                    drawArc(
                        color = VaultBrass,
                        startAngle = -90f,
                        sweepAngle = 360f * progress.coerceIn(0.05f, 1f),
                        useCenter = false,
                        topLeft = topLeft,
                        size = arcSize,
                        style = Stroke(width = stroke, cap = StrokeCap.Round)
                    )
                }
            }
            Spacer(Modifier.width(16.dp))
            Column {
                Text(
                    "$count",
                    style = MaterialTheme.typography.headlineLarge.copy(
                        fontWeight = FontWeight.SemiBold,
                        fontSize = 34.sp,
                        lineHeight = 36.sp
                    ),
                    color = TextWhite
                )
                Text(subtitle, style = MaterialTheme.typography.bodySmall, color = TextGray)
            }
        }
        Spacer(Modifier.height(10.dp))
        EcgDivider(modifier = Modifier.fillMaxWidth().height(18.dp), color = VaultTeal)
    }
}

@Composable
fun ModuleTile(
    count: String,
    label: String,
    iconBg: Color,
    modifier: Modifier = Modifier,
    onClick: (() -> Unit)? = null,
    icon: @Composable () -> Unit
) {
    val shape = RoundedCornerShape(18.dp)
    Column(
        modifier = modifier
            .background(CardSurface, shape)
            .border(1.dp, CardOutline, shape)
            .then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier)
            .padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(20.dp)
    ) {
        Box(
            modifier = Modifier
                .size(34.dp)
                .background(iconBg, RoundedCornerShape(10.dp)),
            contentAlignment = Alignment.Center
        ) { icon() }
        Column {
            Text(
                count,
                style = MaterialTheme.typography.titleLarge.copy(fontWeight = FontWeight.SemiBold),
                color = TextWhite
            )
            Text(label, style = MaterialTheme.typography.labelSmall, color = TextGray)
        }
    }
}
