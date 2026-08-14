package com.rklab.healthvault.ui.screens.passwords

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import com.rklab.healthvault.data.model.VaultGenerateIn
import com.rklab.healthvault.data.model.VaultGenerateOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.components.VaultFilterChip
import com.rklab.healthvault.ui.components.VaultGlassCard
import com.rklab.healthvault.ui.components.VaultPageHeader
import com.rklab.healthvault.ui.components.VaultPrimaryButton
import com.rklab.healthvault.ui.theme.HubBg
import com.rklab.healthvault.ui.theme.HubText
import com.rklab.healthvault.ui.theme.HubTextDim
import com.rklab.healthvault.ui.theme.VaultGold
import com.rklab.healthvault.util.ClipboardUtil
import kotlinx.coroutines.launch

@Composable
fun GeneratorScreen(repository: HealthVaultRepository) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var kind by remember { mutableStateOf("password") }
    var length by remember { mutableFloatStateOf(16f) }
    var words by remember { mutableFloatStateOf(4f) }
    var upper by remember { mutableStateOf(true) }
    var lower by remember { mutableStateOf(true) }
    var numbers by remember { mutableStateOf(true) }
    var symbols by remember { mutableStateOf(true) }
    var result by remember { mutableStateOf<VaultGenerateOut?>(null) }

    fun generate() {
        scope.launch {
            result = runCatching {
                repository.generatePassword(
                    VaultGenerateIn(
                        kind = kind,
                        length = length.toInt(),
                        word_count = words.toInt(),
                        uppercase = upper,
                        lowercase = lower,
                        numbers = numbers,
                        symbols = symbols
                    )
                )
            }.getOrNull()
        }
    }
    LaunchedEffect(Unit) { generate() }

    Column(
        Modifier
            .fillMaxSize()
            .background(HubBg)
            .padding(20.dp)
            .verticalScroll(rememberScrollState())
    ) {
        VaultPageHeader(
            eyebrow = "GENERATOR",
            title = "Password generator"
        )
        Spacer(Modifier.height(8.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            VaultFilterChip(
                selected = kind == "password",
                onClick = { kind = "password"; generate() },
                label = "Password"
            )
            VaultFilterChip(
                selected = kind == "passphrase",
                onClick = { kind = "passphrase"; generate() },
                label = "Passphrase"
            )
        }
        Spacer(Modifier.height(12.dp))
        result?.let {
            VaultGlassCard {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(it.value, color = HubText, fontFamily = FontFamily.Monospace)
                        Text(
                            "Strength ${it.score}/4",
                            color = HubTextDim,
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                    IconButton(onClick = { ClipboardUtil.copy(context, "Password", it.value) }) {
                        Icon(Icons.Filled.ContentCopy, null, tint = VaultGold)
                    }
                }
            }
        }
        Spacer(Modifier.height(16.dp))
        if (kind == "password") {
            Text("Length ${length.toInt()}", color = HubTextDim)
            Slider(
                value = length,
                onValueChange = { length = it },
                valueRange = 8f..64f,
                steps = 55,
                colors = SliderDefaults.colors(
                    thumbColor = VaultGold,
                    activeTrackColor = VaultGold,
                    inactiveTrackColor = HubTextDim.copy(alpha = 0.3f)
                )
            )
        } else {
            Text("Words ${words.toInt()}", color = HubTextDim)
            Slider(
                value = words,
                onValueChange = { words = it },
                valueRange = 3f..10f,
                steps = 6,
                colors = SliderDefaults.colors(
                    thumbColor = VaultGold,
                    activeTrackColor = VaultGold,
                    inactiveTrackColor = HubTextDim.copy(alpha = 0.3f)
                )
            )
        }
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text("A–Z", color = HubText)
            Switch(
                checked = upper,
                onCheckedChange = { upper = it },
                colors = SwitchDefaults.colors(
                    checkedThumbColor = VaultGold,
                    checkedTrackColor = VaultGold.copy(alpha = 0.4f)
                )
            )
        }
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text("a–z", color = HubText)
            Switch(
                checked = lower,
                onCheckedChange = { lower = it },
                colors = SwitchDefaults.colors(
                    checkedThumbColor = VaultGold,
                    checkedTrackColor = VaultGold.copy(alpha = 0.4f)
                )
            )
        }
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text("0–9", color = HubText)
            Switch(
                checked = numbers,
                onCheckedChange = { numbers = it },
                colors = SwitchDefaults.colors(
                    checkedThumbColor = VaultGold,
                    checkedTrackColor = VaultGold.copy(alpha = 0.4f)
                )
            )
        }
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text("Symbols", color = HubText)
            Switch(
                checked = symbols,
                onCheckedChange = { symbols = it },
                colors = SwitchDefaults.colors(
                    checkedThumbColor = VaultGold,
                    checkedTrackColor = VaultGold.copy(alpha = 0.4f)
                )
            )
        }
        Spacer(Modifier.height(12.dp))
        VaultPrimaryButton("Generate", onClick = { generate() })
    }
}
