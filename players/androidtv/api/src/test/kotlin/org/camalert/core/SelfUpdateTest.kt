// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

/** #126, the same cases as tests/core/test_selfupdate.py. */
class SelfUpdateTest {
    private fun gitHub(version: String = "1.4.0", sums: String? = null, data: ByteArray? = null): (String) -> ByteArray {
        val name = SelfUpdate.assetName("androidtv", version)
        val body = data ?: "apk-$version".toByteArray()
        val files = mapOf(
            SelfUpdate.sumsUrl(version) to (sums ?: "${SelfUpdate.sha256(body)}  $name\n").toByteArray(),
            SelfUpdate.assetUrl("androidtv", version) to body,
        )
        return { url -> files[url] ?: throw java.io.IOException("404 $url") }
    }

    private fun refused(why: String, block: () -> Unit) {
        try {
            block()
            fail("expected UpdateError: $why")
        } catch (e: SelfUpdate.UpdateError) {
            assertTrue("${e.message} should contain $why", why in (e.message ?: ""))
        }
    }

    @Test
    fun requestRules() {
        assertEquals("1.4.0", SelfUpdate.checkRequest("1.3.1", "1.4.0"))
        assertEquals("1.3.2", SelfUpdate.checkRequest("1.3.1", "v1.3.2"))
        assertEquals("0.0.1", SelfUpdate.checkRequest("0.0.0-test", "0.0.1"))
        refused("off") { SelfUpdate.checkRequest("1.3.1", "1.4.0", false) }
        refused("not newer") { SelfUpdate.checkRequest("1.3.1", "1.3.1") }
        refused("not newer") { SelfUpdate.checkRequest("1.3.1", "1.2.0") }
        refused("not newer") { SelfUpdate.checkRequest("1.10.0", "1.9.9") }
        for (bad in listOf("1.4", "1.4.0-beta", "../1.4.0", "", null)) refused("invalid") { SelfUpdate.checkRequest("1.3.1", bad) }
    }

    @Test
    fun fixedUrlsAndSums() {
        assertEquals("https://github.com/kevinrossnl/camalert/releases/download/v1.4.0/camalert-androidtv-1.4.0.apk",
            SelfUpdate.assetUrl("androidtv", "1.4.0"))
        assertTrue(SelfUpdate.sumsUrl("1.4.0").endsWith("/v1.4.0/SHA256SUMS"))
        refused("no update file") { SelfUpdate.assetName("browser", "1.4.0") }
        val h = "a".repeat(64)
        assertEquals(mapOf("x.zip" to h, "y.apk" to h), SelfUpdate.parseSums("$h  x.zip\n${h.uppercase()} *y.apk\nnoise\n"))
    }

    @Test
    fun fetchChecksTheSum() {
        assertEquals("apk-1.4.0", String(SelfUpdate.fetch("androidtv", "1.4.0", gitHub()).second))
        refused("checksum") { SelfUpdate.fetch("androidtv", "1.4.0", gitHub(sums = "${"0".repeat(64)}  camalert-androidtv-1.4.0.apk\n")) }
        refused("not listed") { SelfUpdate.fetch("androidtv", "1.4.0", gitHub(sums = "")) }
        refused("size") { SelfUpdate.fetch("androidtv", "1.4.0", gitHub(data = ByteArray(0))) }
        try {
            SelfUpdate.fetch("androidtv", "1.4.0", gitHub(version = "9.9.9"))
            fail()
        } catch (e: java.io.IOException) {
        }
    }

    @Test
    fun state() {
        val st = SelfUpdate.UpdateState()
        assertEquals(mapOf("update_state" to "idle", "update_version" to null, "update_error" to null), st.asStatus())
        assertFalse(st.busy())
        st.set("downloading", "1.4.0")
        assertTrue(st.busy())
        st.set("failed", error = "checksum does not match")
        assertEquals("checksum does not match", st.asStatus()["update_error"])
        assertEquals("1.4.0", st.asStatus()["update_version"])
        st.set("waiting")
        assertEquals(null, st.error)
    }
}
