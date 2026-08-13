package com.rklab.healthvault.autofill

import android.app.assist.AssistStructure
import android.os.CancellationSignal
import android.service.autofill.AutofillService
import android.service.autofill.Dataset
import android.service.autofill.FillCallback
import android.service.autofill.FillRequest
import android.service.autofill.FillResponse
import android.service.autofill.SaveCallback
import android.service.autofill.SaveRequest
import android.view.autofill.AutofillId
import android.view.autofill.AutofillValue
import android.widget.RemoteViews
import com.rklab.healthvault.data.VaultAutofillStore

class VaultAutofillService : AutofillService() {

    override fun onFillRequest(
        request: FillRequest,
        cancellationSignal: CancellationSignal,
        callback: FillCallback
    ) {
        val structure = request.fillContexts.lastOrNull()?.structure
        if (structure == null) {
            callback.onSuccess(null)
            return
        }
        val parsed = parse(structure)
        if (parsed.usernameId == null && parsed.passwordId == null) {
            callback.onSuccess(null)
            return
        }
        val logins = VaultAutofillStore.load(this)
        val matches = logins.filter {
            VaultAutofillStore.matches(it, parsed.webDomain, parsed.packageName)
        }.ifEmpty { logins.take(8) }
        if (matches.isEmpty()) {
            callback.onSuccess(null)
            return
        }
        val response = FillResponse.Builder()
        for (login in matches) {
            val presentation = RemoteViews(packageName, android.R.layout.simple_list_item_1).apply {
                setTextViewText(android.R.id.text1, "${login.name} · ${login.username ?: ""}")
            }
            val dataset = Dataset.Builder(presentation)
            parsed.usernameId?.let {
                dataset.setValue(it, AutofillValue.forText(login.username.orEmpty()), presentation)
            }
            parsed.passwordId?.let {
                dataset.setValue(it, AutofillValue.forText(login.password.orEmpty()), presentation)
            }
            response.addDataset(dataset.build())
        }
        callback.onSuccess(response.build())
    }

    override fun onSaveRequest(request: SaveRequest, callback: SaveCallback) {
        callback.onSuccess()
    }

    private data class Parsed(
        val usernameId: AutofillId?,
        val passwordId: AutofillId?,
        val webDomain: String?,
        val packageName: String?
    )

    private fun parse(structure: AssistStructure): Parsed {
        var username: AutofillId? = null
        var password: AutofillId? = null
        var webDomain: String? = null
        val pkg = structure.activityComponent?.packageName
        for (i in 0 until structure.windowNodeCount) {
            val root = structure.getWindowNodeAt(i).rootViewNode
            walk(root) { node ->
                if (webDomain == null && !node.webDomain.isNullOrBlank()) {
                    webDomain = node.webDomain
                }
                val hints = (node.autofillHints?.toList().orEmpty() + listOfNotNull(node.htmlInfo?.tag))
                    .joinToString(" ").lowercase()
                val id = (node.idEntry ?: "").lowercase()
                val hint = (node.hint ?: "").lowercase()
                val blob = "$hints $id $hint"
                when {
                    username == null && (
                        blob.contains("username") || blob.contains("email") ||
                            blob.contains("login") || hints.contains("username") ||
                            hints.contains("email")
                        ) && !blob.contains("password") -> username = node.autofillId
                    password == null && (
                        blob.contains("password") || hints.contains("password") ||
                            node.inputType and 0x00000080 != 0
                        ) -> password = node.autofillId
                }
            }
        }
        return Parsed(username, password, webDomain, pkg)
    }

    private fun walk(node: AssistStructure.ViewNode, visit: (AssistStructure.ViewNode) -> Unit) {
        visit(node)
        for (i in 0 until node.childCount) walk(node.getChildAt(i), visit)
    }
}
