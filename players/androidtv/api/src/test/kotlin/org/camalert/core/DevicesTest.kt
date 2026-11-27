// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

/** #66: devices list, Foscam CGI, ONVIF and the client give the same answers as the Python core. */
@Suppress("UNCHECKED_CAST")
class DevicesTest {
    private val ref = Exported.core["devices"] as Map<String, List<Map<String, Any?>>>
    private fun bytes(v: Any?) = (v as List<Number>).map { it.toByte() }.toByteArray()
    private fun dev(m: Map<String, Any?>) = Device(m["type"] as String, m["host"] as String, (m["port"] as Number).toInt(),
        m["user"] as String, m["password"] as String)

    @Test
    fun parseLikeTheCore() {
        for (c in ref.getValue("parse")) {
            val want = (c["out"] as Map<String, Map<String, Any?>>).mapValues { dev(it.value) }
            assertEquals(c["text"].toString(), want, Devices.parse(c["text"] as String))
        }
    }

    @Test
    fun foscamLikeTheCore() {
        for (c in ref.getValue("foscam_url")) {
            assertEquals(c["out"], Devices.foscamUrl(dev(c["dev"] as Map<String, Any?>), c["cmd"] as String,
                (c["params"] as Map<String, Any?>).mapValues { it.value.toString() }))
        }
        for (c in ref.getValue("foscam_alarm")) assertEquals(c["xml"].toString(), c["out"], Devices.foscamAlarm(c["xml"] as String?))
        for (c in ref.getValue("foscam_ptz")) {
            assertEquals(c["action"].toString(), c["out"], Devices.foscamPtz(c["action"] as String).toList())
        }
        for (c in ref.getValue("alarm_edge")) {
            assertEquals("${c["previous"]} ${c["now"]}", c["out"], Devices.alarmEdge(c["previous"] as Boolean?, c["now"] as Boolean))
        }
    }

    @Test
    fun onvifLikeTheCore() {
        for (c in ref.getValue("created")) assertEquals(c["out"], Devices.onvifCreated((c["ts"] as Number).toDouble()))
        for (c in ref.getValue("digest")) {
            assertEquals(c["out"], Devices.wsseDigest(c["password"] as String, bytes(c["nonce"]), c["created"] as String))
        }
        for (c in ref.getValue("envelope")) {
            assertEquals(c["user"].toString(), c["out"], Devices.onvifEnvelope(c["body"] as String, c["user"] as String?,
                c["password"] as String, bytes(c["nonce"]), c["created"] as String))
        }
        for (c in ref.getValue("body")) {
            val v = (c["vector"] as List<Number>?)?.let { Triple(it[0].toDouble(), it[1].toDouble(), it[2].toDouble()) }
            assertEquals(c["action"].toString(), c["out"], Devices.onvifBody(c["action"] as String, c["token"] as String?, v))
        }
        for (c in ref.getValue("xaddrs")) assertEquals(c["out"], Devices.onvifXaddrs(c["xml"] as String))
        for (c in ref.getValue("profile")) assertEquals(c["out"], Devices.onvifProfileToken(c["xml"] as String))
        for (c in ref.getValue("time")) assertEquals(c["out"]?.let { (it as Number).toLong() }, Devices.onvifTime(c["xml"] as String))
        for (c in ref.getValue("fault")) assertEquals(c["out"], Devices.onvifFault(c["xml"] as String?))
    }

    @Test
    fun defaultLoginNeverForUnifi() {
        val devs = Devices.parse("a|onvif|h||\nb|foscam|h|own|pw\nc|unifi|h||")
        val out = Devices.withDefaultLogin(devs, "def", "secret")
        assertEquals(Pair("def", "secret"), out.getValue("a").let { Pair(it.user, it.password) })
        assertEquals(Pair("own", "pw"), out.getValue("b").let { Pair(it.user, it.password) })
        assertEquals(Pair("", ""), out.getValue("c").let { Pair(it.user, it.password) })
        assertFalse("never the password in a log line", out.getValue("a").toString().contains("secret"))
    }

    /** A fake camera: answers by url, records what was asked. */
    private class Camera(val answers: (String, String) -> Pair<Int, String>) : Transport {
        val calls = ArrayList<Pair<String, String>>()
        override fun send(method: String, url: String, headers: Map<String, String>, body: ByteArray?): HttpAnswer {
            val b = body?.let { String(it, Charsets.UTF_8) } ?: ""
            calls.add(Pair(url, b))
            val (code, text) = answers(url, b)
            return HttpAnswer(code, emptyMap(), emptyList(), text.toByteArray(Charsets.UTF_8))
        }
    }

