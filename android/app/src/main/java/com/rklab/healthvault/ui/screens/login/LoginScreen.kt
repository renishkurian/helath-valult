package com.rklab.healthvault.ui.screens.login

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.rklab.healthvault.ui.theme.*
import com.rklab.healthvault.util.ViewModelFactory
import com.rklab.healthvault.data.repository.HealthVaultRepository

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

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Paper)
            .padding(horizontal = 28.dp),
        verticalArrangement = Arrangement.Center
    ) {
        Text("VAULT", style = MaterialTheme.typography.labelMedium, color = InkSoft)
        Spacer(Modifier.height(6.dp))
        Text(
            if (isRegisterMode) "Create your\naccount" else "Welcome\nback",
            style = MaterialTheme.typography.headlineLarge,
            color = Ink
        )
        Spacer(Modifier.height(6.dp))
        Text(
            "Health records and passwords — kept on your own server.",
            style = MaterialTheme.typography.bodyMedium,
            color = InkSoft
        )
        Spacer(Modifier.height(28.dp))

        if (isRegisterMode) {
            OutlinedTextField(
                value = fullName,
                onValueChange = { fullName = it },
                label = { Text("Full name") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true
            )
            Spacer(Modifier.height(12.dp))
        }

        OutlinedTextField(
            value = email,
            onValueChange = { email = it },
            label = { Text("Email") },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email)
        )
        Spacer(Modifier.height(12.dp))
        OutlinedTextField(
            value = password,
            onValueChange = { password = it },
            label = { Text(if (isRegisterMode) "Password (min 8 characters)" else "Password") },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password)
        )

        if (state is AuthUiState.TotpRequired) {
            Spacer(Modifier.height(12.dp))
            OutlinedTextField(
                value = totpCode,
                onValueChange = { totpCode = it.filter(Char::isDigit).take(6) },
                label = { Text("Authenticator code") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number)
            )
        }

        if (state is AuthUiState.Error) {
            Spacer(Modifier.height(10.dp))
            Text((state as AuthUiState.Error).message, color = StampRed, style = MaterialTheme.typography.bodySmall)
        }

        Spacer(Modifier.height(20.dp))
        Button(
            onClick = {
                val totp = state
                if (totp is AuthUiState.TotpRequired) viewModel.verifyTotp(totp.totpToken, totpCode)
                else if (isRegisterMode) viewModel.register(email, password, fullName)
                else viewModel.login(email, password)
            },
            modifier = Modifier.fillMaxWidth().height(50.dp),
            colors = ButtonDefaults.buttonColors(containerColor = Navy),
            enabled = state !is AuthUiState.Loading
        ) {
            if (state is AuthUiState.Loading) {
                CircularProgressIndicator(modifier = Modifier.size(20.dp), color = White, strokeWidth = 2.dp)
            } else {
                Text(
                    when {
                        state is AuthUiState.TotpRequired -> "Verify code"
                        isRegisterMode -> "Create account"
                        else -> "Log in"
                    },
                    color = White
                )
            }
        }

        Spacer(Modifier.height(16.dp))
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.Center
        ) {
            Text(
                if (isRegisterMode) "Already have an account? " else "New here? ",
                style = MaterialTheme.typography.bodySmall, color = InkSoft
            )
            Text(
                if (isRegisterMode) "Log in" else "Create one",
                style = MaterialTheme.typography.bodySmall,
                color = Navy,
                modifier = Modifier.clickable { isRegisterMode = !isRegisterMode }
            )
        }

        Spacer(Modifier.height(28.dp))
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center) {
            Text(
                "Server: ${repository.getServerUrl() ?: "not set"}",
                style = MaterialTheme.typography.labelSmall,
                color = InkSoft
            )
            Spacer(Modifier.width(6.dp))
            Text(
                "Change",
                style = MaterialTheme.typography.labelSmall,
                color = Navy,
                modifier = Modifier.clickable(onClick = onChangeServer)
            )
        }
    }
}
