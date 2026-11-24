// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

/** Test data exported from the Python sources (tools/export_contract.py). */
object Exported {
    fun load(name: String): Map<String, Any?> {
        val s = Exported::class.java.getResourceAsStream("/contract/$name") ?: error("contract/$name missing")
        return Json.obj(s.use { String(it.readBytes(), Charsets.UTF_8) })
    }

    val http by lazy { load("http.json") }
    val mqtt by lazy { load("mqtt.json") }
    val core by lazy { load("core.json") }

    @Suppress("UNCHECKED_CAST")
    val dns: Map<String, List<String>> by lazy { http["dns"] as Map<String, List<String>> }

    /** The fake resolver of tests/fakes/dns.py: names under .example only. */
    fun resolve(host: String): List<String> {
        val h = host.lowercase().trimEnd('.')
        if (h.endsWith(".example")) return dns[h] ?: emptyList()
        return Access.resolve(host)
    }
}

/** The same as tests/fakes/controller.py: records every call. */
@Suppress("UNCHECKED_CAST")
class RecordingController(results: Map<String, Any?>? = null, val fail: String? = null) : Controller {
    private val base = Exported.http["controller"] as Map<String, Any?>
    val calls = ArrayList<List<Any?>>()
    val ptz = (base["ptz"] as List<String>).toSet()
    val results = HashMap((base["results"] as Map<String, String>)).apply { results?.forEach { (k, v) -> put(k, v.toString()) } }
    override val events = (base["events"] as List<Map<String, Any?>>)
    override var lastCaller: Triple<Double, String, String>? = null
    var dndOn = false

    private fun call(vararg x: Any?) {
        calls.add(x.toList())
        if (fail == x[0]) throw IllegalStateException("boom")
    }

    override fun show(stream: String?, seconds: Int?, mode: String?, priority: String?, source: String, label: String?, eventId: String?): String {
        call("show", stream, seconds, mode, priority, source, label)
        return results.getValue("show")
    }

    override fun hide() = call("hide")
    override fun mosaic(streams: String?, seconds: Int): String { call("mosaic", streams, seconds); return results.getValue("mosaic") }
    override fun tour(streams: String?, interval: Int?): String { call("tour", streams, interval); return results.getValue("tour") }
    override fun hasPtz(name: String) = name.isNotEmpty() && name in ptz
    override fun ptzMove(move: String, name: String?): Boolean { call("ptz", move, name); return true }
    override fun setDnd(on: Boolean) { call("dnd", on); dndOn = on }
    override fun status(): Map<String, Any?> = mapOf("window" to null, "live" to null, "paused" to false, "dnd" to dndOn)
}

class FakeDisplay : Display {
    val calls = ArrayList<String>()
    var current = Screen(null, null)
    override fun photo(tiles: List<Tile>, seconds: Int, label: String?) { calls.add("photo ${tiles.joinToString(",") { it.name }} $seconds"); current = Screen(if (tiles.size > 1) "strip" else "photo", tiles[0].name, tiles.map { it.name }) }
    override fun extend(seconds: Int) { calls.add("extend $seconds") }
    override fun live(tile: Tile, seconds: Int, volumePercent: Int) { calls.add("live ${tile.name} $seconds $volumePercent"); current = Screen("live", tile.name) }
    override fun notify(tile: Tile, seconds: Int) { calls.add("notify ${tile.name} $seconds"); current = Screen("notify", tile.name) }
    override fun mosaic(tiles: List<Tile>, seconds: Int) { calls.add("mosaic ${tiles.joinToString(",") { it.name }} $seconds"); current = Screen("mosaic", null) }
    override fun tour(tiles: List<Tile>, interval: Int) { calls.add("tour ${tiles.joinToString(",") { it.name }} $interval"); current = Screen("tour", tiles[0].name) }
    override fun hide() { calls.add("hide"); current = Screen(null, null) }
    override fun screen() = current
}

class FakeEnv(var values: MutableMap<String, Any?> = Schema.validate(emptyMap()).first.toMutableMap()) : PlayerEnv {
    var names = listOf("front_door", "garden", "driveway")
    var time = 1000.0
    var hm = Pair(12, 0)
    var on = true
    var nowPlaying = "none"
    val logs = ArrayList<String>()
    var chimes = 0
    override fun settings() = values
    override fun setSetting(id: String, value: Any?) { values[id] = value }
    override fun cameraNames() = names
    override fun screenOn() = on
    override fun playing() = nowPlaying
    override fun chime() { chimes++ }
    override fun log(message: String, level: String) { logs.add(message) }
    override fun now() = time
    override fun localTime() = hm
}
