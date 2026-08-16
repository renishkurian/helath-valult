package com.rklab.healthvault.util

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.activity.result.ActivityResultLauncher
import androidx.activity.result.IntentSenderRequest
import com.google.mlkit.vision.documentscanner.GmsDocumentScannerOptions
import com.google.mlkit.vision.documentscanner.GmsDocumentScanning
import com.google.mlkit.vision.documentscanner.GmsDocumentScanningResult
import java.io.File

/**
 * Adobe Scan–style capture via Google ML Kit Document Scanner:
 * edge detect, auto-crop, filters, multi-page, JPEG + PDF export.
 */
object DocumentScannerHelper {

    fun options(
        maxPages: Int = 30,
        allowGallery: Boolean = true
    ): GmsDocumentScannerOptions =
        GmsDocumentScannerOptions.Builder()
            .setGalleryImportAllowed(allowGallery)
            .setPageLimit(maxPages.coerceIn(1, 50))
            .setResultFormats(
                GmsDocumentScannerOptions.RESULT_FORMAT_JPEG,
                GmsDocumentScannerOptions.RESULT_FORMAT_PDF
            )
            .setScannerMode(GmsDocumentScannerOptions.SCANNER_MODE_FULL)
            .build()

    fun start(
        activity: Activity,
        launcher: ActivityResultLauncher<IntentSenderRequest>,
        onError: (String) -> Unit,
        maxPages: Int = 30
    ) {
        val scanner = GmsDocumentScanning.getClient(options(maxPages = maxPages))
        scanner.getStartScanIntent(activity)
            .addOnSuccessListener { intentSender ->
                launcher.launch(IntentSenderRequest.Builder(intentSender).build())
            }
            .addOnFailureListener { e ->
                onError(e.message ?: "Document scanner unavailable on this device")
            }
    }

    data class ScanResult(
        val pageImages: List<File>,
        val pdf: File?,
        val pageCount: Int
    )

    fun parseResult(context: Context, data: Intent?): ScanResult? {
        val result = GmsDocumentScanningResult.fromActivityResultIntent(data) ?: return null
        val pages = result.pages.orEmpty().mapIndexedNotNull { idx, page ->
            val uri = page.imageUri ?: return@mapIndexedNotNull null
            FileUtil.copyUriToCacheFile(context, uri, "scan_page_${System.currentTimeMillis()}_$idx")
                .let { FileUtil.enhanceImageFile(it) }
        }
        val pdfFile = result.pdf?.uri?.let { uri ->
            FileUtil.copyUriToCacheFile(context, uri, "scan_${System.currentTimeMillis()}")
        }
        if (pages.isEmpty() && pdfFile == null) return null
        return ScanResult(
            pageImages = pages,
            pdf = pdfFile,
            pageCount = pages.size.coerceAtLeast(if (pdfFile != null) 1 else 0)
        )
    }

    /** Prefer PDF when available; otherwise merge page JPEGs into one PDF. */
    fun filesForUpload(context: Context, scan: ScanResult, preferPdf: Boolean): List<Pair<File, String>> {
        if (preferPdf) {
            val pdf = scan.pdf ?: if (scan.pageImages.isNotEmpty()) {
                FileUtil.mergeImagesToPdf(context, scan.pageImages)
            } else null
            if (pdf != null) return listOf(pdf to "application/pdf")
        }
        if (scan.pageImages.isNotEmpty()) {
            return scan.pageImages.map { it to "image/jpeg" }
        }
        scan.pdf?.let { return listOf(it to "application/pdf") }
        return emptyList()
    }
}
