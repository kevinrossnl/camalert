// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

/** One camera on screen: name, title, snapshot url and live url (null = none). */
data class Tile(val name: String, val title: String, val snapshot: String?, val live: String?)

/** What is on screen now (the Android overlay reports it). */
data class Screen(val kind: String?, val stream: String?, val streams: List<String> = emptyList())

/** The screen of the player: overlay windows on Android TV (implemented in the app, faked in the JVM tests). */
interface Display {
    /** priority: what the window marks (#48), "normal" = no frame. */
    fun photo(tiles: List<Tile>, seconds: Int, label: String?, priority: String = "normal")
    fun extend(seconds: Int)
    fun live(tile: Tile, seconds: Int, volumePercent: Int)
    fun notify(tile: Tile, seconds: Int)
    fun mosaic(tiles: List<Tile>, seconds: Int)
    fun tour(tiles: List<Tile>, interval: Int)
    fun hide()
    fun screen(): Screen
}

/** What the player knows about its device. */
interface PlayerEnv {
    fun settings(): Map<String, Any?>
    fun setSetting(id: String, value: Any?)
    /** Camera names of go2rtc (may block; [] when unknown). */
    fun cameraNames(): List<String>
    /** Composite streams (an own mosaic in go2rtc) of the last camera list (#125). */
    fun compositeStreams(): Set<String> = emptySet()
    /** #15: camera name -> (go2rtc server, stream) of the last camera list. */
    fun serverMap(): Map<String, Pair<String, String>> = emptyMap()
    /** Direct mode (#124): the cameras of the camera list (no go2rtc). */
    fun directCameras(): List<DirectCamera> = emptyList()
    fun screenOn(): Boolean = true
    fun wake() {}
    /** "none" | "video" | "audio": what another app plays (for skip_playing). */
    fun playing(): String = "none"
    fun chime() {}
    fun log(message: String, level: String = "normal") {}
    fun changed() {}
    /** Camera control (#66): does this camera have PTZ (a line in the devices list), and move it (blocking). */
    fun hasPtz(name: String): Boolean = false
    fun ptzMove(move: String, name: String): Boolean = false
    fun now(): Double = System.currentTimeMillis() / 1000.0
    fun localTime(): Pair<Int, Int> = java.util.Calendar.getInstance().let { Pair(it.get(java.util.Calendar.HOUR_OF_DAY), it.get(java.util.Calendar.MINUTE)) }
}

/**
 * show / mosaic / tour / hide with the same rules as the Enigma2 and Kodi players (Kodi controller.py): do not
 * disturb, cooldown, active hours, "not while playing", 2-4 cameras = multi-camera window, more = mosaic,
 * unknown camera = error; events with codes (present.reason).
 */
class PlayerController(private val env: PlayerEnv, private val display: Display) : Controller {
    override var lastCaller: Triple<Double, String, String>? = null
    private val _events = ArrayList<Map<String, Any?>>()
    override val events: List<Map<String, Any?>> get() = synchronized(_events) { _events.toList() }
    private val lastShown = HashMap<String, Double>()
    private var names: List<String> = emptyList()
    private var namesAt = 0.0
    private val lock = Object()
    val stats = Stats()

    class Stats {
        val requests = java.util.TreeMap<String, Int>()
        var errors = 0
        var unreachable = 0
        var lastEvent = 0.0
        val started = System.currentTimeMillis() / 1000.0
    }

    fun refreshNames(): List<String> {
        try {
            names = env.cameraNames()
            namesAt = env.now()
        } catch (e: Exception) {
            env.log("camera list failed: ${e.message}", "error")
        }
        return names
    }

    fun knownNames(): List<String> = if (names.isEmpty() || env.now() - namesAt > 60) refreshNames() else names

    /** Tile of a camera from the settings (go2rtc), or null without a valid go2rtc address. In direct mode (#124)
     *  the camera list gives the RTSP stream and the (optional) snapshot url. */
    fun tile(name: String, s: Map<String, Any?> = env.settings()): Tile? {
        if (s["source"]?.toString() == "direct") {
            val cam = env.directCameras().firstOrNull { it.name == name } ?: return null
            return Tile(name, cam.title, cam.snapshot, cam.rtsp)  // the title from the camera list, as on Enigma2 and Kodi
        }
        val servers = Servers.serverList(s["server"]?.toString(), s["more_servers"]?.toString())  // #15
        val (server, stream) = Servers.resolve(name, servers, env.serverMap())
        if (server == null) return null
        val titles = Cameras.parseMap(s["titles"]?.toString())
        val (liveServer, live) = Servers.resolve(Cameras.liveStreamName(name, s["substreams"]?.toString()), servers, env.serverMap())
        val url = when (s["live_format"]?.toString()) {
            "rtsp" -> Urls.rtspUrl(liveServer, live, Urls.validPort(s["rtsp_port"], 8554))
            "hls" -> Urls.hlsUrl(liveServer, live)
            else -> Urls.mp4Url(liveServer, live)
        }
        return Tile(name, Cameras.titleFor(name, titles), Urls.snapshotUrl(server, stream), url)
    }

