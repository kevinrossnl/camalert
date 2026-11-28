// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

import java.net.URLDecoder

/**
 * The CamAlert HTTP API v1, the same as on every player (port of core/camalert_core/api.py, #5):
 *
 *     POST /camalert/<action>   actions: show, mosaic, tour, hide, dnd (with on=...), ptz, webhook
 *     GET  /camalert/<action>   reads: status, cameras, dnd (state), events, log, metrics
 *                               (GET of an action still works, but is deprecated and logged once per caller)
 *     Parameters: query string, form body or JSON object body.
 *     test=1 on any request (#62): the caller source becomes "test": no chime, the event is tagged "test".
 *     status answers "screen" (#63): none / photo / strip / notification / live / mosaic / tour.
 *     Token: header X-CamAlert-Token (a token= query parameter still works: deprecated, logged once, redacted)
 *
 * The Kotlin tests run every row of the shared contract table (tests/contract/api_table.py, exported to JSON by
 * tools/export_contract.py) against this class.
 */
class Request(
    method: String?, val path: String, args: Map<String, String> = emptyMap(), val ip: String = "",
    val headerToken: String? = null, val userAgent: String = "", val body: ByteArray = ByteArray(0),
    val contentType: String = "",
) {
    val method = (method ?: "GET").uppercase()
    val args = LinkedHashMap(args)
}

class Response(val code: Int, val body: Any?, val contentType: String = "application/json", headers: Map<String, String> = emptyMap()) {
    val headers = LinkedHashMap(headers)

    fun payload(): ByteArray = (if (body is String) body else Json.write(body)).toByteArray(Charsets.UTF_8)
}

class Invalid(message: String) : Exception(message)

/** The screen side of a player (same interface on every player). */
interface Controller {
    var lastCaller: Triple<Double, String, String>?
    val events: List<Map<String, Any?>>
    fun show(stream: String?, seconds: Int?, mode: String?, priority: String?, source: String, label: String?, eventId: String? = null): String
    fun hide()
    /** #87: a photo window with its own id (a player without several windows: the normal window). */
    fun showWindow(stream: String?, seconds: Int?, mode: String?, priority: String?, source: String, label: String?, windowId: String): String =
        show(stream, seconds, mode, priority, source, label)
    /** #87: closes only the window with this id. */
    fun hideWindow(windowId: String) {}
    fun mosaic(streams: String?, seconds: Int): String
    fun tour(streams: String?, interval: Int?): String
    fun hasPtz(name: String): Boolean
    fun ptzMove(move: String, name: String?): Boolean
    fun setDnd(on: Boolean)
    fun status(): Map<String, Any?>
}

/** What a player provides to the API. settings(): enabled, allow, token, duration, camera, dnd, ha_webhook,
 *  position, size. */
interface Backend {
    val platform: String
    val version: String
    fun settings(): Map<String, Any?>
    fun controller(): Controller
    fun node(): Pair<String, String>
    fun cameras(): List<Map<String, Any?>>
    /** Saves the Home Assistant webhook and the secret that signs the colour keys (#82); "" removes them. */
    fun setWebhook(url: String, secret: String = "")
    /** Saves position or size (#84); value is one of Api.displaySettings[key]. */
    fun setDisplay(key: String, value: String)
    /** Turns guest mode on or off (#11): the guest cameras are hidden while it is on. */
    fun setGuest(on: Boolean)
    /** go2rtc address (and default camera, null = keep) sent by Home Assistant; shows the setup message (#122). */
    fun setSetup(server: String, camera: String?)
    fun logTail(lines: Int): List<String>
    fun metrics(): String
    fun statusExtra(): Map<String, Any?> = emptyMap()
    /** update_state, update_version, update_error (#126). */
    fun updateStatus(): Map<String, Any?> = SelfUpdate.UpdateState().asStatus()
    /** Starts installing release [version] in the background (#126); the version is already checked. */
    fun startUpdate(version: String): Unit = throw UnsupportedOperationException("update")
    fun log(message: String, level: String = "normal") {}
    /** #89: play the WAV at url (or speak text) in the background; true when it will be spoken. Never blocks. */
    fun speak(url: String?, text: String?, priority: String): Boolean = false
    /** Host name resolver for the webhook check (blocking). */
    fun resolve(host: String): List<String> = Access.resolve(host)
}

class Api(val data: CoreData = CoreData.load()) {
    private class Route(val name: String, val action: Boolean = false, val sensitive: Boolean = false,
                        val handler: (Backend, Controller, MutableMap<String, String>, Map<String, Any?>, String) -> Any)

