package com.rklab.healthvault.util

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.os.Handler
import android.os.Looper
import android.widget.Toast

object ClipboardUtil {
    fun copy(context: Context, label: String, value: String, clearAfterMs: Long = 60_000) {
        val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        clipboard.setPrimaryClip(ClipData.newPlainText(label, value))
        Toast.makeText(context, "$label copied · clears in 60s", Toast.LENGTH_SHORT).show()
        Handler(Looper.getMainLooper()).postDelayed({
            val current = clipboard.primaryClip?.getItemAt(0)?.text?.toString()
            if (current == value) {
                clipboard.setPrimaryClip(ClipData.newPlainText("", ""))
            }
        }, clearAfterMs)
    }
}
