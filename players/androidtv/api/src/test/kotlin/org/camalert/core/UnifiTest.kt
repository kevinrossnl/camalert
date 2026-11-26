// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

/** UniFi Protect source on Android TV (#72): same answers as the Python core, session and poller against a fake. */
@Suppress("UNCHECKED_CAST")
class UnifiTest {
    private val ref = Exported.core["unifi"] as Map<String, Any?>
    private fun cases(name: String) = ref[name] as List<Map<String, Any?>>
    private fun j(v: Any?) = Json.write(v, true)

    @Test
    fun helpersGiveTheCoreAnswers() {
        for (c in cases("slug")) assertEquals("slug(${c["in"]})", c["out"], Unifi.slug(c["in"] as String?))
        for (c in cases("protect_cameras")) assertEquals(j(c["out"]), j(Unifi.protectCameras(c["in"])))
        for (c in cases("camera_map")) assertEquals(j(c["out"]), j(Unifi.cameraMap(c["in"] as String?)))
        for (c in cases("wanted_kinds")) assertEquals("wanted_kinds(${c["in"]})", c["out"], Unifi.wantedKinds(c["in"] as String?))
        for (c in cases("kind_rules")) {
            val got = Unifi.kindRules(c["in"] as String?).mapValues { listOf(it.value.priority, it.value.mode, it.value.camera) }
            assertEquals("kind_rules(${c["in"]})", j(c["out"]), j(got))
        }
        for (c in cases("camera_rules")) {
            val got = Unifi.cameraRules(c["in"] as String?).mapValues { listOf(it.value.priority, it.value.mode, it.value.seconds) }
            assertEquals("camera_rules(${c["in"]})", j(c["out"]), j(got))
        }
        for (c in cases("event_kinds")) assertEquals(j(c["out"]), j(Unifi.eventKinds(c["in"] as Map<*, *>?)))
        for (c in cases("events_path")) {
            val a = c["args"] as List<Number>
            assertEquals(c["out"], Unifi.eventsPath(a[0].toLong(), a[1].toLong(), a[2].toInt()))
        }
        for (c in cases("snapshot_path")) {
            val got = try { mapOf("ok" to Unifi.snapshotPath(c["in"] as String?)) } catch (e: IllegalArgumentException) { mapOf("error" to e.message) }
            assertEquals(j(c["out"]), j(got))
        }
        for (c in cases("match")) {
            val m = Unifi.match(c["ev"] as Map<*, *>, c["cams"] as Map<*, *>, c["kinds"] as List<String>, c["names"] as Map<String, String>)
            assertEquals(j(c["out"]), j(m?.toList()))
        }
        assertEquals(j(ref["kind_labels"]), j(Unifi.KIND_LABELS))
    }

    @Test
    fun checkGivesTheCoreTrigger() {
        for (c in cases("check")) {
            val t = Unifi.check(c["settings"] as Map<String, Any?>, c["previous"] as Map<*, *>?, c["now"] as Map<*, *>?)
            val got = t?.let { mapOf("camera" to it.camera, "priority" to it.priority, "label" to it.label, "mode" to it.mode, "seconds" to it.seconds) }
            assertEquals("check(${c["settings"]}, ${c["previous"]})", j(c["out"]), j(got))
        }
    }

    @Test
    fun loginBackoffAndRetryAfter() {
        for (c in cases("retry_after")) {
            assertEquals("retry_after(${c["value"]})", (c["out"] as Number?)?.toInt(),
                LoginBackoff.retryAfter(c["value"] as String?, (c["now"] as Number).toDouble()))
        }
        val b = LoginBackoff()
        for (c in cases("backoff")) {
            val e = b.failed(LoginError("x", "auth"), 1000.0, (c["wait"] as Number?)?.toInt())
            assertEquals((c["next_in"] as Number).toDouble(), e.nextAt!! - 1000.0, 0.0)
            assertEquals((c["failures"] as Number).toInt(), b.failures)
        }
    }

