package com.rklab.healthvault.data

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch

private val Context.dataStore by preferencesDataStore(name = "healthvault_prefs")

/**
 * Access/refresh tokens are short-lived secrets, so they're kept in
 * EncryptedSharedPreferences (backed by the Android Keystore) rather than
 * plain DataStore — consistent with "medical data must be encrypted": a
 * stolen token is a skeleton key to everything else.
 */
class TokenManager(private val context: Context) {

    private val masterKey = MasterKey.Builder(context)
        .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
        .build()

    private val encryptedPrefs = EncryptedSharedPreferences.create(
        context,
        "healthvault_secure_prefs",
        masterKey,
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
    )

    fun saveTokens(access: String, refresh: String) {
        encryptedPrefs.edit()
            .putString(KEY_ACCESS, access)
            .putString(KEY_REFRESH, refresh)
            .apply()
    }

    fun getAccessToken(): String? = encryptedPrefs.getString(KEY_ACCESS, null)
    fun getRefreshToken(): String? = encryptedPrefs.getString(KEY_REFRESH, null)

    fun clear() {
        encryptedPrefs.edit().clear().apply()
        CoroutineScope(Dispatchers.IO).launch {
            context.dataStore.edit { it.clear() }
        }
    }

    // Non-sensitive UI prefs (e.g. last selected person) can live in plain DataStore.
    suspend fun setActivePerson(personId: String) {
        context.dataStore.edit { it[ACTIVE_PERSON] = personId }
    }

    fun activePersonFlow(): Flow<String?> =
        context.dataStore.data.map { it[ACTIVE_PERSON] }

    val activePersonId: Flow<String?>
        get() = activePersonFlow()

    suspend fun setActivePersonId(id: String) {
        context.dataStore.edit { it[ACTIVE_PERSON] = id }
    }

    suspend fun setBiometricEnabled(enabled: Boolean) {
        context.dataStore.edit { it[BIOMETRIC_ENABLED] = enabled }
    }

    val isBiometricEnabled: Flow<Boolean> =
        context.dataStore.data.map { it[BIOMETRIC_ENABLED] ?: false }

    companion object {
        private const val KEY_ACCESS = "access_token"
        private const val KEY_REFRESH = "refresh_token"
        private val ACTIVE_PERSON = stringPreferencesKey("active_person_id")
        private val BIOMETRIC_ENABLED = androidx.datastore.preferences.core.booleanPreferencesKey("biometric_enabled")
    }
}
