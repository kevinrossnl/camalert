// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

/**
 * Every row of the shared HTTP API contract (tests/contract/api_table.py, exported to contract/http.json) against
 * the Kotlin API (#64): the same rows the Enigma2 and Kodi players pass. A row that differs fails, unless it is in
 * KNOWN with the issue that fixes it; a KNOWN entry that no longer differs fails as well (stale).
 */
@Suppress("UNCHECKED_CAST")
class HttpContractTest {
    companion object {
        /** row name -> issue that removes the difference. Must trend to zero. */
        val KNOWN: Map<String, String> = emptyMap()
        val rows = Exported.http["rows"] as List<Map<String, Any?>>
    }

    class Answer(val code: Int, val body: Any?, val headers: Map<String, String>)

    class TestBackend(private val values: Map<String, Any?>, private val ctl: Controller, private val cams: List<String>?) : Backend {
        override val platform = "androidtv"
        override val version = "0.0.0-test"
        val logged = ArrayList<String>()
        var hook: String? = null
        override fun settings() = values
        override fun controller() = ctl
        override fun node() = Pair("node1", "CamAlert test")
        override fun cameras(): List<Map<String, Any?>> =
            (cams ?: error("no camera list")).map { mapOf("name" to it, "title" to Cameras.displayName(it).let { t -> t.substring(0, 1) + t.substring(1).lowercase() }, "snapshot" to true) }
        var secret: String? = null
        override fun setWebhook(url: String, secret: String) { hook = url; this.secret = secret }
        val display = HashMap<String, String>()
        override fun setDisplay(key: String, value: String) { display[key] = value }
        var guest: Boolean? = null
        override fun setGuest(on: Boolean) { guest = on }
        var setup: Pair<String, String?>? = null
        override fun setSetup(server: String, camera: String?) { setup = Pair(server, camera) }
        override fun logTail(lines: Int) = listOf("started", "url http://u:pw1@x/ token=abc").take(lines)
        override fun metrics() = PlayerController(FakeEnv(), FakeDisplay()).metrics(version, platform)
        override fun statusExtra() = mapOf("mqtt" to false)
        override fun startUpdate(version: String) { (ctl as? RecordingController)?.calls?.add(listOf("update", version)) }
        override fun log(message: String, level: String) { logged.add(message) }
        override fun resolve(host: String) = Exported.resolve(host)
    }

    private fun backendFor(r: Map<String, Any?>, ctl: RecordingController) = TestBackend(
        (r["settings"] as Map<String, Any?>).mapValues { if (it.value is Long) (it.value as Long).toInt() else it.value },
        ctl, r["cameras"] as List<String>?)

    private fun ctlFor(r: Map<String, Any?>): RecordingController {
        val c = r["ctl"] as Map<String, Any?>
        return RecordingController(c["results"] as Map<String, Any?>?, c["fail"] as String?)
    }

    /** The request of a row as the Python adapters build it: POST = form body (or the raw JSON body). */
    private fun request(r: Map<String, Any?>): Request {
        val args = (r["args"] as Map<String, Any?>).mapValues { it.value.toString() }
        val method = r["method"] as String
        var query = args
        var body = ByteArray(0)
        var ctype = ""
        if (method == "POST" && r["body"] == null) {
            query = emptyMap()
            body = args.entries.joinToString("&") { enc(it.key) + "=" + enc(it.value) }.toByteArray()
            ctype = "application/x-www-form-urlencoded"
        } else if (r["body"] != null) {
            body = (r["body"] as String).toByteArray()
            ctype = "application/json"
        }
        return Request(method, r["path"] as String, query, r["ip"] as String, r["header"] as String?, r["user_agent"] as String, body, ctype)
    }

    private fun enc(s: String) = URLEncoder.encode(s, "UTF-8")

    private fun same(a: Any?, b: Any?) = Json.write(a, sortKeys = true) == Json.write(b, sortKeys = true)

    /** What is wrong in the answer to row r (empty = matches the contract). */
    private fun differences(r: Map<String, Any?>, ans: Answer, ctl: RecordingController): List<String> {
        val out = ArrayList<String>()
        if (ans.code != (r["code"] as Number).toInt()) out.add("status ${ans.code}, expected ${r["code"]}")
        (r["json"] as Map<String, Any?>?)?.let { want ->
            val body = ans.body as? Map<String, Any?> ?: emptyMap()
            for ((k, v) in want) if (!same(body[k], v)) out.add("$k=${Json.write(body[k])}, expected ${Json.write(v)}")
        }
        (r["calls"] as List<Any?>?)?.let { want -> if (!same(ctl.calls, want)) out.add("controller calls ${Json.write(ctl.calls)}, expected ${Json.write(want)}") }
        for ((k, v) in r["headers"] as Map<String, Any?>) {
            val got = ans.headers.entries.firstOrNull { it.key.equals(k, ignoreCase = true) }?.value
            if (got != v) out.add("header $k=$got, expected $v")
        }
        val check = r["check"] as String?
        if (check != null && out.isEmpty() && !runCheck(check, ans.body)) out.add("check $check failed on ${ans.body}")
        return out
    }

