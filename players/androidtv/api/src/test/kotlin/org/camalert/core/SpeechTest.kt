// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** #89: the same rules as camalert_core.speech (tests/core/test_speech.py). */
class SpeechTest {
    @Test
    fun setting() {
        assertTrue(Speech.speakWanted("high", "high"))
        assertTrue(Speech.speakWanted("high", "alarm"))
        assertFalse(Speech.speakWanted("high", "normal"))
        assertTrue(Speech.speakWanted("all", "normal"))
        assertFalse(Speech.speakWanted("off", "alarm"))
    }

    @Test
    fun request() {
        assertEquals(Pair(null, null), Speech.request(emptyMap(), null))
        assertEquals("Someone at the door", Speech.request(mapOf("say" to "  Someone  at the\tdoor "), null).second)
        assertEquals(Speech.MAX_TEXT, Speech.request(mapOf("say" to "x".repeat(999)), null).second!!.length)
        val url = "http://192.168.1.20:8123/api/tts_proxy/abc.wav"
        assertEquals(Pair(url, "Hi"), Speech.request(mapOf("say_url" to url, "say" to "Hi"), null))
        assertEquals("http://homeassistant.local:8123/a.wav", Speech.request(mapOf("say_url" to "http://homeassistant.local:8123/a.wav"), null).first)
        for (bad in listOf("http://8.8.8.8/a.wav", "https://tts.example.com/a.wav", "file:///etc/passwd", "http://192.168.1.2/" + "a".repeat(3000))) {
            try {
                Speech.request(mapOf("say_url" to bad), null)
                throw AssertionError("accepted $bad")
            } catch (e: Speech.SpeechError) {
            }
        }
    }

    @Test
    fun shouldSpeakAndWav() {
        val url = "http://192.168.1.20/a.wav"
        assertTrue(Speech.shouldSpeak("high", "high", "ha", "show", url, null))
        assertTrue(Speech.shouldSpeak("high", "alarm", "api", "wake", null, "Alarm"))
        assertFalse(Speech.shouldSpeak("high", "high", "test", "show", url, null))
        assertFalse(Speech.shouldSpeak("high", "high", "menu", "show", url, null))
        assertFalse(Speech.shouldSpeak("high", "high", "ha", "ignore", url, null))
        assertFalse(Speech.shouldSpeak("off", "alarm", "ha", "show", url, null))
        assertTrue(Speech.isWav("RIFF$\u0000\u0000\u0000WAVEfmt ".toByteArray(Charsets.ISO_8859_1) + ByteArray(24)))
        assertFalse(Speech.isWav("ID3\u0004".toByteArray(Charsets.ISO_8859_1) + ByteArray(20)))
        assertNull(Speech.request(mapOf("say" to "   "), null).second)
    }
}
