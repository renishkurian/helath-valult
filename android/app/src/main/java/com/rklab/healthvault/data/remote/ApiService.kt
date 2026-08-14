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

    @POST("auth/invite")
    suspend fun inviteViewer(@Body body: InviteViewerRequest): UserOut

    @GET("auth/members")
    suspend fun listVaultMembers(): List<UserOut>

    @DELETE("auth/members/{id}")
    suspend fun removeVaultMember(@Path("id") id: String): Response<Unit>

    @POST("auth/devices")
    suspend fun registerDevice(@Body body: DeviceTokenIn): Response<Unit>

    @GET("auth/login-challenges")
    suspend fun listLoginChallenges(): List<LoginChallengeOut>

    @GET("auth/login-challenges/{id}")
    suspend fun getLoginChallenge(@Path("id") id: String): LoginChallengeOut

    @POST("auth/login-challenges/{id}/approve")
    suspend fun approveLoginChallenge(@Path("id") id: String): Response<Unit>

    @POST("auth/login-challenges/{id}/deny")
    suspend fun denyLoginChallenge(@Path("id") id: String): Response<Unit>

    @POST("auth/totp/setup")
    suspend fun totpSetup(): TotpSetupOut

    @POST("auth/totp/enable")
    suspend fun totpEnable(@Body body: TotpVerifyIn): Response<Unit>

    @POST("auth/totp/disable")
    suspend fun totpDisable(@Body body: TotpVerifyIn): Response<Unit>

    @POST("auth/app-approve")
    suspend fun setAppApprove(@Body body: AppApproveIn): UserOut

    @POST("auth/totp/verify")
    suspend fun totpVerify(@Body body: TotpVerifyIn): LoginResponse

    // ---------- People ----------
    @GET("people")
    suspend fun listPeople(): List<PersonOut>

    @POST("people")
    suspend fun addPerson(@Body body: PersonCreate): PersonOut

    @PATCH("people/{id}")
    suspend fun updatePerson(@Path("id") id: String, @Body body: PersonUpdate): PersonOut

    @POST("people/{id}/ice")
    suspend fun enableIce(@Path("id") id: String): PersonOut

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
        @Query("category") category: String? = null,
        @Query("tag") tag: String? = null,
        @Query("year") year: String? = null,
        @Query("hospital") hospital: String? = null,
        @Query("expiring") expiring: Boolean = false,
        @Query("favorite") favorite: Boolean = false
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
        @Part("expiry_date") expiryDate: RequestBody?,
        @Part("tags") tags: RequestBody?,
        @Part files: List<MultipartBody.Part>  // supports 1..N files
    ): DocumentOut

    @Multipart
    @POST("documents/{id}/versions")
    suspend fun replaceDocumentVersion(
        @Path("id") id: String,
        @Part("title") title: RequestBody?,
        @Part("notes") notes: RequestBody?,
        @Part files: List<MultipartBody.Part>
    ): DocumentOut

    @GET("documents/{id}/versions")
    suspend fun listDocumentVersions(@Path("id") id: String): List<DocumentVersionOut>

    @Streaming
    @GET("documents/{id}/versions/{versionId}/files/{index}/download")
    suspend fun downloadDocumentVersionFile(
        @Path("id") id: String,
        @Path("versionId") versionId: String,
        @Path("index") index: Int
    ): ResponseBody

    @PUT("documents/{id}")
    suspend fun updateDocument(
        @Path("id") id: String,
        @Body body: DocumentUpdate
    ): DocumentOut

    @GET("documents/{id}")
    suspend fun getDocument(@Path("id") id: String): DocumentOut

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

    @POST("documents/{id}/favorite")
    suspend fun favoriteDocument(@Path("id") id: String): Response<Unit>

    @DELETE("documents/{id}/favorite")
    suspend fun unfavoriteDocument(@Path("id") id: String): Response<Unit>

    @POST("documents/bulk/delete")
    suspend fun bulkDeleteDocuments(@Body body: BulkIds): Response<Unit>

    @POST("documents/bulk/tag")
    suspend fun bulkTagDocuments(@Body body: BulkIds): List<DocumentOut>

    @GET("documents/recent")
    suspend fun recentDocuments(): List<DocumentOut>

    // ---------- Reminders ----------
    @GET("reminders")
    suspend fun listReminders(
        @Query("person_id") personId: String? = null,
        @Query("upcoming_only") upcomingOnly: Boolean = false
    ): List<ReminderOut>

    @POST("reminders")
    suspend fun addReminder(@Body body: ReminderCreate): ReminderOut

    @POST("reminders/{id}/complete")
    suspend fun completeReminder(@Path("id") id: String): ReminderOut

    @DELETE("reminders/{id}")
    suspend fun deleteReminder(@Path("id") id: String): Response<Unit>

    // ---------- Search ----------
    @GET("search")
    suspend fun search(@Query("q") query: String, @Query("person_id") personId: String? = null): SearchResult

    // ---------- Share links ----------
    @POST("share")
    suspend fun createShareLink(@Body body: ShareLinkCreate): ShareLinkOut

    @GET("share/mine")
    suspend fun listMyShareLinks(@Query("document_id") documentId: String? = null): List<ShareLinkOut>

    @GET("share/{id}")
    suspend fun getShareLink(@Path("id") id: String): ShareLinkDetailOut

    @DELETE("share/{id}")
    suspend fun revokeShareLink(@Path("id") id: String): Response<Unit>

    // ---------- Audit log ----------
    @GET("audit")
    suspend fun listAuditLog(
        @Query("document_id") documentId: String? = null,
        @Query("limit") limit: Int = 100
    ): List<AuditLogOut>

    // ---------- Backup ----------
    @Streaming
    @GET("backup/export")
    suspend fun exportBackup(
        @Query("person_id") personId: String? = null,
        @Query("password") password: String? = null
    ): ResponseBody

    @Multipart
    @POST("backup/restore")
    suspend fun restoreBackup(
        @Part file: MultipartBody.Part,
        @Part("password") password: RequestBody?
    ): okhttp3.ResponseBody

    @GET("labs/trends")
    suspend fun labTrends(
        @Query("person_id") personId: String,
        @Query("metric") metric: String? = null
    ): List<LabTrend>

    @GET("labs/alerts")
    suspend fun labAlerts(@Query("person_id") personId: String): List<LabAlert>

    @POST("share/packs")
    suspend fun createSharePack(@Body body: SharePackCreate): SharePackOut

    @GET("share/packs")
    suspend fun listSharePacks(): List<SharePackOut>

    @DELETE("share/packs/{id}")
    suspend fun revokeSharePack(@Path("id") id: String): Response<Unit>

    @GET("medicines")
    suspend fun listMedicines(@Query("person_id") personId: String): List<MedicineOut>
    @POST("medicines")
    suspend fun addMedicine(@Body body: MedicineIn): MedicineOut
    @DELETE("medicines/{id}")
    suspend fun deleteMedicine(@Path("id") id: String): Response<Unit>

    @GET("vaccinations")
    suspend fun listVaccinations(@Query("person_id") personId: String): List<VaccinationOut>
    @POST("vaccinations")
    suspend fun addVaccination(@Body body: VaccinationIn): VaccinationOut
    @DELETE("vaccinations/{id}")
    suspend fun deleteVaccination(@Path("id") id: String): Response<Unit>

    @GET("visits")
    suspend fun listVisits(@Query("person_id") personId: String): List<VisitOut>
    @POST("visits")
    suspend fun addVisit(@Body body: VisitIn): VisitOut
    @DELETE("visits/{id}")
    suspend fun deleteVisit(@Path("id") id: String): Response<Unit>

    @GET("claims")
    suspend fun listClaims(@Query("person_id") personId: String): List<ClaimOut>
    @POST("claims")
    suspend fun addClaim(@Body body: ClaimIn): ClaimOut
    @GET("claims/spend")
    suspend fun yearlySpend(@Query("person_id") personId: String, @Query("year") year: Int? = null): SpendOut

    @GET("doctors")
    suspend fun listDoctors(): List<DoctorOut>
    @POST("doctors")
    suspend fun addDoctor(@Body body: DoctorIn): DoctorOut
    @DELETE("doctors/{id}")
    suspend fun deleteDoctor(@Path("id") id: String): Response<Unit>

    @GET("growth")
    suspend fun listGrowth(@Query("person_id") personId: String): List<GrowthOut>
    @POST("growth")
    suspend fun addGrowth(@Body body: GrowthIn): GrowthOut

    @GET("uhids")
    suspend fun listUhids(@Query("person_id") personId: String): List<UhidOut>
    @POST("uhids")
    suspend fun addUhid(@Body body: UhidIn): UhidOut

    @GET("timeline")
    suspend fun timeline(@Query("person_id") personId: String): List<TimelineItem>

    @GET("storage/stats")
    suspend fun storageStats(): StorageStats

    @GET("backup/google")
    suspend fun googleDriveStatus(): GoogleDriveStatus

    @POST("backup/google/settings")
    suspend fun googleDriveSettings(@Body body: GoogleDriveSettingsIn): GoogleDriveStatus

    @POST("backup/google/run")
    suspend fun googleDriveRun(): GoogleDriveRunOut

    // ---------- Password Vault ----------
    @GET("vault/folders")
    suspend fun listVaultFolders(): List<VaultFolderOut>

    @POST("vault/folders")
    suspend fun createVaultFolder(@Body body: VaultFolderIn): VaultFolderOut

    @PATCH("vault/folders/{id}")
    suspend fun renameVaultFolder(@Path("id") id: String, @Body body: VaultFolderIn): VaultFolderOut

    @DELETE("vault/folders/{id}")
    suspend fun deleteVaultFolder(@Path("id") id: String): Response<Unit>

    @GET("vault/items")
    suspend fun listVaultItems(
        @Query("q") q: String? = null,
        @Query("item_type") itemType: String? = null,
        @Query("folder_id") folderId: String? = null,
        @Query("favorite") favorite: Boolean = false
    ): List<VaultItemOut>

    @POST("vault/items")
    suspend fun createVaultItem(@Body body: VaultItemIn): VaultItemOut

    @GET("vault/items/{id}")
    suspend fun getVaultItem(@Path("id") id: String): VaultItemOut

    @PATCH("vault/items/{id}")
    suspend fun updateVaultItem(@Path("id") id: String, @Body body: VaultItemUpdate): VaultItemOut

    @DELETE("vault/items/{id}")
    suspend fun trashVaultItem(@Path("id") id: String): Response<Unit>

    @POST("vault/items/{id}/restore")
    suspend fun restoreVaultItem(@Path("id") id: String): VaultItemOut

    @DELETE("vault/items/{id}/permanent")
    suspend fun deleteVaultItemForever(@Path("id") id: String): Response<Unit>

    @POST("vault/items/{id}/favorite")
    suspend fun favoriteVaultItem(@Path("id") id: String): VaultItemOut

    @DELETE("vault/items/{id}/favorite")
    suspend fun unfavoriteVaultItem(@Path("id") id: String): VaultItemOut

    @GET("vault/items/{id}/totp")
    suspend fun vaultItemTotp(@Path("id") id: String): VaultTotpOut

    @GET("vault/items/{id}/history")
    suspend fun vaultItemHistory(@Path("id") id: String): List<VaultHistoryOut>

    @POST("vault/generate")
    suspend fun generatePassword(@Body body: VaultGenerateIn): VaultGenerateOut

    @GET("vault/health")
    suspend fun vaultHealth(): VaultHealthOut

    @GET("vault/trash")
    suspend fun listVaultTrash(): List<VaultItemOut>

    @POST("vault/trash/empty")
    suspend fun emptyVaultTrash(): Response<Unit>

    @GET("vault/sends")
    suspend fun listVaultSends(): List<VaultSendOut>

    @POST("vault/sends")
    suspend fun createVaultSend(@Body body: VaultSendCreate): VaultSendOut

    @DELETE("vault/sends/{id}")
    suspend fun revokeVaultSend(@Path("id") id: String): Response<Unit>

    // ---------- Document Vault ----------
    @GET("locker/summary")
    suspend fun lockerSummary(): LockerSummaryOut

    @GET("locker/types")
    suspend fun listLockerTypes(): List<LockerTypeOut>

    @GET("locker")
    suspend fun listLockerItems(
        @Query("doc_type") docType: String? = null,
        @Query("q") q: String? = null,
        @Query("expiring") expiring: Boolean = false
    ): List<LockerItemOut>

    @Multipart
    @POST("locker")
    suspend fun createLockerItem(
        @Part("title") title: RequestBody,
        @Part("doc_type") docType: RequestBody,
        @Part("custom_type") customType: RequestBody?,
        @Part("holder_name") holderName: RequestBody?,
        @Part("issuer") issuer: RequestBody?,
        @Part("id_number") idNumber: RequestBody?,
        @Part("issued_on") issuedOn: RequestBody?,
        @Part("expiry_date") expiryDate: RequestBody?,
        @Part("tags") tags: RequestBody?,
        @Part("notes") notes: RequestBody?,
        @Part files: List<MultipartBody.Part>
    ): LockerItemOut

    @GET("locker/{id}")
    suspend fun getLockerItem(@Path("id") id: String): LockerItemOut

    @PATCH("locker/{id}")
    suspend fun updateLockerItem(@Path("id") id: String, @Body body: LockerItemUpdate): LockerItemOut

    @DELETE("locker/{id}")
    suspend fun deleteLockerItem(@Path("id") id: String): Response<Unit>

    @GET("locker/{id}/files")
    suspend fun listLockerFiles(@Path("id") id: String): List<LockerFileOut>

    @Streaming
    @GET("locker/{id}/download")
    suspend fun downloadLockerItem(@Path("id") id: String): ResponseBody

    @Streaming
    @GET("locker/{id}/files/{fileId}/download")
    suspend fun downloadLockerFile(
        @Path("id") id: String,
        @Path("fileId") fileId: String
    ): ResponseBody

    // ---------- Money Manager ----------
    @GET("finance/summary")
    suspend fun financeSummary(@Query("year_month") yearMonth: String? = null): FinanceSummaryOut

    @GET("finance/accounts")
    suspend fun listFinanceAccounts(): List<FinanceAccountOut>

    @POST("finance/accounts")
    suspend fun createFinanceAccount(@Body body: FinanceAccountIn): FinanceAccountOut

    @GET("finance/categories")
    suspend fun listFinanceCategories(@Query("account_id") accountId: String? = null): List<FinanceCategoryOut>

    @POST("finance/categories")
    suspend fun createFinanceCategory(@Body body: FinanceCategoryIn): FinanceCategoryOut

    @GET("finance/transactions")
    suspend fun listFinanceTransactions(
        @Query("year_month") yearMonth: String? = null,
        @Query("txn_type") txnType: String? = null,
        @Query("account_id") accountId: String? = null,
        @Query("q") q: String? = null
    ): List<FinanceTxnOut>

    @POST("finance/transactions")
    suspend fun createFinanceTransaction(@Body body: FinanceTxnIn): FinanceTxnOut

    @Multipart
    @POST("finance/transactions/{id}/image")
    suspend fun uploadFinanceImage(
        @Path("id") id: String,
        @Part file: MultipartBody.Part
    ): FinanceTxnOut

    @Streaming
    @GET("finance/transactions/{id}/image")
    suspend fun downloadFinanceImage(@Path("id") id: String): ResponseBody

    @DELETE("finance/transactions/{id}")
    suspend fun deleteFinanceTransaction(@Path("id") id: String): Response<Unit>

    @GET("finance/emis")
    suspend fun listFinanceEmis(@Query("status") status: String? = null): List<FinanceEmiOut>

    @POST("finance/emis")
    suspend fun createFinanceEmi(@Body body: FinanceEmiIn): FinanceEmiOut

    @POST("finance/emis/{id}/post")
    suspend fun postFinanceEmi(@Path("id") id: String): FinanceEmiOut

    @POST("finance/emis/{id}/pause")
    suspend fun pauseFinanceEmi(@Path("id") id: String): FinanceEmiOut

    @DELETE("finance/emis/{id}")
    suspend fun deleteFinanceEmi(@Path("id") id: String): Response<Unit>

    @GET("finance/reports")
    suspend fun financeReports(
        @Query("year_month") yearMonth: String? = null,
        @Query("kind") kind: String = "expense"
    ): FinanceReportOut

    @GET("finance/ai-keys")
    suspend fun listFinanceAiKeys(): List<FinanceAiKeyOut>

    @POST("finance/ai-keys")
    suspend fun createFinanceAiKey(@Body body: FinanceAiKeyIn): FinanceAiKeyOut

    @GET("finance/messages")
    suspend fun listFinanceMessages(@Query("status") status: String? = "pending"): List<FinanceMessageOut>

    @POST("finance/messages/ingest")
    suspend fun ingestFinanceMessages(@Body body: FinanceMessageIn): List<FinanceMessageOut>

    @POST("finance/messages/{id}/accept")
    suspend fun acceptFinanceMessage(@Path("id") id: String, @Query("account_id") accountId: String? = null): FinanceTxnOut

    // ---------- URL Vault ----------
    @GET("urls/summary")
    suspend fun urlSummary(): UrlSummaryOut

    @GET("urls")
    suspend fun listUrlItems(
        @Query("q") q: String? = null,
        @Query("category_id") categoryId: String? = null,
        @Query("tag_id") tagId: String? = null,
        @Query("favorite") favorite: Boolean = false
    ): List<UrlItemOut>

    @POST("urls")
    suspend fun createUrlItem(@Body body: UrlItemIn): UrlItemOut

    @GET("urls/{id}")
    suspend fun getUrlItem(@Path("id") id: String): UrlItemOut

    @PATCH("urls/{id}")
    suspend fun updateUrlItem(@Path("id") id: String, @Body body: UrlItemUpdate): UrlItemOut

    @DELETE("urls/{id}")
    suspend fun deleteUrlItem(@Path("id") id: String): Response<Unit>

    @POST("urls/{id}/preview")
    suspend fun refreshUrlPreview(@Path("id") id: String): UrlItemOut

    @POST("urls/{id}/favorite")
    suspend fun toggleUrlFavorite(@Path("id") id: String): UrlItemOut

    @POST("urls/{id}/share")
    suspend fun createUrlShare(@Path("id") id: String, @Body body: UrlShareCreate): UrlShareOut

    @GET("urls/shares")
    suspend fun listUrlShares(@Query("item_id") itemId: String? = null): List<UrlShareOut>

    @POST("urls/shares/{id}/revoke")
    suspend fun revokeUrlShare(@Path("id") id: String): Response<Unit>

    @GET("urls/categories")
    suspend fun listUrlCategories(): List<UrlCategoryOut>

    @POST("urls/categories")
    suspend fun createUrlCategory(@Body body: UrlCategoryIn): UrlCategoryOut

    @PATCH("urls/categories/{id}")
    suspend fun updateUrlCategory(@Path("id") id: String, @Body body: UrlCategoryIn): UrlCategoryOut

    @DELETE("urls/categories/{id}")
    suspend fun deleteUrlCategory(@Path("id") id: String): Response<Unit>

    @GET("urls/tags")
    suspend fun listUrlTags(): List<UrlTagOut>

    @POST("urls/tags")
    suspend fun createUrlTag(@Body body: UrlTagIn): UrlTagOut

    @PATCH("urls/tags/{id}")
    suspend fun updateUrlTag(@Path("id") id: String, @Body body: UrlTagIn): UrlTagOut

    @DELETE("urls/tags/{id}")
    suspend fun deleteUrlTag(@Path("id") id: String): Response<Unit>
}
