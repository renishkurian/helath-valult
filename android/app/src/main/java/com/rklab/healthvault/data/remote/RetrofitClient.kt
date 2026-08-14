package com.rklab.healthvault.data.remote

import com.google.gson.GsonBuilder
import com.google.gson.TypeAdapter
import com.google.gson.stream.JsonReader
import com.google.gson.stream.JsonToken
import com.google.gson.stream.JsonWriter
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

        val gsonBuilder = GsonBuilder()
            .registerTypeAdapter(Boolean::class.java, FlexibleBooleanAdapter)
            .registerTypeAdapter(Boolean::class.javaObjectType, FlexibleBooleanAdapter)
        Boolean::class.javaPrimitiveType?.let { gsonBuilder.registerTypeAdapter(it, FlexibleBooleanAdapter) }
        val gson = gsonBuilder.create()

        val client = OkHttpClient.Builder()
            .addInterceptor(DynamicBaseUrlInterceptor(serverConfig))
            .addInterceptor(AuthInterceptor(tokenManager))
            .authenticator(TokenRefreshAuthenticator(tokenManager, serverConfig))
            .addInterceptor(logging)
            .connectTimeout(20, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .writeTimeout(30, TimeUnit.SECONDS)
            .build()

        return Retrofit.Builder()
            .baseUrl(PLACEHOLDER_BASE_URL)
            .client(client)
            .addConverterFactory(GsonConverterFactory.create(gson))
            .build()
            .create(ApiService::class.java)
    }
}

/** SQLite/legacy payloads sometimes send 0/1 instead of true/false. */
private object FlexibleBooleanAdapter : TypeAdapter<Boolean>() {
    override fun write(out: JsonWriter, value: Boolean?) {
        if (value == null) out.nullValue() else out.value(value)
    }

    override fun read(reader: JsonReader): Boolean {
        return when (reader.peek()) {
            JsonToken.NULL -> {
                reader.nextNull()
                false
            }
            JsonToken.BOOLEAN -> reader.nextBoolean()
            JsonToken.NUMBER -> reader.nextInt() != 0
            JsonToken.STRING -> {
                val raw = reader.nextString()
                raw.equals("true", true) || raw == "1"
            }
            else -> {
                reader.skipValue()
                false
            }
        }
    }
}
