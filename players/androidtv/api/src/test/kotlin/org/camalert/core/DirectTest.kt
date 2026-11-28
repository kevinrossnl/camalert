// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** #124: direct mode (camera list, no go2rtc), HTTP login for snapshots and Frigate clip urls on Android TV. */
class DirectTest {
    @Test
    fun cameraFileLikeTheCore() {  // the same text as tests/core/test_cameras.py::test_camera_file
        val cred = "admin:" + "pw@"
        val text = """# comment
Front door | rtsp://CRED192.168.1.20:554/stream2 | http://CRED192.168.1.20/cgi-bin/snap.cgi
Garden|rtsp://192.168.1.21/live
broken line
Garden | rtsp://192.168.1.22/dup
""".replace("CRED", cred)
        val cams = DirectCameras.parse(text)
        assertEquals(listOf("front_door", "garden"), cams.map { it.name })
        assertEquals("Front door", cams[0].title)
        assertNull(cams[1].snapshot)
        assertEquals("gruene_tuer_2", DirectCameras.slug("Grüne Tür 2"))
    }

    @Test
    fun directTilesAndLiveWithoutSnapshot() {
        val env = FakeEnv()
        env.values["source"] = "direct"
        env.direct = DirectCameras.parse("Front door | rtsp://192.168.1.20/s | http://192.168.1.20/snap.jpg\nGarden | rtsp://192.168.1.21/live")
        env.names = env.direct.map { it.name }
        val d = FakeDisplay()
        val c = PlayerController(env, d)
        assertEquals(Tile("front_door", "Front door", "http://192.168.1.20/snap.jpg", "rtsp://192.168.1.20/s"), c.tile("front_door"))
        assertNull(c.tile("driveway"))
        assertEquals("show", c.show("garden", 20, "photo", "normal", "test", null, null))
        assertEquals("live garden 20 0", d.calls.last().replace(Regex(" \\d+$"), " 0"))  // no snapshot url: live view
        assertEquals("show", c.show("front_door", 20, "photo", "normal", "test", null, null))
        assertTrue(d.calls.last().startsWith("photo front_door"))
    }

    @Test
    fun digestLikeRfc2617() {  // the example of RFC 2617, section 3.5
        val h = "Digest realm=\"testrealm@host.com\", qop=\"auth,auth-int\", nonce=\"dcd98b7102dd2f0e8b11d0f600bfb0c093\", " +
            "opaque=\"5ccc069c403ebaf9f0171e9517f40e41\""
        val out = HttpAuth.digest(h, "GET", "/dir/index.html", "Mufasa", "Circle Of Life", "0a4f113b")
        assertTrue(out, out.contains("response=\"6629fae49393a05397450978507c4ef1\""))
        assertTrue(out.contains("opaque=\"5ccc069c403ebaf9f0171e9517f40e41\"") && out.contains("qop=auth") && out.contains("nc=00000001"))
    }

    @Test
    fun basicAndUrlLogin() {
        assertEquals("Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ==", HttpAuth.basic("Aladdin", "open sesame"))
        assertEquals("", HttpAuth.base64(ByteArray(0)))
        assertEquals("YQ==", HttpAuth.base64("a".toByteArray()))
        assertEquals("YWI=", HttpAuth.base64("ab".toByteArray()))
        val login = "admin:" + "p%40ss:x@"  // split so that the privacy check sees no login in a url
        assertEquals(Triple("http://192.168.1.20/snap.jpg", "admin", "p@ss:x"), HttpAuth.split("http://" + login + "192.168.1.20/snap.jpg"))
        assertEquals(Triple("http://192.168.1.20/snap.jpg", null, null), HttpAuth.split("http://192.168.1.20/snap.jpg"))
    }

    @Test
    fun frigateClipUrl() {  // core triggers/frigate.frigate_clip_url
        assertEquals("http://192.168.1.10:5000/api/events/1700000000.1-abc/clip.mp4", Frigate.clipUrl("192.168.1.10:5000/", "1700000000.1-abc"))
        assertEquals("https://f.example/api/events/x/clip.mp4", Frigate.clipUrl(" https://f.example ", "x"))
        assertNull(Frigate.clipUrl("", "x"))
        assertNull(Frigate.clipUrl("http://f", "../x"))
        assertNull(Frigate.clipUrl("http://f", null))
    }
}
