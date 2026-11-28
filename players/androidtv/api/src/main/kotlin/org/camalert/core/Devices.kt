// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

import java.io.ByteArrayInputStream
import java.net.URLEncoder
import java.security.MessageDigest
import java.security.SecureRandom
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import javax.xml.parsers.DocumentBuilderFactory
import org.w3c.dom.Element

/** One camera of the devices list (core devices/config.py): type foscam / onvif / unifi. */
data class Device(val type: String, val host: String, val port: Int, val user: String, val password: String) {
    override fun toString() = "Device($type, $host:$port)"  // never the password in a log line
}

class DeviceError(message: String) : Exception(message)

/**
 * Camera devices (#66): the same 'name|type|host:port|user|password' lines as devices.conf on Enigma2 and Kodi,
 * Foscam CGI and ONVIF PTZ (core devices/config.py, foscam.py, onvif.py). Pure functions, checked against the
 * core's reference answers (CoreReferenceTest).
 */
object Devices {
    val TYPES = listOf("foscam", "onvif", "unifi")
    val PTZ_VECTORS = mapOf("up" to Triple(0.0, 0.5, 0.0), "down" to Triple(0.0, -0.5, 0.0), "left" to Triple(-0.5, 0.0, 0.0),
        "right" to Triple(0.5, 0.0, 0.0), "zoom_in" to Triple(0.0, 0.0, 0.5), "zoom_out" to Triple(0.0, 0.0, -0.5))

    /** core parse_devices: unknown types and broken lines are skipped; the password is the rest of the line. */
    fun parse(text: String?): Map<String, Device> {
        val out = LinkedHashMap<String, Device>()
        for (raw in (text ?: "").lines()) {
            val line = raw.trim()
            if (line.isEmpty() || line.startsWith("#")) continue
            val parts = line.split("|", limit = 5)
            if (parts.size < 3) continue
            val name = parts[0].trim()
            val kind = parts[1].trim().lowercase()
            val addr = parts[2].trim()
            if (name.isEmpty() || kind !in TYPES || addr.isEmpty()) continue
            val default = when (kind) { "foscam" -> 88; "unifi" -> 443; else -> 80 }
            var host = addr
            var port = default
            if (addr.count { it == ':' } == 1) {
                host = addr.substringBeforeLast(':')
                val p = addr.substringAfterLast(':')
                port = if (p.isEmpty()) default else Urls.validPort(p, default)
            }
            out[name] = Device(kind, host, port, if (parts.size > 3) parts[3].trim() else "", if (parts.size > 4) parts[4] else "")
        }
        return out
    }

    /** The default camera login where a line has none (Kodi klogic.with_default_login); never for UniFi consoles. */
    fun withDefaultLogin(devs: Map<String, Device>, user: String, password: String): Map<String, Device> =
        devs.mapValues { (_, d) ->
            if (d.type == "unifi") d
            else d.copy(user = d.user.ifEmpty { user }, password = d.password.ifEmpty { password })
        }

    fun base(d: Device) = "http://${d.host}:${d.port}"

    // --- Foscam CGI -------------------------------------------------------------------------------------------------
    private fun q(v: String) = URLEncoder.encode(v, "UTF-8").replace("+", "%20").replace("*", "%2A").replace("%7E", "~")

    fun foscamUrl(d: Device, cmd: String, params: Map<String, String> = emptyMap()): String {
        val all = listOf("cmd" to cmd) + params.toSortedMap().toList() + listOf("usr" to d.user, "pwd" to d.password)
        return "${base(d)}/cgi-bin/CGIProxy.fcgi?" + all.joinToString("&") { "${it.first}=${q(it.second)}" }
    }

    fun foscamValues(xml: String?): Map<String, String> =
        Regex("<(\\w+)>([^<]*)</\\1>").findAll(xml ?: "").associate { it.groupValues[1] to it.groupValues[2] }

    fun foscamAlarm(xml: String?): Boolean {
        val v = foscamValues(xml)
        if ((v["result"] ?: "0") != "0") return false
        return listOf("motionDetectAlarm", "soundAlarm", "humanDetectAlarmState").any { v[it] == "2" }
    }

    fun alarmEdge(previous: Boolean?, now: Boolean) = now && previous != true

    private val FOSCAM_PTZ = mapOf("up" to "ptzMoveUp", "down" to "ptzMoveDown", "left" to "ptzMoveLeft", "right" to "ptzMoveRight",
        "zoom_in" to "zoomIn", "zoom_out" to "zoomOut", "home" to "ptzReset")

