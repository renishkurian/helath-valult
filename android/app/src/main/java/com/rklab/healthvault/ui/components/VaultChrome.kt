package com.rklab.healthvault.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.rklab.healthvault.ui.theme.CardOutline
import com.rklab.healthvault.ui.theme.CardSurface
import com.rklab.healthvault.ui.theme.HubBg
import com.rklab.healthvault.ui.theme.HubGlass
import com.rklab.healthvault.ui.theme.HubStroke
import com.rklab.healthvault.ui.theme.HubText
import com.rklab.healthvault.ui.theme.HubTextDim
import com.rklab.healthvault.ui.theme.HubViolet
import com.rklab.healthvault.ui.theme.Ink
import com.rklab.healthvault.ui.theme.InkSoft
import com.rklab.healthvault.ui.theme.TextDark
import com.rklab.healthvault.ui.theme.VaultGold
import com.rklab.healthvault.ui.theme.VaultGoldSoft

val VaultCardShape = RoundedCornerShape(16.dp)
val VaultChipShape = RoundedCornerShape(20.dp)

@Composable
fun vaultFieldColors() = OutlinedTextFieldDefaults.colors(
    focusedBorderColor = VaultGold,
    unfocusedBorderColor = CardOutline,
    focusedLabelColor = VaultGold,
    unfocusedLabelColor = InkSoft,
    cursorColor = VaultGold,
    focusedTextColor = Ink,
    unfocusedTextColor = Ink,
    focusedContainerColor = CardSurface,
    unfocusedContainerColor = CardSurface,
)

@Composable
fun VaultScreen(
    modifier: Modifier = Modifier,
    content: @Composable ColumnScope.() -> Unit
) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .background(HubBg)
            .padding(horizontal = 20.dp),
        content = content
    )
}

@Composable
fun VaultPageHeader(
    eyebrow: String,
    title: String,
    modifier: Modifier = Modifier,
    subtitle: String? = null,
    actions: @Composable RowScope.() -> Unit = {}
) {
    Row(
        modifier = modifier.fillMaxWidth().padding(top = 16.dp, bottom = 8.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.Top
    ) {
        Column(Modifier.weight(1f)) {
            Text(eyebrow, style = MaterialTheme.typography.labelMedium, color = VaultGold)
            Spacer(Modifier.height(4.dp))
            Text(title, style = MaterialTheme.typography.headlineMedium, color = HubText, fontWeight = FontWeight.Bold)
            if (!subtitle.isNullOrBlank()) {
                Spacer(Modifier.height(4.dp))
                Text(subtitle, style = MaterialTheme.typography.bodySmall, color = HubTextDim)
            }
        }
        Row(content = actions)
    }
}

@Composable
fun VaultBackLink(label: String = "← Back", onClick: () -> Unit) {
    TextButton(onClick = onClick, contentPadding = PaddingValues(0.dp)) {
        Text(label, color = VaultGold)
    }
}

@Composable
fun VaultGlassCard(
    modifier: Modifier = Modifier,
    content: @Composable ColumnScope.() -> Unit
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .clip(VaultCardShape)
            .background(HubGlass)
            .border(1.dp, HubStroke, VaultCardShape)
            .padding(16.dp),
        content = content
    )
}

@Composable
fun VaultPrimaryButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    leadingIcon: ImageVector? = null
) {
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.fillMaxWidth().height(50.dp),
        shape = RoundedCornerShape(14.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = VaultGold,
            contentColor = TextDark,
            disabledContainerColor = VaultGoldSoft,
            disabledContentColor = TextDark.copy(alpha = 0.5f)
        )
    ) {
        if (leadingIcon != null) {
            Icon(leadingIcon, contentDescription = null, tint = TextDark)
            Spacer(Modifier.width(8.dp))
        }
        Text(text, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
fun VaultOutlinedButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    color: Color = VaultGold,
    leadingIcon: ImageVector? = null
) {
    OutlinedButton(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(14.dp),
        border = BorderStroke(1.dp, color.copy(alpha = 0.45f)),
        colors = ButtonDefaults.outlinedButtonColors(contentColor = color)
    ) {
        if (leadingIcon != null) {
            Icon(leadingIcon, contentDescription = null, tint = color)
            Spacer(Modifier.width(8.dp))
        }
        Text(text, color = color)
    }
}

@Composable
fun VaultFilterChip(
    selected: Boolean,
    onClick: () -> Unit,
    label: String
) {
    FilterChip(
        selected = selected,
        onClick = onClick,
        label = { Text(label) },
        shape = VaultChipShape,
        colors = FilterChipDefaults.filterChipColors(
            containerColor = HubGlass,
            labelColor = HubTextDim,
            selectedContainerColor = VaultGoldSoft,
            selectedLabelColor = VaultGold
        )
    )
}

@Composable
fun VaultListRow(
    title: String,
    subtitle: String,
    meta: String? = null,
    badge: String? = null,
    accent: Color = HubViolet,
    favorite: Boolean = false,
    onClick: () -> Unit
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(VaultCardShape)
            .background(HubGlass)
            .border(1.dp, HubStroke, VaultCardShape)
            .clickable(onClick = onClick)
            .padding(14.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            Modifier
                .size(42.dp)
                .clip(RoundedCornerShape(12.dp))
                .background(accent.copy(alpha = 0.18f)),
            contentAlignment = Alignment.Center
        ) {
            Text(
                title.take(1).uppercase(),
                color = accent,
                fontWeight = FontWeight.Bold
            )
        }
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(title, color = HubText, fontWeight = FontWeight.SemiBold)
                if (favorite) {
                    Spacer(Modifier.width(6.dp))
                    Text("★", color = VaultGold, style = MaterialTheme.typography.labelSmall)
                }
            }
            Text(subtitle, color = HubTextDim, style = MaterialTheme.typography.bodySmall)
        }
        if (!badge.isNullOrBlank()) {
            Text(
                badge,
                color = VaultGold,
                style = MaterialTheme.typography.labelSmall,
                modifier = Modifier.padding(end = 8.dp)
            )
        }
        if (!meta.isNullOrBlank()) {
            Text(meta, color = HubTextDim, style = MaterialTheme.typography.labelSmall)
        }
    }
}

@Composable
fun VaultFab(onClick: () -> Unit, icon: ImageVector, contentDescription: String) {
    FloatingActionButton(
        onClick = onClick,
        containerColor = VaultGold,
        contentColor = TextDark,
        shape = RoundedCornerShape(16.dp)
    ) {
        Icon(icon, contentDescription = contentDescription)
    }
}
