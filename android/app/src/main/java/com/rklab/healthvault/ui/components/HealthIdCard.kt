package com.rklab.healthvault.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.rklab.healthvault.data.model.CardOut
import com.rklab.healthvault.ui.theme.*

@Composable
fun HealthIdCard(
    card: CardOut,
    patientName: String,
    onShare: () -> Unit = {},
    onClick: () -> Unit = {},
    modifier: Modifier = Modifier
) {
    val initials = patientName.split(" ").take(2).mapNotNull { it.firstOrNull()?.uppercaseChar() }.joinToString("")
    val hospitalStr = card.hospital_name.uppercase()

    Box(
        modifier = modifier
            .clip(RoundedCornerShape(18.dp))
            .background(CardSurface)
            .border(1.dp, CardOutline, RoundedCornerShape(18.dp))
            .padding(20.dp)
    ) {
        Column {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.Top
            ) {
                Column {
                    Text(
                        hospitalStr,
                        style = MaterialTheme.typography.labelSmall,
                        color = TextGray,
                        letterSpacing = 1.5.sp
                    )
                    Spacer(Modifier.height(4.dp))
                    Text("Patient Health ID", style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold), color = TextWhite)
                }
                
                // Verified Badge
                Row(
                    modifier = Modifier
                        .clip(RoundedCornerShape(12.dp))
                        .border(1.dp, Sage.copy(alpha = 0.5f), RoundedCornerShape(12.dp))
                        .padding(horizontal = 8.dp, vertical = 4.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Box(modifier = Modifier.size(6.dp).clip(CircleShape).background(Sage))
                    Spacer(Modifier.width(6.dp))
                    Text("VERIFIED", style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.Bold), color = Sage)
                }
            }

            Spacer(Modifier.height(24.dp))

            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    modifier = Modifier
                        .size(56.dp)
                        .clip(RoundedCornerShape(14.dp))
                        .background(GradientPrimary),
                    contentAlignment = Alignment.Center
                ) {
                    Text(initials, style = MaterialTheme.typography.titleLarge.copy(fontWeight = FontWeight.Bold), color = TextWhite)
                }
                Spacer(Modifier.width(16.dp))
                Column {
                    Text(patientName, style = MaterialTheme.typography.titleLarge.copy(fontWeight = FontWeight.Bold), color = TextWhite)
                    Spacer(Modifier.height(4.dp))
                    Text(
                        "ID ${card.patient_id ?: "—"}",
                        style = MaterialTheme.typography.labelLarge,
                        color = TextGray
                    )
                }
            }

            Spacer(Modifier.height(24.dp))

            // Decorative heartbeat line
            Canvas(modifier = Modifier.fillMaxWidth().height(24.dp)) {
                val path = Path().apply {
                    moveTo(0f, size.height / 2f)
                    lineTo(size.width * 0.4f, size.height / 2f)
                    lineTo(size.width * 0.45f, 0f)
                    lineTo(size.width * 0.5f, size.height)
                    lineTo(size.width * 0.55f, size.height / 4f)
                    lineTo(size.width * 0.6f, size.height / 2f)
                    lineTo(size.width, size.height / 2f)
                }
                drawPath(
                    path = path,
                    color = CardOutline,
                    style = Stroke(width = 2.dp.toPx())
                )
            }

            Spacer(Modifier.height(16.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                MetaItem("BLOOD", card.blood_group ?: "—")
                MetaItem("VALID TILL", card.valid_till ?: "—")
                MetaItem("WARD", card.ward ?: "—")
            }

            Spacer(Modifier.height(24.dp))

            Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                OutlinedButton(
                    onClick = onShare,
                    modifier = Modifier.weight(1f).height(48.dp),
                    shape = RoundedCornerShape(12.dp),
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = TextWhite),
                    border = androidx.compose.foundation.BorderStroke(1.dp, CardOutline)
                ) {
                    Text("Share", fontSize = 14.sp, fontWeight = FontWeight.Medium)
                }
                
                Button(
                    onClick = onClick,
                    modifier = Modifier.weight(1f).height(48.dp),
                    shape = RoundedCornerShape(12.dp),
                    contentPadding = PaddingValues(0.dp), // To allow gradient fill
                    colors = ButtonDefaults.buttonColors(containerColor = Color.Transparent, contentColor = TextWhite)
                ) {
                    Box(
                        modifier = Modifier.fillMaxSize().background(GradientPrimary),
                        contentAlignment = Alignment.Center
                    ) {
                        Text("View details", fontSize = 14.sp, fontWeight = FontWeight.Medium)
                    }
                }
            }
        }
    }
}

@Composable
private fun MetaItem(label: String, value: String) {
    Column {
        Text(label, style = MaterialTheme.typography.labelSmall, color = TextGray)
        Spacer(Modifier.height(4.dp))
        Text(value, style = MaterialTheme.typography.bodyLarge, color = TextWhite)
    }
}
