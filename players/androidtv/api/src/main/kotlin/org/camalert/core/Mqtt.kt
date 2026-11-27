// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

import java.io.ByteArrayOutputStream
import java.io.IOException
import java.net.InetSocketAddress
import java.net.Socket
import java.net.SocketTimeoutException

/**
 * Minimal MQTT 3.1.1 client (QoS 0) with Home Assistant discovery and the Frigate trigger; the same topics as the
 * Enigma2 and Kodi players (core mqtt/codec.py + topics.py, Kodi mqtt.py):
 *
 *     camalert/<node>/show | mosaic | hide | dnd/set     commands
 *     camalert/<node>/state | dnd | availability         published (retained)
 *     camalert/<node>/button                             colour keys (event entity)
 *     <frigate prefix>/events                            Frigate detections (optional)
 *
 * No library: the protocol subset is small and the same code runs in the JVM tests against a fake broker.
 */
object MqttCodec {
    fun len(n0: Int): ByteArray {
        var n = n0
        val out = ByteArrayOutputStream()
        while (true) {
            var b = n % 128
            n /= 128
            if (n > 0) b = b or 0x80
            out.write(b)
            if (n == 0) return out.toByteArray()
        }
    }

    fun str(s: String) = bytes(s.toByteArray(Charsets.UTF_8))
    fun bytes(b: ByteArray) = byteArrayOf((b.size shr 8).toByte(), (b.size and 0xff).toByte()) + b

    fun connect(clientId: String, user: String?, password: String?, willTopic: String?, willPayload: String = "offline", keepalive: Int = 60): ByteArray {
        var flags = 0x02
        var payload = str(clientId)
        if (!willTopic.isNullOrEmpty()) {
            flags = flags or 0x04 or 0x20
            payload += str(willTopic) + str(willPayload)
        }
        if (!user.isNullOrEmpty()) {
            flags = flags or 0x80
            payload += str(user)
            if (!password.isNullOrEmpty()) {
                flags = flags or 0x40
                payload += str(password)
            }
        }
        val body = str("MQTT") + byteArrayOf(4, flags.toByte(), (keepalive shr 8).toByte(), (keepalive and 0xff).toByte()) + payload
        return byteArrayOf(0x10) + len(body.size) + body
    }

    fun publish(topic: String, payload: ByteArray, retain: Boolean = false): ByteArray {
        val body = str(topic) + payload
        return byteArrayOf((0x30 or (if (retain) 1 else 0)).toByte()) + len(body.size) + body
    }

    fun publish(topic: String, payload: String, retain: Boolean = false) = publish(topic, payload.toByteArray(Charsets.UTF_8), retain)

    fun subscribe(packetId: Int, topics: List<String>): ByteArray {
        var body = byteArrayOf((packetId shr 8).toByte(), (packetId and 0xff).toByte())
        for (t in topics) body += str(t) + byteArrayOf(0)
        return byteArrayOf(0x82.toByte()) + len(body.size) + body
    }

    val PING = byteArrayOf(0xc0.toByte(), 0)
    val DISCONNECT = byteArrayOf(0xe0.toByte(), 0)

    class Packet(val type: Int, val flags: Int, val body: ByteArray)

    /** Splits a buffer into complete packets: (packets, rest). */
    fun split(buffer: ByteArray): Pair<List<Packet>, ByteArray> {
        val packets = ArrayList<Packet>()
        var i = 0
        while (buffer.size - i >= 2) {
            var mult = 1
            var length = 0
            var j = i + 1
            while (true) {
                if (j >= buffer.size) return Pair(packets, buffer.copyOfRange(i, buffer.size))
                val b = buffer[j].toInt() and 0xff
                length += (b and 0x7f) * mult
                mult *= 128
                j++
                if (b and 0x80 == 0) break
            }
            if (buffer.size - j < length) break
            val first = buffer[i].toInt() and 0xff
            packets.add(Packet(first shr 4, first and 0x0f, buffer.copyOfRange(j, j + length)))
            i = j + length
        }
        return Pair(packets, buffer.copyOfRange(i, buffer.size))
    }

