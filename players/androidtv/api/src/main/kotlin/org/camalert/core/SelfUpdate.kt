// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

import java.security.MessageDigest

/**
 * Updating a player from Home Assistant (#126), the same as camalert_core.selfupdate: only CamAlert's own GitHub
 * release (a fixed URL), only a newer version, only a file whose SHA-256 is in the release's SHA256SUMS.
 */
object SelfUpdate {
    const val REPO = "kevinrossnl/camalert"
    const val SUMS = "SHA256SUMS"
    const val MAX_BYTES = 64 * 1024 * 1024
    val ASSETS = mapOf(
        "enigma2" to "enigma2-plugin-extensions-camalert_%s_all.ipk",
        "kodi" to "service.camalert-%s.zip",
        "androidtv" to "camalert-androidtv-%s.apk",
    )
    val STATES = listOf("idle", "downloading", "installing", "waiting", "failed")
    private val VERSION = Regex("^\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}$")

    class UpdateError(message: String) : Exception(message)

    fun releaseBase(version: String) = "https://github.com/$REPO/releases/download/v$version/"

    /** Like camalert_core.update.version_tuple: the first four numbers. */
    fun versionTuple(v: String?): List<Int> =
        Regex("\\d+").findAll((v ?: "").trimStart('v', 'V')).take(4).map { it.value.toInt() }.toList().ifEmpty { listOf(0) }

    private fun newer(a: List<Int>, b: List<Int>): Boolean {
        for (i in 0 until maxOf(a.size, b.size)) {
            val x = a.getOrElse(i) { -1 }
            val y = b.getOrElse(i) { -1 }
            if (x != y) return x > y
        }
        return false
    }

    /** The version to install, or UpdateError: updates off, not a plain X.Y.Z version, or not newer. */
    fun checkRequest(current: String, version: String?, allowed: Boolean = true): String {
        if (!allowed) throw UpdateError("updates from Home Assistant are off")
        val v = (version ?: "").trim().trimStart('v', 'V')
        if (!VERSION.matches(v)) throw UpdateError("invalid version")
        if (!newer(versionTuple(v), versionTuple(current))) throw UpdateError("not newer than the installed version")
        return v
    }

    fun assetName(platform: String, version: String): String =
        (ASSETS[platform] ?: throw UpdateError("no update file for this player")).format(version)

    fun assetUrl(platform: String, version: String) = releaseBase(version) + assetName(platform, version)

    fun sumsUrl(version: String) = releaseBase(version) + SUMS

    fun parseSums(text: String?): Map<String, String> {
        val out = LinkedHashMap<String, String>()
        for (line in (text ?: "").lines()) {
            val m = Regex("^([0-9a-fA-F]{64})\\s+\\*?(\\S.*?)\\s*$").find(line) ?: continue
            out[m.groupValues[2]] = m.groupValues[1].lowercase()
        }
        return out
    }

    fun sha256(data: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(data).joinToString("") { "%02x".format(it) }

    /** (file name, bytes) of the checked release file; opener(url) returns the body. */
    fun fetch(platform: String, version: String, opener: (String) -> ByteArray): Pair<String, ByteArray> {
        val name = assetName(platform, version)
        val want = parseSums(String(opener(sumsUrl(version)), Charsets.UTF_8))[name]
            ?: throw UpdateError("$name is not listed in $SUMS")
        val data = opener(assetUrl(platform, version))
        if (data.isEmpty() || data.size > MAX_BYTES) throw UpdateError("download has an unexpected size")
        if (sha256(data) != want) throw UpdateError("checksum does not match")
        return Pair(name, data)
    }

    /** update_state / update_version / update_error in /camalert/status. */
    class UpdateState {
        @Volatile var state = "idle"; private set
        @Volatile var version: String? = null; private set
        @Volatile var error: String? = null; private set

        @Synchronized
        fun set(state: String, version: String? = null, error: String? = null): UpdateState {
            require(state in STATES) { state }
            this.state = state
            if (version != null) this.version = version
            this.error = if (state == "failed") error else null
            return this
        }

        fun busy() = state in listOf("downloading", "installing", "waiting")

        fun asStatus(): Map<String, Any?> = linkedMapOf("update_state" to state, "update_version" to version, "update_error" to error)
    }
}