    val limit = RateLimiter(30, 10.0)
    val warned: MutableSet<String> = java.util.Collections.synchronizedSet(HashSet())

    private val routes: Map<String, Route> = listOf(
        Route("show", action = true, handler = ::show), Route("camalert", action = true, handler = ::show),
        Route("hide", action = true, handler = ::hide), Route("mosaic", action = true, handler = ::mosaic),
        Route("tour", action = true, handler = ::tour), Route("ptz", action = true, handler = ::ptz),
        Route("webhook", action = true, handler = ::webhook), Route("setup", action = true, handler = ::setup),
        Route("update", action = true, handler = ::update),
        Route("dnd", handler = ::dnd),
        Route("status", handler = ::status), Route("settings", handler = ::settings), Route("cameras", handler = ::cameras),
        Route("log", sensitive = true, handler = ::log), Route("events", sensitive = true, handler = ::events),
        Route("metrics", sensitive = true, handler = ::metrics),
    ).associateBy { it.name }

    /** Settings a caller may change through /camalert/settings (#84), with their choices from the schema. */
    val displaySettings: Map<String, List<String>> =
        listOf("position", "size").associateWith { data.byId.getValue(it).choices ?: emptyList() }

    fun reset() {
        limit.clear()
        warned.clear()
    }

    // --- parameters ------------------------------------------------------------------------------------------------
    companion object {
        private val NAME = Regex("^[A-Za-z0-9_.-]+$")
        private val SECRET = Regex("^[0-9a-f]{32,128}$")  // webhook secret (#82)
        val TRUE = listOf("1", "true", "on", "yes")
        val FALSE = listOf("0", "false", "off", "no")

        /** null (= default) or 'a,b' with only valid camera names; Invalid otherwise. */
        fun camerasParam(value: String?, many: Boolean = true): String? {
            if (value == null || value.isBlank()) return null
            val names = value.trim().split(Regex("[,\\s]+")).filter { it.isNotEmpty() }
            if (names.isEmpty() || names.any { !NAME.matches(it) } || (!many && names.size > 1)) throw Invalid("invalid camera name")
            return names.joinToString(",")
        }

        fun choiceParam(args: Map<String, String>, key: String, allowed: List<String>): String? {
            val v = args[key]
            if (v.isNullOrEmpty()) return null
            if (v !in allowed) throw Invalid("invalid $key")
            return v
        }

        fun boolParam(value: String, name: String = "on"): Boolean {
            val t = value.trim().lowercase()
            if (t in TRUE) return true
            if (t in FALSE) return false
            throw Invalid("$name must be 1 or 0")
        }

        /** Parameters from a POST body: JSON object or form; else {}. */
        fun parseBody(contentType: String?, body: ByteArray): Map<String, String> {
            if (body.isEmpty()) return emptyMap()
            val text = String(body, Charsets.UTF_8)
            if ("json" in (contentType ?: "") || text.trimStart().startsWith("{")) {
                val d = try { Json.parse(text) } catch (e: Exception) { throw Invalid("invalid JSON body") }
                if (d !is Map<*, *>) throw Invalid("invalid JSON body")
                return d.entries.associate { it.key.toString() to pyStr(it.value) }
            }
            return parseQuery(text)
        }

        /** urllib.parse.parse_qs(keep_blank_values=True), first value of each key. */
        fun parseQuery(text: String): Map<String, String> {
            val out = LinkedHashMap<String, String>()
            for (part in text.split('&', ';')) {
                if (part.isEmpty()) continue
                val k = dec(part.substringBefore('='))
                val v = if ('=' in part) dec(part.substringAfter('=')) else continue
                if (k !in out) out[k] = v
            }
            return out
        }

        private fun dec(s: String) = try { URLDecoder.decode(s, "UTF-8") } catch (e: Exception) { s }
    }

    private fun localUrl(b: Backend, url: String, callerIp: String?): String {
        val why = Access.urlTarget(url, callerIp) { b.resolve(it) }
        if (why != null) throw Invalid(why)
        return url
    }

