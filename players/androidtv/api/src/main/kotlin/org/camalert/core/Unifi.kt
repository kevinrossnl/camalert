// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.security.cert.X509Certificate
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager

/**
 * UniFi Protect events (#72): the Kotlin port of core devices/unifi.py (pure helpers), triggers/unifi.py (check(),
 * PollStatus) and the read-only Protect session of devices/client.py (login backoff #78). Reference answers of the
 * Python core are checked by CoreReferenceTest; the network goes through [Transport] (faked in the tests).
 *
 * Only GET requests after the login: bootstrap (camera list) and events. A local Protect user with the role
 * "View Only" is enough; its login is kept outside the settings (on Android in its own private preferences file).
 */
object Unifi {
    const val LOGIN_PATH = "/api/auth/login"
    const val BOOTSTRAP_PATH = "/proxy/protect/api/bootstrap"
    val EVENT_TYPES = listOf("ring", "motion", "smartDetectZone", "smartDetectLine")
    val KINDS = listOf("ring", "person", "vehicle", "animal", "package", "motion")
    const val DEFAULT_KINDS = "ring,person"
    val PRIORITIES = listOf("normal", "high", "alarm")
    val MODES = listOf("photo", "live", "notify", "log")
    val SECONDS = 5..300
    /** Labels of the kinds (core triggers/unifi.KIND_LABELS), translated by the player. */
    val KIND_LABELS = linkedMapOf("ring" to "Doorbell", "person" to "Person", "vehicle" to "Vehicle",
        "animal" to "Animal", "package" to "Package", "motion" to "Motion")
    private val FOLD = mapOf('ä' to "ae", 'ö' to "oe", 'ü' to "ue", 'ß' to "ss", 'é' to "e", 'è' to "e", 'à' to "a", 'ç' to "c")
    private val NON_SLUG = Regex("[^a-z0-9]+")
    private val CAMERA_ID = Regex("^[0-9a-fA-F]{6,64}$")

    /** A Protect display name as a go2rtc-style camera name: 'Front Door' -> 'front_door', 'Hügel' -> 'huegel'. */
    fun slug(name: String?): String {
        val s = (name ?: "").trim().lowercase()
        val folded = buildString { for (ch in s) append(FOLD[ch] ?: ch.toString()) }
        return NON_SLUG.replace(folded, "_").trim('_')
    }

    /** {Protect camera id: camera name} from a bootstrap answer (adopted cameras only). */
    fun protectCameras(bootstrap: Any?): Map<String, String> {
        val out = LinkedHashMap<String, String>()
        val cams = (bootstrap as? Map<*, *>)?.get("cameras") as? List<*> ?: return out
        for (cam in cams) {
            if (cam !is Map<*, *> || !truthy(cam["id"]) || cam["isAdopted"] == false) continue
            val shown = cam["displayName"]?.takeIf { truthy(it) } ?: cam["name"]?.takeIf { truthy(it) } ?: ""
            val name = slug(shown.toString())
            if (name.isNotEmpty()) out[cam["id"].toString()] = name
        }
        return out
    }

    /** 'protect_name=go2rtc_name|...' (same format as the Frigate map) -> map; broken parts are skipped. */
    fun cameraMap(text: String?): Map<String, String> {
        val out = LinkedHashMap<String, String>()
        for (part in (text ?: "").split("|")) {
            val i = part.indexOf('=')
            if (i < 0) continue
            val k = slug(part.substring(0, i))
            val v = part.substring(i + 1).trim()
            if (k.isNotEmpty() && v.isNotEmpty()) out[k] = v
        }
        return out
    }

    /** 'ring, person' -> [ring, person] in KINDS order; unknown words are ignored, empty = DEFAULT_KINDS. */
    fun wantedKinds(text: String?): List<String> {
        val src = if (text.isNullOrEmpty()) DEFAULT_KINDS else text
        val words = src.split(",").map { it.trim().lowercase() }.filter { it.isNotEmpty() }.toSet()
        return KINDS.filter { it in words }.ifEmpty { wantedKinds(DEFAULT_KINDS) }
    }

    data class KindRule(val priority: String?, val mode: String?, val camera: String?)
    data class CameraRule(val priority: String?, val mode: String?, val seconds: Int?)

    private fun fields(v: String): List<String> = v.split("/").map { it.trim() } + listOf("", "", "")

