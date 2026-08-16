package com.rklab.healthvault.ui.screens.lock

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Fingerprint
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.rklab.healthvault.ui.theme.*

@Composable
fun PinLockScreen(error: Boolean, onSubmit: (String) -> Unit) {
    var pin by remember { mutableStateOf("") }
    val pulse = rememberInfiniteTransition(label = "unlock-pulse")
    val scale by pulse.animateFloat(
        initialValue = 1f,
        targetValue = 1.04f,
        animationSpec = infiniteRepeatable(tween(1400, easing = LinearEasing), RepeatMode.Reverse),
        label = "ring-scale"
    )
    val ringAlpha by pulse.animateFloat(
        initialValue = 0.35f,
        targetValue = 0.75f,
        animationSpec = infiniteRepeatable(tween(1400, easing = LinearEasing), RepeatMode.Reverse),
        label = "ring-alpha"
    )

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(DarkBackground)
            .padding(horizontal = 28.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(
            "HEALTH VAULT",
            style = MaterialTheme.typography.labelMedium.copy(
                fontFamily = FontFamily.Monospace,
                letterSpacing = 4.sp,
                fontWeight = FontWeight.Medium
            ),
            color = TextMuted
        )
        Spacer(Modifier.height(6.dp))
        Text(
            "Private. Local. Yours.",
            style = MaterialTheme.typography.bodyMedium.copy(fontStyle = FontStyle.Italic),
            color = TextGray
        )

        Spacer(Modifier.height(36.dp))

        Box(contentAlignment = Alignment.Center, modifier = Modifier.size(150.dp)) {
            Canvas(modifier = Modifier.fillMaxSize().scale(scale)) {
                drawCircle(
                    color = VaultTeal.copy(alpha = ringAlpha * 0.45f),
                    radius = size.minDimension / 2f - 4.dp.toPx(),
                    style = Stroke(width = 1.5.dp.toPx())
                )
                drawCircle(
                    color = VaultTeal.copy(alpha = ringAlpha * 0.7f),
                    radius = size.minDimension / 2f - 18.dp.toPx(),
                    style = Stroke(width = 1.5.dp.toPx())
                )
            }
            Box(
                modifier = Modifier
                    .size(88.dp)
                    .background(CardSurface, CircleShape)
                    .border(1.dp, CardOutline, CircleShape),
                contentAlignment = Alignment.Center
            ) {
                Icon(
                    Icons.Filled.Fingerprint,
                    contentDescription = "Unlock",
                    tint = VaultTeal,
                    modifier = Modifier.size(36.dp)
                )
            }
        }

        Spacer(Modifier.height(22.dp))
        EcgDivider(modifier = Modifier.fillMaxWidth(0.75f).height(20.dp))

        Spacer(Modifier.height(22.dp))
        Text("Touch to unlock", style = MaterialTheme.typography.titleMedium, color = TextWhite)
        Text(
            "or enter your PIN",
            style = MaterialTheme.typography.bodySmall,
            color = TextMuted,
            modifier = Modifier.padding(top = 4.dp)
        )

        Spacer(Modifier.height(20.dp))
        OutlinedTextField(
            value = pin,
            onValueChange = { if (it.length <= 8) pin = it.filter(Char::isDigit) },
            label = { Text("PIN") },
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
            isError = error,
            singleLine = true,
            colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = VaultTeal,
                cursorColor = VaultTeal,
                focusedLabelColor = VaultTeal
            )
        )
        if (error) {
            Text("Wrong PIN", color = StampRed, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 8.dp))
        }

        Spacer(Modifier.height(16.dp))
        Button(
            onClick = { onSubmit(pin) },
            enabled = pin.length >= 4,
            modifier = Modifier.fillMaxWidth().height(52.dp),
            shape = androidx.compose.foundation.shape.RoundedCornerShape(16.dp),
            colors = ButtonDefaults.buttonColors(containerColor = VaultTeal, contentColor = TextDark)
        ) {
            Text("Unlock", fontWeight = FontWeight.SemiBold)
        }
    }
}

@Composable
fun EcgDivider(modifier: Modifier = Modifier, color: androidx.compose.ui.graphics.Color = VaultTeal) {
    Canvas(modifier = modifier) {
        val path = Path().apply {
            val mid = size.height / 2f
            moveTo(0f, mid)
            lineTo(size.width * 0.27f, mid)
            lineTo(size.width * 0.32f, size.height * 0.15f)
            lineTo(size.width * 0.37f, size.height * 0.85f)
            lineTo(size.width * 0.42f, mid)
            lineTo(size.width * 0.62f, mid)
            lineTo(size.width * 0.66f, size.height * 0.25f)
            lineTo(size.width * 0.70f, mid)
            lineTo(size.width, mid)
        }
        drawPath(
            path = path,
            color = color.copy(alpha = 0.7f),
            style = Stroke(width = 2.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round)
        )
    }
}