    private val xml = Exported.core["devices"].let { ref ->
        mapOf("time" to (ref as Map<String, List<Map<String, Any?>>>).getValue("time")[0]["xml"] as String,
            "caps" to ref.getValue("xaddrs")[0]["xml"] as String, "profiles" to ref.getValue("profile")[0]["xml"] as String,
            "ok" to ref.getValue("fault")[2]["xml"] as String, "fault" to ref.getValue("fault")[0]["xml"] as String)
    }

    @Test
    fun onvifMoveFindsServiceProfileAndStops() {
        val cam = Camera { _, body ->
            when {
                "GetSystemDateAndTime" in body -> Pair(200, xml.getValue("time"))
                "GetCapabilities" in body -> Pair(200, xml.getValue("caps"))
                "GetProfiles" in body -> Pair(200, xml.getValue("profiles"))
                else -> Pair(200, xml.getValue("ok"))
            }
        }
        val slept = ArrayList<Long>()
        val client = DeviceClient(cam, clock = { 1764000000.0 }, sleep = { slept.add(it) })
        val d = Device("onvif", "192.168.1.30", 80, "admin", "pa|ss")
        client.ptz(d, "left")
        client.ptz(d, "home")
        val actions = cam.calls.map { (_, b) -> Regex("<(?:tds|trt|tptz):(\\w+)").find(b.substringAfter("<s:Body>"))!!.groupValues[1] }
        assertEquals(listOf("GetSystemDateAndTime", "GetCapabilities", "GetProfiles", "ContinuousMove", "Stop", "GotoHomePosition"), actions)
        assertEquals("http://192.168.1.30/onvif/PTZ", cam.calls[3].first)  // the PTZ service address, trimmed
        assertTrue(cam.calls[3].second.contains("<tptz:ProfileToken>Profile_2</tptz:ProfileToken>"))  // the profile with PTZ
        assertTrue(cam.calls[3].second.contains("x=\"-0.5\" y=\"0\""))
        assertFalse("GetSystemDateAndTime goes without a login", cam.calls[0].second.contains("UsernameToken"))
        assertTrue(cam.calls[1].second.contains("<Username>admin</Username>"))
        assertFalse(cam.calls.any { it.second.contains("pa|ss") })  // a digest, never the password itself
        assertEquals(listOf(DeviceClient.MOVE_MILLIS), slept)
    }

    @Test
    fun onvifFaultAndUnreachableNeverShowThePassword() {
        val client = DeviceClient(Camera { _, _ -> Pair(400, xml.getValue("fault")) }, sleep = {})
        val d = Device("onvif", "192.168.1.30", 80, "admin", "secret")
        try { client.ptz(d, "up"); fail() } catch (e: DeviceError) { assertEquals("ONVIF GetCapabilities: Sender not Authorized", e.message) }
        val down = DeviceClient({ _, _, _, _ -> throw java.net.ConnectException("refused: secret") }, sleep = {})
        val f = Device("foscam", "192.168.1.31", 88, "admin", "secret")
        try { down.ptz(f, "up"); fail() } catch (e: DeviceError) {
            assertEquals("camera not reachable (ConnectException)", e.message)
            assertFalse(e.message!!.contains("secret"))
        }
        try { client.ptz(Device("unifi", "h", 443, "", ""), "up"); fail() } catch (e: DeviceError) { }
        try { client.ptz(d, "spin"); fail() } catch (e: DeviceError) { }
    }

    @Test
    fun foscamMoveAndAlarmPolling() {
        var motion = "1"
        val cam = Camera { url, _ ->
            when {
                "cmd=getDevState" in url -> Pair(200, "<CGI_Result><result>0</result><motionDetectAlarm>$motion</motionDetectAlarm></CGI_Result>")
                else -> Pair(200, "<CGI_Result><result>0</result></CGI_Result>")
            }
        }
        val client = DeviceClient(cam, sleep = {})
        val f = Device("foscam", "192.168.1.31", 88, "admin", "pw")
        client.ptz(f, "zoom_in")
        assertEquals(listOf("zoomIn", "zoomStop"), cam.calls.map { Regex("cmd=(\\w+)").find(it.first)!!.groupValues[1] })
        val poller = FoscamPoller(client)
        val shown = ArrayList<FoscamPoller.Trigger>()
        val devs = mapOf("garden" to f, "front_door" to Device("onvif", "h", 80, "", ""))
        val s = mapOf<String, Any?>("foscam_priority" to "high", "foscam_mode" to "live", "foscam_seconds" to 20)
        poller.once(s, devs) { shown.add(it) }
        motion = "2"
        poller.once(s, devs) { shown.add(it) }
        poller.once(s, devs) { shown.add(it) }  // still the same alarm: not again
        motion = "1"
        poller.once(s, devs) { shown.add(it) }
        motion = "2"
        poller.once(s, devs) { shown.add(it) }
        assertEquals(listOf(FoscamPoller.Trigger("garden", "high", "live", 20, null), FoscamPoller.Trigger("garden", "high", "live", 20, null)), shown)
    }
}
