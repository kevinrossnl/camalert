// CamAlert for Android TV. Copyright (C) 2026 CamAlert developers. GPL v2.
package org.camalert.tv

import android.annotation.SuppressLint
import android.content.Context
import android.content.SharedPreferences
import android.provider.Settings
import android.util.Log
import android.view.KeyEvent
import org.camalert.core.CoreData
import org.camalert.core.Obs
import org.camalert.core.Schema
import org.camalert.core.UnifiConsole
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.security.SecureRandom
import java.security.cert.X509Certificate
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager

/** The log: logcat (tag CamAlert) plus the last lines in memory for /camalert/log, and optionally a remote syslog
 *  (log_syslog, RFC 5424 over UDP, #66); everything redacted. */
object CamLog {
    private val lines = ArrayDeque<String>()
    @Volatile var level = "normal"
    @Volatile var syslog: Pair<String, Int>? = null
    @Volatile var hostname = "-"
    // UDP is sent from its own thread: log() is also called on the main thread (no network there on Android)
    private val sender by lazy { java.util.concurrent.Executors.newSingleThreadExecutor { r -> Thread(r, "camalert-syslog").apply { isDaemon = true } } }
    private var socket: java.net.DatagramSocket? = null

    fun log(message: String, lvl: String = "normal") {
        if (!Obs.logAllowed(level, lvl)) return
        val text = Obs.redact(message)
        syslog?.let { target -> send(target, Obs.syslogLine(text, lvl, hostname, System.currentTimeMillis() / 1000.0)) }
        val stamp = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.ROOT).format(Date())
        synchronized(lines) {
            lines.addLast("$stamp [$lvl] $text")
            while (lines.size > 2000) lines.removeFirst()
        }
        if (lvl == "error") Log.e("CamAlert", text) else Log.i("CamAlert", text)
    }

    fun tail(n: Int): List<String> = synchronized(lines) { lines.toList().takeLast(n) }

    private fun send(target: Pair<String, Int>, line: String) {
        try {
            sender.execute {
                try {
                    val s = socket ?: java.net.DatagramSocket().also { socket = it }
                    val data = line.toByteArray(Charsets.UTF_8)
                    s.send(java.net.DatagramPacket(data, data.size, java.net.InetAddress.getByName(target.first), target.second))
                } catch (e: Exception) {
                    // like the other players: a syslog that is not reachable never stops CamAlert
                }
            }
        } catch (e: java.util.concurrent.RejectedExecutionException) {
        }
    }
}

/**
 * api_https (#66): a self-signed certificate (CN=CamAlert, 10 years) of this device in the Android KeyStore; the
 * private key never leaves the KeyStore. Callers must turn off certificate checking (as on the other players).
 */
object TlsCert {
    private const val ALIAS = "camalert-api"

    fun context(): javax.net.ssl.SSLContext {
        val ks = java.security.KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        if (!ks.containsAlias(ALIAS)) {
            val start = Date()
            val end = Date(start.time + 3650L * 24 * 3600 * 1000)
            val spec = android.security.keystore.KeyGenParameterSpec.Builder(ALIAS,
                android.security.keystore.KeyProperties.PURPOSE_SIGN or android.security.keystore.KeyProperties.PURPOSE_DECRYPT)
                .setCertificateSubject(javax.security.auth.x500.X500Principal("CN=CamAlert"))
                .setCertificateSerialNumber(java.math.BigInteger.valueOf(start.time))
                .setCertificateNotBefore(start)
                .setCertificateNotAfter(end)
                .setKeySize(2048)
                .setDigests(android.security.keystore.KeyProperties.DIGEST_NONE, android.security.keystore.KeyProperties.DIGEST_SHA256,
                    android.security.keystore.KeyProperties.DIGEST_SHA384, android.security.keystore.KeyProperties.DIGEST_SHA512)
                .setSignaturePaddings(android.security.keystore.KeyProperties.SIGNATURE_PADDING_RSA_PKCS1,
                    android.security.keystore.KeyProperties.SIGNATURE_PADDING_RSA_PSS)
                .setEncryptionPaddings(android.security.keystore.KeyProperties.ENCRYPTION_PADDING_RSA_PKCS1)
                .build()
            java.security.KeyPairGenerator.getInstance(android.security.keystore.KeyProperties.KEY_ALGORITHM_RSA, "AndroidKeyStore")
                .apply { initialize(spec) }.generateKeyPair()
        }
        val kmf = javax.net.ssl.KeyManagerFactory.getInstance(javax.net.ssl.KeyManagerFactory.getDefaultAlgorithm())
        kmf.init(ks, null)
        return javax.net.ssl.SSLContext.getInstance("TLS").apply { init(kmf.keyManagers, null, null) }
    }
}