    /** (start command, stop command or null) for a PTZ action on a Foscam camera. */
    fun foscamPtz(action: String): Pair<String, String?> = when (action) {
        "zoom_in", "zoom_out" -> Pair(FOSCAM_PTZ.getValue(action), "zoomStop")
        "home" -> Pair("ptzReset", null)
        "stop" -> Pair("ptzStopRun", null)
        else -> Pair(FOSCAM_PTZ[action] ?: throw IllegalArgumentException(action), "ptzStopRun")
    }

    // --- ONVIF (SOAP 1.2) ---------------------------------------------------------------------------------------------
    const val ONVIF_NS = "xmlns:s=\"http://www.w3.org/2003/05/soap-envelope\" xmlns:tds=\"http://www.onvif.org/ver10/device/wsdl\" " +
        "xmlns:trt=\"http://www.onvif.org/ver10/media/wsdl\" xmlns:tptz=\"http://www.onvif.org/ver20/ptz/wsdl\" " +
        "xmlns:tt=\"http://www.onvif.org/ver10/schema\""

    fun wsseDigest(password: String, nonce: ByteArray, created: String): String {
        val sha = MessageDigest.getInstance("SHA-1")
        sha.update(nonce); sha.update(created.toByteArray(Charsets.UTF_8)); sha.update(password.toByteArray(Charsets.UTF_8))
        return HttpAuth.base64(sha.digest())  // java.util.Base64 needs Android 8; the Fire TV runs Android 7
    }

    fun onvifCreated(timestamp: Double): String = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.ROOT)
        .apply { timeZone = TimeZone.getTimeZone("UTC") }.format(Date(timestamp.toLong() * 1000))

    private fun xml(s: String) = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\"", "&quot;")

    fun onvifEnvelope(body: String, user: String? = null, password: String = "", nonce: ByteArray? = null, created: String? = null): String {
        var header = ""
        if (!user.isNullOrEmpty()) {
            header = "<s:Header><Security s:mustUnderstand=\"1\" xmlns=\"http://docs.oasis-open.org/wss/2004/01/" +
                "oasis-200401-wss-wssecurity-secext-1.0.xsd\"><UsernameToken><Username>${xml(user)}</Username>" +
                "<Password Type=\"http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0" +
                "#PasswordDigest\">${wsseDigest(password, nonce!!, created!!)}</Password><Nonce EncodingType=\"http://docs.oasis-open.org/wss/2004/01/" +
                "oasis-200401-wss-soap-message-security-1.0#Base64Binary\">${HttpAuth.base64(nonce)}</Nonce><Created xmlns=\"http://docs." +
                "oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd\">$created</Created>" +
                "</UsernameToken></Security></s:Header>"
        }
        return "<?xml version=\"1.0\" encoding=\"UTF-8\"?><s:Envelope $ONVIF_NS>$header<s:Body>$body</s:Body></s:Envelope>"
    }

    /** Python's "%g" for the velocities (0.5, -0.5, 0). */
    private fun g(v: Double): String = if (v == Math.floor(v)) v.toLong().toString() else v.toString()

    fun onvifBody(action: String, token: String? = null, vector: Triple<Double, Double, Double>? = null): String {
        when (action) {
            "GetSystemDateAndTime" -> return "<tds:GetSystemDateAndTime/>"
            "GetCapabilities" -> return "<tds:GetCapabilities><tds:Category>All</tds:Category></tds:GetCapabilities>"
            "GetProfiles" -> return "<trt:GetProfiles/>"
        }
        val tok = "<tptz:ProfileToken>${xml(token ?: "None")}</tptz:ProfileToken>"
        return when (action) {
            "ContinuousMove" -> {
                val (x, y, z) = vector!!
                "<tptz:ContinuousMove>$tok<tptz:Velocity><tt:PanTilt x=\"${g(x)}\" y=\"${g(y)}\"/><tt:Zoom x=\"${g(z)}\"/></tptz:Velocity></tptz:ContinuousMove>"
            }
            "Stop" -> "<tptz:Stop>$tok<tptz:PanTilt>true</tptz:PanTilt><tptz:Zoom>true</tptz:Zoom></tptz:Stop>"
            "GotoHomePosition" -> "<tptz:GotoHomePosition>$tok</tptz:GotoHomePosition>"
            else -> throw IllegalArgumentException(action)
        }
    }

    private fun parse(xml: String): List<Element> {
        val f = DocumentBuilderFactory.newInstance()
        f.isNamespaceAware = true
        try { f.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true) } catch (e: Exception) { }
        val doc = f.newDocumentBuilder().parse(ByteArrayInputStream(xml.toByteArray(Charsets.UTF_8)))
        val out = ArrayList<Element>()
        fun walk(e: Element) {
            out.add(e)
            var c = e.firstChild
            while (c != null) { if (c is Element) walk(c); c = c.nextSibling }
        }
        walk(doc.documentElement)
        return out
    }

    private fun local(e: Element) = e.localName ?: e.tagName.substringAfter(':')
    private fun children(e: Element): List<Element> {
        val out = ArrayList<Element>()
        var c = e.firstChild
        while (c != null) { if (c is Element) out.add(c); c = c.nextSibling }
        return out
    }

    /** GetCapabilities answer -> {"media": url, "ptz": url} (only what the camera offers). */
    fun onvifXaddrs(xml: String): Map<String, String> {
        val out = LinkedHashMap<String, String>()
        for (el in parse(xml)) {
            val name = local(el).lowercase()
            if (name in listOf("media", "ptz") && name !in out) {
                for (c in children(el)) if (local(c) == "XAddr" && c.textContent.isNotEmpty()) out[name] = c.textContent.trim()
            }
        }
        return out
    }

    /** First media profile token of GetProfiles, preferably one with a PTZ configuration. */
    fun onvifProfileToken(xml: String): String? {
        var first: String? = null
        for (el in parse(xml)) {
            val token = el.getAttribute("token")
            if (local(el) == "Profiles" && token.isNotEmpty()) {
                if (first == null) first = token
                if (children(el).any { local(it) == "PTZConfiguration" }) return token
            }
        }
        return first
    }

    /** GetSystemDateAndTime answer -> UTC unix time of the camera, or null. */
    fun onvifTime(xml: String): Long? {
        for (el in parse(xml)) {
            if (local(el) != "UTCDateTime") continue
            val v = HashMap<String, Int>()
            fun walk(e: Element) {
                if (local(e) in listOf("Year", "Month", "Day", "Hour", "Minute", "Second") && e.textContent.isNotEmpty() && children(e).isEmpty())
                    v[local(e)] = e.textContent.trim().toInt()
                children(e).forEach { walk(it) }
            }
            walk(el)
            if (v.size == 6) {
                val c = Calendar.getInstance(TimeZone.getTimeZone("UTC"))
                c.clear()
                c.set(v.getValue("Year"), v.getValue("Month") - 1, v.getValue("Day"), v.getValue("Hour"), v.getValue("Minute"), v.getValue("Second"))
                return c.timeInMillis / 1000
            }
            return null
        }
        return null
    }

    fun onvifFault(xml: String?): String? {
        if (xml == null || !xml.contains("Fault>")) return null
        val m = Regex("<(?:\\w+:)?Text[^>]*>([^<]*)</(?:\\w+:)?Text>").find(xml)
        return m?.groupValues?.get(1) ?: "SOAP fault"
    }
}

