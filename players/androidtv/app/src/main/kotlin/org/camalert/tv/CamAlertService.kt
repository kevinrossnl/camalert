// CamAlert for Android TV. Copyright (C) 2026 CamAlert developers. GPL v2.
package org.camalert.tv

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.content.pm.ServiceInfo
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import org.camalert.core.Access
import org.camalert.core.Api
import org.camalert.core.Backend
import org.camalert.core.Cameras
import org.camalert.core.Controller
import org.camalert.core.HttpServer
import org.camalert.core.MqttClient
import org.camalert.core.MqttTopics
import org.camalert.core.Obs
import org.camalert.core.PlayerController
import org.camalert.core.PlayerEnv
import org.camalert.core.Present
import org.camalert.core.Tile
import org.camalert.core.Unifi
import org.camalert.core.UnifiPoller
import org.camalert.core.UrlTransport
import org.camalert.core.Urls
import org.camalert.core.Warm

/**
 * The CamAlert service: started at boot and by the app, runs in the foreground (a TV device kills background
 * services) and keeps the HTTP API (port 8099), the MQTT client and the overlay alive.
 */
class CamAlertService : Service(), SharedPreferences.OnSharedPreferenceChangeListener {
    companion object {
        const val PLATFORM = "androidtv"
        const val MODEL = "Android TV"
        @Volatile var instance: CamAlertService? = null

        fun start(ctx: Context) {
            val i = Intent(ctx, CamAlertService::class.java)
            if (Build.VERSION.SDK_INT >= 26) ctx.startForegroundService(i) else ctx.startService(i)
        }
    }

    lateinit var store: Store
    lateinit var tr: Tr
    lateinit var present: Present
    lateinit var overlay: Overlay
    lateinit var controller: PlayerController
    lateinit var unifiLogin: UnifiLogin
    /** UniFi Protect consoles (#72), polled in their own thread every unifi_interval seconds. */
    val unifi = UnifiPoller(UrlTransport(), { m, l -> CamLog.log(m, l) })
    private var unifiThread: Thread? = null
    private val api = Api()
    private var server: HttpServer? = null
    private var serverPort = -1
    private var serverHttps = false
    private var mqtt: MqttClient? = null
    private var mqttKey = ""
    private val main = Handler(Looper.getMainLooper())
    val version: String by lazy {
        try { packageManager.getPackageInfo(packageName, 0).versionName ?: "0" } catch (e: Exception) { "0" }
    }
    val node: String by lazy { nodeId(this) }

    fun settings() = store.values()

    fun nodeName(s: Map<String, Any?> = settings()) = s["mqtt_name"]?.toString()?.trim()?.ifEmpty { null } ?: "CamAlert ${deviceName(this)}"

    fun cameraNames(): List<String> {
        val s = settings()
        val server = Urls.normalizeServer(s["server"]?.toString()) ?: return emptyList()
        val names = Urls.streamsFromJson(String(Net.fetch("$server/api/streams", s["verify_ssl"] != false, 5000), Charsets.UTF_8))
        return Warm.visibleCameras(names, s["ready_cameras"]?.toString())  // #113: helper streams are not cameras
    }

    fun tile(name: String) = controller.tile(name)

    fun mqttConnected() = mqtt?.up == true

    private val env = object : PlayerEnv {
        override fun settings() = this@CamAlertService.settings()
        override fun setSetting(id: String, value: Any?) = store.set(id, value)
        override fun cameraNames() = this@CamAlertService.cameraNames()
        override fun screenOn() = (getSystemService(Context.POWER_SERVICE) as PowerManager).isInteractive
        override fun wake() {
            @Suppress("DEPRECATION")
            val wl = (getSystemService(Context.POWER_SERVICE) as PowerManager).newWakeLock(
                PowerManager.SCREEN_BRIGHT_WAKE_LOCK or PowerManager.ACQUIRE_CAUSES_WAKEUP, "camalert:wake")
            wl.acquire(5000)
        }
        override fun playing() = if ((getSystemService(Context.AUDIO_SERVICE) as AudioManager).isMusicActive) "video" else "none"
        override fun chime() {
            try {
                val tg = ToneGenerator(AudioManager.STREAM_NOTIFICATION, 80)
                tg.startTone(ToneGenerator.TONE_PROP_BEEP2, 400)
                main.postDelayed({ tg.release() }, 1000)
            } catch (e: Exception) {
                CamLog.log("chime failed: $e", "error")
            }
        }
        override fun log(message: String, level: String) = CamLog.log(message, level)
        override fun changed() { mqtt?.let { m -> Thread { m.publishState() }.start() } }
    }