    /** (topic, payload) of an incoming PUBLISH. */
    fun parsePublish(flags: Int, body: ByteArray): Pair<String, ByteArray> {
        val n = ((body[0].toInt() and 0xff) shl 8) or (body[1].toInt() and 0xff)
        val topic = String(body, 2, n, Charsets.UTF_8)
        var rest = body.copyOfRange(2 + n, body.size)
        if ((flags shr 1) and 0x03 != 0) rest = rest.copyOfRange(2, rest.size)
        return Pair(topic, rest)
    }
}

object MqttTopics {
    /** Payload of a show command: 'front_door' or JSON {"cam", "sec", "mode", "priority", "label"}. */
    fun command(payload: ByteArray): Map<String, Any?> {
        val text = String(payload, Charsets.UTF_8).trim()
        if (text.startsWith("{")) {
            val d = try { Json.parse(text) } catch (e: Exception) { return emptyMap() }
            if (d !is Map<*, *>) return emptyMap()
            return listOf("cam", "sec", "mode", "priority", "label").filter { it in d }.associateWith { d[it] }
        }
        return if (text.isEmpty()) emptyMap() else mapOf("cam" to text)
    }

    /** Subscription for this player's own retained discovery configs (#116, core mqtt/topics.discovery_filter). */
    fun discoveryFilter(node: String, base: String = "homeassistant") = "$base/+/camalert_$node/+/config"

    /** Home Assistant discovery: [(topic, payload)], the same as core mqtt/topics.discovery() apart from the model. */
    fun discovery(node: String, name: String, cameras: List<Pair<String, String>>, model: String, prefix: String = "camalert", base: String = "homeassistant"): List<Pair<String, String>> {
        val avail = "$prefix/$node/availability"
        val device = mapOf("identifiers" to listOf("camalert_$node"), "name" to name, "manufacturer" to "CamAlert", "model" to model)
        val msgs = ArrayList<Pair<String, String>>()
        fun add(kind: String, oid: String, conf: MutableMap<String, Any?>) {
            conf["unique_id"] = "camalert_${node}_$oid"
            conf["object_id"] = "camalert_${node}_$oid"
            conf["availability_topic"] = avail
            conf["device"] = device
            msgs.add(Pair("$base/$kind/camalert_$node/$oid/config", Json.write(conf, sortKeys = true)))
        }
        for ((cam, title) in cameras) {
            add("button", "show_$cam", mutableMapOf("name" to "Show $title", "icon" to "mdi:cctv", "command_topic" to "$prefix/$node/show", "payload_press" to cam))
        }
        add("button", "mosaic", mutableMapOf("name" to "Mosaic", "icon" to "mdi:view-grid", "command_topic" to "$prefix/$node/mosaic", "payload_press" to ""))
        add("button", "hide", mutableMapOf("name" to "Hide camera", "icon" to "mdi:close-box", "command_topic" to "$prefix/$node/hide", "payload_press" to ""))
        add("sensor", "on_screen", mutableMapOf("name" to "Camera on screen", "icon" to "mdi:television", "state_topic" to "$prefix/$node/state"))
        add("switch", "dnd", mutableMapOf("name" to "Do not disturb", "icon" to "mdi:bell-off", "command_topic" to "$prefix/$node/dnd/set",
            "state_topic" to "$prefix/$node/dnd", "payload_on" to "ON", "payload_off" to "OFF"))
        add("event", "button", mutableMapOf("name" to "Remote button", "icon" to "mdi:remote", "state_topic" to "$prefix/$node/button",
            "event_types" to listOf("red", "green", "yellow", "blue")))
        return msgs
    }

    /** Payload of camalert/<id>/button and the Home Assistant webhook (core keymap.button_event). */
    fun buttonEvent(node: String, camera: String?, button: String) =
        Json.write(mapOf("event_type" to button, "button" to button, "camera" to (camera ?: ""), "receiver" to node), sortKeys = true)
}

