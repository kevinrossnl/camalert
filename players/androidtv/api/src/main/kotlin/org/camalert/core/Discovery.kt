// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

/**
 * What the player announces on the local network as _camalert._tcp (#121), the same as camalert_core.discovery:
 * instance name, port and the TXT keys id, name, platform, version, api_version, https. Never a token. The app
 * registers it with Android's NsdManager while the API is on.
 */
object Discovery {
    const val SERVICE_TYPE = "_camalert._tcp"
    val TXT_KEYS = listOf("id", "name", "platform", "version", "api_version", "https")

    private val CONTROL = Regex("[\\x00-\\x1f\\x7f]")

    /** Runs of whitespace (Unicode, like Python's \\s) become one space. No regex with the Unicode flag: Android's ICU regex
     *  rejects that flag and the app crashed at start on Fire OS 6 (1.3.0). */
    private fun clean(text: Any?): String {
        val s = CONTROL.replace(text?.toString() ?: "", " ")
        val out = StringBuilder(s.length)
        var space = false
        for (c in s) {
            if (c.isWhitespace()) { space = true; continue }
            if (space && out.isNotEmpty()) out.append(' ')
            space = false
            out.append(c)
        }
        return out.toString()
    }

    /** text shortened to at most limit UTF-8 bytes, never in the middle of a character. */
    private fun cut(text: String, limit: Int): String {
        if (text.toByteArray(Charsets.UTF_8).size <= limit) return text
        val out = StringBuilder()
        var bytes = 0
        var i = 0
        while (i < text.length) {
            val cp = text.codePointAt(i)
            val s = String(Character.toChars(cp))
            val n = s.toByteArray(Charsets.UTF_8).size
            if (bytes + n > limit) break
            out.append(s)
            bytes += n
            i += Character.charCount(cp)
        }
        return out.toString().trimEnd()
    }

    fun instanceName(name: String?, nodeId: String?): String = cut(clean(name).ifEmpty { "CamAlert ${clean(nodeId)}" }, 63)

    fun hostLabel(nodeId: String?): String {
        val label = Regex("[^a-z0-9-]").replace((nodeId ?: "").lowercase(), "-").trim('-').take(50).ifEmpty { "player" }
        return "camalert-$label.local."
    }

    fun txtRecord(nodeId: String?, name: String?, platform: String, version: String, apiVersion: Int, https: Boolean): List<Pair<String, String>> {
        val v = mapOf("id" to clean(nodeId), "name" to clean(name), "platform" to clean(platform), "version" to clean(version),
            "api_version" to apiVersion.toString(), "https" to if (https) "1" else "0")
        return TXT_KEYS.map { Pair(it, v.getValue(it)) }
    }

    /** {host, instance, port, txt} (as camalert_core.discovery.service_info), or null without an id. */
    fun serviceInfo(nodeId: String?, name: String?, platform: String, version: String, apiVersion: Int, port: Int, https: Boolean): Map<String, Any>? {
        if (clean(nodeId).isEmpty()) return null
        return linkedMapOf("host" to hostLabel(nodeId), "instance" to instanceName(name, nodeId), "port" to port,
            "txt" to txtRecord(nodeId, name, platform, version, apiVersion, https).map { listOf(it.first, it.second) })
    }

    /** Announce only while the API is on (both "allow" values answer the local network). */
    fun shouldAdvertise(s: Map<String, Any?>): Boolean = s["enabled"] == true && (s["allow"] ?: "lan") in listOf("lan", "any")
}