    // --- handlers --------------------------------------------------------------------------------------------------
    private fun show(b: Backend, ctl: Controller, a: MutableMap<String, String>, s: Map<String, Any?>, source: String): Any {
        val cam = camerasParam(a["cam"])
        val mode = choiceParam(a, "mode", Rules.MODES + "strip")
        val priority = choiceParam(a, "priority", Rules.PRIORITIES)
        val sec = if (Rules.hasSeconds(a["sec"])) Rules.showSeconds(a["sec"], (s["duration"] as? Number)?.toInt() ?: 30) else null  // 0: until hide (#81)
        val (sayUrl, say) = try { Speech.request(a, a["_ip"]) } catch (e: Speech.SpeechError) { throw Invalid(e.message ?: "invalid say_url") }  // #89
        val wid = windowId(a)
        val res = if (wid != null) ctl.showWindow(cam, sec, mode, priority, source, a["label"], wid)  // #87
                  else ctl.show(cam, sec, mode, priority, source, a["label"])
        val out = linkedMapOf<String, Any?>("result" to (res in listOf("show", "extend", "wake")), "action" to res, "cam" to (cam ?: s["camera"]))
        if (wid != null) out["id"] = wid
        if (sayUrl != null || say != null) {
            out["spoken"] = Speech.shouldSpeak(s["speak"]?.toString() ?: "high", priority ?: "normal", source, res, sayUrl, say) &&
                b.speak(sayUrl, say, priority ?: "normal")
        }
        return out
    }

    private fun windowId(a: Map<String, String>): String? =
        try { Windows.idParam(a["id"]) } catch (e: IllegalArgumentException) { throw Invalid(e.message ?: "invalid window id") }

    private fun hide(b: Backend, ctl: Controller, a: MutableMap<String, String>, s: Map<String, Any?>, source: String): Any {
        val wid = windowId(a)
        if (wid != null) {  // #87: only the window with this id
            ctl.hideWindow(wid)
            return mapOf("result" to true, "action" to "hide", "id" to wid)
        }
        ctl.hide()
        return mapOf("result" to true, "action" to "hide")
    }

    private fun mosaic(b: Backend, ctl: Controller, a: MutableMap<String, String>, s: Map<String, Any?>, source: String): Any {
        val cam = camerasParam(a["cam"])
        val sec = if (!a["sec"].isNullOrEmpty()) Rules.clampSeconds(a["sec"], 60) else 60
        val res = ctl.mosaic(cam, sec)
        b.log("mosaic from $source: cameras=${cam ?: "-"} -> $res")
        return mapOf("result" to (res == "show"), "action" to res)
    }

    private fun tour(b: Backend, ctl: Controller, a: MutableMap<String, String>, s: Map<String, Any?>, source: String): Any {
        val cam = camerasParam(a["cam"])
        val iv = a["interval"]
        val res = ctl.tour(cam, if (!iv.isNullOrEmpty() && iv.all { it.isDigit() }) iv.toBigInteger().min(60.toBigInteger()).toInt().coerceAtLeast(3) else null)
        b.log("tour from $source: cameras=${cam ?: "-"} -> $res")
        return mapOf("result" to (res == "show"), "action" to res)
    }

    private fun dnd(b: Backend, ctl: Controller, a: MutableMap<String, String>, s: Map<String, Any?>, source: String): Any {
        var dnd = s["dnd"] == true
        if ("on" in a) {
            dnd = boolParam(a.getValue("on"))
            ctl.setDnd(dnd)
        }
        return mapOf("result" to true, "action" to "dnd", "dnd" to dnd)
    }

    private fun ptz(b: Backend, ctl: Controller, a: MutableMap<String, String>, s: Map<String, Any?>, source: String): Any {
        val cam = a["cam"]
        val move = a["move"]
        if (move !in data.ptzActions || cam.isNullOrEmpty() || !NAME.matches(cam) || !ctl.hasPtz(cam)) throw Invalid("camera without PTZ or unknown move")
        return mapOf("result" to ctl.ptzMove(move!!, cam), "cam" to cam, "move" to move)
    }

    private fun webhook(b: Backend, ctl: Controller, a: MutableMap<String, String>, s: Map<String, Any?>, source: String): Any {
        val url = (a["url"] ?: "").trim()
        val secret = if (url.isNotEmpty()) (a["secret"] ?: "").trim().lowercase() else ""
        if (url.isNotEmpty()) localUrl(b, url, a["_ip"])
        if (secret.isNotEmpty() && !SECRET.matches(secret)) throw Invalid("invalid secret")
        if (url != (s["ha_webhook"] ?: "") || secret != (s["ha_webhook_secret"]?.toString() ?: "")) {
            b.setWebhook(url, secret)
            b.log("Home Assistant webhook ${if (url.isNotEmpty()) (if (secret.isNotEmpty()) "set, keys signed" else "set") else "removed"}")
        }
        return mapOf("result" to true, "webhook" to url.isNotEmpty(), "signed" to secret.isNotEmpty())
    }