/**
 * Camera control and Foscam alarms over the network (core devices/client.py): blocking calls, run them in a
 * thread. Error messages never contain a url or a password.
 */
class DeviceClient(private val transport: Transport, private val clock: () -> Double = { System.currentTimeMillis() / 1000.0 },
                   private val sleep: (Long) -> Unit = { Thread.sleep(it) }) {
    private val random = SecureRandom()
    private val onvif = HashMap<String, OnvifSession>()

    private fun get(url: String): String {
        val a = try { transport.send("GET", url, emptMap, null) } catch (e: Exception) {
            throw DeviceError("camera not reachable (${e.javaClass.simpleName})")
        }
        return String(a.body, Charsets.UTF_8)
    }

    fun foscamState(d: Device): Boolean = Devices.foscamAlarm(get(Devices.foscamUrl(d, "getDevState")))

    private fun foscamCommand(d: Device, cmd: String) {
        if (!get(Devices.foscamUrl(d, cmd)).contains("<result>0</result>")) throw DeviceError("Foscam $cmd refused")
    }

    private inner class OnvifSession(val d: Device) {
        val deviceUrl = Devices.base(d) + "/onvif/device_service"
        var offset = 0.0
        var xaddrs: Map<String, String> = emptyMap()
        var token: String? = null

        fun call(url: String, action: String, auth: Boolean = true, token: String? = null, vector: Triple<Double, Double, Double>? = null): String {
            val body = Devices.onvifBody(action, token, vector)
            val env = if (auth && d.user.isNotEmpty()) {
                val nonce = ByteArray(16).also { random.nextBytes(it) }
                Devices.onvifEnvelope(body, d.user, d.password, nonce, Devices.onvifCreated(clock() + offset))
            } else Devices.onvifEnvelope(body)
            val a = try {
                transport.send("POST", url, mapOf("Content-Type" to "application/soap+xml; charset=utf-8"), env.toByteArray(Charsets.UTF_8))
            } catch (e: Exception) {
                throw DeviceError("ONVIF $action: camera not reachable (${e.javaClass.simpleName})")
            }
            val xml = String(a.body, Charsets.UTF_8)
            val fault = Devices.onvifFault(xml)
            if (a.code >= 400) throw DeviceError("ONVIF $action: ${fault ?: a.code}")
            if (fault != null) throw DeviceError("ONVIF $action: $fault")
            return xml
        }

        fun prepare() {
            if (token != null) return
            try {
                Devices.onvifTime(call(deviceUrl, "GetSystemDateAndTime", auth = false))?.let { offset = it - clock() }
            } catch (e: Exception) { }
            xaddrs = try { Devices.onvifXaddrs(call(deviceUrl, "GetCapabilities")) } catch (e: DeviceError) { throw e } catch (e: Exception) {
                throw DeviceError("ONVIF GetCapabilities: unreadable answer")
            }
            if ("ptz" !in xaddrs) throw DeviceError("camera has no ONVIF PTZ service")
            token = try { Devices.onvifProfileToken(call(xaddrs["media"] ?: deviceUrl, "GetProfiles")) } catch (e: DeviceError) { throw e } catch (e: Exception) {
                throw DeviceError("ONVIF GetProfiles: unreadable answer")
            }
            if (token == null) throw DeviceError("no ONVIF media profile")
        }

        fun ptz(action: String, millis: Long) {
            prepare()
            val url = xaddrs.getValue("ptz")
            when (action) {
                "home" -> call(url, "GotoHomePosition", token = token)
                "stop" -> call(url, "Stop", token = token)
                else -> {
                    call(url, "ContinuousMove", token = token, vector = Devices.PTZ_VECTORS.getValue(action))
                    sleep(millis)
                    call(url, "Stop", token = token)
                }
            }
        }
    }

    /** Moves the camera for [millis] and stops (blocking). Throws DeviceError. */
    fun ptz(d: Device, action: String, millis: Long = MOVE_MILLIS) {
        if (action !in PTZ_ACTIONS) throw DeviceError("unknown move")
        when (d.type) {
            "unifi" -> throw DeviceError("UniFi Protect: no PTZ")
            "foscam" -> {
                val (start, stop) = Devices.foscamPtz(action)
                foscamCommand(d, start)
                if (stop != null) {
                    sleep(millis)
                    foscamCommand(d, stop)
                }
            }
            else -> {
                val key = "${d.host}:${d.port}:${d.user}:${d.password.hashCode()}"
                val s = synchronized(onvif) { onvif.getOrPut(key) { OnvifSession(d) } }
                try {
                    s.ptz(action, millis)
                } catch (e: DeviceError) {
                    synchronized(onvif) { onvif.remove(key) }  // find services and profile again next time
                    throw e
                }
            }
        }
    }

    companion object {
        const val MOVE_MILLIS = 500L
        val PTZ_ACTIONS = listOf("up", "down", "left", "right", "zoom_in", "zoom_out", "home", "stop")
        private val emptMap = emptyMap<String, String>()
    }
}

