// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

/** When a camera is shown, camera names and URLs (core rules.py, cameras.py, urls.py, events.py). */
object Rules {
    val MODES = listOf("photo", "live", "notify")
    val PRIORITIES = listOf("normal", "high", "alarm")
    const val MIN_SECONDS = 5
    const val MAX_SECONDS = 300

    /** int(value) like Python (surrounding blanks allowed), clamped to 5..300; the default if it is no number. */
    fun clampSeconds(value: Any?, default: Int = 30): Int {
        val n = when (value) {
            is Number -> value.toInt()
            null -> return default
            else -> value.toString().trim().toIntOrNull() ?: return default
        }
        return n.coerceIn(MIN_SECONDS, MAX_SECONDS)
    }

    fun pickMode(value: String?, default: String = "photo") = if (value in MODES) value!! else default
    fun pickPriority(value: String?) = if (value in PRIORITIES) value!! else "normal"

    /** 'ignore', 'extend' or 'show'. */
    fun decide(inStandby: Boolean, current: String?, window: String?, requested: String?): String {
        if (inStandby || requested.isNullOrEmpty()) return "ignore"
        if (current == requested) return "ignore"
        if (window == requested) return "extend"
        return "show"
    }

    fun inTimeWindow(now: Pair<Int, Int>, start: Pair<Int, Int>, end: Pair<Int, Int>): Boolean {
        val n = now.first * 60 + now.second
        val a = start.first * 60 + start.second
        val b = end.first * 60 + end.second
        if (a == b) return true
        return if (a < b) n in a until b else n >= a || n < b
    }

    fun clockTuple(value: String?): Pair<Int, Int> {
        val t = (value ?: "").trim()
        if (":" in t) {
            val p = t.split(":")
            return Pair((p[0].trim().toIntOrNull() ?: 0).mod(24), (p[1].trim().toIntOrNull() ?: 0).mod(60))
        }
        val n = t.toIntOrNull() ?: return Pair(0, 0)
        return Pair((n / 3600).mod(24), (n / 60).mod(60))
    }

    fun loweredVolume(current: Int, percent: Int): Int =
        Math.round(current * percent.coerceIn(0, 100) / 100.0).toInt().coerceIn(0, 100)

    fun blockedByRules(priority: String, limitHours: Boolean, inHours: Boolean, skipPlaying: Boolean, playing: Boolean): Boolean {
        if (priority != "normal") return false
        return (limitHours && !inHours) || (skipPlaying && playing)
    }

    fun dndBlocks(priority: String, dndOn: Boolean, level: String = "normal"): Boolean {
        if (!dndOn || priority == "alarm") return false
        return priority == "normal" || (level == "high" && priority == "high")
    }

    fun cooldownSeconds(name: String?, text: String?): Int {
        val m = HashMap<String, String>()
        for (p in (text ?: "").split("|").map { it.trim() }) {
            if ("=" in p) m[p.substringBefore("=").trim()] = p.substringAfter("=").trim()
        }
        for (key in listOf(name ?: "", "*")) {
            val v = m[key]?.toDoubleOrNull() ?: continue
            return v.toInt().coerceIn(0, 3600)
        }
        return 0
    }

    fun inCooldown(lastShown: Double?, now: Double, seconds: Int): Boolean =
        seconds > 0 && lastShown != null && now - lastShown >= 0 && now - lastShown < seconds

    /** Doorbell chime: off / high (high and alarm) / all. */
    fun chimeWanted(setting: String, priority: String) = when (setting) {
        "all" -> true
        "high" -> priority == "high" || priority == "alarm"
        else -> false
    }
}

object Cameras {
    private val NAME = Regex("^[A-Za-z0-9_.-]+$")

    fun valid(name: String?) = name != null && NAME.matches(name)

    fun parseCams(value: String?): List<String> {
        val out = ArrayList<String>()
        for (c in (value ?: "").split(Regex("[,\\s]+"))) if (NAME.matches(c) && c !in out) out.add(c)
        return out.take(9)
    }

    fun neighbour(items: List<String>, current: String?, step: Int): String? {
        if (items.isEmpty()) return null
        val i = items.indexOf(current)
        if (i < 0) return items[0]
        return items[(i + step).mod(items.size)]
    }

