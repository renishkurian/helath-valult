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
import com.rklab.healthvault.ui.theme.*
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

    Column(Modifier.fillMaxSize().background(Paper).padding(20.dp).verticalScroll(rememberScrollState())) {
        Text("GENERATOR", style = MaterialTheme.typography.labelMedium, color = InkSoft)
        Text("Password generator", style = MaterialTheme.typography.headlineMedium, color = Ink)
        Spacer(Modifier.height(16.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(selected = kind == "password", onClick = { kind = "password"; generate() }, label = { Text("Password") })
            FilterChip(selected = kind == "passphrase", onClick = { kind = "passphrase"; generate() }, label = { Text("Passphrase") })
        }
        Spacer(Modifier.height(12.dp))
        result?.let {
            Surface(color = White, shape = MaterialTheme.shapes.medium, modifier = Modifier.fillMaxWidth()) {
                Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(it.value, color = Ink, fontFamily = FontFamily.Monospace)
                        Text("Strength ${it.score}/4", color = InkSoft, style = MaterialTheme.typography.bodySmall)
                    }
                    IconButton(onClick = { ClipboardUtil.copy(context, "Password", it.value) }) {
                        Icon(Icons.Filled.ContentCopy, null, tint = Navy)
                    }
                }
            }
        }
        Spacer(Modifier.height(16.dp))
        if (kind == "password") {
            Text("Length ${length.toInt()}", color = InkSoft)
            Slider(value = length, onValueChange = { length = it }, valueRange = 8f..64f, steps = 55)
        } else {
            Text("Words ${words.toInt()}", color = InkSoft)
            Slider(value = words, onValueChange = { words = it }, valueRange = 3f..10f, steps = 6)
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Text("A–Z", color = Ink); Switch(checked = upper, onCheckedChange = { upper = it })
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Text("a–z", color = Ink); Switch(checked = lower, onCheckedChange = { lower = it })
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Text("0–9", color = Ink); Switch(checked = numbers, onCheckedChange = { numbers = it })
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Text("Symbols", color = Ink); Switch(checked = symbols, onCheckedChange = { symbols = it })
        }
        Spacer(Modifier.height(12.dp))
        Button(onClick = { generate() }, modifier = Modifier.fillMaxWidth(), colors = ButtonDefaults.buttonColors(containerColor = Navy)) {
            Text("Generate", color = TextWhite)
        }
    }
}
