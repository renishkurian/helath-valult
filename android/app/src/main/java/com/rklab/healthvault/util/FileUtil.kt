package com.rklab.healthvault.util

import android.content.Context
import android.net.Uri
import java.io.File

object FileUtil {
    /** Copies whatever the Uri points to into app cache so Retrofit can read it as a plain File. */
    fun copyUriToCacheFile(context: Context, uri: Uri, suggestedName: String): File {
        val resolver = context.contentResolver
        val mimeType = resolver.getType(uri) ?: "application/octet-stream"
        val ext = mimeTypeToExtension(mimeType)
        val outFile = File(context.cacheDir.resolve("uploads").apply { mkdirs() }, "$suggestedName$ext")
        resolver.openInputStream(uri)?.use { input ->
            outFile.outputStream().use { output -> input.copyTo(output) }
        }
        return outFile
    }

    fun mimeTypeOf(context: Context, uri: Uri): String =
        context.contentResolver.getType(uri) ?: "application/octet-stream"

    private fun mimeTypeToExtension(mime: String): String = when {
        mime.contains("pdf") -> ".pdf"
        mime.contains("png") -> ".png"
        mime.contains("jpeg") || mime.contains("jpg") -> ".jpg"
        mime.contains("webp") -> ".webp"
        else -> ""
    }

    fun newCaptureFile(context: Context): File {
        val dir = File(context.cacheDir, "captures").apply { mkdirs() }
        return File(dir, "capture_${System.currentTimeMillis()}.jpg")
    }
}