    private val backend = object : Backend {
        override val platform = PLATFORM
        override val version get() = this@CamAlertService.version
        override fun settings() = this@CamAlertService.settings()
        override fun controller(): Controller = this@CamAlertService.controller
        override fun node() = Pair(node, nodeName())
        override fun cameras(): List<Map<String, Any?>> {
            val s = settings()
            val titles = Cameras.parseMap(s["titles"]?.toString())
            return cameraNames().map { n -> mapOf("name" to n, "title" to Cameras.titleFor(n, titles), "snapshot" to true) }
        }
        override fun setWebhook(url: String) = store.set("ha_webhook", url)
        override fun logTail(lines: Int) = CamLog.tail(lines)
        override fun metrics() = controller.metrics(version, PLATFORM)
        override fun statusExtra() = mapOf("mqtt" to mqttConnected())
        override fun log(message: String, level: String) = CamLog.log(message, level)
    }

    private val host = object : Overlay.Host {
        override fun settings() = this@CamAlertService.settings()
        override val present get() = this@CamAlertService.present
        override val tr get() = this@CamAlertService.tr
        override fun show(stream: String, mode: String, priority: String, source: String) {
            Thread { controller.show(stream, null, mode, priority, source, null) }.start()
        }
        override fun neighbour(current: String?, step: Int): Tile? = controller.neighbour(current, step)
        override fun colourKey(camera: String?, colour: String) = sendButton(camera, colour)
        override fun unreachable() { synchronized(controller.stats) { controller.stats.unreachable++ } }
        override fun changed() = env.changed()
        override fun warmPicture(camera: String): ByteArray? = warm.frame(camera)
        override fun protectPicture(camera: String, width: Int): ByteArray? {
            val s = settings()
            protectPictures.configure(unifiLogin.consoles(), s["unifi_cameras"]?.toString(), s["protect_snapshots"] != false)
            return protectPictures(camera, width)
        }
    }

    /** #109: pictures of UniFi Protect cameras through the poller's Protect session (no keyframe wait). */
    private val protectPictures = org.camalert.core.ProtectSnapshots({ c, cam, names, w -> unifi.snapshot(c, cam, names, w) })

    /** #111: ready cameras get a warm MJPEG feed while CamAlert is on and the screen is on. */
    val warm = org.camalert.core.WarmFeeds({ url -> Net.openStream(url, settings()["verify_ssl"] != false) })
    private var warmThread: Thread? = null

    private fun startWarm() {
        warmThread = Thread({
            while (!Thread.currentThread().isInterrupted) {
                try {
                    val s = settings()
                    val on = s["enabled"] != false &&
                        (getSystemService(Context.POWER_SERVICE) as PowerManager).isInteractive
                    warm.update(s["server"]?.toString(), s["ready_cameras"]?.toString(), on)
                } catch (e: Exception) {  // never let it die
                    CamLog.log("keep cameras ready: $e", "error")
                }
                try {
                    Thread.sleep(1000)
                } catch (e: InterruptedException) {
                    break
                }
            }
        }, "camalert-warm-check").apply { isDaemon = true; start() }
    }

    /** A colour key while a camera is on screen -> Home Assistant (MQTT event entity and webhook). */
    fun sendButton(camera: String?, colour: String) {
        val s = settings()
        if (s["ha_buttons"] == false) return
        CamLog.log("button $colour on camera $camera -> Home Assistant")
        Thread {
            mqtt?.publishButton(camera, colour)
            val hook = s["ha_webhook"]?.toString()?.trim() ?: ""
            if (hook.isNotEmpty()) {
                try {
                    val why = Access.urlTarget(hook)  // checked again on use: a name may resolve elsewhere now (#53)
                    if (why != null) throw IllegalArgumentException(why)
                    Net.fetch(hook, true, 5000, MqttTopics.buttonEvent(node, camera, colour).toByteArray())
                } catch (e: Exception) {
                    CamLog.log("button webhook failed: ${e.message}", "error")
                }
            }
        }.start()
    }

    override fun onCreate() {
        super.onCreate()
        instance = this
        store = Store(this)
        store.normalize()
        tr = Tr(this)
        present = Present(tr = tr)
        overlay = Overlay(this, host)
        controller = PlayerController(env, overlay)
        unifiLogin = UnifiLogin(this)
        CamLog.level = settings()["log_level"]?.toString() ?: "normal"
        foreground()
        store.prefs.registerOnSharedPreferenceChangeListener(this)
        CamLog.log("CamAlert $version started (node $node)")
        apply()
        startUnifi()
        startWarm()
    }

