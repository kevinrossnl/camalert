package org.camalert.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.concurrent.atomic.AtomicBoolean

/** #120: same scenarios as tests/core/test_wizard.py. */
class WizardTest {
    private val streams = """{"front_door": {"producers": [{"url": "rtsp://192.168.1.20:7447/abc"}]},
        "front_door_jpeg": {"producers": [{"url": "ffmpeg:front_door#video=mjpeg"}]},
        "garden": {"producers": [{"url": "rtsp://192.168.1.21/stream1"}]}}"""

    @Test fun opensOnlyOnANewPlayer() {
        assertTrue(Wizard.shouldStart(mapOf("server" to "")))
        assertTrue(Wizard.shouldStart(emptyMap()))
        assertFalse(Wizard.shouldStart(mapOf("server" to "http://192.168.1.10:1984")))
        assertFalse(Wizard.shouldStart(mapOf("server" to "", "wizard_done" to true)))
        assertFalse(Wizard.shouldStart(mapOf("server" to "", "source" to "direct")))
    }

    @Test fun steps() {
        assertEquals(listOf("go2rtc", "camera", "test", "done"), Wizard.STEPS)
        assertEquals("camera", Wizard.nextStep("go2rtc"))
        assertNull(Wizard.nextStep("done"))
    }

    @Test fun candidatesMostLikelyFirst() {
        val c = Wizard.candidates("192.168.1.50", "192.168.1.10")
        assertEquals(listOf("http://homeassistant.local:1984", "http://192.168.1.10:1984"), c.take(2))
        assertEquals(2 + 253, c.size)
        assertTrue("http://192.168.1.50:1984" in c)
        assertEquals(listOf("http://homeassistant.local:1984"), Wizard.candidates(null))
        assertEquals(listOf("http://homeassistant.local:1984"), Wizard.candidates("fe80::1"))
    }

    @Test fun haHost() {
        assertEquals("192.168.1.10", Wizard.haHost(mapOf("ha_webhook" to "http://192.168.1.10:8123/api/webhook/x")))
        assertEquals("192.168.1.11", Wizard.haHost(mapOf("mqtt_host" to "192.168.1.11")))
        assertNull(Wizard.haHost(emptyMap()))
    }

    @Test fun scanFindsGo2rtcInOrderAndIgnoresOtherServices() {
        val go2rtc = setOf("http://192.168.1.30:1984", "http://homeassistant.local:1984")
        val found = Wizard.scan(Wizard.candidates("192.168.1.50"), { srv ->
            when {
                srv in go2rtc -> Wizard.camerasFrom(streams)
                srv == "http://192.168.1.1:1984" -> Wizard.camerasFrom("<html>router</html>")
                else -> null
            }
        })
        assertEquals(listOf("http://homeassistant.local:1984", "http://192.168.1.30:1984"), found.map { it.first })
        assertEquals(listOf("front_door", "garden"), found[0].second)  // helper streams left out
    }

    @Test fun scanHasATimeLimit() {
        val start = System.currentTimeMillis()
        val found = Wizard.scan(Wizard.candidates("192.168.1.50"), { srv ->
            if (srv == "http://192.168.1.2:1984") listOf("front_door") else { Thread.sleep(5000); null }
        }, budgetMs = 500)
        assertTrue(System.currentTimeMillis() - start < 2000)
        assertEquals(listOf("http://192.168.1.2:1984"), found.map { it.first })
    }

    @Test fun scanCanBeStopped() {
        assertEquals(emptyList<Pair<String, List<String>>>(),
            Wizard.scan(listOf("http://192.168.1.2:1984"), { listOf("front_door") }, stop = AtomicBoolean(true)))
    }

    @Test fun sameGo2rtcUnderTwoAddressesOnce() {
        val found = listOf(Pair("http://homeassistant.local:1984", listOf("front_door")),
            Pair("http://192.168.1.10:1984", listOf("front_door")), Pair("http://192.168.1.30:1984", listOf("garden")))
        assertEquals(listOf("http://homeassistant.local:1984", "http://192.168.1.30:1984"),
            Wizard.uniqueServers(found).map { it.first })
    }

    @Test fun answers() {
        assertEquals(emptyList<String>(), Wizard.camerasFrom("{}"))
        assertNull(Wizard.camerasFrom("[1]"))
        assertNull(Wizard.camerasFrom("not json"))
    }

    @Test fun typedAddress() {
        assertEquals("http://192.168.1.10:1984", Wizard.serverFromInput("192.168.1.10"))
        assertEquals("http://192.168.1.10:1985", Wizard.serverFromInput(" http://192.168.1.10:1985/ "))
        assertNull(Wizard.serverFromInput(""))
        assertNull(Wizard.serverFromInput("http://"))
    }

    @Test fun resultAndLastScreen() {
        assertEquals(mapOf("wizard_done" to true, "source" to "go2rtc", "server" to "http://192.168.1.10:1984",
            "camera" to "garden"), Wizard.result("http://192.168.1.10:1984", "garden"))
        assertEquals(mapOf("wizard_done" to true), Wizard.result())
        assertEquals(Pair("TV player", "192.168.1.40:8099"), Wizard.addText("TV player", "192.168.1.40", 8099))
    }
}
