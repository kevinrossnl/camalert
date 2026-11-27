// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/** show / mosaic / tour / hide rules of the Android TV player (the same rules as Kodi's controller.py). */
class PlayerControllerTest {
    private lateinit var env: FakeEnv
    private lateinit var display: FakeDisplay
    private lateinit var ctl: PlayerController

    @Before
    fun setUp() {
        env = FakeEnv()
        env.values["server"] = "http://192.168.1.10:1984"
        env.values["camera"] = "front_door"
        display = FakeDisplay()
        ctl = PlayerController(env, display)
    }

    private fun show(cam: String? = null, mode: String? = null, priority: String? = null, sec: Int? = null) =
        ctl.show(cam, sec, mode, priority, "api", null)

    @Test
    fun photoWindowWithDefaults() {
        assertEquals("show", show())
        assertEquals(listOf("photo front_door 30"), display.calls)
        assertEquals("front_door", ctl.status()["window"])
        assertEquals("photo", ctl.status()["screen"])
        ctl.hide()
        assertEquals("none", ctl.status()["screen"])
        val e = ctl.events[0]
        assertEquals(listOf("front_door", "api", "normal", "show", ""), listOf(e["camera"], e["source"], e["priority"], e["action"], e["reason"]))
    }

    @Test
    fun logOnlyModeRecordsButShowsNothing() {
        // display mode 'log' of the UniFi Protect rules (#72, like Kodi #71): event list and log, no window, no chime
        env.values["chime"] = "all"
        assertEquals("ignore", ctl.show("garden", null, "log", "high", "unifi", "Person"))
        assertEquals(emptyList<String>(), display.calls)
        assertEquals(0, env.chimes)
        val e = ctl.events[0]
        assertEquals(listOf("garden", "unifi", "high", "ignore", "log_only", "Person"),
            listOf(e["camera"], e["source"], e["priority"], e["action"], e["reason"], e["label"]))
        assertTrue(env.logs.last().contains("mode=log") && env.logs.last().endsWith("-> ignore (log_only)"))
        assertEquals("show", show("garden"))  // no cooldown started by a log-only event
    }

    @Test
    fun sameCameraExtendsOtherCameraReplaces() {
        show("garden")
        assertEquals("extend", show("garden", sec = 20))
        assertEquals("show", show("front_door"))
        assertEquals(listOf("photo garden 30", "extend 20", "photo front_door 30"), display.calls)
    }

    @Test
    fun tilesHaveGo2rtcUrls() {
        env.values["live_format"] = "rtsp"
        env.values["titles"] = "garden=Back garden"
        val t = ctl.tile("garden")!!
        assertEquals("http://192.168.1.10:1984/api/frame.jpeg?src=garden&width=640", t.snapshot)
        assertEquals("rtsp://192.168.1.10:8554/garden", t.live)
        assertEquals("Back garden", t.title)
        env.values["live_format"] = "mp4"
        env.values["substreams"] = "garden=garden_sub"
        assertEquals("http://192.168.1.10:1984/api/stream.mp4?src=garden_sub", ctl.tile("garden")!!.live)
        env.values["server"] = ""
        assertNull(ctl.tile("garden"))
    }

    @Test
    fun liveAndNotify() {
        env.values["live_volume"] = 40
        assertEquals("show", show("garden", mode = "live"))
        assertEquals("live garden 30 40", display.calls.last())
        assertEquals("garden", ctl.status()["live"])
        assertEquals("show", show("front_door", mode = "live", priority = "alarm"))
        assertEquals("live front_door 30 100", display.calls.last())  // alarm: volume unchanged
        assertEquals("show", show("garden", mode = "notify"))
        assertEquals("notify garden 30", display.calls.last())
        assertEquals("notification", ctl.status()["screen"])
    }

    @Test
    fun severalCameras() {
        assertEquals("show", show("garden,front_door"))
        assertEquals("photo garden,front_door 30", display.calls.last())
        assertEquals("strip", display.screen().kind)
        assertEquals("show", show("a,b,c,d,e"))
        assertEquals("mosaic a,b,c,d,e 30", display.calls.last())
    }

    @Test
    fun rules() {
        env.values["dnd"] = true
        assertEquals("ignore", show("garden"))
        assertEquals("dnd", ctl.events[0]["reason"])
        assertEquals("show", show("garden", priority = "alarm"))
        display.hide()
        env.values["dnd"] = false
        env.values["limit_hours"] = true
        env.values["from_time"] = "07:00"; env.values["until_time"] = "08:00"
        assertEquals("ignore", show("garden"))
        assertEquals("outside_hours", ctl.events[0]["reason"])
        assertEquals("show", show("garden", priority = "high"))
        display.hide()
        env.values["limit_hours"] = false
        env.values["skip_playing"] = "video"
        env.nowPlaying = "video"
        assertEquals("ignore", show("garden"))
        assertEquals("playing", ctl.events[0]["reason"])
        env.nowPlaying = "audio"
        assertEquals("show", show("garden"))
    }