    fun knownCamera(name: String?, names: List<String>) = !name.isNullOrEmpty() && (names.isEmpty() || name in names)

    fun displayName(stream: String?): String {
        val s = (stream ?: "").replace("_", " ").replace("-", " ").trim()
        return if (s.isEmpty()) s else s.substring(0, 1).uppercase() + s.substring(1)
    }

    fun parseMap(text: String?): Map<String, String> {
        val out = LinkedHashMap<String, String>()
        for (part in (text ?: "").split("|")) {
            if ("=" !in part) continue
            val k = part.substringBefore("=").trim()
            val v = part.substringAfter("=").trim()
            if (NAME.matches(k) && v.isNotEmpty()) out[k] = v
        }
        return out
    }

    fun titleFor(name: String, titles: Map<String, String>) = titles[name] ?: displayName(name)

    fun parseOrientation(text: String?) =
        parseMap(text).mapValues { it.value.lowercase() }.filterValues { it in listOf("mirror", "flip", "rot180") }

    fun parseRefresh(text: String?): Map<String, Double> {
        val out = LinkedHashMap<String, Double>()
        for ((k, v) in parseMap(text)) {
            val f = v.replace(",", ".").toDoubleOrNull() ?: continue
            if (f > 0) out[k] = f.coerceIn(0.5, 300.0)
        }
        return out
    }

    fun liveStreamName(name: String, substreams: String?) = parseMap(substreams)[name] ?: name
}

object Urls {
    /** '192.168.1.10', '192.168.1.10:1984' or 'http://host:1984/' -> 'http://host:port' or null. */
    fun normalizeServer(url: String?): String? {
        var u = (url ?: "").trim().trimEnd('/')
        if (u.isEmpty()) return null
        if ("://" !in u) {
            if (u.count { it == ':' } > 1 && !u.startsWith("[")) u = "[$u]"
            u = "http://$u"
        }
        val scheme = u.substringBefore("://").lowercase()
        if (scheme != "http" && scheme != "https") return null
        val auth = u.substringAfter("://").substringBefore('/').substringBefore('?').substringAfterLast('@')
        val host: String
        val portText: String?
        if (auth.startsWith("[")) {
            val end = auth.indexOf(']')
            if (end < 0) return null
            host = auth.substring(1, end)
            portText = auth.substring(end + 1).removePrefix(":").ifEmpty { null }
        } else {
            host = auth.substringBefore(':')
            portText = if (':' in auth) auth.substringAfter(':') else null
        }
        if (host.isEmpty()) return null
        val port = if (portText == null) (if (scheme == "https") 443 else 1984) else
            portText.toIntOrNull()?.takeIf { it in 0..65535 } ?: return null
        val h = host.lowercase().let { if (':' in it) "[$it]" else it }
        return "$scheme://$h:$port"
    }

    fun serverHost(server: String?): String? {
        val auth = (server ?: "").substringAfter("://").substringBefore('/')
        return if (auth.startsWith("[")) auth.substring(1, auth.indexOf(']').coerceAtLeast(1)) else auth.substringBefore(':').ifEmpty { null }
    }

    fun quote(s: String): String {
        val sb = StringBuilder()
        for (b in s.toByteArray(Charsets.UTF_8)) {
            val c = b.toInt() and 0xff
            if ((c in 'a'.code..'z'.code) || (c in 'A'.code..'Z'.code) || (c in '0'.code..'9'.code) || c == '_'.code || c == '.'.code || c == '-'.code || c == '~'.code)
                sb.append(c.toChar()) else sb.append(String.format(java.util.Locale.ROOT, "%%%02X", c))
        }
        return sb.toString()
    }