    private fun cameras(b: Backend, ctl: Controller, a: MutableMap<String, String>, s: Map<String, Any?>, source: String): Any {
        val cams = try { b.cameras() } catch (e: Exception) {
            b.log("camera list failed: ${e.message}", "error")
            return mapOf("result" to false, "error" to "camera source not reachable")
        }
        return mapOf("result" to true, "cameras" to cams)
    }

    /** False while the player was never set up (#122): no go2rtc address, not direct, wizard not finished. */
    fun configured(s: Map<String, Any?>): Boolean =
        !((s["server"]?.toString() ?: "").isBlank() && (s["source"]?.toString() ?: "go2rtc") != "direct" &&
            s["wizard_done"] != true)

    private fun setup(b: Backend, ctl: Controller, a: MutableMap<String, String>, s: Map<String, Any?>, source: String): Any {
        val server = Urls.normalizeServer(a["server"]) ?: throw Invalid("invalid server")
        val camera = camerasParam(a["camera"], many = false)
        if (configured(s) && Access.urlTarget(server, a["_ip"]) { b.resolve(it) } != null) {
            return Response(409, mapOf("result" to false, "error" to "already set up"))
        }
        b.setSetup(server, camera)
        b.log("set up by ${a["_ip"]}: go2rtc $server${if (camera != null) ", camera $camera" else ""}")
        return mapOf("result" to true, "configured" to true, "server" to server,
            "camera" to (camera ?: s["camera"]?.toString() ?: ""))
    }

    /** Home Assistant installs a newer CamAlert release (#126): 403 when allow_update is off, 409 while an update
     *  runs, 400 for a version that is not plain X.Y.Z or not newer. */
    private fun update(b: Backend, ctl: Controller, a: MutableMap<String, String>, s: Map<String, Any?>, source: String): Any {
        val version = try {
            SelfUpdate.checkRequest(b.version, a["version"], s["allow_update"] != false)
        } catch (e: SelfUpdate.UpdateError) {
            return Response(if ("off" in (e.message ?: "")) 403 else 400, mapOf("result" to false, "error" to e.message))
        }
        if (b.updateStatus()["update_state"] in listOf("downloading", "installing", "waiting")) {
            return Response(409, mapOf("result" to false, "error" to "update in progress"))
        }
        b.startUpdate(version)
        b.log("update to $version requested by ${a["_ip"]}")
        val out = LinkedHashMap<String, Any?>(b.updateStatus())
        out["result"] = true; out["version"] = version
        return out
    }

    private fun settings(b: Backend, ctl: Controller, a: MutableMap<String, String>, s: Map<String, Any?>, source: String): Any {
        val new = displaySettings.mapValues { (k, allowed) -> choiceParam(a, k, allowed) }
        val out = LinkedHashMap<String, Any?>()
        out["result"] = true
        for (k in displaySettings.keys) {
            val v = new[k]
            if (v != null && v != s[k]) {
                b.setDisplay(k, v)
                b.log("window $k set to $v")
            }
            out[k] = v ?: s[k]
        }
        val g = a["guest_mode"]
        if (g != null) {  // #11
            val on = boolParam(g, "guest_mode")
            if (on != (s["guest_mode"] == true)) {
                b.setGuest(on)
                b.log("guest mode ${if (on) "on" else "off"}")
            }
            out["guest_mode"] = on
        } else {
            out["guest_mode"] = s["guest_mode"] == true
        }
        return out
    }

    private fun status(b: Backend, ctl: Controller, a: MutableMap<String, String>, s: Map<String, Any?>, source: String): Any {
        val (node, name) = b.node()
        val out = LinkedHashMap<String, Any?>(ctl.status())
        out["result"] = true; out["version"] = b.version; out["id"] = node; out["name"] = name
        out["platform"] = b.platform; out["api_version"] = data.apiVersion; out["capabilities"] = data.capabilities
        out["min_ha_version"] = data.minHaVersion
        for (k in displaySettings.keys) out[k] = s[k]  // #84
        out["configured"] = configured(s)  // #122
        out["guest_mode"] = s["guest_mode"] == true  // #11
        out["button_signing"] = (s["ha_webhook"]?.toString() ?: "").isNotEmpty() && (s["ha_webhook_secret"]?.toString() ?: "").isNotEmpty()  // #82
        out.putAll(b.updateStatus())  // #126
        out.putAll(b.statusExtra())
        if (out["screen"] !in data.screens) {  // a controller that does not know it (#63)
            out["screen"] = if (out["window"] != null) "photo" else if (out["live"] != null) "live" else "none"
        }
        return out
    }

