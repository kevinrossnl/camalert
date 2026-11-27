package org.camalert.core

import java.io.InputStream

/**
 * Keep cameras ready (#111, core warm.py): a warm MJPEG feed per chosen camera while the player is on. The player
 * keeps go2rtc's stream.mjpeg of the camera open and keeps only the last picture; in standby / screen off /
 * CamAlert off the connection is closed and go2rtc stops transcoding by itself.
 */
object Warm {
    const val STALE_SECONDS = 5.0
    val RETRY = listOf(1, 2, 5, 10, 30)
    const val MAX_FRAME = 4 * 1024 * 1024

    /** 'front_door=front_door_jpeg|garden' -> {front_door: front_door_jpeg, garden: garden}; empty = {}. */
    fun parseReady(text: String?): Map<String, String> {
        val out = LinkedHashMap<String, String>()
        for (raw in (text ?: "").replace(",", "|").split("|")) {
            val part = raw.trim()
            if (part.isEmpty()) continue
            val i = part.indexOf('=')
            val cam = (if (i < 0) part else part.substring(0, i)).trim()
            val stream = (if (i < 0) cam else part.substring(i + 1)).trim()
            if (cam.isNotEmpty() && stream.isNotEmpty()) out[cam] = stream
        }
        return out
    }

    fun mjpegUrl(server: String?, stream: String?): String? {
        val base = Urls.normalizeServer(server) ?: return null
        if (stream.isNullOrEmpty()) return null
        return "$base/api/stream.mjpeg?src=" + Urls.quote(stream)
    }
}

/** Splits go2rtc's multipart MJPEG stream (--frame parts with Content-Length) into pictures. */
class MjpegParser {
    private var buf = ByteArray(0)

    private fun indexOf(pat: ByteArray, from: Int): Int {
        outer@ for (i in maxOf(0, from)..buf.size - pat.size) {
            for (j in pat.indices) if (buf[i + j] != pat[j]) continue@outer
            return i
        }
        return -1
    }

    /** Adds bytes; returns the complete pictures (oldest first). Throws IllegalStateException on garbage. */
    fun feed(data: ByteArray, n: Int = data.size): List<ByteArray> {
        buf += data.copyOf(n)
        val out = ArrayList<ByteArray>()
        while (true) {
            val i = indexOf(DASHES, 0)
            if (i < 0) {
                check(buf.size <= Warm.MAX_FRAME) { "no MJPEG boundary" }
                return out
            }
            val headEnd = indexOf(CRLF2, i)
            if (headEnd < 0) {
                check(buf.size - i <= 8192) { "MJPEG part header too long" }
                buf = buf.copyOfRange(i, buf.size)
                return out
            }
            var length: Int? = null
            for (h in String(buf, i, headEnd - i, Charsets.ISO_8859_1).split("\r\n").drop(1)) {
                val k = h.substringBefore(':').trim()
                if (k.equals("content-length", ignoreCase = true)) {
                    length = h.substringAfter(':').trim().toIntOrNull() ?: throw IllegalStateException("bad Content-Length")
                }
            }
            val start = headEnd + 4
            val end: Int
            if (length == null) {
                val nxt = indexOf(BOUNDARY, start)
                if (nxt < 0) {
                    check(buf.size - start <= Warm.MAX_FRAME) { "MJPEG part too large" }
                    buf = buf.copyOfRange(i, buf.size)
                    return out
                }
                end = nxt
            } else {
                check(length <= Warm.MAX_FRAME) { "MJPEG part too large" }
                end = start + length
                if (buf.size < end) {
                    buf = buf.copyOfRange(i, buf.size)
                    return out
                }
            }
            out.add(buf.copyOfRange(start, end))
            buf = buf.copyOfRange(end, buf.size)
        }
    }

    companion object {
        private val DASHES = "--".toByteArray()
        private val CRLF2 = "\r\n\r\n".toByteArray()
        private val BOUNDARY = "\r\n--".toByteArray()
    }
}

/**
 * The warm feeds of the Android TV player. open(url) opens the HTTP stream (the app's own network: certificate
 * setting). update() is called at least once a second; frame(camera) gives the last picture when it is fresh.
 */