    @Test
    fun cooldownUnknownCameraAndScreenOff() {
        env.values["cooldown"] = "*=60"
        assertEquals("show", show("garden"))
        display.hide()
        env.time += 10
        assertEquals("ignore", show("garden"))
        assertEquals("cooldown:60", ctl.events[0]["reason"])
        assertEquals("show", show("garden", priority = "alarm"))
        assertEquals("error", show("nonsense"))
        assertEquals("unknown_camera", ctl.events[0]["reason"])
        env.on = false
        assertEquals("ignore", show("front_door", priority = "high"))
        assertEquals("screen_off", ctl.events[0]["reason"])
        env.values["alarm_wake"] = true
        assertEquals("wake", show("front_door", priority = "alarm"))
    }

    @Test
    fun chimeOnlyWhenWanted() {
        show("garden", priority = "high")
        assertEquals(0, env.chimes)  // default off
        display.hide()
        env.values["chime"] = "high"
        show("front_door", priority = "high")
        assertEquals(1, env.chimes)
        ctl.show("garden", null, null, "alarm", "test", null)
        assertEquals(1, env.chimes)  // test requests never ring (#62)
    }

    @Test
    fun mosaicTourHideDnd() {
        env.values["mosaic"] = "garden,driveway"
        assertEquals("show", ctl.mosaic(null, 60))
        assertEquals("mosaic garden,driveway 60", display.calls.last())
        assertEquals("show", ctl.tour("front_door,garden", null))
        assertEquals("tour front_door,garden 8", display.calls.last())
        assertEquals("tour", ctl.status()["screen"])
        ctl.hide()
        assertEquals("none", ctl.status()["screen"])
        ctl.setDnd(true)
        assertEquals(true, ctl.status()["dnd"])
        env.values["server"] = ""
        assertEquals("error", ctl.mosaic(null, 60))
    }

    @Test
    fun eventListKeepsTwenty() {
        repeat(25) { ctl.show("nonsense$it", null, null, null, "api", null) }
        assertEquals(20, ctl.events.size)
        assertEquals("nonsense24", ctl.events[0]["camera"])
    }

    @Test
    fun metrics() {
        show("garden")
        val m = ctl.metrics("1.0.0", "androidtv")
        assertTrue(m, "camalert_requests_total{platform=\"androidtv\",version=\"1.0.0\",key=\"show\"} 1" in m)
        assertTrue(m, "camalert_on_screen{platform=\"androidtv\",version=\"1.0.0\"} 1" in m)
    }

    @Test
    fun jsonNumbersLikePython() {
        assertEquals("[1795536963.528, 2.5, 12.0, 20, 0.001]", Json.write(listOf(1795536963.528, 2.5, 12.0, 20, 0.001)))
        assertEquals(mapOf("a" to listOf(1L, true, null, "x\u00e9")), Json.parse("{\"a\": [1, true, null, \"x\\u00e9\"]}"))
    }

    @Test
    fun presentAndNames() {
        val p = Present()
        assertEquals("Garden   (2/5, tour)", p.tourStatus("Garden", 2, 5, false))
        assertEquals("Cooldown (30 s)", p.reasonLabel("cooldown:30"))
        assertEquals("live", p.actionFor("window", "OK"))
        assertEquals(listOf("a", "b"), Cameras.parseCams("a, b,a ../x"))
        assertEquals("http://[fd00::10]:1984", Urls.normalizeServer("fd00::10"))
        assertEquals("http://192.168.1.10:1984", Urls.normalizeServer("192.168.1.10/"))
        assertEquals("https://h:443", Urls.normalizeServer("https://h"))
        assertNull(Urls.normalizeServer("ftp://x"))
        assertEquals(listOf("a", "b"), Urls.streamsFromJson("{\"b\": {}, \"a\": {}, \"../x\": {}}"))
        // #117: a stream that only transcodes another stream of the same go2rtc is a helper, not a camera
        val streams = """{"front_door": {"producers": [{"url": "rtsp://192.168.1.10/x"}]},
            "front_door_jpeg": {"producers": [{"url": "ffmpeg:front_door#video=mjpeg#width=640"}]},
            "garden": {"producers": [{"url": "ffmpeg:rtsp://192.168.1.11/s#video=h264"}]},
            "mixed": {"producers": [{"url": "ffmpeg:front_door#video=mjpeg"}, {"url": "rtsp://192.168.1.12/x"}]},
            "orphan": {"producers": [{"url": "ffmpeg:gone#video=mjpeg"}]}}"""
        assertEquals(listOf("front_door", "garden", "mixed", "orphan"), Urls.streamsFromJson(streams))
        assertEquals(setOf("front_door_jpeg"), Urls.derivedStreams(Json.parse(streams) as Map<*, *>))
        assertEquals(Pair(22, 30), Rules.clockTuple("22:30"))
        assertTrue(Rules.inTimeWindow(Pair(23, 0), Pair(22, 0), Pair(6, 0)))
        assertEquals(mapOf("garden" to 0.5), Cameras.parseRefresh("garden=0.1|x=abc"))
    }
}
