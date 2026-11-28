// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/**
 * The problem report of a player (#132), the same as camalert_core.report: status, settings without secrets and the
 * last log lines, scrubbed of passwords, tokens, e-mail addresses, public IP addresses and non-local host names, plus
 * a pre-filled GitHub issue link short enough for a QR code. Constants come from core.json ("report").
 */
@Suppress("UNCHECKED_CAST")
class Report(private val data: CoreData = CoreData.load()) {
    private val cfg = data.raw["report"] as Map<String, Any?>
    private val secretIds = (cfg["secret_ids"] as List<String>).toSet()
    private val statusDropped = (cfg["status_dropped"] as List<String>).toSet()
    private val playerLabels = cfg["player_labels"] as Map<String, String>
    val issuesUrl = cfg["issues_url"] as String
    private val urlMax = (cfg["url_max"] as Number).toInt()
    private val logLines = (cfg["log_lines"] as Number).toInt()
    private val errorLines = (cfg["error_lines"] as Number).toInt()
    private val reportVersion = (cfg["version"] as Number).toInt()

    init {
        (cfg["local_suffixes"] as? List<String>)?.let { localSuffixes = it }
    }

    companion object {
        private val EMAIL = Regex("\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}\\b")
        private val IPV4 = Regex("(?<![\\d.])(\\d{1,3}(?:\\.\\d{1,3}){3})(?![\\d.])")
        private val URL_HOST = Regex("(?i)(\\b[a-z][a-z0-9+.-]*://(?:\\*\\*\\*(?::\\*\\*\\*)?@)?)(\\[[0-9a-f:]+\\]|[^/\\s:?#\\]\\[]+)")
        private val WEBHOOK = Regex("(?i)(/api/webhook/)[A-Za-z0-9_-]+")
        private val ERROR = Regex("(?i)\\b(error|failed|traceback|exception)\\b")
        @Volatile private var localSuffixes: List<String> = listOf(".local", ".lan", ".home", ".home.arpa", ".internal")

        private fun hostOk(host: String): Boolean {
            val h = host.trim('[', ']').lowercase()
            if (Access.lanAddress(h)) return true
            if (':' in h) return false  // an IPv6 address outside the local network
            if ('.' !in h) return true
            return localSuffixes.any { h.endsWith(it) }
        }

        /** text without secrets, e-mail addresses, public IP addresses and non-local host names in urls. */
        fun scrub(text: String?): String {
            var t = Obs.redact(text ?: "")
            t = WEBHOOK.replace(t) { it.groupValues[1] + "***" }
            t = EMAIL.replace(t, "<e-mail>")
            t = URL_HOST.replace(t) { m -> m.groupValues[1] + (if (hostOk(m.groupValues[2])) m.groupValues[2] else "<host>") }
            return IPV4.replace(t) { m ->
                val ip = m.groupValues[1]
                if (ip.split('.').any { it.toInt() > 255 }) ip else if (Access.lanAddress(ip)) ip else "<public-ip>"
            }
        }

        private fun scrubValue(v: Any?): Any? = when (v) {
            is String -> scrub(v)
            is Map<*, *> -> v.entries.associate { it.key.toString() to scrubValue(it.value) }
            is List<*> -> v.map { scrubValue(it) }
            else -> v
        }

        private fun shortId(node: Any?): String {
            val s = node?.toString() ?: ""
            return if (s.codePointCount(0, s.length) > 6) s.substring(0, s.offsetByCodePoints(0, 4)) + "…" else s
        }

        private fun quote(s: String): String {
            val sb = StringBuilder()
            for (b in s.toByteArray(Charsets.UTF_8)) {
                val ch = b.toInt() and 0xFF
                val c = ch.toChar()
                if ((ch < 128 && (c in 'a'..'z' || c in 'A'..'Z' || c in '0'..'9')) || c in "-._~") sb.append(c)
                else sb.append(String.format(Locale.ROOT, "%%%02X", ch))
            }
            return sb.toString()
        }
    }

    /** {schema id: value} without secrets (dropped, not masked) and with scrubbed text values, sorted by id. */
    fun settingsPart(settings: Map<String, Any?>?): Map<String, Any?> =
        (settings ?: emptyMap()).keys.sorted().filter { it !in secretIds }.associateWith { scrubValue(settings!![it]) }

    /** The report of one player (see camalert_core.report.build). */
    fun build(status: Map<String, Any?>?, settings: Map<String, Any?>?, log: List<String>?, extra: Map<String, Any?>?,
              now: Double = System.currentTimeMillis() / 1000.0): Map<String, Any?> {
        val st = LinkedHashMap<String, Any?>()
        for ((k, v) in status ?: emptyMap()) if (k !in statusDropped && k != "result") st[k] = v
        if ("id" in st) st["id"] = shortId(st["id"])
        val lines = (log ?: emptyList()).map { scrub(it) }.takeLast(logLines)
        val errors = lines.filter { ERROR.containsMatchIn(it) }.takeLast(errorLines)
        val fmt = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.ROOT).apply { timeZone = TimeZone.getTimeZone("UTC") }
        return linkedMapOf(
            "report" to reportVersion,
            "created" to fmt.format(Date((Math.floor(now) * 1000).toLong())),
            "camalert" to (status?.get("version") ?: ""),
            "platform" to (status?.get("platform") ?: ""),
            "player" to scrubValue(extra ?: emptyMap<String, Any?>()),
            "status" to scrubValue(st),
            "settings" to settingsPart(settings),
            "errors" to errors,
            "log" to lines,
        )
    }

    fun playerVersion(report: Map<String, Any?>): String {
        val p = report["player"] as? Map<String, Any?> ?: emptyMap()
        val s = listOf("model", "image", "os", "kodi", "android", "browser").mapNotNull { k ->
            p[k]?.takeIf { it.toString().isNotEmpty() }?.toString() }.joinToString(", ")
        return if (s.codePointCount(0, s.length) > 120) s.substring(0, s.offsetByCodePoints(0, 120)) else s
    }

    fun summary(report: Map<String, Any?>): List<String> {
        val st = report["status"] as? Map<String, Any?> ?: emptyMap()
        val platform = report["platform"]?.toString() ?: ""
        val label = playerLabels[platform] ?: platform.ifEmpty { "?" }
        val out = arrayListOf("CamAlert ${report["camalert"]?.toString()?.ifEmpty { null } ?: "?"} on $label")
        val pv = playerVersion(report)
        if (pv.isNotEmpty()) out.add(pv)
        val state = listOf("go2rtc", "mqtt", "home_assistant", "protect", "screen").mapNotNull { k ->
            val v = st[k]
            if (v == null || v == "") null
            else "$k: " + (if (v is Map<*, *> || v is List<*>) Json.write(v, sortKeys = true) else pyStr(v))
        }
        if (state.isNotEmpty()) out.add(state.joinToString(", "))
        val errors = report["errors"] as? List<String> ?: emptyList()
        if (errors.isNotEmpty()) out.add("Last error: " + errors.last().let { if (it.length > 160) it.substring(0, 160) else it })
        return out
    }

    private fun pyStr(v: Any?): String = when (v) { true -> "True"; false -> "False"; null -> "None"; else -> v.toString() }

    /** The bug report form with player, versions and a short summary, below url_max bytes for a QR code. */
    fun issueUrl(report: Map<String, Any?>): String {
        val fields = listOf("template" to "bug_report.yml",
            "player" to (playerLabels[report["platform"]?.toString() ?: ""] ?: "Other / not sure"),
            "camalert_version" to (report["camalert"]?.toString() ?: ""),
            "player_version" to playerVersion(report))
        val pv = playerVersion(report)
        var what = summary(report).drop(1).filter { it != pv }.joinToString("\n")
        fun make(w: String): String {
            val q = fields + (if (w.isNotEmpty()) listOf("logs" to w) else emptyList())
            return issuesUrl + "?" + q.filter { it.second.isNotEmpty() }.joinToString("&") { "${it.first}=${quote(it.second)}" }
        }
        var url = make(what)
        while (url.toByteArray(Charsets.UTF_8).size > urlMax && what.isNotEmpty()) {
            val cut = maxOf(0, what.length - maxOf(10, (url.length - urlMax) / 3))
            what = what.substring(0, cut).trimEnd()
            url = make(what)
        }
        return url
    }
}
