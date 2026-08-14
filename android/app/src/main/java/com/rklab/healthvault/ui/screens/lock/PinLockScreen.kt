package com.rklab.healthvault.ui.screens.lock

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.rklab.healthvault.ui.theme.*

@Composable
fun PinLockScreen(error: Boolean, onSubmit: (String) -> Unit) {
    var pin by remember { mutableStateOf("") }
    Column(
        modifier = Modifier.fillMaxSize().background(HubBg).padding(28.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text("Unlock", style = MaterialTheme.typography.headlineMedium, color = Ink)
        Spacer(Modifier.height(8.dp))
        Text("Enter your app PIN", color = InkSoft)
        Spacer(Modifier.height(16.dp))
        OutlinedTextField(
            value = pin,
            onValueChange = { if (it.length <= 8) pin = it.filter(Char::isDigit) },
            label = { Text("PIN") },
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
            isError = error,
            singleLine = true
        )
        if (error) Text("Wrong PIN", color = StampRed, style = MaterialTheme.typography.bodySmall)
        Spacer(Modifier.height(16.dp))
        Button(
            onClick = { onSubmit(pin) },
            enabled = pin.length >= 4,
            colors = ButtonDefaults.buttonColors(containerColor = Navy)
        ) { Text("Unlock", color = White) }
    }
}