    /** Per event type: 'ring=alarm/live|motion=normal/log/garden' -> {kind: rule}; empty or invalid parts = null. */
    fun kindRules(text: String?): Map<String, KindRule> {
        val out = LinkedHashMap<String, KindRule>()
        for (part in (text ?: "").split("|")) {
            val i = part.indexOf('=')
            if (i < 0) continue
            val k = part.substring(0, i).trim().lowercase()
            if (k !in KINDS) continue
            val f = fields(part.substring(i + 1))
            val prio = f[0].lowercase()
            val mode = f[1].lowercase()
            val rule = KindRule(prio.takeIf { it in PRIORITIES }, mode.takeIf { it in MODES }, f[2].ifEmpty { null })
            if (rule != KindRule(null, null, null)) out[k] = rule
        }
        return out
    }

    /** Per camera: 'front_door=high/photo/30|driveway=normal/log' -> {slug(camera): rule}; seconds 5-300. */
    fun cameraRules(text: String?): Map<String, CameraRule> {
        val out = LinkedHashMap<String, CameraRule>()
        for (part in (text ?: "").split("|")) {
            val i = part.indexOf('=')
            if (i < 0) continue
            val k = slug(part.substring(0, i))
            if (k.isEmpty()) continue
            val f = fields(part.substring(i + 1))
            val prio = f[0].lowercase()
            val mode = f[1].lowercase()
            val secs = f[2].toIntOrNull()
            val rule = CameraRule(prio.takeIf { it in PRIORITIES }, mode.takeIf { it in MODES }, secs?.takeIf { it in SECONDS })
            if (rule != CameraRule(null, null, null)) out[k] = rule
        }
        return out
    }

    /** What a Protect event is about: [ring], [person, vehicle], [motion] or []. */
    fun eventKinds(ev: Map<*, *>?): List<String> = when (val t = ev?.get("type")) {
        "ring" -> listOf("ring")
        "motion" -> listOf("motion")
        "smartDetectZone", "smartDetectLine" -> {
            val types = (ev["smartDetectTypes"] as? List<*>) ?: emptyList<Any?>()
            KINDS.filter { it in types }
        }
        else -> { t; emptyList() }
    }

    /** GET path for the events between two times (ms), oldest first. */
    fun eventsPath(startMs: Long, endMs: Long, limit: Int = 50): String {
        val q = EVENT_TYPES.joinToString("&") { "types=$it" }
        return "/proxy/protect/api/events?start=$startMs&end=$endMs&limit=$limit&orderDirection=ASC&$q"
    }

    fun snapshotPath(cameraId: String?, width: Int = 1280): String {
        require(cameraId != null && CAMERA_ID.matches(cameraId)) { "bad camera id" }
        return "/proxy/protect/api/cameras/$cameraId/snapshot?w=$width&force=true"
    }

    /** (camera name, kind) if the event is one of [kinds] on a known camera, else null. */
    fun match(ev: Map<*, *>?, cams: Map<*, *>, kinds: List<String>, names: Map<String, String> = emptyMap()): Pair<String, String>? {
        val cam = cams[ev?.get("camera")]?.toString()?.ifEmpty { null } ?: return null
        for (k in eventKinds(ev)) if (k in kinds) return Pair(names[cam] ?: cam, k)
        return null
    }

    /** What the player does with an event (core triggers.Trigger of the unifi source). */
    data class Trigger(val camera: String, val priority: String, val label: String?, val mode: String?, val seconds: Int?) {
        val source get() = "unifi"
    }

