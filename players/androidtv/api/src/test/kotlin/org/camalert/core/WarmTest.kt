package org.camalert.core

import java.io.InputStream
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

/** Keep cameras ready (#111): same behaviour as core warm.py (tests/core/test_warm.py). */
class WarmTest {
    private fun part(data: String, length: Boolean = true): ByteArray {
        var head = "--frame\r\nContent-Type: image/jpeg\r\n"
        if (length) head += "Content-Length: ${data.length}\r\n"
        return (head + "\r\n" + data + "\r\n").toByteArray(Charsets.ISO_8859_1)
    }

    /** An endless MJPEG answer: one part per read; records close(). */
    private class FakeStream(val name: String) : InputStream() {
        @Volatile var closed = false
        var n = 0
        override fun read(): Int = throw UnsupportedOperationException()
        override fun read(b: ByteArray, off: Int, len: Int): Int {
            if (closed) return -1
            Thread.sleep(10)
            n++
            val p = ("--frame\r\nContent-Length: ${name.length + 3}\r\n\r\n$name#${n % 10}\r\n").toByteArray()
            System.arraycopy(p, 0, b, off, p.size)
            return p.size
        }
        override fun close() { closed = true }
    }

    private fun waitFor(timeoutMs: Long = 2000, cond: () -> Boolean): Boolean {
        val end = System.currentTimeMillis() + timeoutMs
        while (System.currentTimeMillis() < end) { if (cond()) return true; Thread.sleep(10) }
        return cond()
    }

    @Test
    fun parseReadyAndUrl() {
        assertEquals(emptyMap<String, String>(), Warm.parseReady(""))
        assertEquals(mapOf("front_door" to "front_door_jpeg", "garden" to "garden"),
            Warm.parseReady("front_door=front_door_jpeg| garden ,=x|back_door="))
        assertEquals("http://192.168.1.10:1984/api/stream.mjpeg?src=front%20door", Warm.mjpegUrl("192.168.1.10:1984", "front door"))
        assertNull(Warm.mjpegUrl("", "x"))
        assertNull(Warm.mjpegUrl("192.168.1.10", ""))
    }

    @Test
    fun helperStreamsAreNotCameras() {  // #113
        val names = listOf("back_door", "front_door", "front_door_jpeg", "garden")
        assertEquals(setOf("front_door_jpeg"), Warm.helperStreams("front_door=front_door_jpeg|garden"))
        assertEquals(listOf("back_door", "front_door", "garden"), Warm.visibleCameras(names, "front_door=front_door_jpeg"))
        assertEquals(names, Warm.visibleCameras(names, ""))
        assertEquals(names, Warm.visibleCameras(names, "garden"))
        assertEquals(names, Warm.visibleCameras(names, null))
    }

    @Test
    fun derivedStreamWhileRunning() {  // #117 on a real go2rtc 1.9.15: producer url = own RTSP server + source
        val running = "rtsp://127.0.0.1:8554/front_door?video&source=ffmpeg:front_door%23video%3Dmjpeg%23width%3D640"
        fun p(url: String) = mapOf("producers" to listOf(mapOf("url" to url)))
        val streams = mapOf(
            "front_door" to p("rtsp://192.168.1.10:7447/abc"),
            "front_door_jpeg" to p(running),
            "loop_sub" to p("rtsp://localhost:8554/front_door?video"),
            "elsewhere" to p("rtsp://127.0.0.1:8554/not_here?video"),
            "lan" to p("rtsp://192.168.1.10:8554/front_door"),
        )
        assertEquals(setOf("front_door_jpeg", "loop_sub"), Urls.derivedStreams(streams))
    }

    @Test
    fun compositeStreams() {  // #125: an own mosaic stream in go2rtc
        val mix = "exec:ffmpeg -hide_banner -rtsp_transport tcp -i rtsp://127.0.0.1:8554/front_door -rtsp_transport tcp " +
            "-i rtsp://127.0.0.1:8554/garden -i rtsp://127.0.0.1:8554/garage -i rtsp://127.0.0.1:8554/side " +
            "-filter_complex [0:v]fps=10[v0];[v0][v1]xstack=inputs=4 -c:v libx264 -f rtsp {output}"
        fun p(url: String) = mapOf("producers" to listOf(mapOf("url" to url)))
        val cam = p("rtsp://192.168.1.10:7447/abc")
        val streams = mapOf(
            "front_door" to cam, "garden" to cam, "garage" to cam, "side" to cam,
            "all_cameras" to p(mix),
            "one_input" to p("exec:ffmpeg -i rtsp://127.0.0.1:8554/garden -c:v copy -f rtsp {output}"),
            "lan_mix" to p("exec:ffmpeg -i rtsp://192.168.1.10/a -i rtsp://192.168.1.11/b -filter_complex hstack {output}"),
            "half_known" to p("exec:ffmpeg -i rtsp://127.0.0.1:8554/garden -i rtsp://127.0.0.1:8554/gone -filter_complex hstack {output}"),
        )
        assertEquals(setOf("all_cameras"), Urls.compositeStreams(streams))
        val json = Json.write(streams)
        val (names, comp) = Urls.streamInfoFromJson(json)
        assertTrue("all_cameras" in names)
        assertEquals(setOf("all_cameras"), comp)
        assertFalse("all_cameras" in Urls.overviewCameras(names, comp))
    }

