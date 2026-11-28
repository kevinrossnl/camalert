// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** #82: the same signed colour-key payload as core keymap.button_event (fixed vector from tests/core/test_keymap.py). */
class SignedButtonTest {
    private val secret = "ab".repeat(32)

    @Test
    fun sameSignatureAsTheCore() {
        assertEquals("9475c980198548186a1f9043e69695c6726fdaa8a541b2217a0815ea4c35370e",
            MqttTopics.buttonSignature(secret, "node1", "gate", "green", 1700000000L, "0f".repeat(16)))
        val d = Json.parse(MqttTopics.buttonEvent("node1", "gate", "green", secret, 1700000000L, "0f".repeat(16))) as Map<*, *>
        assertEquals("9475c980198548186a1f9043e69695c6726fdaa8a541b2217a0815ea4c35370e", d["sig"])
        assertEquals(1700000000L, (d["ts"] as Number).toLong())
    }

    @Test
    fun unsignedWithoutSecretAndFreshNonce() {
        val plain = Json.parse(MqttTopics.buttonEvent("n", "c", "red")) as Map<*, *>
        assertFalse("sig" in plain)
        val a = Json.parse(MqttTopics.buttonEvent("n", "c", "red", secret)) as Map<*, *>
        val b = Json.parse(MqttTopics.buttonEvent("n", "c", "red", secret)) as Map<*, *>
        assertNotEquals(a["nonce"], b["nonce"])
        assertTrue(Regex("^[0-9a-f]{32}$").matches(a["nonce"] as String))
    }
}