    /**
     * Trigger for the most important new event since the previous poll, else null (core UnifiSource.check). The
     * first poll after a start only remembers what is there. Settings: unifi_kinds, unifi_cameras, unifi_priority,
     * unifi_mode, unifi_seconds, unifi_rules, unifi_camera_rules, unifi_labels ({kind: text}) or unifi_label.
     */
    fun check(settings: Map<String, Any?>, previous: Map<*, *>?, now: Map<*, *>?): Trigger? {
        if (previous.isNullOrEmpty() || now.isNullOrEmpty()) return null
        val seen = ((previous["events"] as? List<*>) ?: emptyList<Any?>()).map { (it as? Map<*, *>)?.get("id") }.toSet()
        val kinds = wantedKinds(settings["unifi_kinds"]?.toString())
        val names = cameraMap(settings["unifi_cameras"]?.toString())
        val cams = (now["cams"] as? Map<*, *>) ?: emptyMap<Any?, Any?>()
        var best: Pair<String, String>? = null
        for (ev in (now["events"] as? List<*>) ?: emptyList<Any?>()) {
            val e = ev as? Map<*, *> ?: continue
            if (e["id"] in seen) continue
            val hit = match(e, cams, kinds, names) ?: continue
            if (best == null || KINDS.indexOf(hit.second) < KINDS.indexOf(best.second)) best = hit
        }
        val (camera, kind) = best ?: return null
        val rule = kindRules(settings["unifi_rules"]?.toString())[kind]
        val camRule = cameraRules(settings["unifi_camera_rules"]?.toString())[slug(camera)]
        var priority = camRule?.priority ?: rule?.priority ?: settings["unifi_priority"]?.toString()?.ifEmpty { null } ?: "normal"
        if (kind == "ring" && priority == "normal") priority = "high"
        val label = ((settings["unifi_labels"] as? Map<*, *>)?.get(kind)?.toString()?.ifEmpty { null })
            ?: settings["unifi_label"]?.toString()?.ifEmpty { null }
        val mode = camRule?.mode ?: rule?.mode ?: settings["unifi_mode"]?.toString()?.ifEmpty { null }
        val seconds = camRule?.seconds ?: (settings["unifi_seconds"] as? Number)?.toInt()?.takeIf { it != 0 }
        return Trigger(rule?.camera ?: camera, priority, label, mode, seconds)
    }

    /** UniFi Protect check interval in seconds (2-60, default 5), like the other players. */
    fun interval(settings: Map<String, Any?>): Int {
        val n = (settings["unifi_interval"] as? Number)?.toInt() ?: settings["unifi_interval"]?.toString()?.trim()?.toIntOrNull() ?: return 5
        return n.coerceIn(2, 60)
    }

    internal fun truthy(v: Any?): Boolean = when (v) {
        null -> false
        is Boolean -> v
        is Number -> v.toDouble() != 0.0
        is String -> v.isNotEmpty()
        is Collection<*> -> v.isNotEmpty()
        is Map<*, *> -> v.isNotEmpty()
        else -> true
    }
}

/** A UniFi Protect console (core devices file type unifi): host, port (default 443), View Only user. */
data class UnifiConsole(val name: String, val host: String, val port: Int = 443, val user: String, val password: String) {
    override fun toString() = "UnifiConsole($name, $host:$port)"  // never the password

    companion object {
        /** A console address 'host' or 'host:port' (IPv4 or a name); null when empty or broken. */
        fun of(name: String, address: String?, user: String?, password: String?): UnifiConsole? {
            val a = (address ?: "").trim()
            if (a.isEmpty()) return null
            val (host, port) = if (a.count { it == ':' } == 1) {
                val i = a.indexOf(':')
                Pair(a.substring(0, i), a.substring(i + 1).toIntOrNull()?.takeIf { it in 1..65535 } ?: return null)
            } else Pair(a, 443)
            if (host.isEmpty()) return null
            return UnifiConsole(name, host, port, (user ?: "").trim(), password ?: "")
        }
    }
}

open class ProtectError(message: String) : Exception(message)

/** An HTTP error answer of the console (code, Retry-After in seconds or null). */
class ProtectHttpError(message: String, val code: Int, val retryAfter: Int?) : ProtectError(message)

/** A failed or postponed login. kind: auth (401/403), rate (429), network or http; nextAt: next attempt (epoch s). */
class LoginError(message: String, val kind: String, var nextAt: Double? = null) : ProtectError(message)

/** Login backoff of one console (#78): 30 s, 1 min, 2 min, 5 min, then every 15 min; a longer Retry-After wins. */
class LoginBackoff {
    var failures = 0
    var nextAt = 0.0
    var error: LoginError? = null
    var lastLogin: Double? = null

    fun reset() {
        failures = 0; nextAt = 0.0; error = null; lastLogin = null
    }

    /** Throws the LoginError of the current wait (same text, so it is logged once) until nextAt. */
    fun check(now: Double) {
        val e = error ?: return
        if (now < nextAt) throw LoginError(e.message ?: "", e.kind, nextAt)
    }

    fun failed(error: LoginError, now: Double, wait: Int? = null): LoginError {
        var delay = BACKOFF[minOf(failures, BACKOFF.size - 1)]
        failures++
        if (wait != null && wait > 0) delay = maxOf(delay, wait)
        nextAt = now + delay
        error.nextAt = nextAt
        this.error = error
        return error
    }

    fun loggedIn() {
        error = null
    }

