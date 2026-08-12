package com.rklab.healthvault.data.remote

import com.rklab.healthvault.data.TokenManager
import okhttp3.Interceptor
import okhttp3.Response

class AuthInterceptor(private val tokenManager: TokenManager) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val original = chain.request()

        // Don't attach a stale token to the login/register calls themselves.
        val path = original.url.encodedPath
        if (path.endsWith("/auth/login") || path.endsWith("/auth/register")) {
            return chain.proceed(original)
        }

        val token = tokenManager.getAccessToken()
        val request = if (token != null) {
            original.newBuilder().addHeader("Authorization", "Bearer $token").build()
        } else {
            original
        }
        return chain.proceed(request)
    }
}
