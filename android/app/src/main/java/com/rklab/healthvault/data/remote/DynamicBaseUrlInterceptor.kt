package com.rklab.healthvault.data.remote

import com.rklab.healthvault.data.ServerConfigManager
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.Interceptor
import okhttp3.Response

/**
 * Retrofit requires a baseUrl at construction time, but we want the server
 * address to be changeable at runtime from the settings screen without
 * rebuilding Retrofit/OkHttp (which would also orphan any ViewModels that
 * already hold an ApiService reference). So Retrofit is built once against
 * a fixed placeholder, and this interceptor rewrites every outgoing
 * request's scheme/host/port — and prepends any base path from the
 * configured URL (useful if you're reverse-proxying at a sub-path like
 * marketmind.rklab.online/health-vault-api/) — to point at whatever server
 * is currently configured.
 */
class DynamicBaseUrlInterceptor(private val serverConfig: ServerConfigManager) : Interceptor {

    override fun intercept(chain: Interceptor.Chain): Response {
        val original = chain.request()
        val configured = serverConfig.getServerUrl()

        if (configured.isNullOrBlank()) {
            // No server configured yet (shouldn't normally happen — the nav
            // graph routes to server setup first — but fail gracefully
            // rather than crash if it ever does).
            return chain.proceed(original)
        }

        val configuredUrl: HttpUrl = configured.toHttpUrlOrNull() ?: return chain.proceed(original)

        val basePathSegments = configuredUrl.pathSegments.filter { it.isNotEmpty() }
        val requestPathSegments = original.url.pathSegments.filter { it.isNotEmpty() }

        val newUrlBuilder = HttpUrl.Builder()
            .scheme(configuredUrl.scheme)
            .host(configuredUrl.host)
            .port(configuredUrl.port)

        (basePathSegments + requestPathSegments).forEach { segment ->
            newUrlBuilder.addPathSegment(segment)
        }
        original.url.encodedQuery?.let { newUrlBuilder.encodedQuery(it) }

        val newRequest = original.newBuilder().url(newUrlBuilder.build()).build()
        return chain.proceed(newRequest)
    }
}