    companion object {
        val BACKOFF = listOf(30, 60, 120, 300, 900)
        const val RETRY_AFTER_MAX = 3600

        /** Seconds from a Retry-After header (seconds or an HTTP date), capped at RETRY_AFTER_MAX; null if absent/bad. */
        fun retryAfter(value: String?, now: Double): Int? {
            val v = value?.trim() ?: return null
            if (v.isEmpty()) return null
            val secs: Double = if (v.all { it in '0'..'9' }) {
                v.toBigInteger().min(RETRY_AFTER_MAX.toBigInteger()).toDouble()
            } else {
                try {
                    ZonedDateTime.parse(v, DateTimeFormatter.RFC_1123_DATE_TIME).toEpochSecond() - now
                } catch (e: Exception) {
                    return null
                }
            }
            return secs.coerceIn(0.0, RETRY_AFTER_MAX.toDouble()).toInt()
        }
    }
}

/** One HTTP request to a console. headers: lower-case names; setCookies: every Set-Cookie value. */
class HttpAnswer(val code: Int, val headers: Map<String, String>, val setCookies: List<String>, val body: ByteArray)

/** The network of the Protect session (faked in the tests). Throws on a network error. */
fun interface Transport {
    fun send(method: String, url: String, headers: Map<String, String>, body: ByteArray?): HttpAnswer
}

/**
 * Session on a UniFi OS console (cookie + CSRF token), core devices.client.Protect. The console has a self-signed
 * certificate, so it is not checked (LAN only). Logins go through a [LoginBackoff]: never more than one login per
 * backoff window; a 401 on a request logs in once more.
 */
class Protect(val console: UnifiConsole, private val transport: Transport, val backoff: LoginBackoff = LoginBackoff(),
              private val clock: () -> Double = { System.currentTimeMillis() / 1000.0 }) {
    private val base = "https://${console.host}:${console.port}"
    private var csrf: String? = null
    var loggedIn = false
        private set
    private val cookies = LinkedHashMap<String, String>()
    private var cams: Map<String, String> = emptyMap()
    private var camsAt = 0.0

    private fun open(method: String, path: String, headers: Map<String, String>, body: ByteArray?, what: String): HttpAnswer {
        val all = LinkedHashMap(headers)
        if (cookies.isNotEmpty()) all["Cookie"] = cookies.entries.joinToString("; ") { "${it.key}=${it.value}" }
        val r = try {
            transport.send(method, base + path, all, body)
        } catch (e: Exception) {  // never the password or the cookie in the message
            throw ProtectError("UniFi Protect $what: not reachable (${e.javaClass.simpleName})")
        }
        for (c in r.setCookies) {
            val pair = c.substringBefore(';')
            val i = pair.indexOf('=')
            if (i > 0) cookies[pair.substring(0, i).trim()] = pair.substring(i + 1).trim()
        }
        if (r.code >= 400) throw ProtectHttpError("UniFi Protect $what: HTTP ${r.code}", r.code, LoginBackoff.retryAfter(r.headers["retry-after"], clock()))
        return r
    }

    fun login() {
        val now = clock()
        backoff.check(now)
        val b = backoff
        val last = b.lastLogin
        if (last != null && now - last < LoginBackoff.BACKOFF[0]) {
            // the session was refused right after a login: do not log in again at once (#78)
            throw b.failed(LoginError("UniFi Protect: session refused right after the login (check user/password " +
                "and the user's role)", "auth"), now)
        }
        b.lastLogin = now
        loggedIn = false
        cookies.clear()  // an old session cookie makes the console refuse the login (403)
        csrf = null
        val body = Json.write(linkedMapOf("username" to console.user, "password" to console.password, "rememberMe" to false))
            .toByteArray(Charsets.UTF_8)
        try {
            val r = open("POST", Unifi.LOGIN_PATH, mapOf("Content-Type" to "application/json"), body, "login")
            csrf = r.headers["x-csrf-token"] ?: r.headers["x-updated-csrf-token"]
        } catch (e: ProtectHttpError) {
            val err = when (e.code) {
                401, 403 -> LoginError("UniFi Protect login refused (check user/password): HTTP ${e.code}", "auth")
                429 -> LoginError("UniFi Protect login: too many attempts (HTTP 429)", "rate")
                else -> LoginError(e.message ?: "", "http")
            }
            throw b.failed(err, now, e.retryAfter)
        } catch (e: LoginError) {
            throw e
        } catch (e: ProtectError) {
            throw b.failed(LoginError(e.message ?: "", "network"), now)
        }
        b.loggedIn()
        loggedIn = true
    }

    /** GET with one new login when the session ran out (401). JSON value. */
    fun get(path: String): Any? {
        backoff.check(clock())
        var data: ByteArray? = null
        for (attempt in 0..1) {
            if (!loggedIn) login()
            val headers = csrf?.let { mapOf("X-CSRF-Token" to it) } ?: emptyMap()
            try {
                data = open("GET", path, headers, null, "request").body
                break
            } catch (e: ProtectHttpError) {
                if (e.code == 429) throw backoff.failed(LoginError("UniFi Protect request: too many requests (HTTP 429)", "rate"), clock(), e.retryAfter)
                if (attempt == 0 && e.code == 401) {
                    loggedIn = false
                    continue
                }
                throw e
            }
        }
        return try {
            Json.parse(String(data ?: ByteArray(0), Charsets.UTF_8))
        } catch (e: Exception) {
            throw ProtectError("UniFi Protect: unexpected answer")
        }
    }

    fun cameras(now: Double): Map<String, String> {
        if (cams.isEmpty() || now - camsAt > BOOTSTRAP_MAX_AGE) {
            cams = Unifi.protectCameras(get(Unifi.BOOTSTRAP_PATH))
            camsAt = now
        }
        return cams
    }

    /** {now: ms, cams: {id: name}, events: [...]} of the last EVENT_WINDOW seconds. */
    fun state(now: Double = clock()): Map<String, Any?> {
        val c = cameras(now)
        val ms = (now * 1000).toLong()
        val events = get(Unifi.eventsPath(ms - EVENT_WINDOW * 1000L, ms))
        backoff.reset()  // a whole poll worked: the next failure starts at 30 s again
        return mapOf("now" to ms, "cams" to c, "events" to (events as? List<*> ?: emptyList<Any?>()))
    }

    companion object {
        const val BOOTSTRAP_MAX_AGE = 600
        const val EVENT_WINDOW = 60
    }
}

