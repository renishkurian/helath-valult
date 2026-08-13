package com.rklab.healthvault.data

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import com.rklab.healthvault.data.model.VaultItemOut

data class AutofillLogin(
    val id: String,
    val name: String,
    val username: String?,
    val password: String?,
    val uris: List<String>
)

object VaultAutofillStore {
    private const val PREFS = "vault_autofill_cache"
    private const val KEY = "logins"
    private val gson = Gson()

    private fun prefs(context: Context) = EncryptedSharedPreferences.create(
        context,
        PREFS,
        MasterKey.Builder(context).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
    )

    fun save(context: Context, items: List<VaultItemOut>) {
        val logins = items.filter { it.item_type == "login" && it.deleted_at == null }.map {
            AutofillLogin(it.id, it.name, it.username, it.password, it.uris)
        }
        prefs(context).edit().putString(KEY, gson.toJson(logins)).apply()
    }

    fun load(context: Context): List<AutofillLogin> {
        val raw = prefs(context).getString(KEY, null) ?: return emptyList()
        val type = object : TypeToken<List<AutofillLogin>>() {}.type
        return runCatching { gson.fromJson<List<AutofillLogin>>(raw, type) }.getOrNull().orEmpty()
    }

    fun clear(context: Context) {
        prefs(context).edit().remove(KEY).apply()
    }

    fun matches(login: AutofillLogin, webDomain: String?, packageName: String?): Boolean {
        val hay = (login.uris + login.name).joinToString(" ").lowercase()
        val domain = webDomain?.lowercase()?.removePrefix("www.")
        if (!domain.isNullOrBlank() && hay.contains(domain)) return true
        val pkg = packageName?.lowercase()
        return !pkg.isNullOrBlank() && hay.contains(pkg)
    }
}