    override fun show(stream: String?, seconds: Int?, mode: String?, priority: String?, source: String, label: String?, eventId: String?): String {
        val s = env.settings()
        val cam = stream ?: s["camera"]?.toString() ?: ""
        val wait = Rules.cooldownSeconds(cam, s["cooldown"]?.toString())
        val prio = Rules.pickPriority(priority)
        val lab = label?.trim()?.take(40)?.ifEmpty { null }
        if (mode == "log") {  // display mode 'log only' (UniFi Protect rules, #72): event list and log, nothing on screen, no chime
            env.log("request from $source: camera=$cam priority=$prio mode=log label=${label ?: "-"} -> ignore (log_only)", "normal")
            record(cam, lab, source, prio, "ignore", "log_only", eventId)
            env.changed()
            return "ignore"
        }
        var reason = ""
        val result: String
        synchronized(lock) {
            val onScreen = display.screen().stream == cam
            result = try {
                if (!onScreen && prio != "alarm" && Rules.inCooldown(lastShown[cam], env.now(), wait)) {
                    reason = "cooldown:$wait"
                    "ignore"
                } else {
                    val r = doShow(stream, seconds, mode, prio, lab, s, if (source == "menu") "normal" else prio)
                    reason = r.second
                    r.first
                }
            } catch (e: Exception) {
                env.log("show failed: $e", "error")
                "error"
            }
        }
        if (result == "show") lastShown[cam] = env.now()
        synchronized(stats) {
            stats.requests[result] = (stats.requests[result] ?: 0) + 1
            stats.lastEvent = env.now()
            if (result == "error") stats.errors++
        }
        env.log("request from $source: camera=$cam priority=$prio mode=${mode ?: "-"} label=${label ?: "-"} -> $result${if (reason.isNotEmpty()) " ($reason)" else ""}",
            if (result == "error") "error" else "normal")
        record(cam, lab, source, prio, result, reason, eventId)
        if ((result == "show" || result == "extend") && source != "test" && source != "menu" && Rules.chimeWanted(s["chime"]?.toString() ?: "off", prio)) env.chime()
        env.changed()
        return result
    }

    private fun record(cam: String, label: String?, source: String, priority: String, action: String, reason: String, eventId: String?) {
        val ev = linkedMapOf<String, Any?>("time" to env.now(), "camera" to cam, "label" to (label ?: ""), "source" to source,
            "priority" to priority, "action" to action, "reason" to reason, "snapshot" to null, "frigate_id" to eventId)
        synchronized(_events) { Events.add(_events, ev) }
    }

    /** (result, reason code). */
    /** mark: the priority the window marks (#48); "normal" for what the viewer asked for himself (#13). */
    private fun doShow(stream: String?, seconds: Int?, mode: String?, priority: String, label: String?, s: Map<String, Any?>,
                       mark: String = priority): Pair<String, String> {
        if (Rules.dndBlocks(priority, s["dnd"] == true, s["dnd_level"]?.toString() ?: "normal")) return Pair("ignore", "dnd")
        if (!env.screenOn()) {
            if (priority == "alarm" && s["alarm_wake"] == true) {
                env.log("alarm: waking the screen")
                env.wake()
                return Pair("wake", "woken")
            }
            return Pair("ignore", "screen_off")
        }
        val cams = Cameras.parseCams(stream)
        val secs = seconds ?: (s["duration"] as? Number)?.toInt() ?: 30
        val m = Rules.pickMode(mode, s["mode"]?.toString() ?: "photo")
        if (cams.size > 1) {
            if (cams.size <= 4 && m == "photo") {
                val tiles = cams.mapNotNull { tile(it, s) }.filter { it.snapshot != null }
                if (tiles.isEmpty()) return Pair("error", "no_address")
                display.photo(tiles, secs, label, mark)
                return Pair("show", "")
            }
            return Pair(mosaic(cams.joinToString(","), secs), "")
        }
        val name = stream ?: s["camera"]?.toString() ?: ""
        if (name.isEmpty()) return Pair("error", "no_camera")
        if (!Cameras.knownCamera(name, knownNames())) return Pair("error", "unknown_camera")
        val t = tile(name, s) ?: return Pair("error", "no_address")
        val inHours = Rules.inTimeWindow(env.localTime(), Rules.clockTuple(s["from_time"]?.toString()), Rules.clockTuple(s["until_time"]?.toString()))
        val skip = s["skip_playing"]?.toString() ?: "off"
        val playing = env.playing()
        val blockedByPlaying = when (skip) { "all" -> playing != "none"; "video" -> playing == "video"; else -> false }
        if (Rules.blockedByRules(priority, s["limit_hours"] == true, inHours, skip != "off", blockedByPlaying)) {
            return Pair("ignore", if (s["limit_hours"] == true && !inHours) "outside_hours" else "playing")
        }
        val screen = display.screen()
        val windowStream = if (screen.kind == "photo" || screen.kind == "notify") screen.stream else if (m == "live" && screen.kind == "live") screen.stream else null
        val current = if (screen.kind == "live") screen.stream else null
        val action = Rules.decide(false, if (m == "live") null else current, windowStream, name)
        if (action == "ignore") return Pair("ignore", "on_screen")
        val titled = t.copy(title = Events.eventTitle(t.title, label))
        val shown = if (m == "photo" && t.snapshot == null) "live" else m  // direct mode without snapshot url (#124)
        if (action == "extend") {
            display.extend(secs)
            return Pair("extend", "")
        }
        when (shown) {
            "live" -> display.live(titled, secs, if (priority == "alarm") 100 else (s["live_volume"] as? Number)?.toInt() ?: 100)
            "notify" -> display.notify(titled, secs)
            else -> display.photo(listOf(titled), secs, label, mark)
        }
        return Pair("show", "")
    }

