package com.rklab.healthvault.util

object QrLoginPayload {
    private val HEX = Regex("^[a-fA-F0-9]{32}$")
    private const val PREFIX = "healthvault://login/"

    fun parse(raw: String): String? {
        val text = raw.trim()
        val stripped = when {
            text.startsWith(PREFIX, ignoreCase = true) ->
                text.substring(PREFIX.length).trim().trim('/')
            else -> text
        }
        val candidate = stripped.substringBefore('?').substringBefore('#')
        return if (HEX.matches(candidate)) candidate.lowercase() else null
    }
}
