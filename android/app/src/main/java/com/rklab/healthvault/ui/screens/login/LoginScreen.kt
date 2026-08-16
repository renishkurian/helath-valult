package com.rklab.healthvault.ui.screens.login

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsFocusedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Shield
import androidx.compose.material.icons.outlined.Visibility
import androidx.compose.material.icons.outlined.VisibilityOff
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.theme.HubTeal
import com.rklab.healthvault.ui.theme.StampRed
import com.rklab.healthvault.util.ViewModelFactory
import java.net.URI

private val LoginBg = Color(0xFF000000)
private val LoginMuted = Color(0xFF8A8A8A)
private val LoginFaint = Color(0xFF5C5C5C)
private val LoginLine = Color(0xFF2A2A2A)
private val LoginIconTile = Color(0xFF141414)
private val LoginOnTeal = Color(0xFF0A0A0A)

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
    var passwordVisible by remember { mutableStateOf(false) }

    val focusManager = LocalFocusManager.current
    val passwordFocus = remember { FocusRequester() }
    val totpFocus = remember { FocusRequester() }

    val needsTotp = state is AuthUiState.TotpRequired
    val step = if (needsTotp) 2 else 1
    val hostLabel = remember(repository.getServerUrl()) { displayServerHost(repository.getServerUrl()) }

    LaunchedEffect(state) {
        if (state is AuthUiState.Success) onAuthenticated()
        if (state is AuthUiState.TotpRequired) {
            totpCode = ""
            totpFocus.requestFocus()
        }
    }

    fun submit() {
        focusManager.clearFocus()
        val totp = state
        when {
            totp is AuthUiState.TotpRequired -> viewModel.verifyTotp(totp.totpToken, totpCode)
            isRegisterMode -> viewModel.register(email, password, fullName)
            else -> viewModel.login(email, password)
        }
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(LoginBg)
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .statusBarsPadding()
                .navigationBarsPadding()
                .imePadding()
        ) {
            LoginStepProgress(step = step, total = 2)

            Column(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState())
                    .padding(horizontal = 28.dp)
                    .padding(top = 28.dp, bottom = 16.dp)
            ) {
                VaultMark()
                Spacer(Modifier.height(28.dp))

                AnimatedContent(
                    targetState = Triple(needsTotp, isRegisterMode, step),
                    transitionSpec = {
                        (fadeIn() + slideInVertically { it / 12 }) togetherWith
                            (fadeOut() + slideOutVertically { -it / 16 })
                    },
                    label = "login-header"
                ) { (totp, register, currentStep) ->
                    Column {
                        Text(
                            "Step $currentStep of 2",
                            color = LoginMuted,
                            fontSize = 13.sp,
                            fontWeight = FontWeight.Medium
                        )
                        Spacer(Modifier.height(10.dp))
                        Text(
                            when {
                                totp -> "Verify it’s you"
                                register -> "Create your Vault"
                                else -> "Sign in to Vault"
                            },
                            color = Color.White,
                            fontSize = 32.sp,
                            fontWeight = FontWeight.Bold,
                            lineHeight = 38.sp,
                            letterSpacing = (-0.4).sp
                        )
                        Spacer(Modifier.height(8.dp))
                        Text(
                            when {
                                totp -> "Enter the 6-digit code from your authenticator app."
                                register -> "Set up an account on your self-hosted archive."
                                else -> "Access your self-hosted archive."
                            },
                            color = LoginMuted,
                            fontSize = 15.sp,
                            lineHeight = 22.sp
                        )
                    }
                }

                Spacer(Modifier.height(36.dp))

                if (!needsTotp && isRegisterMode) {
                    UnderlineField(
                        value = fullName,
                        onValueChange = { fullName = it },
                        label = "Full name",
                        keyboardOptions = KeyboardOptions(
                            keyboardType = KeyboardType.Text,
                            imeAction = ImeAction.Next
                        ),
                        keyboardActions = KeyboardActions(onNext = { passwordFocus.requestFocus() })
                    )
                    Spacer(Modifier.height(22.dp))
                }

                if (!needsTotp) {
                    UnderlineField(
                        value = email,
                        onValueChange = { email = it },
                        label = "Email",
                        keyboardOptions = KeyboardOptions(
                            keyboardType = KeyboardType.Email,
                            imeAction = ImeAction.Next
                        ),
                        keyboardActions = KeyboardActions(onNext = { passwordFocus.requestFocus() })
                    )
                    Spacer(Modifier.height(22.dp))
                    UnderlineField(
                        value = password,
                        onValueChange = { password = it },
                        label = if (isRegisterMode) "Password (min 8)" else "Password",
                        modifier = Modifier.focusRequester(passwordFocus),
                        visualTransformation = if (passwordVisible) {
                            VisualTransformation.None
                        } else {
                            PasswordVisualTransformation()
                        },
                        keyboardOptions = KeyboardOptions(
                            keyboardType = KeyboardType.Password,
                            imeAction = ImeAction.Done
                        ),
                        keyboardActions = KeyboardActions(onDone = { submit() }),
                        trailing = {
                            IconButton(
                                onClick = { passwordVisible = !passwordVisible },
                                modifier = Modifier.size(40.dp)
                            ) {
                                Icon(
                                    if (passwordVisible) Icons.Outlined.VisibilityOff else Icons.Outlined.Visibility,
                                    contentDescription = if (passwordVisible) "Hide password" else "Show password",
                                    tint = LoginFaint,
                                    modifier = Modifier.size(20.dp)
                                )
                            }
                        }
                    )
                } else {
                    UnderlineField(
                        value = totpCode,
                        onValueChange = { totpCode = it.filter(Char::isDigit).take(6) },
                        label = "Authenticator code",
                        modifier = Modifier.focusRequester(totpFocus),
                        keyboardOptions = KeyboardOptions(
                            keyboardType = KeyboardType.NumberPassword,
                            imeAction = ImeAction.Done
                        ),
                        keyboardActions = KeyboardActions(onDone = { submit() })
                    )
                }

                if (state is AuthUiState.Error) {
                    Spacer(Modifier.height(16.dp))
                    Text(
                        (state as AuthUiState.Error).message,
                        color = StampRed,
                        fontSize = 13.sp,
                        lineHeight = 18.sp
                    )
                }

                Spacer(Modifier.height(28.dp))

                ContinueButton(
                    text = when {
                        state is AuthUiState.Loading -> ""
                        needsTotp -> "Verify"
                        isRegisterMode -> "Create account"
                        else -> "Continue"
                    },
                    loading = state is AuthUiState.Loading,
                    onClick = { submit() }
                )

                if (!needsTotp) {
                    Spacer(Modifier.height(20.dp))
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.Center
                    ) {
                        Text(
                            if (isRegisterMode) "Already have an account? " else "New here? ",
                            color = LoginMuted,
                            fontSize = 13.sp
                        )
                        Text(
                            if (isRegisterMode) "Sign in" else "Create one",
                            color = HubTeal,
                            fontSize = 13.sp,
                            fontWeight = FontWeight.SemiBold,
                            modifier = Modifier.clickable {
                                isRegisterMode = !isRegisterMode
                                if (state is AuthUiState.Error) viewModel.clearError()
                            }
                        )
                    }
                }
            }

            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 28.dp, vertical = 18.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    hostLabel,
                    color = LoginFaint,
                    fontSize = 12.sp,
                    maxLines = 1,
                    modifier = Modifier.weight(1f, fill = false)
                )
                Text(
                    "Switch server",
                    color = HubTeal,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier
                        .clickable(onClick = onChangeServer)
                        .padding(start = 12.dp, top = 8.dp, bottom = 8.dp)
                )
            }
        }
    }
}

