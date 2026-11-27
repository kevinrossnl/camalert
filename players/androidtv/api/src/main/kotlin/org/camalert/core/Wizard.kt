// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

import java.net.DatagramSocket
import java.net.InetSocketAddress
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/**
 * The first-start wizard (#120), port of core/camalert_core/wizard.py: when it starts, where to look for go2rtc,
 * the search in threads with a time limit, and what it saves. The app only draws the dialogs. Never call scan()
 * on the UI thread.
 */
object Wizard {
    const val PORT = 1984
    const val HA_NAME = "homeassistant.local"
    const val TIMEOUT_MS = 800
    const val WORKERS = 32
    const val BUDGET_MS = 10_000L
    val STEPS = listOf("go2rtc", "camera", "test", "done")

    /** Not done before, no go2rtc address and not in direct mode: an installation with an address never sees it. */
    fun shouldStart(s: Map<String, Any?>): Boolean {
        if (s["wizard_done"] == true) return false
        if ((s["source"] ?: "go2rtc") == "direct") return false
        return (s["server"]?.toString() ?: "").isBlank()
    }

    fun nextStep(step: String): String? {
        val i = STEPS.indexOf(step)
        return if (i >= 0 && i < STEPS.size - 1) STEPS[i + 1] else null
    }

    /** The own LAN address (no packet is sent), or null. */
    fun ownIp(open: () -> DatagramSocket = { DatagramSocket() }): String? = try {
        open().use { s ->
            s.connect(InetSocketAddress("192.0.2.1", 9))
            val ip = s.localAddress?.hostAddress
            if (ip == null || ip.startsWith("127.") || ip == "0.0.0.0" || ':' in ip) null else ip
        }
    } catch (e: Exception) {
        null
    }

    /** The Home Assistant host if known: the webhook address or the MQTT broker. */
    fun haHost(s: Map<String, Any?>): String? {
        for (key in listOf("ha_webhook", "mqtt_host")) {
            val v = s[key]?.toString()?.trim() ?: continue
            if (v.isEmpty()) continue
            val host = Urls.serverHost(if ("://" in v) v else "http://$v")
            if (!host.isNullOrEmpty()) return host
        }
        return null
    }

    private fun server(host: String, port: Int) = "http://${if (':' in host) "[$host]" else host}:$port"

    /** homeassistant.local, the Home Assistant host, then every other address of the own /24. */
    fun candidates(own: String?, ha: String? = null, port: Int = PORT): List<String> {
        val out = mutableListOf(server(HA_NAME, port))
        if (ha != null) out.add(server(ha, port))
        val parts = (own ?: "").split(".")
        if (parts.size == 4 && parts.all { p -> p.isNotEmpty() && p.all { it.isDigit() } && p.toInt() in 0..255 }) {
            val net = parts.take(3).joinToString(".")
            for (i in 1..254) out.add(server("$net.$i", port))
        }
        return out.distinct()
    }

    /** Camera names from a go2rtc /api/streams answer; null when it is not one. */
    fun camerasFrom(text: String?): List<String>? {
        val d = try { Json.parse(text ?: "") } catch (e: Exception) { return null }
        if (d !is Map<*, *>) return null
        return Urls.streamsFromJson(text)
    }

    /** [(server, cameras)] of every go2rtc found, in the order of addresses; after budgetMs at the latest. */
    fun scan(addresses: List<String>, probe: (String) -> List<String>?, workers: Int = WORKERS,
             budgetMs: Long = BUDGET_MS, stop: AtomicBoolean = AtomicBoolean(false)): List<Pair<String, List<String>>> {
        if (addresses.isEmpty()) return emptyList()
        val found = java.util.concurrent.ConcurrentHashMap<Int, Pair<String, List<String>>>()
        val pool = Executors.newFixedThreadPool(minOf(workers, addresses.size)) { r ->
            Thread(r, "camalert-wizard").apply { isDaemon = true }
        }
        val deadline = System.currentTimeMillis() + budgetMs
        addresses.forEachIndexed { i, srv ->
            pool.execute {
                if (stop.get() || System.currentTimeMillis() > deadline) return@execute
                val cams = try { probe(srv) } catch (e: Exception) { null }
                if (cams != null) found[i] = Pair(srv, cams)
            }
        }
        pool.shutdown()
        while (!stop.get() && System.currentTimeMillis() < deadline && !pool.awaitTermination(50, TimeUnit.MILLISECONDS)) {
            // wait for the probes, the stop flag or the time limit
        }
        pool.shutdownNow()
        return found.keys.sorted().map { found.getValue(it) }
    }

    /** One entry per go2rtc: the same camera list under two addresses is the same go2rtc (the first is kept). */
    fun uniqueServers(found: List<Pair<String, List<String>>>): List<Pair<String, List<String>>> {
        val seen = HashSet<List<String>>()
        return found.filter { (_, cams) -> !(cams.isNotEmpty() && !seen.add(cams)) }
    }

    fun serverFromInput(text: String?): String? {
        val t = (text ?: "").trim()
        if (t.endsWith("://")) return null
        return Urls.normalizeServer(t)
    }

    /** The settings saved at the end (also when the user stops early: it does not open again). */
    fun result(server: String? = null, camera: String? = null): Map<String, Any?> {
        val out = linkedMapOf<String, Any?>("wizard_done" to true)
        if (server != null) { out["source"] = "go2rtc"; out["server"] = server }
        if (camera != null) out["camera"] = camera
        return out
    }

    fun addText(name: String?, ip: String?, port: Int) = Pair(name?.ifEmpty { null } ?: "CamAlert", "${ip ?: "?"}:$port")
}
