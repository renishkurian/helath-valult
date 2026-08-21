package com.rklab.healthvault.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.rklab.healthvault.data.model.FamilyShareParty
import com.rklab.healthvault.data.model.FamilyShareTargetOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.theme.HubText
import com.rklab.healthvault.ui.theme.HubTextDim
import com.rklab.healthvault.ui.theme.StampRed
import com.rklab.healthvault.ui.theme.VaultGold
import kotlinx.coroutines.launch

/**
 * Dialog to grant a family member view/edit access to a password, health doc, or locker item.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FamilyShareDialog(
    repository: HealthVaultRepository,
    resourceType: String,
    resourceId: String,
    sharedWith: List<FamilyShareParty>,
    onDismiss: () -> Unit,
    onChanged: () -> Unit,
) {
    val scope = rememberCoroutineScope()
    var targets by remember { mutableStateOf<List<FamilyShareTargetOut>>(emptyList()) }
    var shares by remember { mutableStateOf(sharedWith) }
    var selectedUserId by remember { mutableStateOf<String?>(null) }
    var permission by remember { mutableStateOf("view") }
    var targetExpanded by remember { mutableStateOf(false) }
    var permExpanded by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(resourceId) {
        runCatching { repository.listFamilyShareTargets() }
            .onSuccess { targets = it }
            .onFailure { error = it.message }
        runCatching { repository.listFamilyShares(resourceType, resourceId) }
            .onSuccess {
                shares = it.map { s ->
                    FamilyShareParty(
                        user_id = s.to_user_id,
                        full_name = s.to_full_name,
                        email = s.to_email,
                        permission = s.permission,
                        share_id = s.id,
                    )
                }
            }
    }

    val selectedLabel = targets.firstOrNull { it.user_id == selectedUserId }?.let {
        "${it.full_name} (${it.email})"
    } ?: "Choose family member…"

    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        title = { Text("Share with family") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(
                    "They will see this entry in their account. Pick view or edit.",
                    color = HubTextDim,
                    style = MaterialTheme.typography.bodySmall,
                )
                if (shares.isNotEmpty()) {
                    Text("Shared with", color = VaultGold, style = MaterialTheme.typography.labelMedium)
                    shares.forEach { s ->
                        Row(
                            Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Column(Modifier.weight(1f)) {
                                Text(s.full_name.ifBlank { s.user_id }, color = HubText)
                                Text(s.permission, color = HubTextDim, style = MaterialTheme.typography.bodySmall)
                            }
                            TextButton(
                                enabled = !busy,
                                onClick = {
                                    busy = true
                                    error = null
                                    scope.launch {
                                        runCatching {
                                            repository.revokeFamilyShare(resourceType, resourceId, s.user_id)
                                        }.onSuccess {
                                            shares = shares.filterNot { it.user_id == s.user_id }
                                            onChanged()
                                        }.onFailure { error = it.message }
                                        busy = false
                                    }
                                },
                            ) { Text("Revoke", color = StampRed) }
                        }
                    }
                    Spacer(Modifier.height(4.dp))
                }
                ExposedDropdownMenuBox(expanded = targetExpanded, onExpandedChange = { targetExpanded = it }) {
                    OutlinedTextField(
                        value = selectedLabel,
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Family member") },
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(targetExpanded) },
                        modifier = Modifier.menuAnchor().fillMaxWidth(),
                    )
                    ExposedDropdownMenu(expanded = targetExpanded, onDismissRequest = { targetExpanded = false }) {
                        targets.forEach { t ->
                            DropdownMenuItem(
                                text = { Text("${t.full_name} (${t.email})") },
                                onClick = {
                                    selectedUserId = t.user_id
                                    targetExpanded = false
                                },
                            )
                        }
                    }
                }
                ExposedDropdownMenuBox(expanded = permExpanded, onExpandedChange = { permExpanded = it }) {
                    OutlinedTextField(
                        value = if (permission == "edit") "View & edit" else "View only",
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Permission") },
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(permExpanded) },
                        modifier = Modifier.menuAnchor().fillMaxWidth(),
                    )
                    ExposedDropdownMenu(expanded = permExpanded, onDismissRequest = { permExpanded = false }) {
                        DropdownMenuItem(
                            text = { Text("View only") },
                            onClick = { permission = "view"; permExpanded = false },
                        )
                        DropdownMenuItem(
                            text = { Text("View & edit") },
                            onClick = { permission = "edit"; permExpanded = false },
                        )
                    }
                }
                if (error != null) Text(error!!, color = StampRed, style = MaterialTheme.typography.bodySmall)
            }
        },
        confirmButton = {
            TextButton(
                enabled = !busy && selectedUserId != null,
                onClick = {
                    val to = selectedUserId ?: return@TextButton
                    busy = true
                    error = null
                    scope.launch {
                        runCatching {
                            repository.upsertFamilyShare(resourceType, resourceId, to, permission)
                        }.onSuccess { row ->
                            val party = FamilyShareParty(
                                user_id = row.to_user_id,
                                full_name = row.to_full_name,
                                email = row.to_email,
                                permission = row.permission,
                                share_id = row.id,
                            )
                            shares = shares.filterNot { it.user_id == party.user_id } + party
                            selectedUserId = null
                            onChanged()
                        }.onFailure { error = it.message }
                        busy = false
                    }
                },
            ) { Text(if (busy) "Saving…" else "Share", color = VaultGold) }
        },
        dismissButton = {
            TextButton(onClick = { if (!busy) onDismiss() }) {
                Text("Close", color = HubTextDim)
            }
        },
    )
}

@Composable
fun FamilyShareBadge(sharedFrom: FamilyShareParty?, sharedWith: List<FamilyShareParty>, isOwned: Boolean) {
    when {
        sharedFrom != null -> {
            Text(
                "Shared by ${sharedFrom.full_name.ifBlank { "family" }} · ${sharedFrom.permission}",
                color = HubTextDim,
                style = MaterialTheme.typography.bodySmall,
            )
        }
        isOwned && sharedWith.isNotEmpty() -> {
            Text(
                "Shared with ${sharedWith.joinToString { it.full_name.ifBlank { "member" } }}",
                color = HubTextDim,
                style = MaterialTheme.typography.bodySmall,
            )
        }
    }
}