    private fun tilesOf(stream: String?, s: Map<String, Any?>): List<Tile> {
        val streams = Cameras.parseCams(stream).ifEmpty { Cameras.parseCams(s["mosaic"]?.toString()) }.ifEmpty { Urls.overviewCameras(refreshNames(), env.compositeStreams()) }
        return streams.take(9).mapNotNull { tile(it, s) }.filter { it.snapshot != null }
    }

    override fun mosaic(streams: String?, seconds: Int): String {
        val s = env.settings()
        if (!env.screenOn()) return "ignore"
        val tiles = tilesOf(streams, s)
        if (tiles.isEmpty()) return "error"
        display.mosaic(tiles, if (seconds > 0) Rules.clampSeconds(seconds, 60) else 0)
        env.changed()
        return "show"
    }

    override fun tour(streams: String?, interval: Int?): String {
        val s = env.settings()
        if (!env.screenOn()) return "ignore"
        val tiles = tilesOf(streams, s)
        if (tiles.isEmpty()) return "error"
        display.tour(tiles, interval ?: (s["tour_interval"] as? Number)?.toInt() ?: 8)
        env.changed()
        return "show"
    }

    override fun hide() {
        display.hide()
        env.changed()
    }

    /** Another camera in the window / live view (LEFT/RIGHT). */
    fun neighbour(current: String?, step: Int): Tile? {
        val target = Cameras.neighbour(knownNames(), current, step) ?: return null
        return tile(target)
    }

    override fun hasPtz(name: String) = name.isNotEmpty() && env.hasPtz(name)  // #66
    override fun ptzMove(move: String, name: String?): Boolean {
        val cam = name?.ifEmpty { null } ?: display.screen().stream ?: return false
        return env.hasPtz(cam) && env.ptzMove(move, cam)
    }

    override fun setDnd(on: Boolean) {
        env.setSetting("dnd", on)
        env.changed()
    }

    override fun status(): Map<String, Any?> {
        val sc = display.screen()
        return linkedMapOf("window" to (if (sc.kind == "photo" || sc.kind == "strip" || sc.kind == "notify") sc.stream else null),
            "live" to (if (sc.kind == "live") sc.stream else null), "paused" to false,
            "dnd" to (env.settings()["dnd"] == true), "screen" to screenName(sc.kind))
    }

    /** The "screen" value of /camalert/status (#63). */
    fun screenName(kind: String?) = when (kind) {
        null -> "none"
        "notify" -> "notification"
        else -> kind
    }

    fun metrics(version: String, platform: String): String {
        val st = status()
        synchronized(stats) {
            return Obs.metricsText(mapOf(
                "requests_total" to Obs.Metric("counter", "Show requests by result", if (stats.requests.isEmpty()) mapOf("show" to 0) else HashMap(stats.requests)),
                "errors_total" to Obs.Metric("counter", "Errors logged", stats.errors),
                "unreachable_total" to Obs.Metric("counter", "Times a camera was not reachable in the photo window", stats.unreachable),
                "last_event_timestamp_seconds" to Obs.Metric("gauge", "Time of the last request", stats.lastEvent),
                "uptime_seconds" to Obs.Metric("gauge", "Seconds since CamAlert started", env.now() - stats.started),
                "on_screen" to Obs.Metric("gauge", "1 while a camera is on screen", if (st["window"] != null || st["live"] != null) 1 else 0),
                "dnd" to Obs.Metric("gauge", "Do not disturb on", if (st["dnd"] == true) 1 else 0),
                "events" to Obs.Metric("gauge", "Events in the event list", events.size),
            ), mapOf("version" to version, "platform" to platform))
        }
    }
}
