// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

import org.junit.AfterClass
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.BeforeClass
import org.junit.Test
import java.io.IOException
import java.net.InetAddress
import java.net.ServerSocket
import java.net.Socket
import java.util.Collections

/**
 * The MQTT client against an in-process broker, checked against the shared MQTT contract (tests/contract/
 * mqtt_table.py, exported to contract/mqtt.json): topics, retain flags, payloads, last will, commands and Home
 * Assistant discovery identical to the Enigma2 and Kodi players apart from the device model.
 */
@Suppress("UNCHECKED_CAST")
class MqttContractTest {
    class Msg(val topic: String, val payload: ByteArray, val retain: Boolean)

    /** Minimal broker for one client (the Kotlin twin of tests/fakes/broker.py). */
    class Broker : Thread("fake-broker") {
        val server = ServerSocket(0, 5, InetAddress.getLoopbackAddress())
        val messages: MutableList<Msg> = Collections.synchronizedList(ArrayList())
        val subscriptions: MutableList<String> = Collections.synchronizedList(ArrayList())
        val connect = HashMap<String, Any?>()
        @Volatile var client: Socket? = null

        init { isDaemon = true }

        private fun str(b: ByteArray, i: Int): Pair<ByteArray, Int> {
            val n = ((b[i].toInt() and 0xff) shl 8) or (b[i + 1].toInt() and 0xff)
            return Pair(b.copyOfRange(i + 2, i + 2 + n), i + 2 + n)
        }

        override fun run() {
            val s = try { server.accept() } catch (e: IOException) { return }
            client = s
            val inp = s.getInputStream()
            var buf = ByteArray(0)
            val chunk = ByteArray(4096)
            try {
                while (true) {
                    val n = inp.read(chunk)
                    if (n < 0) break
                    val (packets, rest) = MqttCodec.split(buf + chunk.copyOf(n))
                    buf = rest
                    for (p in packets) handle(s, p)
                }
            } catch (e: IOException) {
            }
        }

        private fun handle(s: Socket, p: MqttCodec.Packet) {
            val b = p.body
            when (p.type) {
                1 -> {
                    var (_, i) = str(b, 0)
                    val flags = b[i + 1].toInt() and 0xff
                    i += 4
                    val (cid, j) = str(b, i); i = j
                    connect["client_id"] = String(cid)
                    if (flags and 0x04 != 0) {
                        val (wt, k) = str(b, i); val (wp, l) = str(b, k); i = l
                        connect["will_topic"] = String(wt); connect["will_payload"] = String(wp)
                        connect["will_retain"] = flags and 0x20 != 0
                    }
                    send(s, byteArrayOf(0x20, 2, 0, 0))
                }
                3 -> {
                    val (topic, payload) = MqttCodec.parsePublish(p.flags, b)
                    messages.add(Msg(topic, payload, p.flags and 1 == 1))
                }
                8 -> {
                    var i = 2
                    while (i < b.size) {
                        val (t, j) = str(b, i); subscriptions.add(String(t)); i = j + 1
                    }
                    send(s, byteArrayOf(0x90.toByte(), 3, b[0], b[1], 0))
                }
                12 -> send(s, byteArrayOf(0xd0.toByte(), 0))
            }
        }

        @Synchronized
        fun send(s: Socket, data: ByteArray) { s.getOutputStream().write(data); s.getOutputStream().flush() }

        fun publish(topic: String, payload: String) = send(client!!, MqttCodec.publish(topic, payload))

        fun waitFor(timeout: Long = 5000, pred: () -> Boolean): Boolean {
            val end = System.currentTimeMillis() + timeout
            while (System.currentTimeMillis() < end) {
                if (pred()) return true
                sleep(10)
            }
            return false
        }
    }

