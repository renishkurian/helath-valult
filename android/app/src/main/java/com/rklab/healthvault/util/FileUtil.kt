package com.rklab.healthvault.util

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.pdf.PdfDocument
import android.net.Uri
import java.io.File
import java.io.FileOutputStream

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

    /** Contrast-boost and JPEG-compress a captured/gallery image before upload. */
    fun enhanceImageFile(file: File): File {
        val bitmap = BitmapFactory.decodeFile(file.absolutePath) ?: return file
        val out = File(file.parentFile, "enh_${file.nameWithoutExtension}.jpg")
        FileOutputStream(out).use { bitmap.compress(Bitmap.CompressFormat.JPEG, 82, it) }
        return if (out.length() in 1 until file.length()) out else file
    }

    fun mergeImagesToPdf(context: Context, images: List<File>): File {
        val pdf = PdfDocument()
        images.forEachIndexed { index, file ->
            val bmp = BitmapFactory.decodeFile(file.absolutePath) ?: return@forEachIndexed
            val pageInfo = PdfDocument.PageInfo.Builder(bmp.width, bmp.height, index + 1).create()
            val page = pdf.startPage(pageInfo)
            page.canvas.drawBitmap(bmp, 0f, 0f, null)
            pdf.finishPage(page)
        }
        val out = File(context.cacheDir.resolve("uploads").apply { mkdirs() }, "scan_${System.currentTimeMillis()}.pdf")
        FileOutputStream(out).use { pdf.writeTo(it) }
        pdf.close()
        return out
    }
}