/** What the diagnostics show about the UniFi Protect source (core triggers/unifi.PollStatus); errors redacted. */
class PollStatus {
    var lastPoll: Double? = null
    var lastOk: Double? = null
    var error: String? = null
    var lastEvent: Map<String, Any?>? = null
    var nextRetry: Double? = null
    var consoles = 0

    fun reset() {
        lastPoll = null; lastOk = null; error = null; lastEvent = null; nextRetry = null; consoles = 0
    }

    fun ok(now: Double) {
        lastPoll = now; lastOk = now; error = null; nextRetry = null
    }

    /** Remembers an error; true when it is new (log it once, not at every poll). */
    fun failed(error: Throwable, now: Double): Boolean {
        lastPoll = now
        nextRetry = (error as? LoginError)?.nextAt
        val text = Obs.redact(error.message ?: error.toString()).take(200)
        val new = text != this.error
        this.error = text
        return new
    }

    fun event(trig: Unifi.Trigger, now: Double) {
        lastEvent = mapOf("time" to now, "camera" to trig.camera, "label" to trig.label, "priority" to trig.priority, "mode" to trig.mode)
    }

    /** [(ok true/false/null, text)] for the diagnostics; tr translates core msgids, whenText formats a time. */
    fun lines(tr: (String) -> String, whenText: (Double) -> String): List<Pair<Boolean?, String>> {
        if (consoles == 0) return listOf(Pair(false, tr("UniFi Protect: no console of type unifi in the devices file")))
        if (lastPoll == null) return listOf(Pair(null, tr("UniFi Protect: not checked yet")))
        val out = ArrayList<Pair<Boolean?, String>>()
        error?.let { err ->
            out.add(Pair(false, tr("UniFi Protect: %s").replace("%s", err)))
            nextRetry?.let { out.add(Pair(null, tr("UniFi Protect: next login attempt %s").replace("%s", whenText(it)))) }
        }
        lastOk?.let { out.add(Pair(true, tr("UniFi Protect: last check %s").replace("%s", whenText(it)))) }
        val e = lastEvent
        if (e != null) {
            val label = e["label"]?.toString()
            val what = e["camera"].toString() + (if (!label.isNullOrEmpty()) " ($label)" else "")
            val mode = if (e["mode"] == "log") " [${tr("Log only")}]" else ""
            val text = tr("UniFi Protect: last event %s, %s")
            val i = text.indexOf("%s")
            val j = text.indexOf("%s", i + 2)
            val filled = if (i >= 0 && j >= 0) text.substring(0, i) + whenText(e["time"] as Double) + text.substring(i + 2, j) + what + text.substring(j + 2) else text
            out.add(Pair(true, filled + mode))
        } else {
            out.add(Pair(null, tr("UniFi Protect: no event since the start")))
        }
        return out
    }
}

