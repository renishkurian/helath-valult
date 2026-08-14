package com.rklab.healthvault.ui.screens.passwords

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import com.rklab.healthvault.data.model.VaultFolderOut
import com.rklab.healthvault.data.model.VaultGenerateIn
import com.rklab.healthvault.data.model.VaultItemIn
import com.rklab.healthvault.data.model.VaultItemUpdate
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.components.VaultBackLink
import com.rklab.healthvault.ui.components.VaultFilterChip
import com.rklab.healthvault.ui.components.VaultPageHeader
import com.rklab.healthvault.ui.components.VaultPrimaryButton
import com.rklab.healthvault.ui.components.vaultFieldColors
import com.rklab.healthvault.ui.theme.HubBg
import com.rklab.healthvault.ui.theme.StampRed
import com.rklab.healthvault.ui.theme.VaultGold
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun VaultEditScreen(
    repository: HealthVaultRepository,
    itemId: String?,
    defaultType: String,
    onDone: () -> Unit,
    onBack: () -> Unit
) {
    val scope = rememberCoroutineScope()
    var type by remember { mutableStateOf(defaultType) }
    var name by remember { mutableStateOf("") }
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var uris by remember { mutableStateOf("") }
    var totp by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }
    var folderId by remember { mutableStateOf<String?>(null) }
    var folders by remember { mutableStateOf<List<VaultFolderOut>>(emptyList()) }
    var cardholder by remember { mutableStateOf("") }
    var cardBrand by remember { mutableStateOf("") }
    var cardNumber by remember { mutableStateOf("") }
    var expMonth by remember { mutableStateOf("") }
    var expYear by remember { mutableStateOf("") }
    var cvv by remember { mutableStateOf("") }
    var firstName by remember { mutableStateOf("") }
    var lastName by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }
    var phone by remember { mutableStateOf("") }
    var saving by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val fieldColors = vaultFieldColors()

    LaunchedEffect(itemId) {
        folders = runCatching { repository.listVaultFolders() }.getOrDefault(emptyList())
        if (itemId != null) {
            val item = repository.getVaultItem(itemId)
            type = item.item_type
            name = item.name
            username = item.username.orEmpty()
            password = item.password.orEmpty()
            uris = item.uris.joinToString("\n")
            totp = item.totp_secret.orEmpty()
            notes = item.notes.orEmpty()
            folderId = item.folder_id
            cardholder = item.cardholder_name.orEmpty()
            cardBrand = item.card_brand.orEmpty()
            cardNumber = item.card_number.orEmpty()
            expMonth = item.card_exp_month.orEmpty()
            expYear = item.card_exp_year.orEmpty()
            cvv = item.card_cvv.orEmpty()
            firstName = item.first_name.orEmpty()
            lastName = item.last_name.orEmpty()
            email = item.email.orEmpty()
            phone = item.phone.orEmpty()
        }
    }

    Column(
        Modifier
            .fillMaxSize()
            .background(HubBg)
            .padding(20.dp)
            .verticalScroll(rememberScrollState())
    ) {
        VaultBackLink("← Cancel", onBack)
        VaultPageHeader(
            eyebrow = "PASSWORD VAULT",
            title = if (itemId == null) "New item" else "Edit item"
        )
        Spacer(Modifier.height(4.dp))
        if (itemId == null) {
            val types = listOf("login", "note", "card", "identity")
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                types.forEach { t ->
                    VaultFilterChip(selected = type == t, onClick = { type = t }, label = t)
                }
            }
            Spacer(Modifier.height(12.dp))
        }
        OutlinedTextField(
            name, { name = it }, label = { Text("Name") },
            modifier = Modifier.fillMaxWidth(), singleLine = true, colors = fieldColors
        )
        if (folders.isNotEmpty()) {
            var expanded by remember { mutableStateOf(false) }
            ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { expanded = it }) {
                OutlinedTextField(
                    value = folders.firstOrNull { it.id == folderId }?.name ?: "No folder",
                    onValueChange = {},
                    readOnly = true,
                    label = { Text("Folder") },
                    modifier = Modifier.fillMaxWidth().menuAnchor(),
                    colors = fieldColors
                )
                ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                    DropdownMenuItem(text = { Text("No folder") }, onClick = { folderId = null; expanded = false })
                    folders.forEach { f ->
                        DropdownMenuItem(text = { Text(f.name) }, onClick = { folderId = f.id; expanded = false })
                    }
                }
            }
        }
        if (type == "login" || type == "note") {
            OutlinedTextField(
                username, { username = it }, label = { Text("Username") },
                modifier = Modifier.fillMaxWidth(), singleLine = true, colors = fieldColors
            )
            SecretField(password, { password = it }, "Password", Modifier.fillMaxWidth(), fieldColors)
            TextButton(onClick = {
                scope.launch {
                    runCatching { password = repository.generatePassword(VaultGenerateIn(length = 16)).value }
                }
            }) { Text("Generate password", color = VaultGold) }
            OutlinedTextField(
                uris, { uris = it }, label = { Text("Website / URI (one per line)") },
                modifier = Modifier.fillMaxWidth(), colors = fieldColors
            )
            SecretField(totp, { totp = it }, "Authenticator key", Modifier.fillMaxWidth(), fieldColors)
        }
        if (type == "card") {
            OutlinedTextField(
                cardholder, { cardholder = it }, label = { Text("Cardholder") },
                modifier = Modifier.fillMaxWidth(), colors = fieldColors
            )
            OutlinedTextField(
                cardBrand, { cardBrand = it }, label = { Text("Brand") },
                modifier = Modifier.fillMaxWidth(), colors = fieldColors
            )
            SecretField(cardNumber, { cardNumber = it }, "Number", Modifier.fillMaxWidth(), fieldColors)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    expMonth, { expMonth = it }, label = { Text("MM") },
                    modifier = Modifier.weight(1f), colors = fieldColors
                )
                OutlinedTextField(
                    expYear, { expYear = it }, label = { Text("YYYY") },
                    modifier = Modifier.weight(1f), colors = fieldColors
                )
                SecretField(cvv, { cvv = it }, "CVV", Modifier.weight(1f), fieldColors)
            }
        }
        if (type == "identity") {
            OutlinedTextField(
                firstName, { firstName = it }, label = { Text("First name") },
                modifier = Modifier.fillMaxWidth(), colors = fieldColors
            )
            OutlinedTextField(
                lastName, { lastName = it }, label = { Text("Last name") },
                modifier = Modifier.fillMaxWidth(), colors = fieldColors
            )
            OutlinedTextField(
                email, { email = it }, label = { Text("Email") },
                modifier = Modifier.fillMaxWidth(), colors = fieldColors
            )
            OutlinedTextField(
                phone, { phone = it }, label = { Text("Phone") },
                modifier = Modifier.fillMaxWidth(), colors = fieldColors
            )
        }
        OutlinedTextField(
            notes, { notes = it }, label = { Text("Notes") },
            modifier = Modifier.fillMaxWidth().height(120.dp), colors = fieldColors
        )
        if (error != null) Text(error!!, color = StampRed)
        Spacer(Modifier.height(16.dp))
        VaultPrimaryButton(
            text = if (saving) "Saving…" else "Save",
            onClick = {
                saving = true
                scope.launch {
                    runCatching {
                        val uriList = uris.split('\n', ',').map { it.trim() }.filter { it.isNotBlank() }
                        if (itemId == null) {
                            repository.createVaultItem(
                                VaultItemIn(
                                    folder_id = folderId, item_type = type, name = name.trim(),
                                    username = username.ifBlank { null }, password = password.ifBlank { null },
                                    totp_secret = totp.ifBlank { null }, uris = uriList, notes = notes.ifBlank { null },
                                    cardholder_name = cardholder.ifBlank { null }, card_brand = cardBrand.ifBlank { null },
                                    card_number = cardNumber.ifBlank { null }, card_exp_month = expMonth.ifBlank { null },
                                    card_exp_year = expYear.ifBlank { null }, card_cvv = cvv.ifBlank { null },
                                    first_name = firstName.ifBlank { null }, last_name = lastName.ifBlank { null },
                                    email = email.ifBlank { null }, phone = phone.ifBlank { null }
                                )
                            )
                        } else {
                            repository.updateVaultItem(
                                itemId,
                                VaultItemUpdate(
                                    folder_id = folderId, name = name.trim(),
                                    username = username, password = password.ifBlank { null },
                                    totp_secret = totp.ifBlank { null }, uris = uriList, notes = notes.ifBlank { null },
                                    cardholder_name = cardholder.ifBlank { null }, card_brand = cardBrand.ifBlank { null },
                                    card_number = cardNumber.ifBlank { null }, card_exp_month = expMonth.ifBlank { null },
                                    card_exp_year = expYear.ifBlank { null }, card_cvv = cvv.ifBlank { null },
                                    first_name = firstName.ifBlank { null }, last_name = lastName.ifBlank { null },
                                    email = email.ifBlank { null }, phone = phone.ifBlank { null }
                                )
                            )
                        }
                        onDone()
                    }.onFailure { error = it.message }
                    saving = false
                }
            },
            enabled = name.isNotBlank() && !saving
        )
    }
}

@Composable
private fun SecretField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    modifier: Modifier = Modifier,
    colors: TextFieldColors
) {
    var visible by remember { mutableStateOf(false) }
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        label = { Text(label) },
        modifier = modifier,
        singleLine = true,
        colors = colors,
        visualTransformation = if (visible) VisualTransformation.None else PasswordVisualTransformation(),
        trailingIcon = {
            IconButton(onClick = { visible = !visible }) {
                Icon(
                    if (visible) Icons.Filled.VisibilityOff else Icons.Filled.Visibility,
                    contentDescription = if (visible) "Hide $label" else "Show $label",
                    tint = VaultGold
                )
            }
        }
    )
}
