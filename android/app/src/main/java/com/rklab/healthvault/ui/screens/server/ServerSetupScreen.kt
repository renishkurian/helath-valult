package com.rklab.healthvault.ui.screens.server

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsFocusedAsState
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
import androidx.compose.material.icons.outlined.Dns
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.rklab.healthvault.BuildConfig
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.theme.HubTeal
import com.rklab.healthvault.ui.theme.StampRed
import com.rklab.healthvault.util.ViewModelFactory

private val SetupBg = Color(0xFF000000)
private val SetupMuted = Color(0xFF8A8A8A)
private val SetupFaint = Color(0xFF5C5C5C)
private val SetupLine = Color(0xFF2A2A2A)
private val SetupIconTile = Color(0xFF141414)
private val SetupOnTeal = Color(0xFF0A0A0A)

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

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(SetupBg)
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .statusBarsPadding()
                .navigationBarsPadding()
                .imePadding()
        ) {
            // First-run: connecting the server is the prelude to sign-in.
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 28.dp)
                    .padding(top = 10.dp)
                    .height(3.dp)
                    .clip(RoundedCornerShape(2.dp))
                    .background(SetupLine)
            ) {
                Box(
                    modifier = Modifier
                        .fillMaxWidth(0.35f)
                        .height(3.dp)
                        .clip(RoundedCornerShape(2.dp))
                        .background(HubTeal)
                )
            }

            Column(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState())
                    .padding(horizontal = 28.dp)
                    .padding(top = 28.dp, bottom = 16.dp)
            ) {
                Box(
                    modifier = Modifier
                        .size(48.dp)
                        .clip(RoundedCornerShape(12.dp))
                        .background(SetupIconTile)
                        .border(1.dp, Color(0xFF222222), RoundedCornerShape(12.dp)),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(
                        Icons.Outlined.Dns,
                        contentDescription = null,
                        tint = HubTeal,
                        modifier = Modifier.size(26.dp)
                    )
                }
                Spacer(Modifier.height(28.dp))
                Text(
                    "Before you sign in",
                    color = SetupMuted,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.Medium
                )
                Spacer(Modifier.height(10.dp))
                Text(
                    "Connect your server",
                    color = Color.White,
                    fontSize = 32.sp,
                    fontWeight = FontWeight.Bold,
                    lineHeight = 38.sp,
                    letterSpacing = (-0.4).sp
                )
                Spacer(Modifier.height(8.dp))
                Text(
                    "Point this app at your self-hosted Vault — LAN IP, WireGuard, or domain.",
                    color = SetupMuted,
                    fontSize = 15.sp,
                    lineHeight = 22.sp
                )

                Spacer(Modifier.height(36.dp))

                ServerUnderlineField(
                    value = url,
                    onValueChange = { url = it },
                    label = "Server address",
                    keyboardOptions = KeyboardOptions(
                        keyboardType = KeyboardType.Uri,
                        imeAction = ImeAction.Done
                    ),
                    keyboardActions = KeyboardActions(
                        onDone = { viewModel.testAndSave(url) }
                    )
                )

                if (state is ServerSetupState.Error) {
                    Spacer(Modifier.height(16.dp))
                    Text(
                        (state as ServerSetupState.Error).message,
                        color = StampRed,
                        fontSize = 13.sp,
                        lineHeight = 18.sp
                    )
                }

                Spacer(Modifier.height(28.dp))

                val testing = state is ServerSetupState.Testing
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(54.dp)
                        .clip(RoundedCornerShape(14.dp))
                        .background(HubTeal)
                        .clickable(enabled = !testing) { viewModel.testAndSave(url) },
                    contentAlignment = Alignment.Center
                ) {
                    if (testing) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(20.dp),
                                color = SetupOnTeal,
                                strokeWidth = 2.dp
                            )
                            Spacer(Modifier.size(10.dp))
                            Text(
                                "Checking…",
                                color = SetupOnTeal,
                                fontSize = 16.sp,
                                fontWeight = FontWeight.Bold
                            )
                        }
                    } else {
                        Text(
                            "Continue",
                            color = SetupOnTeal,
                            fontSize = 16.sp,
                            fontWeight = FontWeight.Bold
                        )
                    }
                }

                Spacer(Modifier.height(16.dp))
                Text(
                    "Nothing leaves your network except the address you enter.",
                    color = SetupFaint,
                    fontSize = 12.sp,
                    lineHeight = 18.sp
                )
            }
        }
    }
}

@Composable
private fun ServerUnderlineField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    keyboardOptions: KeyboardOptions = KeyboardOptions.Default,
    keyboardActions: KeyboardActions = KeyboardActions.Default
) {
    val interaction = remember { MutableInteractionSource() }
    val focused by interaction.collectIsFocusedAsState()
    val labelColor = when {
        focused -> HubTeal
        value.isNotEmpty() -> SetupMuted
        else -> SetupFaint
    }

    Column(modifier = Modifier.fillMaxWidth()) {
        BasicTextField(
            value = value,
            onValueChange = onValueChange,
            modifier = Modifier
                .fillMaxWidth()
                .padding(vertical = 10.dp),
            singleLine = true,
            textStyle = TextStyle(
                color = Color.White,
                fontSize = 16.sp,
                fontWeight = FontWeight.Medium
            ),
            cursorBrush = SolidColor(HubTeal),
            keyboardOptions = keyboardOptions,
            keyboardActions = keyboardActions,
            interactionSource = interaction
        )
        HorizontalDivider(
            thickness = 1.dp,
            color = if (focused) HubTeal.copy(alpha = 0.55f) else SetupLine
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
