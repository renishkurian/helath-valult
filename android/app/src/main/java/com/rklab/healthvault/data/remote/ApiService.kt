package com.rklab.healthvault.data.remote

import com.rklab.healthvault.data.model.*
import okhttp3.MultipartBody
import okhttp3.RequestBody
import okhttp3.ResponseBody
import retrofit2.Response
import retrofit2.http.*

interface ApiService {

    // ---------- Auth ----------
    @FormUrlEncoded
    @POST("auth/login")
    suspend fun login(
        @Field("username") email: String,
        @Field("password") password: String
    ): LoginResponse

    @POST("auth/register")
    suspend fun register(@Body body: RegisterRequest): LoginResponse

    @GET("auth/me")
    suspend fun me(): UserOut

    // ---------- People ----------
    @GET("people")
    suspend fun listPeople(): List<PersonOut>

    @POST("people")
    suspend fun addPerson(@Body body: PersonCreate): PersonOut

    @DELETE("people/{id}")
    suspend fun deletePerson(@Path("id") id: String): Response<Unit>

    // ---------- Cards ----------
    @GET("cards")
    suspend fun listCards(@Query("person_id") personId: String? = null): List<CardOut>

    @POST("cards")
    suspend fun addCard(@Body body: CardCreate): CardOut

    @DELETE("cards/{id}")
    suspend fun deleteCard(@Path("id") id: String): Response<Unit>

    // ---------- Documents ----------
    @GET("documents")
    suspend fun listDocuments(
        @Query("person_id") personId: String? = null,
        @Query("category") category: String? = null
    ): List<DocumentOut>

    @Multipart
    @POST("documents")
    suspend fun uploadDocument(
        @Part("person_id") personId: RequestBody,
        @Part("category") category: RequestBody,
        @Part("custom_category") customCategory: RequestBody?,
        @Part("title") title: RequestBody,
        @Part("hospital_name") hospitalName: RequestBody?,
        @Part("doc_date") docDate: RequestBody?,
        @Part("notes") notes: RequestBody?,
        @Part files: List<MultipartBody.Part>  // supports 1..N files
    ): DocumentOut

    @PUT("documents/{id}")
    suspend fun updateDocument(
        @Path("id") id: String,
        @Body body: DocumentUpdate
    ): DocumentOut

    @GET("documents/{id}/files")
    suspend fun listDocumentFiles(@Path("id") id: String): List<DocumentFileOut>

    @Streaming
    @GET("documents/{id}/download")
    suspend fun downloadDocument(@Path("id") id: String): ResponseBody

    @Streaming
    @GET("documents/{id}/files/{fileId}/download")
    suspend fun downloadDocumentFile(
        @Path("id") id: String,
        @Path("fileId") fileId: String
    ): ResponseBody

    @DELETE("documents/{id}")
    suspend fun deleteDocument(@Path("id") id: String): Response<Unit>

    // ---------- Reminders ----------
    @GET("reminders")
    suspend fun listReminders(
        @Query("person_id") personId: String? = null,
        @Query("upcoming_only") upcomingOnly: Boolean = false
    ): List<ReminderOut>

    @POST("reminders")
    suspend fun addReminder(@Body body: ReminderCreate): ReminderOut

    @DELETE("reminders/{id}")
    suspend fun deleteReminder(@Path("id") id: String): Response<Unit>

    // ---------- Search ----------
    @GET("search")
    suspend fun search(@Query("q") query: String, @Query("person_id") personId: String? = null): SearchResult
}
