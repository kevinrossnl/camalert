// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

import java.security.MessageDigest

/** A camera of direct mode (no go2rtc, #124): core cameras.parse_camera_file. */
data class DirectCamera(val name: String, val title: String, val rtsp: String, val snapshot: String?)

/** Direct mode (#124): the camera list of the other players' cameras.conf, one camera per line. */
object DirectCameras {
    private val LIVE = listOf("rtsp://", "rtsps://", "rtspt://", "http://", "https://")

    /** 'Front Door' -> 'front_door' (core cameras.slug, umlauts included). */
    fun slug(name: String?): String {
        var n = (name ?: "").lowercase()
        for ((a, b) in listOf("ä" to "ae", "ö" to "oe", "ü" to "ue", "ß" to "ss", "é" to "e", "è" to "e", "à" to "a")) n = n.replace(a, b)
        val out = StringBuilder()
        var sep = false
        for (c in n) {
            if (c in 'a'..'z' || c in '0'..'9') {
                if (sep && out.isNotEmpty()) out.append('_')
                sep = false
                out.append(c)
            } else sep = true
        }
        return out.toString()
    }

    /** name | rtsp-url | snapshot-url (optional), # = comment; core cameras.parse_camera_file. */
    fun parse(text: String?): List<DirectCamera> {
        val cams = ArrayList<DirectCamera>()
        for (raw in (text ?: "").lines()) {
            val line = raw.trim()
            if (line.isEmpty() || line.startsWith("#")) continue
            val parts = line.split("|").map { it.trim() }
            if (parts.size < 2 || LIVE.none { parts[1].startsWith(it) }) continue
            val name = slug(parts[0])
            if (name.isEmpty() || cams.any { it.name == name }) continue
            val snap = if (parts.size > 2 && (parts[2].startsWith("http://") || parts[2].startsWith("https://"))) parts[2] else null
            cams.add(DirectCamera(name, parts[0], parts[1], snap))
        }
        return cams
    }
}

/**
 * user:password@ in a snapshot url (#124): HttpURLConnection ignores it, so the app answers a 401 itself with Basic
 * or Digest (RFC 7616, MD5 and qop=auth, as cameras use). Base64 is our own: java.util.Base64 needs Android 8.
 */
object HttpAuth {
    /** (url without the login, user, password); user null when the url has none. */
    fun split(url: String): Triple<String, String?, String?> {
        val m = Regex("^([a-zA-Z][a-zA-Z0-9+.-]*://)([^/@]*)@(.*)$").find(url) ?: return Triple(url, null, null)
        val (scheme, info, rest) = m.destructured
        val user = info.substringBefore(":")
        val pass = if (":" in info) info.substringAfter(":") else ""
        return Triple(scheme + rest, decode(user), decode(pass))
    }

    private fun decode(s: String) = try { java.net.URLDecoder.decode(s.replace("+", "%2B"), "UTF-8") } catch (e: Exception) { s }

    fun basic(user: String, password: String): String = "Basic " + base64("$user:$password".toByteArray(Charsets.UTF_8))

    /** Parameters of a WWW-Authenticate: Digest challenge (realm, nonce, qop, opaque, algorithm). */
    fun challenge(header: String): Map<String, String> {
        val out = HashMap<String, String>()
        Regex("(\\w+)=(\"([^\"]*)\"|([^,\\s]+))").findAll(header.substringAfter(" ", "")).forEach {
            out[it.groupValues[1].lowercase()] = it.groupValues[3].ifEmpty { it.groupValues[4] }
        }
        return out
    }

    fun digest(header: String, method: String, uri: String, user: String, password: String, cnonce: String, nc: String = "00000001"): String {
        val c = challenge(header)
        val realm = c["realm"] ?: ""
        val nonce = c["nonce"] ?: ""
        val qop = c["qop"]?.split(",")?.map { it.trim() }?.firstOrNull { it == "auth" }
        val ha1 = md5("$user:$realm:$password")
        val ha2 = md5("$method:$uri")
        val response = if (qop != null) md5("$ha1:$nonce:$nc:$cnonce:$qop:$ha2") else md5("$ha1:$nonce:$ha2")
        val parts = mutableListOf("username=\"$user\"", "realm=\"$realm\"", "nonce=\"$nonce\"", "uri=\"$uri\"", "response=\"$response\"")
        if (qop != null) parts += listOf("qop=$qop", "nc=$nc", "cnonce=\"$cnonce\"")
        c["opaque"]?.let { parts += "opaque=\"$it\"" }
        c["algorithm"]?.let { parts += "algorithm=$it" }
        return "Digest " + parts.joinToString(", ")
    }

    private fun md5(s: String) = MessageDigest.getInstance("MD5").digest(s.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }

    private const val ABC = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"

    fun base64(data: ByteArray): String {
        val sb = StringBuilder()
        var i = 0
        while (i < data.size) {
            val b0 = data[i].toInt() and 0xff
            val b1 = if (i + 1 < data.size) data[i + 1].toInt() and 0xff else -1
            val b2 = if (i + 2 < data.size) data[i + 2].toInt() and 0xff else -1
            sb.append(ABC[b0 shr 2])
            sb.append(ABC[((b0 and 3) shl 4) or (if (b1 < 0) 0 else b1 shr 4)])
            sb.append(if (b1 < 0) '=' else ABC[((b1 and 15) shl 2) or (if (b2 < 0) 0 else b2 shr 6)])
            sb.append(if (b2 < 0) '=' else ABC[b2 and 63])
            i += 3
        }
        return sb.toString()
    }
}