/**
 * Foscam motion / sound alarms (core triggers/foscam.py, #66): polls every Foscam camera of the devices list and
 * shows the camera when an alarm starts, not on every poll while it lasts.
 */
class FoscamPoller(private val client: DeviceClient, private val log: (String, String) -> Unit = { _, _ -> }) {
    private val previous = HashMap<String, Boolean>()
    private val failing = HashSet<String>()

    data class Trigger(val camera: String, val priority: String, val mode: String?, val seconds: Int?, val label: String?)

    /** One round over the Foscam cameras; [show] gets a trigger per camera whose alarm just started. */
    fun once(settings: Map<String, Any?>, devices: Map<String, Device>, show: (Trigger) -> Unit) {
        for ((name, d) in devices) {
            if (d.type != "foscam") continue
            val now = try {
                client.foscamState(d).also { if (failing.remove(name)) log("Foscam $name reachable again", "normal") }
            } catch (e: DeviceError) {
                if (failing.add(name)) log("Foscam $name: ${e.message}", "error")
                continue
            }
            val was = previous[name]
            previous[name] = now
            if (Devices.alarmEdge(was, now)) {
                show(Trigger(name, settings["foscam_priority"]?.toString()?.ifEmpty { null } ?: "normal",
                    settings["foscam_mode"]?.toString()?.ifEmpty { null }, (settings["foscam_seconds"] as? Number)?.toInt(),
                    settings["foscam_label"]?.toString()?.ifEmpty { null }))
            }
        }
    }
}
