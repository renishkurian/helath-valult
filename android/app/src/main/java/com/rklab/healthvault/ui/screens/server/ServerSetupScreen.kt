package com.rklab.healthvault.ui.screens.server

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Dns
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.rklab.healthvault.BuildConfig
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.theme.*
import com.rklab.healthvault.util.ViewModelFactory

@Composable
fun ServerSetupScreen(
    repository: HealthVaultRepository,
    onConnected: () -> Unit
) {
    val viewModel: ServerSetupViewModel = viewModel(factory = ViewModelFactory(repository))
    val state by viewModel.state.collectAsState()

    var url by remember {
        mutableStateOf(repository.getServerUrl() ?: BuildConfig.DEFAULT_SERVER_URL)
    }

    LaunchedEffect(state) {
        if (state is ServerSetupState.Success) onConnected()
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(HubBg)
            .padding(horizontal = 28.dp),
        verticalArrangement = Arrangement.Center
    ) {
        Box(
            modifier = Modifier
                .size(56.dp)
                .clip(RoundedCornerShape(16.dp))
                .background(Navy),
            contentAlignment = Alignment.Center
        ) {
            Icon(Icons.Filled.Dns, contentDescription = null, tint = White)
        }
        Spacer(Modifier.height(20.dp))

        Text("VAULT HUB", style = MaterialTheme.typography.labelMedium, color = VaultGold)
        Spacer(Modifier.height(6.dp))
        Text("Connect to your\nserver", style = MaterialTheme.typography.headlineLarge, color = Ink)
        Spacer(Modifier.height(8.dp))
        Text(
            "Point this app at your own Vault Hub server — the address of the Pi (or domain) where it's running.",
            style = MaterialTheme.typography.bodyMedium,
            color = InkSoft
        )
        Spacer(Modifier.height(28.dp))

        OutlinedTextField(
            value = url,
            onValueChange = { url = it },
            label = { Text("Server address") },
            placeholder = { Text("192.168.0.50:8000") },
            supportingText = { Text("LAN IP, WireGuard IP, or domain — http:// assumed if you leave off the scheme") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
            modifier = Modifier.fillMaxWidth()
        )

        if (state is ServerSetupState.Error) {
            Spacer(Modifier.height(10.dp))
            Text((state as ServerSetupState.Error).message, color = StampRed, style = MaterialTheme.typography.bodySmall)
        }

        Spacer(Modifier.height(20.dp))
        Button(
            onClick = { viewModel.testAndSave(url) },
            modifier = Modifier.fillMaxWidth().height(50.dp),
            colors = ButtonDefaults.buttonColors(containerColor = Navy),
            enabled = state !is ServerSetupState.Testing
        ) {
            if (state is ServerSetupState.Testing) {
                CircularProgressIndicator(modifier = Modifier.size(20.dp), color = White, strokeWidth = 2.dp)
                Spacer(Modifier.width(10.dp))
                Text("Checking connection…", color = White)
            } else {
                Text("Connect", color = White, fontWeight = FontWeight.SemiBold)
            }
        }

        Spacer(Modifier.height(14.dp))
        Text(
            "Nothing is sent anywhere except the address you enter — this app only talks to your own server.",
            style = MaterialTheme.typography.labelSmall,
            color = InkSoft
        )
    }
}
