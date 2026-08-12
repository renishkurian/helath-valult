package com.rklab.healthvault.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
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

    Box(
        modifier = modifier
            .clip(RoundedCornerShape(18.dp))
            .background(Brush.linearGradient(listOf(Navy, NavyDeep)))
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
                        card.hospital_name.uppercase(),
                        style = MaterialTheme.typography.labelMedium,
                        color = Color(0xFFB9C7D2)
                    )
                    Spacer(Modifier.height(2.dp))
                    Text("Patient Health ID", style = MaterialTheme.typography.titleMedium, color = White)
                }
                Box(
                    modifier = Modifier
                        .size(52.dp)
                        .clip(CircleShape),
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        "VERIFIED\nCOPY",
                        style = MaterialTheme.typography.labelSmall,
                        color = StampRed,
                        textAlign = TextAlign.Center,
                        fontWeight = FontWeight.SemiBold,
                        modifier = Modifier
                            .border(1.5.dp, StampRed, CircleShape)
                            .padding(6.dp)
                    )
                }
            }

            Spacer(Modifier.height(18.dp))

            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    modifier = Modifier
                        .size(50.dp)
                        .clip(CircleShape)
                        .background(Color(0xFF3E5A70)),
                    contentAlignment = Alignment.Center
                ) {
                    Text(initials, style = MaterialTheme.typography.titleLarge, color = White)
                }
                Spacer(Modifier.width(14.dp))
                Column {
                    Text(patientName, style = MaterialTheme.typography.titleLarge, color = White)
                    Spacer(Modifier.height(2.dp))
                    Text(
                        "ID ${card.patient_id ?: "—"}",
                        style = MaterialTheme.typography.labelLarge,
                        color = Color(0xFFB9C7D2)
                    )
                }
            }

            Spacer(Modifier.height(14.dp))

            Row(
                modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
                horizontalArrangement = Arrangement.spacedBy(22.dp)
            ) {
                MetaItem("BLOOD GROUP", card.blood_group ?: "—")
                MetaItem("VALID TILL", card.valid_till ?: "—")
                MetaItem("WARD", card.ward ?: "—")
            }

            Spacer(Modifier.height(14.dp))

            Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                OutlinedButton(
                    onClick = onShare,
                    modifier = Modifier.weight(1f),
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = White)
                ) {
                    Icon(Icons.Filled.Share, contentDescription = null, modifier = Modifier.size(14.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("Share", fontSize = 12.5.sp)
                }
                Button(
                    onClick = onClick,
                    modifier = Modifier.weight(1f),
                    colors = ButtonDefaults.buttonColors(containerColor = White, contentColor = NavyDeep)
                ) {
                    Text("View details", fontSize = 12.5.sp, fontWeight = FontWeight.SemiBold)
                }
            }
        }
    }
}

@Composable
private fun MetaItem(label: String, value: String) {
    Column {
        Text(label, style = MaterialTheme.typography.labelSmall, color = Color(0xFF8FA2B0))
        Spacer(Modifier.height(2.dp))
        Text(value, style = MaterialTheme.typography.labelLarge, color = White)
    }
}