/** The settings (schema ids), stored in the default SharedPreferences; always read through Schema.validate. */
class Store(private val ctx: Context) {
    val prefs: SharedPreferences = ctx.getSharedPreferences(ctx.packageName + "_preferences", Context.MODE_PRIVATE)

    fun values(): Map<String, Any?> = Schema.validate(prefs.all).first

    fun set(id: String, value: Any?) {
        val e = prefs.edit()
        when (value) {
            is Boolean -> e.putBoolean(id, value)
            null -> e.remove(id)
            else -> e.putString(id, value.toString())
        }
        e.apply()
    }

    /** Stored types must match the preference widgets: booleans for switches, strings for everything else. */
    fun normalize() {
        val e = prefs.edit()
        for ((k, v) in prefs.all) {
            val s = CoreData.load().byId[k] ?: continue
            if (s.type == "bool" && v !is Boolean) e.putBoolean(k, s.coerce(v) as Boolean)
            if (s.type != "bool" && v !is String) e.putString(k, v.toString())
        }
        e.apply()
    }
}

/**
 * The UniFi Protect console login (#72): address, View Only user and password in their own private preferences
 * file, never in the settings, the log, /camalert/status or a backup of the settings (like the devices file of the
 * other players).
 */
class UnifiLogin(ctx: Context) {
    val prefs: SharedPreferences = ctx.getSharedPreferences(ctx.packageName + "_unifi", Context.MODE_PRIVATE)

    fun consoles(): List<UnifiConsole> = listOfNotNull(UnifiConsole.of("protect", prefs.getString("address", null),
        prefs.getString("user", null), prefs.getString("password", null)))
}

/** tr(msgid) for core texts and settings labels: generated resource t_<crc32> (tools/i18n/i18n.py). */
class Tr(private val ctx: Context) : (String) -> String {
    private val cache = HashMap<String, String>()

    @SuppressLint("DiscouragedApi")
    override fun invoke(msgid: String): String = synchronized(cache) {
        cache.getOrPut(msgid) {
            val crc = java.util.zip.CRC32().apply { update(msgid.toByteArray(Charsets.UTF_8)) }.value
            val id = ctx.resources.getIdentifier(String.format(Locale.ROOT, "t_%08x", crc), "string", ctx.packageName)
            if (id == 0) msgid else ctx.getString(id).ifEmpty { msgid }
        }
    }

    @SuppressLint("DiscouragedApi")
    fun named(name: String, fallback: String): String {
        val id = ctx.resources.getIdentifier(name.replace('.', '_'), "string", ctx.packageName)
        return if (id == 0) fallback else ctx.getString(id)
    }
}

