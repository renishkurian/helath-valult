package com.rklab.healthvault.data.remote

import com.google.gson.Gson
import com.rklab.healthvault.data.ServerConfigManager
import com.rklab.healthvault.data.TokenManager
import com.rklab.healthvault.data.model.LoginResponse
import com.rklab.healthvault.data.model.RefreshIn
import okhttp3.Authenticator
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.Route
import java.util.concurrent.TimeUnit

/**
 * Access tokens expire in about an hour. Without this, Settings (and Drive /
 * 2FA status) fail silently and look "off" even when the website is connected.
 */
class TokenRefreshAuthenticator(
    private val tokenManager: TokenManager,
    private val serverConfig: ServerConfigManager
) : Authenticator {

    private val lock = Any()
    private val gson = Gson()
    private val refreshClient = OkHttpClient.Builder()
        .addInterceptor(DynamicBaseUrlInterceptor(serverConfig))
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .build()

    override fun authenticate(route: Route?, response: Response): Request? {
        val path = response.request.url.encodedPath
        if (path.endsWith("/auth/login") || path.endsWith("/auth/register") || path.endsWith("/auth/refresh")) {
            return null
        }
        if (responseCount(response) >= 2) return null

        val newAccess = synchronized(lock) {
            val current = tokenManager.getAccessToken()
            val failed = response.request.header("Authorization")
                ?.removePrefix("Bearer ")
                ?.trim()
            if (!current.isNullOrBlank() && current != failed) current
            else refreshBlocking()
        } ?: return null

        return response.request.newBuilder()
            .header("Authorization", "Bearer $newAccess")
            .build()
    }

    private fun refreshBlocking(): String? {
        val refresh = tokenManager.getRefreshToken()?.takeIf { it.isNotBlank() } ?: return null
        val encoded = java.net.URLEncoder.encode(refresh, Charsets.UTF_8.name())
        val json = gson.toJson(RefreshIn(refresh))
        val request = Request.Builder()
            .url("http://localhost/auth/refresh?refresh_token=$encoded")
            .post(json.toRequestBody(JSON))
            .build()
        return try {
            refreshClient.newCall(request).execute().use { res ->
                if (!res.isSuccessful) return null
                val body = res.body?.string().orEmpty()
                val parsed = gson.fromJson(body, LoginResponse::class.java) ?: return null
                if (parsed.access_token.isBlank()) return null
                tokenManager.saveTokens(parsed.access_token, parsed.refresh_token.ifBlank { refresh })
                parsed.access_token
            }
        } catch (_: Exception) {
            null
        }
    }

    private fun responseCount(response: Response): Int {
        var n = 1
        var prior = response.priorResponse
        while (prior != null) {
            n++
            prior = prior.priorResponse
        }
        return n
    }

    companion object {
        private val JSON = "application/json; charset=utf-8".toMediaType()
    }
}