@Composable
private fun LoginStepProgress(step: Int, total: Int) {
    val fraction = (step.coerceIn(1, total).toFloat() / total.toFloat()).coerceIn(0.08f, 1f)
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 28.dp)
            .padding(top = 10.dp)
            .height(3.dp)
            .clip(RoundedCornerShape(2.dp))
            .background(LoginLine)
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth(fraction)
                .height(3.dp)
                .clip(RoundedCornerShape(2.dp))
                .background(HubTeal)
        )
    }
}

@Composable
private fun VaultMark() {
    Box(
        modifier = Modifier
            .size(48.dp)
            .clip(RoundedCornerShape(12.dp))
            .background(LoginIconTile)
            .border(1.dp, Color(0xFF222222), RoundedCornerShape(12.dp)),
        contentAlignment = Alignment.Center
    ) {
        Icon(
            Icons.Outlined.Shield,
            contentDescription = null,
            tint = HubTeal,
            modifier = Modifier.size(26.dp)
        )
    }
}

@Composable
private fun ContinueButton(
    text: String,
    loading: Boolean,
    onClick: () -> Unit
) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(54.dp)
            .clip(RoundedCornerShape(14.dp))
            .background(HubTeal)
            .clickable(enabled = !loading, onClick = onClick),
        contentAlignment = Alignment.Center
    ) {
        if (loading) {
            CircularProgressIndicator(
                modifier = Modifier.size(22.dp),
                color = LoginOnTeal,
                strokeWidth = 2.dp
            )
        } else {
            Text(
                text,
                color = LoginOnTeal,
                fontSize = 16.sp,
                fontWeight = FontWeight.Bold
            )
        }
    }
}

@Composable
private fun UnderlineField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    modifier: Modifier = Modifier,
    visualTransformation: VisualTransformation = VisualTransformation.None,
    keyboardOptions: KeyboardOptions = KeyboardOptions.Default,
    keyboardActions: KeyboardActions = KeyboardActions.Default,
    trailing: (@Composable () -> Unit)? = null
) {
    val interaction = remember { MutableInteractionSource() }
    val focused by interaction.collectIsFocusedAsState()
    val labelColor = when {
        focused -> HubTeal
        value.isNotEmpty() -> LoginMuted
        else -> LoginFaint
    }

    Column(modifier = modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically
        ) {
            BasicTextField(
                value = value,
                onValueChange = onValueChange,
                modifier = Modifier
                    .weight(1f)
                    .padding(vertical = 10.dp),
                singleLine = true,
                textStyle = TextStyle(
                    color = Color.White,
                    fontSize = 16.sp,
                    fontWeight = FontWeight.Medium,
                    letterSpacing = 0.1.sp
                ),
                cursorBrush = SolidColor(HubTeal),
                visualTransformation = visualTransformation,
                keyboardOptions = keyboardOptions,
                keyboardActions = keyboardActions,
                interactionSource = interaction
            )
            if (trailing != null) trailing()
        }
        HorizontalDivider(
            thickness = 1.dp,
            color = if (focused) HubTeal.copy(alpha = 0.55f) else LoginLine
        )
        Spacer(Modifier.height(6.dp))
        Text(
            label,
            color = labelColor,
            fontSize = 12.sp,
            fontWeight = FontWeight.Medium
        )
    }
}

private fun displayServerHost(raw: String?): String {
    if (raw.isNullOrBlank()) return "No server set"
    val trimmed = raw.trim().trimEnd('/')
    return try {
        val withScheme = if ("://" in trimmed) trimmed else "http://$trimmed"
        URI(withScheme).host?.takeIf { it.isNotBlank() }
            ?: trimmed.removePrefix("https://").removePrefix("http://")
    } catch (_: Exception) {
        trimmed.removePrefix("https://").removePrefix("http://")
    }
}