    @Test
    fun talkStreamIsNeverACamera() {  // #98: <camera>_talk with only a backchannel source
        fun p(url: String) = mapOf("producers" to listOf(mapOf("url" to url)))
        val talk = "exec:ffmpeg -f alaw -ar 8000 -ac 1 -i - -c:a aac -f adts udp://192.168.1.14:7004#backchannel=1#audio=alaw/8000"
        val streams = mapOf("front_door" to p("rtsp://192.168.1.10:7447/abc"), "front_door_talk" to p(talk),
            "side_talk" to p("rtsp://192.168.1.12/x"))
        assertEquals(setOf("front_door_talk"), Urls.derivedStreams(streams))
        assertTrue(Urls.isBackchannel(talk))
        assertFalse(Urls.isBackchannel(null))
    }

    @Test
    fun parserInChunksAndWithoutLength() {
        val all = part("one") + part("two", false) + part("three")
        val p = MjpegParser()
        val got = ArrayList<String>()
        var i = 0
        while (i < all.size) {
            val chunk = all.copyOfRange(i, minOf(all.size, i + 7))
            p.feed(chunk).forEach { got.add(String(it, Charsets.ISO_8859_1)) }
            i += 7
        }
        assertEquals(listOf("one", "two", "three"), got)
        try {
            MjpegParser().feed("--frame\r\nContent-Length: x\r\n\r\n".toByteArray()); fail()
        } catch (e: IllegalStateException) {}
    }

    @Test
    fun readyOnlyWhileActive() {
        val opened = ArrayList<FakeStream>()
        val feeds = WarmFeeds({ url -> FakeStream(url.substringAfter("src=")).also { synchronized(opened) { opened.add(it) } } })
        feeds.update("192.168.1.10:1984", "", true)  // empty setting: nothing
        feeds.update("192.168.1.10:1984", "door=front_door", false)  // player off: nothing
        Thread.sleep(100)
        assertEquals(0, opened.size)
        assertEquals(listOf(Pair<Boolean?, String>(null, "Ready: door (not while the player is off)")), feeds.lines { it })
        val t0 = System.currentTimeMillis()
        feeds.update("192.168.1.10:1984", "door=front_door", true)
        assertTrue(waitFor(1000) { feeds.frame("door") != null })
        assertTrue(System.currentTimeMillis() - t0 < 1000)
        assertTrue(String(feeds.frame("door")!!).startsWith("front_door#"))
        assertTrue(feeds.lines { it }[0].first == true)
        feeds.update("192.168.1.10:1984", "door=front_door", true)  // unchanged: no new connection
        assertEquals(1, opened.size)
        feeds.update("192.168.1.10:1984", "door=front_door", false)  // standby: closed
        assertTrue(waitFor { opened[0].closed })
        assertNull(feeds.frame("door"))
        assertTrue(waitFor { feeds.running.isEmpty() })
    }

    @Test
    fun reconnectsAfterErrors() {
        var t = 1000.0
        val opens = ArrayList<String>()
        lateinit var feeds: WarmFeeds
        feeds = WarmFeeds({ url -> opens.add(url); if (opens.size >= 3) feeds.update("", "", false); throw java.io.IOException("refused") },
            clock = { t }, sleep = { t += it / 1000.0 }, start = { })
        feeds.update("192.168.1.10", "front_door", true)
        feeds.run("front_door", "u", 1)
        assertEquals(3, opens.size)
        assertTrue(feeds.running.isEmpty())
        assertFalse(feeds.active)
    }

    /** One picture, then nothing (a stalled feed) until closed. */
    private class StallStream : InputStream() {
        @Volatile var closed = false
        var sent = false
        override fun read(): Int = throw UnsupportedOperationException()
        override fun read(b: ByteArray, off: Int, len: Int): Int {
            if (!sent) {
                sent = true
                val p = "--frame\r\nContent-Length: 3\r\n\r\npic\r\n".toByteArray()
                System.arraycopy(p, 0, b, off, p.size)
                return p.size
            }
            while (!closed) Thread.sleep(10)
            return -1
        }
        override fun close() { closed = true }
    }

    @Test
    fun stalePictureIsNotUsed() {
        var t = 1000.0
        val feeds = WarmFeeds({ StallStream() }, clock = { t })
        feeds.update("192.168.1.10", "front_door", true)
        assertTrue(waitFor { feeds.frame("front_door") != null })
        assertEquals("pic", String(feeds.frame("front_door")!!))
        t += Warm.STALE_SECONDS + 0.1  // the feed stalled: the old picture is not used
        assertNull(feeds.frame("front_door"))
        assertTrue(feeds.lines { it }[0].first == false)
        feeds.stop()
    }
}
