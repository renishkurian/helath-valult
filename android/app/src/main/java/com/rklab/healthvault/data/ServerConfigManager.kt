package com.rklab.healthvault.data

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.util.concurrent.TimeUnit

/**
 * Holds the user-configured server base URL (e.g. "http://192.168.0.50:8000/"
 * or "https://marketmind.rklab.online/health-vault-api/"), set from the
 * in-app server setup screen — same idea as Immich's "configure server"
 * flow. Stored in plain SharedPreferences (synchronous, and not sensitive —
 * unlike the JWT, a server address alone isn't a secret) so it can be read
 * synchronously from the network interceptor without blocking on DataStore.
 */
class ServerConfigManager(context: Context) {

    private val prefs = context.getSharedPreferences("healthvault_server_config", Context.MODE_PRIVATE)

    fun getServerUrl(): String? = prefs.getString(KEY_URL, null)

    fun isConfigured(): Boolean = !getServerUrl().isNullOrBlank()

    fun setServerUrl(rawUrl: String) {
        prefs.edit().putString(KEY_URL, normalize(rawUrl)).apply()
    }

    fun clear() {
        prefs.edit().remove(KEY_URL).apply()
    }

    /** Ensures a scheme and a trailing slash, e.g. "192.168.0.50:8000" -> "http://192.168.0.50:8000/" */
    fun normalize(input: String): String {
        var url = input.trim()
        if (!url.startsWith("http://") && !url.startsWith("https://")) {
            url = "http://$url"
        }
        if (!url.endsWith("/")) url += "/"
        return url
    }

    /**
     * One-off connectivity check against {url}/health. Uses its own throwaway
     * OkHttpClient — deliberately doesn't touch the saved config or the
     * app-wide Retrofit client, so testing a candidate URL never affects
     * in-flight requests elsewhere in the app.
     */
    suspend fun testConnection(rawUrl: String): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            val url = normalize(rawUrl)
            val client = OkHttpClient.Builder()
                .connectTimeout(6, TimeUnit.SECONDS)
                .readTimeout(6, TimeUnit.SECONDS)
                .build()
            val request = Request.Builder().url("${url}health").get().build()
            client.newCall(request).execute().use { response ->
                if (response.isSuccessful) Result.success(Unit)
                else Result.failure(Exception("Server responded with ${response.code}"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    companion object {
        private const val KEY_URL = "server_base_url"
    }
}