    companion object {
        val T = Exported.mqtt
        val node = T["node"] as String
        val KNOWN: Map<String, String> = emptyMap()  // command name -> issue
        lateinit var broker: Broker
        lateinit var ctl: RecordingController
        val calls = HashMap<String, List<Any?>?>()
        lateinit var messages: List<Msg>

        fun topic(t: String) = t.replace("{node}", node)

        @BeforeClass @JvmStatic
        fun run() {
            broker = Broker().apply { start() }
            ctl = RecordingController()
            val settings = HashMap(Schema.validate(emptyMap()).first).apply {
                putAll(T["settings"] as Map<String, Any?>)
                put("mqtt_host", "127.0.0.1"); put("mqtt_port", broker.server.localPort); put("enabled", true)
            }
            val cams = (T["cameras"] as List<Map<String, String>>).map { Pair(it.getValue("name"), it.getValue("title")) }
            val client = MqttClient(node, { settings }, { ctl }, { cams }, { T["name"] as String }, "Android TV")
            client.start()
            assertTrue(broker.waitFor { broker.subscriptions.isNotEmpty() })
            assertTrue(broker.waitFor { broker.messages.any { it.topic.endsWith("/config") } })
            for (c in T["commands"] as List<Map<String, Any?>>) {
                val before = ctl.calls.size
                broker.publish(topic(c["topic"] as String), c["payload"] as String)
                broker.waitFor { ctl.calls.size > before }
                calls[c["name"] as String] = if (ctl.calls.size > before) ctl.calls[before] else null
            }
            client.publishButton("garden", "red")
            assertTrue(broker.waitFor { broker.messages.any { it.topic.endsWith("/button") } })
            broker.waitFor { broker.messages.count { it.topic.endsWith("/state") } >= 3 }
            client.shutdown()
            broker.waitFor { broker.messages.any { it.topic.endsWith("/availability") && String(it.payload) == "offline" } }
            messages = broker.messages.toList()
        }

        @AfterClass @JvmStatic
        fun stop() { broker.server.close() }
    }

    @Test
    fun subscriptions() {
        assertEquals((T["subscribed"] as List<String>).map(::topic).sorted(), broker.subscriptions.sorted())
    }

    @Test
    fun lastWillAndClientId() {
        val w = T["last_will"] as Map<String, Any?>
        assertEquals(topic(w["topic"] as String), broker.connect["will_topic"])
        assertEquals(w["payload"], broker.connect["will_payload"])
        assertEquals(w["retain"], broker.connect["will_retain"])
        assertEquals(topic(T["client_id"] as String), broker.connect["client_id"])
    }

    private fun matches(pattern: String, t: String): Boolean {
        val p = pattern.split("/")
        val x = t.split("/")
        for ((i, part) in p.withIndex()) {
            if (part == "#") return true
            if (i >= x.size || (part != "+" && part != x[i])) return false
        }
        return p.size == x.size
    }

    private fun check(c: Map<String, Any?>, payload: ByteArray): Boolean = when (c["kind"]) {
        "one_of" -> String(payload) in (c["values"] as List<String>)
        "json_keys" -> (Json.parse(String(payload)) as Map<String, Any?>).keys.containsAll(c["keys"] as List<String>)
        else -> payload.isNotEmpty()
    }

    @Test
    fun publishedTopicsMatchTheTable() {
        val table = T["published"] as List<Map<String, Any?>>
        assertTrue(messages.isNotEmpty())
        for (m in messages) {
            val row = table.firstOrNull { matches(topic(it["topic"] as String), m.topic) }
            assertTrue("${m.topic} is not in the MQTT table", row != null)
            assertEquals("retain of ${m.topic}", row!!["retain"], m.retain)
            assertTrue("${m.topic} payload ${String(m.payload)}", check(row["check"] as Map<String, Any?>, m.payload))
        }
        for (row in table) assertTrue("never published ${row["topic"]}", messages.any { matches(topic(row["topic"] as String), it.topic) })
    }

    @Test
    fun commands() {
        val unexpected = ArrayList<String>()
        val stale = ArrayList<String>()
        for (c in T["commands"] as List<Map<String, Any?>>) {
            val name = c["name"] as String
            val differs = Json.write(calls[name]) != Json.write(c["call"])
            if (differs && name !in KNOWN) unexpected.add("$name: ${Json.write(calls[name])}, expected ${Json.write(c["call"])}")
            else if (!differs && name in KNOWN) stale.add(name)
        }
        assertEquals(emptyList<String>(), unexpected)
        assertEquals("fixed: remove from KNOWN", emptyList<String>(), stale)
    }

    @Test
    fun discoveryIsTheSameAsOnEveryPlayer() {
        val ours = LinkedHashMap<String, Map<String, Any?>>()
        for (m in messages.filter { it.topic.startsWith("homeassistant/") }) {
            val d = Json.parse(String(m.payload)) as MutableMap<String, Any?>
            val device = (d["device"] as Map<String, Any?>).toMutableMap()
            assertEquals("Android TV", device.remove("model"))
            d["device"] = device
            ours[m.topic] = d
        }
        val want = (T["discovery"] as List<Map<String, Any?>>).associate { it["topic"] as String to it["payload"] }
        assertEquals(Json.write(want, true), Json.write(ours, true))
    }
}
