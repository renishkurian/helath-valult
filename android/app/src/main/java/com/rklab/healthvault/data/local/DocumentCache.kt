package com.rklab.healthvault.data.local

import android.content.Context
import java.io.File

/** Keeps the last-viewed document files on device so they open offline. */
object DocumentCache {
    private const val MAX_FILES = 20

    fun dir(context: Context): File =
        File(context.filesDir, "documents").also { it.mkdirs() }

    fun fileFor(context: Context, key: String): File = File(dir(context), key)

    fun prune(context: Context) {
        val files = dir(context).listFiles()?.sortedBy { it.lastModified() } ?: return
        val extra = files.size - MAX_FILES
        if (extra > 0) {
            files.take(extra).forEach { it.delete() }
        }
    }
}