    private fun log(b: Backend, ctl: Controller, a: MutableMap<String, String>, s: Map<String, Any?>, source: String): Any {
        val l = a["lines"] ?: ""
        val n = if (l.isNotEmpty() && l.all { it.isDigit() }) l.toBigInteger().min(2000.toBigInteger()).toInt() else 200
        return mapOf("result" to true, "lines" to b.logTail(minOf(n, 2000)).map { Obs.redact(it) })
    }

    private fun events(b: Backend, ctl: Controller, a: MutableMap<String, String>, s: Map<String, Any?>, source: String): Any =
        mapOf("result" to true, "events" to ctl.events.map { e -> e.filterKeys { it != "snapshot" } })

    private fun metrics(b: Backend, ctl: Controller, a: MutableMap<String, String>, s: Map<String, Any?>, source: String): Any =
        Response(200, b.metrics(), "text/plain; version=0.0.4")

    fun routeOf(path: String?): String? {
        val p = (path ?: "").trimEnd('/')
        if (!(p == "/camalert" || p.startsWith("/camalert/"))) return null
        val name = p.substringAfterLast('/')
        return if (name in routes) name else null
    }

    private fun once(b: Backend, key: String, message: String, level: String = "normal") {
        if (warned.add(key)) b.log(message, level)
    }

    private fun error(code: Int, text: String) = Response(code, mapOf("result" to false, "error" to text))

    /** Response for one request. Never throws. */
    fun handle(b: Backend, req: Request, now: Double = System.currentTimeMillis() / 1000.0): Response {
        val ip = req.ip
        if (!limit.allow(ip, now)) return error(429, "too many requests")
        val s = try { b.settings() } catch (e: Exception) {
            b.log("request failed: ${e.message}", "error")
            return error(500, "internal error")
        }
        val allow = s["allow"]?.toString() ?: "lan"
        val token = s["token"]?.toString() ?: ""
        if (Access.exposedWithoutToken(allow, token, ip)) {
            once(b, "exposed|$ip", "WARNING: API called from $ip outside the local network without a token; set an access token", "error")
        }
        val queryToken = req.args.remove("token")
        val given = req.headerToken?.takeIf { it.isNotEmpty() } ?: queryToken ?: ""
        if (!Access.clientAllowed(ip, allow) || !Access.tokenOk(token, given)) return error(403, "forbidden")
        if (queryToken != null && req.headerToken.isNullOrEmpty()) {
            once(b, "query token|$ip", "deprecated: $ip sends the token in the URL; use the X-CamAlert-Token header")
        }
        if (s["enabled"] != true) return Response(200, mapOf("result" to false, "error" to "disabled"))
        val route = routes[routeOf(req.path) ?: return error(404, "unknown action")]!!
        if (req.method != "GET" && req.method != "POST") {
            return Response(405, mapOf("result" to false, "error" to "method not allowed"), headers = mapOf("Allow" to "GET, POST"))
        }
        if (route.sensitive && !Access.clientAllowed(ip, "lan") && token.isEmpty()) return error(403, "forbidden")
        val headers = LinkedHashMap<String, String>()
        val out: Any
        try {
            val args = LinkedHashMap(req.args)
            if (req.method == "POST") {
                args.putAll(parseBody(req.contentType, req.body))
                args.remove("token")
            }
            val isAction = route.action || (route.name == "dnd" && "on" in args) ||
                (route.name == "settings" && (displaySettings.keys.any { it in args } || "guest_mode" in args))
            if (isAction && req.method == "GET") {
                headers["Deprecation"] = "true"
                once(b, "get|${route.name}|$ip", "deprecated: $ip uses GET for /camalert/${route.name}; use POST")
            }
            var source = Events.callerSource(req.userAgent)
            if ("test" in args && boolParam(args.remove("test")!!, "test")) source = data.testSource  // #62: no chime, tagged
            val ctl = b.controller()
            ctl.lastCaller = Triple(now, ip, source)
            b.log("API ${req.method} ${req.path} ${Obs.redact(args.entries.sortedBy { it.key }.joinToString("&") { "${it.key}=${it.value}" })} from $ip ($source)", "verbose")
            args["_ip"] = ip
            out = route.handler(b, ctl, args, s, source)
        } catch (e: Invalid) {
            return Response(400, mapOf("result" to false, "error" to (e.message ?: "invalid")), headers = headers)
        } catch (e: Exception) {
            b.log("request failed: $e", "error")
            return error(500, "internal error")
        }
        if (out is Response) {
            out.headers.putAll(headers)
            return out
        }
        return Response(200, out, headers = headers)
    }
}