    /** Helper streams in a go2rtc /api/streams answer (#117): every source transcodes another stream of the same
     *  go2rtc (`ffmpeg:<stream>#...`), as Keep cameras ready and the live substreams do. Not a camera. */
    /** The go2rtc stream a producer url reads from (#117): ffmpeg:<stream>#... or go2rtc's own RTSP server. */
    fun sourceStream(url: String?): String? {
        if (url == null) return null
        if (url.startsWith("ffmpeg:")) return url.removePrefix("ffmpeg:").substringBefore("#")
        val uri = try { java.net.URI(url) } catch (e: Exception) { return null }
        if (uri.scheme !in setOf("rtsp", "rtsps") || uri.host?.trim('[', ']') !in setOf("127.0.0.1", "localhost", "::1")) return null
        val source = (uri.rawQuery ?: "").split("&").firstOrNull { it.startsWith("source=") }
            ?.removePrefix("source=")?.let { java.net.URLDecoder.decode(it, "UTF-8") }
        if (source != null && source.startsWith("ffmpeg:")) return source.removePrefix("ffmpeg:").substringBefore("#")
        return (uri.path ?: "").trimStart('/').ifEmpty { null }
    }

    fun derivedStreams(data: Map<*, *>): Set<String> {
        val names = data.keys.map { it.toString() }.toSet()
        val out = mutableSetOf<String>()
        for ((k, info) in data) {
            val name = k.toString()
            val producers = (info as? Map<*, *>)?.get("producers") as? List<*> ?: continue
            if (producers.isEmpty()) continue
            val bases = producers.map { p -> sourceStream((p as? Map<*, *>)?.get("url") as? String) }
            if (bases.all { it != null && it != name && it in names }) out.add(name)
        }
        return out
    }

    fun streamsFromJson(text: String?, allStreams: Boolean = false): List<String> {
        val d = try { Json.parse(text ?: "") } catch (e: Exception) { return emptyList() }
        if (d !is Map<*, *>) return emptyList()
        val skip = if (allStreams) emptySet() else derivedStreams(d)
        return d.keys.map { it.toString() }.filter { Cameras.valid(it) && it !in skip }.sorted()
    }

    fun snapshotUrl(server: String?, stream: String?, width: Int = 640): String? =
        if (server.isNullOrEmpty() || stream.isNullOrEmpty()) null else "$server/api/frame.jpeg?src=${quote(stream)}&width=$width"

    /** A go2rtc frame.jpeg URL with cache=<n>s for the first picture of a window (#110, frames.with_cache). */
    fun withCache(url: String?, seconds: Int): String? {
        if (url.isNullOrEmpty() || seconds <= 0 || "/api/frame.jpeg" !in url || Regex("[?&]cache=").containsMatchIn(url)) return url
        return url + (if ('?' in url) "&" else "?") + "cache=${seconds}s"
    }

    /** rtsp:// towards go2rtc (the player forces RTSP over TCP itself). */
    fun rtspUrl(server: String?, stream: String?, port: Int = 8554): String? {
        val host = serverHost(server) ?: return null
        if (stream.isNullOrEmpty()) return null
        val h = if (':' in host) "[$host]" else host
        return "rtsp://$h:$port/${quote(stream)}"
    }

    fun mp4Url(server: String?, stream: String?): String? =
        if (server.isNullOrEmpty() || stream.isNullOrEmpty()) null else "$server/api/stream.mp4?src=${quote(stream)}"

    fun hlsUrl(server: String?, stream: String?): String? =
        if (server.isNullOrEmpty() || stream.isNullOrEmpty()) null else "$server/api/stream.m3u8?src=${quote(stream)}"

    fun validPort(value: Any?, default: Int): Int {
        val p = value?.toString()?.trim()?.toIntOrNull() ?: return default
        return if (p in 1..65535) p else default
    }
}

object Events {
    const val LIMIT = 20

    fun callerSource(userAgent: String?): String {
        val ua = (userAgent ?: "").lowercase()
        return if ("homeassistant" in ua || "home assistant" in ua || "aiohttp" in ua) "ha" else "api"
    }

    fun eventTitle(title: String, label: String?) = if (!label.isNullOrEmpty()) "$label · $title" else title

    /** Newest first, at most [limit]; returns the events that fell off. */
    fun <T> add(events: MutableList<T>, event: T, limit: Int = LIMIT): List<T> {
        events.add(0, event)
        val dropped = if (events.size > limit) events.subList(limit, events.size).toList() else emptyList()
        while (events.size > limit) events.removeAt(events.size - 1)
        return dropped
    }

    fun diagLine(ok: Boolean?, text: String) =
        "${when (ok) { true -> "[ OK ]"; false -> "[FAIL]"; null -> "[ -- ]" }}  ${Obs.redact(text)}"
}