class WarmFeeds(private val open: (String) -> InputStream,
                private val clock: () -> Double = { System.currentTimeMillis() / 1000.0 },
                private val sleep: (Long) -> Unit = { Thread.sleep(it) },
                private val start: (Runnable) -> Unit = { r -> Thread(r, "camalert-warm").apply { isDaemon = true; start() } },
                private val chunk: Int = 65536) {
    private val lock = Object()
    private var urls: Map<String, String> = emptyMap()
    var active = false
        private set
    private var gen = 0
    private val frames = HashMap<String, Pair<ByteArray, Double>>()
    private val streams = HashMap<String, InputStream>()
    private val errors = HashMap<String, String>()
    val running: MutableSet<String> = java.util.Collections.synchronizedSet(HashSet())

    fun update(server: String?, readyText: String?, on: Boolean) {
        val u = LinkedHashMap<String, String>()
        for ((cam, stream) in Warm.parseReady(readyText).toSortedMap()) Warm.mjpegUrl(server, stream)?.let { u[cam] = it }
        val act = on && u.isNotEmpty()
        val old: List<InputStream>
        val g: Int
        synchronized(lock) {
            if (u == urls && act == active) return
            urls = u; active = act
            gen++; g = gen
            old = streams.values.toList()
            streams.clear()
            if (!act) { frames.clear(); errors.clear() }
        }
        old.forEach { close(it) }
        if (act) for ((cam, url) in u) start(Runnable { run(cam, url, g) })
    }

    fun stop() = update("", "", false)

    private fun current(g: Int) = synchronized(lock) { active && g == gen }

    fun run(cam: String, url: String, g: Int) {
        running.add(cam)
        var fails = 0
        try {
            while (current(g)) {
                var s: InputStream? = null
                try {
                    s = open(url)
                    synchronized(lock) {
                        if (!(active && g == gen)) { close(s); return }
                        streams[cam] = s
                    }
                    read(cam, s, g)
                    fails = 0
                } catch (e: Exception) {
                    synchronized(lock) { if (g == gen) errors[cam] = e.javaClass.simpleName }
                } finally {
                    s?.let { close(it); synchronized(lock) { if (streams[cam] === it) streams.remove(cam) } }
                }
                if (!current(g)) return
                val wait = Warm.RETRY[minOf(fails, Warm.RETRY.size - 1)]
                fails++
                val end = clock() + wait
                while (current(g) && clock() < end) sleep(200)
            }
        } finally {
            running.remove(cam)
        }
    }

    private fun read(cam: String, s: InputStream, g: Int) {
        val parser = MjpegParser()
        val buf = ByteArray(chunk)
        while (current(g)) {
            val n = s.read(buf)
            if (n < 0) throw java.io.IOException("stream ended")
            for (pic in parser.feed(buf, n)) synchronized(lock) {
                if (g == gen) { frames[cam] = Pair(pic, clock()); errors.remove(cam) }
            }
        }
    }

    /** The last picture of a ready camera when it is at most maxAge seconds old, else null. */
    fun frame(camera: String?, maxAge: Double = Warm.STALE_SECONDS): ByteArray? {
        val f = synchronized(lock) { if (active) frames[camera] else null } ?: return null
        return if (clock() - f.second > maxAge) null else f.first
    }

    /** Diagnostics lines: per ready camera its last picture or that it is not connected. */
    fun lines(tr: (String) -> String): List<Pair<Boolean?, String>> {
        val cams: List<String>
        val fr: Map<String, Pair<ByteArray, Double>>
        val er: Map<String, String>
        val on: Boolean
        synchronized(lock) { cams = urls.keys.sorted(); fr = HashMap(frames); er = HashMap(errors); on = active }
        val out = ArrayList<Pair<Boolean?, String>>()
        for (cam in cams) {
            val p = fr[cam]
            if (!on) out.add(Pair(null, tr("Ready: %s (not while the player is off)").replace("%s", cam)))
            else if (p != null && clock() - p.second <= Warm.STALE_SECONDS)
                out.add(Pair(true, tr("Ready: %s (last picture %d s ago)").replace("%s", cam)
                    .replace("%d", (clock() - p.second).toInt().toString())))
            else out.add(Pair(false, tr("Ready: %s not connected").replace("%s", cam) + (er[cam]?.let { " ($it)" } ?: "")))
        }
        return out
    }

    private fun close(s: InputStream) {
        try { s.close() } catch (e: Exception) {}
    }
}