object Net {
    private val trustAll: SSLContext by lazy {
        SSLContext.getInstance("TLS").apply {
            init(null, arrayOf<TrustManager>(object : X509TrustManager {
                @SuppressLint("TrustAllX509TrustManager")
                override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) {}
                @SuppressLint("TrustAllX509TrustManager")
                override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {}
                override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
            }), SecureRandom())
        }
    }

    /** GET (or POST with body) -> bytes; IOException on HTTP errors. verify=false accepts self-signed certificates
     *  (setting *Check certificates*, only in your own network). */
    fun fetch(url: String, verify: Boolean = true, timeoutMs: Int = 5000, body: ByteArray? = null, max: Int = 8 shl 20): ByteArray {
        val c = URL(url).openConnection() as HttpURLConnection
        if (!verify && c is HttpsURLConnection) {
            c.sslSocketFactory = trustAll.socketFactory
            c.setHostnameVerifier { _, _ -> true }
        }
        c.connectTimeout = timeoutMs
        c.readTimeout = timeoutMs
        c.setRequestProperty("User-Agent", "CamAlert-AndroidTV")
        try {
            if (body != null) {
                c.requestMethod = "POST"
                c.doOutput = true
                c.setRequestProperty("Content-Type", "application/json")
                c.outputStream.use { it.write(body) }
            }
            val code = c.responseCode
            if (code !in 200..299) throw java.io.IOException("HTTP $code")
            c.inputStream.use { inp ->
                val out = ByteArrayOutputStream()
                val buf = ByteArray(16384)
                while (true) {
                    val n = inp.read(buf)
                    if (n < 0) break
                    out.write(buf, 0, n)
                    if (out.size() > max) throw java.io.IOException("answer too large")
                }
                return out.toByteArray()
            }
        } finally {
            c.disconnect()
        }
    }
}

/** Android key codes -> the key names of the core key map (keymap.py, player androidtv). */
object KeyNames {
    fun of(code: Int): String? = when (code) {
        KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER, KeyEvent.KEYCODE_NUMPAD_ENTER, KeyEvent.KEYCODE_BUTTON_A -> "OK"
        KeyEvent.KEYCODE_BACK, KeyEvent.KEYCODE_ESCAPE, KeyEvent.KEYCODE_BUTTON_B -> "BACK"
        KeyEvent.KEYCODE_DPAD_LEFT -> "LEFT"
        KeyEvent.KEYCODE_DPAD_RIGHT -> "RIGHT"
        KeyEvent.KEYCODE_DPAD_UP -> "UP"
        KeyEvent.KEYCODE_DPAD_DOWN -> "DOWN"
        KeyEvent.KEYCODE_MENU -> "MENU"
        KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE -> "PLAY_PAUSE"
        KeyEvent.KEYCODE_MEDIA_PLAY -> "PLAY"
        KeyEvent.KEYCODE_MEDIA_PAUSE -> "PAUSE"
        KeyEvent.KEYCODE_MEDIA_STOP -> "STOP"
        KeyEvent.KEYCODE_MEDIA_FAST_FORWARD -> "FAST_FORWARD"
        KeyEvent.KEYCODE_MEDIA_REWIND -> "REWIND"
        KeyEvent.KEYCODE_CHANNEL_UP -> "CHANNEL_UP"
        KeyEvent.KEYCODE_CHANNEL_DOWN -> "CHANNEL_DOWN"
        KeyEvent.KEYCODE_PROG_RED -> "RED"
        KeyEvent.KEYCODE_PROG_GREEN -> "GREEN"
        KeyEvent.KEYCODE_PROG_YELLOW -> "YELLOW"
        KeyEvent.KEYCODE_PROG_BLUE -> "BLUE"
        KeyEvent.KEYCODE_VOLUME_UP -> "VOLUME_UP"
        KeyEvent.KEYCODE_VOLUME_DOWN -> "VOLUME_DOWN"
        KeyEvent.KEYCODE_VOLUME_MUTE -> "MUTE"
        else -> null
    }

    val COLOURS = mapOf("RED" to "red", "GREEN" to "green", "YELLOW" to "yellow", "BLUE" to "blue")
}

/** Stable id of this player: from ANDROID_ID (MAC addresses are hidden since Android 6). */
@SuppressLint("HardwareIds")
fun nodeId(ctx: Context): String {
    val id = Settings.Secure.getString(ctx.contentResolver, Settings.Secure.ANDROID_ID) ?: "0"
    return ("atv" + id.lowercase().filter { it.isLetterOrDigit() }).take(15)
}

fun deviceName(ctx: Context): String =
    (try { Settings.Global.getString(ctx.contentResolver, Settings.Global.DEVICE_NAME) } catch (e: Exception) { null })
        ?.takeIf { it.isNotBlank() } ?: android.os.Build.MODEL
