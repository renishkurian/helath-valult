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
import com.rklab.healthvault.ui.theme.*
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

    Column(Modifier.fillMaxSize().background(Paper).padding(20.dp).verticalScroll(rememberScrollState())) {
        TextButton(onClick = onBack) { Text("← Cancel", color = Navy) }
        Text(if (itemId == null) "New item" else "Edit item", style = MaterialTheme.typography.headlineMedium, color = Ink)
        Spacer(Modifier.height(12.dp))
        if (itemId == null) {
            val types = listOf("login", "note", "card", "identity")
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                types.forEach { t ->
                    FilterChip(selected = type == t, onClick = { type = t }, label = { Text(t) })
                }
            }
            Spacer(Modifier.height(12.dp))
        }
        OutlinedTextField(name, { name = it }, label = { Text("Name") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
        if (folders.isNotEmpty()) {
            var expanded by remember { mutableStateOf(false) }
            ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { expanded = it }) {
                OutlinedTextField(
                    value = folders.firstOrNull { it.id == folderId }?.name ?: "No folder",
                    onValueChange = {},
                    readOnly = true,
                    label = { Text("Folder") },
                    modifier = Modifier.fillMaxWidth().menuAnchor()
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
            OutlinedTextField(username, { username = it }, label = { Text("Username") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
            SecretField(password, { password = it }, "Password", Modifier.fillMaxWidth())
            TextButton(onClick = {
                scope.launch {
                    runCatching { password = repository.generatePassword(VaultGenerateIn(length = 16)).value }
                }
            }) { Text("Generate password", color = Navy) }
            OutlinedTextField(uris, { uris = it }, label = { Text("Website / URI (one per line)") }, modifier = Modifier.fillMaxWidth())
            SecretField(totp, { totp = it }, "Authenticator key", Modifier.fillMaxWidth())
        }
        if (type == "card") {
            OutlinedTextField(cardholder, { cardholder = it }, label = { Text("Cardholder") }, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(cardBrand, { cardBrand = it }, label = { Text("Brand") }, modifier = Modifier.fillMaxWidth())
            SecretField(cardNumber, { cardNumber = it }, "Number", Modifier.fillMaxWidth())
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(expMonth, { expMonth = it }, label = { Text("MM") }, modifier = Modifier.weight(1f))
                OutlinedTextField(expYear, { expYear = it }, label = { Text("YYYY") }, modifier = Modifier.weight(1f))
                SecretField(cvv, { cvv = it }, "CVV", Modifier.weight(1f))
            }
        }
        if (type == "identity") {
            OutlinedTextField(firstName, { firstName = it }, label = { Text("First name") }, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(lastName, { lastName = it }, label = { Text("Last name") }, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(email, { email = it }, label = { Text("Email") }, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(phone, { phone = it }, label = { Text("Phone") }, modifier = Modifier.fillMaxWidth())
        }
        OutlinedTextField(notes, { notes = it }, label = { Text("Notes") }, modifier = Modifier.fillMaxWidth().height(120.dp))
        if (error != null) Text(error!!, color = StampRed)
        Spacer(Modifier.height(16.dp))
        Button(
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
            enabled = name.isNotBlank() && !saving,
            modifier = Modifier.fillMaxWidth(),
            colors = ButtonDefaults.buttonColors(containerColor = Navy)
        ) { Text(if (saving) "Saving…" else "Save", color = TextWhite) }
    }
}

@Composable
private fun SecretField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    modifier: Modifier = Modifier
) {
    var visible by remember { mutableStateOf(false) }
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        label = { Text(label) },
        modifier = modifier,
        singleLine = true,
        visualTransformation = if (visible) VisualTransformation.None else PasswordVisualTransformation(),
        trailingIcon = {
            IconButton(onClick = { visible = !visible }) {
                Icon(
                    if (visible) Icons.Filled.VisibilityOff else Icons.Filled.Visibility,
                    contentDescription = if (visible) "Hide $label" else "Show $label"
                )
            }
        }
    )
}