/** Frigate detections via MQTT (core triggers/frigate.py). */
class Frigate(val settings: Map<String, Any?>) {
    val seen = HashMap<String, Double>()
    val enabled get() = settings["frigate_enabled"] == true

    fun topic(): String {
        val p = (settings["frigate_prefix"]?.toString() ?: "frigate").trim().trim('/')
        return "${p.ifEmpty { "frigate" }}/events"
    }

    class Trigger(val camera: String, val priority: String, val label: String?, val eventId: String, val mode: String?, val seconds: Int?)

    fun parse(payload: ByteArray, now: Double, debounce: Double = 5.0): Trigger? {
        val d = try { Json.parse(String(payload, Charsets.UTF_8)) } catch (e: Exception) { return null } as? Map<*, *> ?: return null
        if (d["type"] !in listOf("new", "update")) return null
        val after = d["after"] as? Map<*, *> ?: return null
        if (after["false_positive"].truthy() || !after["camera"].truthy()) return null
        val camera = after["camera"].toString()
        val label = after["label"]?.toString() ?: ""
        var sub = after["sub_label"]
        if (sub is List<*>) sub = sub.firstOrNull()
        val wanted = (settings["frigate_labels"]?.toString() ?: "").split(",").map { it.trim().lowercase() }.filter { it.isNotEmpty() }
        if (wanted.isNotEmpty() && label.lowercase() !in wanted) return null
        val stream = Cameras.parseMap(settings["frigate_map"]?.toString()).getOrDefault(camera, camera)
        if (!Cameras.valid(stream)) return null
        if (debounce > 0 && now - (seen[stream] ?: -1e18) < debounce) return null
        seen[stream] = now
        val title = (sub?.toString()?.takeIf { it.isNotEmpty() && sub.truthy() }) ?: label.replace("_", " ").let { s ->
            if (s.isEmpty()) null else s.substring(0, 1).uppercase() + s.substring(1).lowercase()
        }
        return Trigger(stream, settings["frigate_priority"]?.toString()?.ifEmpty { null } ?: "normal", title,
            after["id"]?.toString() ?: "", settings["frigate_mode"]?.toString()?.ifEmpty { null },
            (settings["frigate_seconds"] as? Number)?.toInt()?.takeIf { it > 0 })
    }

    private fun Any?.truthy(): Boolean = when (this) {
        null -> false
        is Boolean -> this
        is Number -> this.toDouble() != 0.0
        is String -> this.isNotEmpty()
        is Collection<*> -> this.isNotEmpty()
        is Map<*, *> -> this.isNotEmpty()
        else -> true
    }
}

/**
 * Removes this player's stale Home Assistant discovery configs (#116, core mqtt/topics.DiscoveryCleaner): with
 * discovery off every config of this player, otherwise the button of a camera that is no longer in the camera list.
 * Read back from the broker (retained), so it also works after a reinstall. Nothing goes while the list is unknown.
 */
class DiscoveryCleaner(private val node: String, private val base: String = "homeassistant") {
    private var cameras: Set<String>? = null
    private var enabled = true
    val pending = ArrayList<String>()

    fun ours(topic: String): Boolean {
        val p = topic.split("/")
        return p.size == 5 && p[0] == base && p[2] == "camalert_$node" && p[4] == "config"
    }

    private fun stale(topic: String): Boolean {
        if (!enabled) return true
        val p = topic.split("/")
        return p[1] == "button" && p[3].startsWith("show_") && p[3].substring(5) !in cameras!!
    }

    @Synchronized
    fun seen(topic: String, payload: ByteArray): List<String> {
        if (payload.isEmpty() || !ours(topic)) return emptyList()
        if (enabled && cameras == null) {
            if (topic !in pending && pending.size < MAX_PENDING) pending.add(topic)
            return emptyList()
        }
        return if (stale(topic)) listOf(topic) else emptyList()
    }