    private fun runCheck(name: String, body: Any?): Boolean = when (name) {
        "status_keys" -> {
            val b = body as Map<String, Any?>
            (Exported.http["status_keys"] as List<String>).all { it in b } && b["result"] == true && (b["api_version"] as? Number)?.toInt() == 1 &&
                (b["capabilities"] as List<String>).containsAll(listOf("post", "header_token", "show", "ptz", "screen", "test")) &&
                b["screen"] in (Exported.http["screens"] as List<String>)
        }
        "no_snapshot_paths" -> {
            val ev = (body as Map<String, Any?>)["events"] as List<Map<String, Any?>>
            ev.isNotEmpty() && ev[0]["camera"] == "garden" && ev.all { "snapshot" !in it }
        }
        "log_lines" -> (body as Map<String, Any?>)["lines"] is List<*>
        "no_spoken_key" -> body is Map<*, *> && "spoken" !in body  // #89
        "prometheus" -> body is String && "camalert_uptime_seconds" in body && "camalert_requests_total" in body
        else -> error("unknown check $name: add it here")
    }

    private fun direct(api: Api, r: Map<String, Any?>, ctl: RecordingController): Answer {
        val resp = api.handle(backendFor(r, ctl), request(r))
        return Answer(resp.code, resp.body, resp.headers)
    }

    private fun runTable(call: (Map<String, Any?>, RecordingController) -> Answer?): Pair<List<String>, List<String>> {
        val unexpected = ArrayList<String>()
        val stale = ArrayList<String>()
        for (r in rows) {
            val ctl = ctlFor(r)
            val ans = call(r, ctl) ?: continue
            val diff = differences(r, ans, ctl)
            val known = KNOWN[r["name"]]
            if (diff.isNotEmpty() && known == null) unexpected.add("${r["name"]}: ${diff.joinToString("; ")}")
            else if (known != null && diff.isEmpty()) stale.add("${r["name"]} ($known)")
        }
        return Pair(unexpected, stale)
    }

    @Test
    fun everyRowOfTheContract() {
        val api = Api()
        val (unexpected, stale) = runTable { r, ctl -> api.reset(); direct(api, r, ctl) }
        assertEquals("androidtv differs from the API contract", emptyList<String>(), unexpected)
        assertEquals("fixed: remove from KNOWN", emptyList<String>(), stale)
        println("HTTP contract: ${rows.size} rows, ${rows.size - KNOWN.size} pass, ${KNOWN.size} KNOWN")
    }

    @Test
    fun rateLimit() {
        val api = Api()
        val rl = Exported.http["rate_limit"] as Map<String, Any?>
        val r = rows.first { it["name"] == "status" }
        val codes = (1..(rl["requests"] as Number).toInt()).map {
            api.handle(backendFor(r, ctlFor(r)), Request("GET", "/camalert/status", ip = rl["ip"] as String)).code
        }
        assertEquals(200, codes[0])
        assertTrue(429 in codes)
        assertEquals((rl["limit"] as Number).toInt(), api.limit.limit)
    }

    /** The same rows over a real socket through HttpServer (rows from a LAN address: the socket is 127.0.0.1). */
    @Test
    fun everyLanRowOverHttp() {
        val api = Api()
        var current: TestBackend? = null
        val proxy = object : Backend by TestBackend(emptyMap(), RecordingController(), null) {
            override fun settings() = current!!.settings()
            override fun controller() = current!!.controller()
            override fun cameras() = current!!.cameras()
            override fun metrics() = current!!.metrics()
            override fun statusExtra() = current!!.statusExtra()
            override fun node() = current!!.node()
            override fun logTail(lines: Int) = current!!.logTail(lines)
            override fun setWebhook(url: String, secret: String) = current!!.setWebhook(url, secret)
            override fun setDisplay(key: String, value: String) = current!!.setDisplay(key, value)
            override fun setGuest(on: Boolean) = current!!.setGuest(on)
            override fun setSetup(server: String, camera: String?) = current!!.setSetup(server, camera)
            override fun startUpdate(version: String) = current!!.startUpdate(version)
            override fun updateStatus() = current!!.updateStatus()
            override fun resolve(host: String) = Exported.resolve(host)
        }
        val server = HttpServer(api, proxy, 0, java.net.InetAddress.getLoopbackAddress())
        server.start()
        var ran = 0
        try {
            val (unexpected, stale) = runTable { r, ctl ->
                if (!Access.lanAddress(r["ip"] as String)) return@runTable null
                api.reset()
                current = backendFor(r, ctl)
                ran++
                overHttp(server.localPort, request(r))
            }
            assertEquals("over HTTP", emptyList<String>(), unexpected)
            assertEquals(emptyList<String>(), stale)
        } finally {
            server.stop()
        }
        assertTrue(ran > 40)
    }

    private fun overHttp(port: Int, req: Request): Answer {
        val q = req.args.entries.joinToString("&") { enc(it.key) + "=" + enc(it.value) }
        val c = URL("http://127.0.0.1:$port${req.path}${if (q.isNotEmpty()) "?$q" else ""}").openConnection() as HttpURLConnection
        if (req.method == "PUT") c.doOutput = true
        c.requestMethod = req.method
        req.headerToken?.let { c.setRequestProperty("X-CamAlert-Token", it) }
        c.setRequestProperty("User-Agent", req.userAgent)
        if (req.body.isNotEmpty() || req.method == "POST") {
            c.doOutput = true
            if (req.contentType.isNotEmpty()) c.setRequestProperty("Content-Type", req.contentType)
            c.outputStream.use { it.write(req.body) }
        }
        val code = c.responseCode
        val text = (if (code < 400) c.inputStream else c.errorStream).use { String(it.readBytes(), Charsets.UTF_8) }
        val ctype = c.contentType ?: ""
        val headers = c.headerFields.filterKeys { it != null }.mapValues { it.value.joinToString(",") }
        return Answer(code, if (ctype.startsWith("application/json")) Json.parse(text) else text, headers)
    }
}
