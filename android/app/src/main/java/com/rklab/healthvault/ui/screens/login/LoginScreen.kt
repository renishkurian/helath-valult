package com.rklab.healthvault.ui.screens.login

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.components.VaultGlassCard
import com.rklab.healthvault.ui.components.VaultPrimaryButton
import com.rklab.healthvault.ui.components.vaultFieldColors
import com.rklab.healthvault.ui.theme.HubBg
import com.rklab.healthvault.ui.theme.HubTeal
import com.rklab.healthvault.ui.theme.HubText
import com.rklab.healthvault.ui.theme.HubTextDim
import com.rklab.healthvault.ui.theme.HubViolet
import com.rklab.healthvault.ui.theme.StampRed
import com.rklab.healthvault.ui.theme.VaultGold
import com.rklab.healthvault.util.ViewModelFactory

@Composable
fun LoginScreen(
    repository: HealthVaultRepository,
    onAuthenticated: () -> Unit,
    onChangeServer: () -> Unit = {}
) {
    val viewModel: LoginViewModel = viewModel(factory = ViewModelFactory(repository))
    val state by viewModel.state.collectAsState()

    var isRegisterMode by remember { mutableStateOf(false) }
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var fullName by remember { mutableStateOf("") }
    var totpCode by remember { mutableStateOf("") }

    LaunchedEffect(state) {
        if (state is AuthUiState.Success) onAuthenticated()
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(HubBg)
    ) {
        Box(
            Modifier
                .fillMaxSize()
                .background(
                    Brush.radialGradient(
                        colors = listOf(HubViolet.copy(alpha = 0.22f), Color.Transparent),
                        radius = 900f
                    )
                )
        )
        Box(
            Modifier
                .fillMaxSize()
                .background(
                    Brush.radialGradient(
                        colors = listOf(HubTeal.copy(alpha = 0.12f), Color.Transparent),
                        center = Offset(200f, 1400f),
                        radius = 800f
                    )
                )
        )
        Column(
            modifier = Modifier
                .fillMaxSize()
                .statusBarsPadding()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 24.dp, vertical = 28.dp),
            verticalArrangement = Arrangement.Center
        ) {
            Text("HEALTH VAULT", style = MaterialTheme.typography.labelMedium, color = VaultGold)
            Spacer(Modifier.height(8.dp))
            Text(
                if (isRegisterMode) "Create your\naccount" else "Welcome\nback",
                style = MaterialTheme.typography.headlineLarge,
                color = HubText,
                fontWeight = FontWeight.Bold
            )
            Spacer(Modifier.height(8.dp))
            Text(
                "Health records and passwords — kept on your own server.",
                style = MaterialTheme.typography.bodyMedium,
                color = HubTextDim
            )
            Spacer(Modifier.height(28.dp))

            VaultGlassCard {
                if (isRegisterMode) {
                    OutlinedTextField(
                        value = fullName,
                        onValueChange = { fullName = it },
                        label = { Text("Full name") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                        colors = vaultFieldColors()
                    )
                    Spacer(Modifier.height(12.dp))
                }
                OutlinedTextField(
                    value = email,
                    onValueChange = { email = it },
                    label = { Text("Email") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
                    colors = vaultFieldColors()
                )
                Spacer(Modifier.height(12.dp))
                OutlinedTextField(
                    value = password,
                    onValueChange = { password = it },
                    label = { Text(if (isRegisterMode) "Password (min 8 characters)" else "Password") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    visualTransformation = PasswordVisualTransformation(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                    colors = vaultFieldColors()
                )
                if (state is AuthUiState.TotpRequired) {
                    Spacer(Modifier.height(12.dp))
                    OutlinedTextField(
                        value = totpCode,
                        onValueChange = { totpCode = it.filter(Char::isDigit).take(6) },
                        label = { Text("Authenticator code") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        colors = vaultFieldColors()
                    )
                }
                if (state is AuthUiState.Error) {
                    Spacer(Modifier.height(10.dp))
                    Text((state as AuthUiState.Error).message, color = StampRed, style = MaterialTheme.typography.bodySmall)
                }
                Spacer(Modifier.height(18.dp))
                if (state is AuthUiState.Loading) {
                    Box(Modifier.fillMaxWidth().height(50.dp), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator(modifier = Modifier.size(22.dp), color = VaultGold, strokeWidth = 2.dp)
                    }
                } else {
                    VaultPrimaryButton(
                        text = when {
                            state is AuthUiState.TotpRequired -> "Verify code"
                            isRegisterMode -> "Create account"
                            else -> "Log in"
                        },
                        onClick = {
                            val totp = state
                            if (totp is AuthUiState.TotpRequired) viewModel.verifyTotp(totp.totpToken, totpCode)
                            else if (isRegisterMode) viewModel.register(email, password, fullName)
                            else viewModel.login(email, password)
                        }
                    )
                }
            }

            Spacer(Modifier.height(18.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center) {
                Text(
                    if (isRegisterMode) "Already have an account? " else "New here? ",
                    style = MaterialTheme.typography.bodySmall,
                    color = HubTextDim
                )
                Text(
                    if (isRegisterMode) "Log in" else "Create one",
                    style = MaterialTheme.typography.bodySmall,
                    color = VaultGold,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.clickable { isRegisterMode = !isRegisterMode }
                )
            }
            Spacer(Modifier.height(24.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center) {
                Text(
                    "Server: ${repository.getServerUrl() ?: "not set"}",
                    style = MaterialTheme.typography.labelSmall,
                    color = HubTextDim
                )
                Spacer(Modifier.width(6.dp))
                Text(
                    "Change",
                    style = MaterialTheme.typography.labelSmall,
                    color = VaultGold,
                    modifier = Modifier.clickable(onClick = onChangeServer)
                )
            }
        }
    }
}