    @Test
    fun diagnosticsLines() {
        for (c in cases("poll_status")) {
            val st = PollStatus()
            val news = ArrayList<Boolean>()
            for (step in c["steps"] as List<List<Any?>>) {
                when (step[0]) {
                    "consoles" -> st.consoles = (step[1] as Number).toInt()
                    "ok" -> st.ok((step[1] as Number).toDouble())
                    "fail" -> {
                        val err = if (step[3] != null) LoginError(step[2] as String, "auth", (step[3] as Number).toDouble()) else ProtectError(step[2] as String)
                        news.add(st.failed(err, (step[1] as Number).toDouble()))
                    }
                    else -> st.event(Unifi.Trigger(step[2] as String, step[4] as String, step[3] as String?, step[5] as String?, null), (step[1] as Number).toDouble())
                }
            }
            assertEquals(c["new"], news)
            val got = st.lines({ it }, { "t${it.toLong()}" }).map { listOf(it.first, it.second) }
            assertEquals(j(c["lines"]), j(got))
        }
    }

    // --- session and poller against a fake console ------------------------------------------------------------

    private class FakeConsole : Transport {
        val calls = ArrayList<Pair<String, String>>()
        var loginCode = 200
        var getCode = 200
        var retryAfter: String? = null
        var expired = false  // the next GET answers 401 once
        var down = false
        var events: List<Map<String, Any?>> = emptyList()
        var lastHeaders: Map<String, String> = emptyMap()

        override fun send(method: String, url: String, headers: Map<String, String>, body: ByteArray?): HttpAnswer {
            if (down) throw java.net.ConnectException("refused")
            calls.add(Pair(method, url.substringAfter("443")))
            lastHeaders = headers
            val ra = retryAfter?.let { mapOf("retry-after" to it) } ?: emptyMap()
            if (url.endsWith(Unifi.LOGIN_PATH)) {
                if (method != "POST" || headers["Cookie"] != null) return HttpAnswer(403, ra, emptyList(), ByteArray(0))
                val b = String(body!!)
                assertTrue(b.contains("\"username\": \"viewer\"") || b.contains("\"username\":\"viewer\""))
                return HttpAnswer(loginCode, ra + mapOf("x-csrf-token" to "csrf1"), listOf("TOKEN=abc; Path=/; HttpOnly"), ByteArray(0))
            }
            assertEquals("GET", method)
            if (expired) {
                expired = false
                return HttpAnswer(401, ra, emptyList(), ByteArray(0))
            }
            if (getCode != 200) return HttpAnswer(getCode, ra, emptyList(), ByteArray(0))
            if (headers["Cookie"] != "TOKEN=abc" || headers["X-CSRF-Token"] != "csrf1") return HttpAnswer(401, ra, emptyList(), ByteArray(0))
            val data: Any = if (url.contains("bootstrap")) mapOf("cameras" to listOf(mapOf("id" to "c1", "displayName" to "Front Door")))
            else events
            return HttpAnswer(200, emptyMap(), emptyList(), Json.write(data).toByteArray())
        }
    }

    private val console = UnifiConsole("protect", "192.0.2.1", 443, "viewer", "s3cret")

    @Test
    fun sessionLogsInOnceAndOnlyReads() {
        val fake = FakeConsole()
        var t = 1000.0
        val p = Protect(console, fake, LoginBackoff()) { t }
        val st = p.state()
        assertEquals(mapOf("c1" to "front_door"), st["cams"])
        assertEquals(listOf("POST", "GET", "GET"), fake.calls.map { it.first })
        assertTrue(fake.calls[2].second.startsWith("/proxy/protect/api/events?start=940000&end=1000000"))
        t += 5
        p.state()
        assertEquals(4, fake.calls.size)  // no new login, camera names kept (bootstrap every 10 min)
        fake.expired = true
        t += 60
        p.state()
        assertEquals(listOf("GET", "POST", "GET"), fake.calls.drop(4).map { it.first })  // one new login after a 401
        assertFalse(console.toString().contains("s3cret"))
    }

    @Test
    fun refusedLoginBacksOff() {
        val fake = FakeConsole().apply { loginCode = 401 }
        var t = 1000.0
        val b = LoginBackoff()
        val p = Protect(console, fake, b) { t }
        try { p.state(); fail() } catch (e: LoginError) {
            assertEquals("auth", e.kind)
            assertEquals(1030.0, e.nextAt!!, 0.0)
            assertFalse(e.message!!.contains("s3cret"))
        }
        t += 10
        try { p.state(); fail() } catch (e: LoginError) { assertEquals(1030.0, e.nextAt!!, 0.0) }
        assertEquals(1, fake.calls.size)  // no login while it waits
        t = 1031.0
        fake.loginCode = 429
        fake.retryAfter = "600"
        try { p.state(); fail() } catch (e: LoginError) {
            assertEquals("rate", e.kind)
            assertEquals(1631.0, e.nextAt!!, 0.0)  // Retry-After beats the 60 s step
        }
        fake.loginCode = 200
        fake.retryAfter = null
        t = 1700.0
        p.state()
        assertEquals(0, b.failures)  // a whole poll worked: the backoff starts again at 30 s
    }

