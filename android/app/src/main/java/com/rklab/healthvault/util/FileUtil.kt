package com.rklab.healthvault.util

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.pdf.PdfDocument
import android.net.Uri
import java.io.File
import java.io.FileOutputStream
import kotlin.math.max
import kotlin.math.roundToInt

object FileUtil {
    private const val MAX_EDGE = 2048
    private const val JPEG_QUALITY = 78

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

    /**
     * Downscale large photos and JPEG-compress before upload to save storage.
     * Returns a new `.jpg` when compression succeeds; otherwise the original file.
     */
    fun enhanceImageFile(file: File): File {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(file.absolutePath, bounds)
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return file

        val longest = max(bounds.outWidth, bounds.outHeight)
        var sample = 1
        while (longest / sample > MAX_EDGE * 2) sample *= 2

        val opts = BitmapFactory.Options().apply { inSampleSize = sample }
        var bitmap = BitmapFactory.decodeFile(file.absolutePath, opts) ?: return file
        val w = bitmap.width
        val h = bitmap.height
        val edge = max(w, h)
        if (edge > MAX_EDGE) {
            val scale = MAX_EDGE.toFloat() / edge
            val nw = max(1, (w * scale).roundToInt())
            val nh = max(1, (h * scale).roundToInt())
            val scaled = Bitmap.createScaledBitmap(bitmap, nw, nh, true)
            if (scaled !== bitmap) {
                bitmap.recycle()
                bitmap = scaled
            }
        }

        val out = File(file.parentFile, "enh_${file.nameWithoutExtension}.jpg")
        FileOutputStream(out).use { bitmap.compress(Bitmap.CompressFormat.JPEG, JPEG_QUALITY, it) }
        bitmap.recycle()
        return if (out.length() > 0) out else file
    }

    fun mergeImagesToPdf(context: Context, images: List<File>): File {
        val pdf = PdfDocument()
        images.forEachIndexed { index, file ->
            val bmp = BitmapFactory.decodeFile(file.absolutePath) ?: return@forEachIndexed
            val pageInfo = PdfDocument.PageInfo.Builder(bmp.width, bmp.height, index + 1).create()
            val page = pdf.startPage(pageInfo)
            page.canvas.drawBitmap(bmp, 0f, 0f, null)
            pdf.finishPage(page)
            bmp.recycle()
        }
        val out = File(context.cacheDir.resolve("uploads").apply { mkdirs() }, "scan_${System.currentTimeMillis()}.pdf")
        FileOutputStream(out).use { pdf.writeTo(it) }
        pdf.close()
        return out
    }

    /** Copy many files into a durable pending folder for offline upload sync. */
    fun stagePendingUpload(context: Context, files: List<File>, mimeTypes: List<String>): Pair<String, String> {
        val dir = File(context.filesDir, "pending_uploads/${System.currentTimeMillis()}").apply { mkdirs() }
        val stagedMimes = mutableListOf<String>()
        files.forEachIndexed { idx, src ->
            val mime = mimeTypes.getOrElse(idx) { "application/octet-stream" }
            val ext = mimeTypeToExtension(mime).ifBlank { src.extension.let { if (it.isNotBlank()) ".$it" else "" } }
            val dest = File(dir, "%03d$ext".format(idx))
            src.copyTo(dest, overwrite = true)
            stagedMimes += mime
        }
        return dir.absolutePath to stagedMimes.joinToString("\n")
    }

    fun listStagedPendingFiles(dirPath: String): List<File> {
        val dir = File(dirPath)
        if (!dir.isDirectory) {
            val single = File(dirPath)
            return if (single.isFile) listOf(single) else emptyList()
        }
        return dir.listFiles()?.filter { it.isFile }?.sortedBy { it.name } ?: emptyList()
    }
}
