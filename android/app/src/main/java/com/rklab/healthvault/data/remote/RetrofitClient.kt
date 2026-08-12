package com.rklab.healthvault.data.remote

import com.rklab.healthvault.BuildConfig
import com.rklab.healthvault.data.ServerConfigManager
import com.rklab.healthvault.data.TokenManager
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

object RetrofitClient {

    // Never actually used for a real request — DynamicBaseUrlInterceptor
    // rewrites scheme/host/port/base-path on every call to whatever server
    // is currently configured. Retrofit just needs *a* valid absolute URL
    // to be built with.
    private const val PLACEHOLDER_BASE_URL = "http://localhost/"

    fun create(tokenManager: TokenManager, serverConfig: ServerConfigManager): ApiService {
        val logging = HttpLoggingInterceptor().apply {
            level = if (BuildConfig.DEBUG) HttpLoggingInterceptor.Level.BASIC
                    else HttpLoggingInterceptor.Level.NONE
        }

        val client = OkHttpClient.Builder()
            .addInterceptor(DynamicBaseUrlInterceptor(serverConfig))
            .addInterceptor(AuthInterceptor(tokenManager))
            .addInterceptor(logging)
            .connectTimeout(20, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .writeTimeout(30, TimeUnit.SECONDS)
            .build()

        return Retrofit.Builder()
            .baseUrl(PLACEHOLDER_BASE_URL)
            .client(client)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(ApiService::class.java)
    }
}