    private fun foreground() {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val b = if (Build.VERSION.SDK_INT >= 26) {
            nm.createNotificationChannel(NotificationChannel("camalert", "CamAlert", NotificationManager.IMPORTANCE_MIN))
            Notification.Builder(this, "camalert")
        } else {
            @Suppress("DEPRECATION") Notification.Builder(this).setPriority(Notification.PRIORITY_MIN)
        }
        val open = PendingIntent.getActivity(this, 0, Intent(this, SettingsActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        val port = Urls.validPort(settings()["http_port"], 8099)
        val n = b.setContentTitle("CamAlert").setContentText(getString(R.string.notification_running, port))
            .setSmallIcon(R.drawable.icon).setContentIntent(open).setOngoing(true).build()
        if (Build.VERSION.SDK_INT >= 34) startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        else startForeground(1, n)
    }

    /** Starts or restarts what the settings changed: HTTP server (port), MQTT (broker settings). */
    private fun apply() {
        val s = settings()
        CamLog.level = s["log_level"]?.toString() ?: "normal"
        val port = Urls.validPort(s["http_port"], 8099)
        CamLog.syslog = Obs.parseHostPort(s["log_syslog"]?.toString())
        CamLog.hostname = deviceName(this)
        val wantHttps = s["api_https"] == true
        if (server == null || port != serverPort || wantHttps != serverHttps) {
            server?.stop()
            // api_https (#66): self-signed certificate in the Android KeyStore; without one the API stays on HTTP
            val ssl = if (wantHttps) try { TlsCert.context() } catch (e: Exception) {
                CamLog.log("could not create certificate: $e", "error")
                null
            } else null
            server = try {
                HttpServer(api, backend, port, null, ssl).also { it.start() }
                    .also { CamLog.log("listening on port $port${if (it.https) " (https)" else ""}") }
            } catch (e: Exception) {
                CamLog.log("could not start HTTP API on port $port: $e", "error")
                null
            }
            serverPort = port
            serverHttps = wantHttps
        }
        val key = listOf("mqtt_enabled", "mqtt_host", "mqtt_port", "mqtt_user", "mqtt_password", "mqtt_discovery", "mqtt_name",
            "frigate_enabled", "frigate_prefix").joinToString("|") { "${s[it]}" }
        if (key != mqttKey) {
            mqttKey = key
            mqtt?.let { m -> Thread { m.shutdown() }.start() }
            mqtt = null
            if (s["mqtt_enabled"] == true && !s["mqtt_host"]?.toString().isNullOrBlank()) {
                mqtt = MqttClient(node, ::settings, { controller }, {
                    val titles = Cameras.parseMap(settings()["titles"]?.toString())
                    cameraNames().map { Pair(it, Cameras.titleFor(it, titles)) }
                }, { nodeName() }, MODEL) { m, l -> CamLog.log(m, l) }.also { it.start() }
            }
        }
    }

    override fun onSharedPreferenceChanged(prefs: SharedPreferences?, key: String?) {
        main.removeCallbacks(applyLater)
        main.postDelayed(applyLater, 500)
    }

    private val applyLater = Runnable { apply() }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_STICKY

    override fun onBind(intent: Intent?): IBinder? = null

    /** The UniFi Protect poller thread: the first answer is only the baseline, errors are logged once (#78). */
    private fun startUnifi() {
        unifiThread = Thread({
            while (!Thread.currentThread().isInterrupted) {
                var wait = 5
                try {
                    val s = settings()
                    val labels = Unifi.KIND_LABELS.mapValues { tr(it.value) }
                    unifi.once(s + ("unifi_labels" to labels), unifiLogin.consoles()) { t ->
                        controller.show(t.camera, t.seconds, t.mode, t.priority, t.source, t.label, null)
                    }
                    wait = Unifi.interval(s)
                } catch (e: Exception) {  // never let the poller die silently
                    CamLog.log("UniFi Protect: $e", "error")
                }
                try {
                    Thread.sleep(wait * 1000L)
                } catch (e: InterruptedException) {
                    break
                }
            }
        }, "camalert-unifi").apply { isDaemon = true; start() }
    }

    override fun onDestroy() {
        CamLog.log("CamAlert stopped")
        unifiThread?.interrupt()
        warmThread?.interrupt()
        warm.stop()
        store.prefs.unregisterOnSharedPreferenceChangeListener(this)
        server?.stop()
        mqtt?.let { m -> Thread { m.shutdown() }.start() }
        overlay.hide()
        instance = null
        super.onDestroy()
    }
}

/** Starts the service after a boot or an app update (Fire OS: only after the app was opened once). */
class BootReceiver : android.content.BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED || intent.action == Intent.ACTION_MY_PACKAGE_REPLACED) {
            try {
                CamAlertService.start(context)
            } catch (e: Exception) {
                CamLog.log("start at boot failed: $e", "error")
            }
        }
    }
}