    @Test
    fun rateLimitedRequestAndNetworkError() {
        val fake = FakeConsole()
        var t = 1000.0
        val p = Protect(console, fake, LoginBackoff()) { t }
        p.state()
        fake.getCode = 429
        t += 5
        try { p.state(); fail() } catch (e: LoginError) { assertEquals("rate", e.kind) }
        val q = Protect(console, FakeConsole().apply { down = true }, LoginBackoff()) { t }
        try { q.state(); fail() } catch (e: LoginError) {
            assertEquals("network", e.kind)
            assertEquals("UniFi Protect login: not reachable (ConnectException)", e.message)
        }
    }

    @Test
    fun pollerFirstAnswerIsTheBaselineThenNewEventsShow() {
        val fake = FakeConsole()
        var t = 1000.0
        val logs = ArrayList<Pair<String, String>>()
        val poller = UnifiPoller(fake, { m, l -> logs.add(Pair(m, l)) }) { t }
        val shown = ArrayList<Unifi.Trigger>()
        val s = mapOf<String, Any?>("enabled" to true, "unifi_enabled" to true, "unifi_kinds" to "ring,person",
            "unifi_labels" to mapOf("ring" to "Doorbell"))
        fake.events = listOf(mapOf("id" to "old", "camera" to "c1", "type" to "ring"))
        poller.once(s, listOf(console)) { shown.add(it) }
        assertEquals(emptyList<Unifi.Trigger>(), shown)  // no old events on screen after a start
        fake.events = fake.events + mapOf("id" to "new", "camera" to "c1", "type" to "ring")
        t += 5
        poller.once(s, listOf(console)) { shown.add(it) }
        assertEquals(listOf(Unifi.Trigger("front_door", "high", "Doorbell", null, null)), shown)
        assertEquals("unifi", shown[0].source)
        val lines = poller.status.lines({ it }) { "t" }
        assertTrue(lines.any { it.second == "UniFi Protect: last event t, front_door (Doorbell)" })
        // an error is logged once and the next answer is a baseline again
        fake.down = true
        t += 5
        poller.once(s, listOf(console)) { shown.add(it) }
        poller.once(s, listOf(console)) { shown.add(it) }
        assertEquals(1, logs.count { it.second == "error" })
        fake.down = false
        t = 2000.0
        fake.events = fake.events + mapOf("id" to "newer", "camera" to "c1", "type" to "ring")
        poller.once(s, listOf(console)) { shown.add(it) }
        assertEquals(1, shown.size)
        // switched off: nothing is asked, status cleared
        val before = fake.calls.size
        poller.once(s + ("unifi_enabled" to false), listOf(console)) { shown.add(it) }
        assertEquals(before, fake.calls.size)
        assertEquals(0, poller.status.consoles)
        assertTrue(logs.none { it.first.contains("s3cret") })
    }

    @Test
    fun consoleAddressAndInterval() {
        assertEquals(UnifiConsole("p", "192.0.2.1", 443, "u", "pw"), UnifiConsole.of("p", " 192.0.2.1 ", " u ", "pw"))
        assertEquals(8443, UnifiConsole.of("p", "nvr.local:8443", "u", "pw")!!.port)
        assertNull(UnifiConsole.of("p", "", "u", "pw"))
        assertNull(UnifiConsole.of("p", "host:0", "u", "pw"))
        assertNull(UnifiConsole.of("p", ":443", "u", "pw"))
        assertEquals(5, Unifi.interval(emptyMap()))
        assertEquals(2, Unifi.interval(mapOf("unifi_interval" to 1)))
        assertEquals(60, Unifi.interval(mapOf("unifi_interval" to 99)))
        assertEquals(10, Unifi.interval(mapOf("unifi_interval" to "10")))
    }
}
