// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

/**
 * Spoken announcement with a request (#89), the same as camalert_core.speech: `say_url` (a WAV from Home
 * Assistant's TTS, in the local network) and `say` (the text; the app can speak it with Android's own engine when
 * there is no audio url). The setting `speak`: off / high (doorbell and alarm) / all; never for a test or the
 * viewer's own key, only when the request is shown.
 */
object Speech {
    const val MAX_TEXT = 300
    const val MAX_URL = 2048
    const val MAX_AUDIO = 4 * 1024 * 1024
    val CHOICES = listOf("off", "high", "all")

    class SpeechError(message: String) : IllegalArgumentException(message)

    fun speakWanted(setting: String?, priority: String?): Boolean =
        setting == "all" || (setting == "high" && priority in listOf("high", "alarm"))

    /** (url or null, text or null) from the request; SpeechError when say_url is invalid. No DNS lookups. */
    fun request(args: Map<String, String>, callerIp: String?): Pair<String?, String?> {
        val raw = args["say"]
        val text = if (raw.isNullOrEmpty()) null else raw.split(' ', '\t', '\n', '\r').filter { it.isNotEmpty() }
            .joinToString(" ").take(MAX_TEXT).ifEmpty { null }
        val u = args["say_url"]
        if (u.isNullOrEmpty()) return Pair(null, text)
        val url = u.trim()
        if (url.length > MAX_URL) throw SpeechError("say_url is too long")
        val why = Access.urlTarget(url, callerIp) { emptyList() }
        if (why != null) throw SpeechError("say_url: " + why.replace("url host name does not resolve", "use an IP address or a local name"))
        return Pair(url, text)
    }

    fun shouldSpeak(setting: String?, priority: String?, source: String, result: String, url: String?, text: String?): Boolean {
        if (url == null && text == null) return false
        if (result !in listOf("show", "extend", "wake")) return false
        if (source == "test" || source == "menu") return false
        return speakWanted(setting, priority ?: "normal")
    }

    fun isWav(data: ByteArray): Boolean = data.size > 12 &&
        data[0] == 'R'.code.toByte() && data[1] == 'I'.code.toByte() && data[2] == 'F'.code.toByte() && data[3] == 'F'.code.toByte() &&
        data[8] == 'W'.code.toByte() && data[9] == 'A'.code.toByte() && data[10] == 'V'.code.toByte() && data[11] == 'E'.code.toByte()
}
