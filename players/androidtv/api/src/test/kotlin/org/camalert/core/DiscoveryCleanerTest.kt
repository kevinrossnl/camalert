package org.camalert.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** #116, the Kotlin twin of tests/core/test_mqtt.py TestDiscoveryCleaner. */
class DiscoveryCleanerTest {
    private val c = DiscoveryCleaner("node1")
    private val x = "{}".toByteArray()
    private fun cfg(oid: String, kind: String = "button", node: String = "node1") = "homeassistant/$kind/camalert_$node/$oid/config"

    @Test
    fun filter() = assertEquals("homeassistant/+/camalert_node1/+/config", MqttTopics.discoveryFilter("node1"))

    @Test
    fun waitsForTheCameraList() {
        assertEquals(emptyList<String>(), c.seen(cfg("show_old"), x))
        assertEquals(emptyList<String>(), c.seen(cfg("show_garden"), x))
        assertEquals(listOf(cfg("show_old")), c.known(listOf("garden", "front_door")))
        assertEquals(emptyList<String>(), c.seen(cfg("show_garden"), x))
        assertEquals(listOf(cfg("show_front_door_jpeg")), c.seen(cfg("show_front_door_jpeg"), x))
    }

    @Test
    fun keepsFixedEntitiesAndOtherPlayers() {
        c.known(listOf("garden"))
        for ((oid, kind) in listOf("mosaic" to "button", "hide" to "button", "on_screen" to "sensor", "dnd" to "switch", "button" to "event"))
            assertEquals(oid, emptyList<String>(), c.seen(cfg(oid, kind), x))
        assertEquals(emptyList<String>(), c.seen(cfg("show_old", node = "other"), x))
        assertEquals(emptyList<String>(), c.seen("camalert/node1/show", "garden".toByteArray()))
        assertEquals(emptyList<String>(), c.seen(cfg("show_old"), ByteArray(0)))
    }

    @Test
    fun unknownListRemovesNothing() {
        for (i in 0 until 600) c.seen(cfg("show_$i"), x)
        assertTrue(c.pending.size <= DiscoveryCleaner.MAX_PENDING)
    }

    @Test
    fun discoveryOff() {
        c.seen(cfg("show_garden"), x)
        assertEquals(listOf(cfg("show_garden")), c.disabled())
        assertEquals(listOf(cfg("mosaic")), c.seen(cfg("mosaic"), x))
        assertEquals(emptyList<String>(), c.seen(cfg("show_x", node = "other"), x))
        assertEquals(emptyList<String>(), c.known(listOf("garden")))
        assertEquals(emptyList<String>(), c.seen(cfg("mosaic"), x))
    }
}