    private fun flush(): List<String> {
        val out = pending.filter { stale(it) }
        pending.clear()
        return out
    }

    @Synchronized
    fun known(names: List<String>): List<String> {
        cameras = names.toSet(); enabled = true
        return flush()
    }

    @Synchronized
    fun disabled(): List<String> {
        enabled = false
        return flush()
    }

    companion object { const val MAX_PENDING = 500 }
}

/**
 * The MQTT session of the player. Settings: mqtt_enabled, mqtt_host, mqtt_port, mqtt_user, mqtt_password,
 * mqtt_discovery, mqtt_name, enabled, frigate_*. The player gives its controller and camera list.
 */
class MqttClient(
    private val node: String,
    private val settings: () -> Map<String, Any?>,
    private val controller: () -> Controller?,
    private val cameras: () -> List<Pair<String, String>>,
    private val nodeName: () -> String,
    private val model: String,
    private val log: (String, String) -> Unit = { _, _ -> },
) : Thread("camalert-mqtt") {
    private val prefix = "camalert/$node/"
    @Volatile private var sock: Socket? = null
    private val wlock = Object()
    @Volatile var stopping = false
    @Volatile var up = false
    private var frigateSeen = HashMap<String, Double>()
    @Volatile private var cleaner = DiscoveryCleaner(node)

    init { isDaemon = true }

    fun send(data: ByteArray) {
        synchronized(wlock) {
            try { sock?.getOutputStream()?.apply { write(data); flush() } } catch (e: IOException) { }
        }
    }

    fun publish(sub: String, payload: String, retain: Boolean = false) = send(MqttCodec.publish(prefix + sub, payload, retain))

    override fun run() {
        var delay = 2000L
        while (!stopping) {
            val s = settings()
            try {
                session(s)
                delay = 2000L
            } catch (e: Exception) {
                if (!stopping) log("MQTT connection failed: ${e.message}", "normal")
            }
            up = false
            synchronized(wlock) {
                try { sock?.close() } catch (e: IOException) { }
                sock = null
            }
            if (stopping) break
            try { sleep(delay) } catch (e: InterruptedException) { break }
            delay = minOf(120_000L, delay * 2)
        }
    }

    private fun session(s: Map<String, Any?>) {
        val socket = Socket()
        socket.connect(InetSocketAddress(s["mqtt_host"].toString().trim(), Urls.validPort(s["mqtt_port"], 1883)), 10_000)
        socket.soTimeout = 1000
        synchronized(wlock) { sock = socket }
        send(MqttCodec.connect("camalert-$node", s["mqtt_user"]?.toString()?.ifEmpty { null },
            s["mqtt_password"]?.toString()?.ifEmpty { null }, prefix + "availability"))
        var buf = ByteArray(0)
        var lastPing = System.currentTimeMillis()
        val input = socket.getInputStream()
        val chunk = ByteArray(4096)
        while (!stopping) {
            try {
                val n = input.read(chunk)
                if (n < 0) throw IOException("closed by broker")
                val (packets, rest) = MqttCodec.split(buf + chunk.copyOf(n))
                buf = rest
                for (p in packets) {
                    if (p.type == 2) {
                        if (p.body.size > 1 && p.body[1].toInt() != 0) throw IOException("refused, code ${p.body[1]}")
                        connected(s)
                    } else if (p.type == 3) {
                        val (topic, payload) = MqttCodec.parsePublish(p.flags, p.body)
                        if (cleaner.ours(topic)) clear(cleaner.seen(topic, payload))  // own discovery config (#116)
                        else Thread { command(topic, payload) }.apply { isDaemon = true }.start()
                    }
                }
            } catch (e: SocketTimeoutException) {
            }
            if (System.currentTimeMillis() - lastPing > 30_000) {
                send(MqttCodec.PING)
                lastPing = System.currentTimeMillis()
            }
        }
    }

    private fun frigate(s: Map<String, Any?>) = Frigate(s).also { it.seen.putAll(frigateSeen) }

    fun subscriptions(s: Map<String, Any?>): List<String> {
        val topics = listOf("show", "mosaic", "hide", "dnd/set").map { prefix + it }.toMutableList()
        val f = Frigate(s)
        if (f.enabled && f.topic() !in topics) topics.add(f.topic())
        topics.add(MqttTopics.discoveryFilter(node))
        return topics
    }

    private fun connected(s: Map<String, Any?>) {
        up = true
        log("MQTT connected as $node", "normal")
        cleaner = DiscoveryCleaner(node).also { if (s["mqtt_discovery"] != true) it.disabled() }
        send(MqttCodec.subscribe(1, subscriptions(s)))
        publish("availability", "online", true)
        publishState()
        if (s["mqtt_discovery"] == true) Thread { announce() }.apply { isDaemon = true }.start()
    }

    fun announce() {
        val cams = try { cameras() } catch (e: Exception) {
            log("MQTT discovery failed: ${e.message}", "normal")
            return
        }
        clear(cleaner.known(cams.map { it.first }))
        for ((topic, payload) in MqttTopics.discovery(node, nodeName(), cams, model)) send(MqttCodec.publish(topic, payload, true))
        log("MQTT discovery sent for ${cams.size} cameras", "normal")
    }

    /** Removes stale Home Assistant discovery configs: an empty retained payload (#116). */
    fun clear(topics: List<String>) {
        for (t in topics) {
            send(MqttCodec.publish(t, ByteArray(0), true))
            log("MQTT discovery removed $t", "normal")
        }
    }

    fun publishState() {
        val st = controller()?.status() ?: emptyMap()
        publish("state", (st["window"] ?: st["live"] ?: "none").toString(), true)
        publish("dnd", if (st["dnd"] == true) "ON" else "OFF", true)
    }

    fun publishButton(camera: String?, button: String) {
        if (up) publish("button", MqttTopics.buttonEvent(node, camera, button))
    }

    /** One incoming message (runs in its own thread, like on Kodi). */
    fun command(topic: String, payload: ByteArray) {
        val s = settings()
        val ctl = controller()
        if (s["enabled"] != true || ctl == null) return
        try {
            val f = frigate(s)
            if (f.enabled && topic == f.topic()) {
                val t = synchronized(frigateSeen) {
                    f.parse(payload, System.currentTimeMillis() / 1000.0).also { frigateSeen.putAll(f.seen) }
                }
                if (t != null) {
                    log("Frigate detection on ${t.camera}", "normal")
                    ctl.show(t.camera, t.seconds, t.mode, t.priority, "frigate", t.label, t.eventId)
                }
                return
            }
            when (if (topic.startsWith(prefix)) topic.substring(prefix.length) else "") {
                "hide" -> ctl.hide()
                "mosaic" -> ctl.mosaic(String(payload, Charsets.UTF_8).trim().ifEmpty { null }, 60)
                "show" -> {
                    val c = MqttTopics.command(payload)
                    val raw = c["sec"]?.takeIf { it != false && it.toString().isNotEmpty() && !(it is Number && it.toDouble() == 0.0) }
                    val sec = raw?.let { Rules.clampSeconds(if (it is Double) it.toInt() else it) }
                    ctl.show(c["cam"]?.toString(), sec, c["mode"]?.toString(), c["priority"]?.toString(), "mqtt", c["label"]?.toString())
                }
                "dnd/set" -> ctl.setDnd(String(payload, Charsets.UTF_8).trim().uppercase() in listOf("ON", "1", "TRUE"))
            }
        } catch (e: Exception) {
            log("MQTT command failed: ${e.message}", "normal")
        }
        try { sleep(500) } catch (e: InterruptedException) { }
        publishState()
    }

    fun shutdown() {
        stopping = true
        publish("availability", "offline", true)
        send(MqttCodec.DISCONNECT)
        synchronized(wlock) { try { sock?.close() } catch (e: IOException) { } }
        interrupt()
    }
}