/**
 * Polls the UniFi Protect consoles (core: the players' UnifiPoller). once() is called every [Unifi.interval]
 * seconds from a background thread: the first answer after a start or an error only sets the baseline (no old
 * events on screen); errors are logged once (redacted) and kept in [status] for the diagnostics.
 */
class UnifiPoller(private val transport: Transport, private val log: (String, String) -> Unit,
                  private val clock: () -> Double = { System.currentTimeMillis() / 1000.0 }) {
    val status = PollStatus()
    private val state = HashMap<String, Map<String, Any?>?>()
    private val sessions = HashMap<UnifiConsole, Protect>()
    private val backoffs = HashMap<Pair<String, Int>, LoginBackoff>()
    private var consolesKey: List<UnifiConsole>? = null

    /** settings: the player settings (+ unifi_labels); consoles: the configured consoles; show: the controller. */
    fun once(settings: Map<String, Any?>, consoles: List<UnifiConsole>, show: (Unifi.Trigger) -> Unit) {
        if (settings["enabled"] == false || settings["unifi_enabled"] != true) {
            state.clear()
            status.reset()
            return
        }
        if (consoles != consolesKey) {  // new credentials: fresh sessions, no login backoff (#78)
            consolesKey = consoles
            sessions.clear()
            backoffs.values.forEach { it.reset() }
        }
        status.consoles = consoles.size
        for (c in consoles.sortedBy { it.name }) {
            if (c.name !in state) log("UniFi Protect: polling console ${c.name} every ${Unifi.interval(settings)} s", "normal")
            val previous = state[c.name]
            val session = sessions.getOrPut(c) { Protect(c, transport, backoffs.getOrPut(Pair(c.host, c.port)) { LoginBackoff() }, clock) }
            val now = try {
                session.state(clock())
            } catch (e: Exception) {
                state[c.name] = null
                if (status.failed(e, clock())) log("UniFi Protect ${c.name}: ${status.error}", "error")
                continue
            }
            state[c.name] = now
            status.ok(clock())
            val trig = Unifi.check(settings, previous, now) ?: continue
            status.event(trig, clock())
            show(trig)
        }
    }
}

/** The real network (Android and JVM): HTTPS without certificate checks, for a console in the local network only. */
class UrlTransport(private val timeoutMs: Int = 8000) : Transport {
    private val trustAll: SSLContext by lazy {
        SSLContext.getInstance("TLS").apply {
            init(null, arrayOf<TrustManager>(object : X509TrustManager {
                override fun checkClientTrusted(chain: Array<out X509Certificate>?, authType: String?) {}
                override fun checkServerTrusted(chain: Array<out X509Certificate>?, authType: String?) {}
                override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
            }), null)
        }
    }

    override fun send(method: String, url: String, headers: Map<String, String>, body: ByteArray?): HttpAnswer {
        val c = URL(url).openConnection() as HttpURLConnection
        if (c is HttpsURLConnection) {
            c.sslSocketFactory = trustAll.socketFactory
            c.setHostnameVerifier { _, _ -> true }
        }
        c.requestMethod = method
        c.connectTimeout = timeoutMs
        c.readTimeout = timeoutMs * 2
        c.instanceFollowRedirects = false
        for ((k, v) in headers) c.setRequestProperty(k, v)
        if (body != null) {
            c.doOutput = true
            c.outputStream.use { it.write(body) }
        }
        val code = c.responseCode
        val stream = if (code >= 400) c.errorStream else c.inputStream
        val data = stream?.use { s -> ByteArrayOutputStream().also { s.copyTo(it) }.toByteArray() } ?: ByteArray(0)
        val hdrs = HashMap<String, String>()
        val cookies = ArrayList<String>()
        for ((k, v) in c.headerFields) {
            if (k == null) continue
            if (k.equals("Set-Cookie", true)) cookies.addAll(v) else hdrs[k.lowercase()] = v.joinToString(",")
        }
        c.disconnect()
        return HttpAnswer(code, hdrs, cookies, data)
    }
}
