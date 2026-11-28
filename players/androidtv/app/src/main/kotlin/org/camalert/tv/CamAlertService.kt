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
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.media.MediaPlayer
import android.media.ToneGenerator
import android.speech.tts.TextToSpeech
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
import org.camalert.core.Discovery
import org.camalert.core.GoServer
import org.camalert.core.HttpServer
import org.camalert.core.MqttClient
import org.camalert.core.Servers
import org.camalert.core.MqttTopics
import org.camalert.core.Obs
import org.camalert.core.PlayerController
import org.camalert.core.PlayerEnv
import org.camalert.core.SelfUpdate
import org.camalert.core.Speech
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
    override fun attachBaseContext(base: android.content.Context) = super.attachBaseContext(Lang.wrap(base))  // #10

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
    /** Camera devices (#66): camera control (ONVIF, Foscam) and Foscam alarms, own private file. */
    lateinit var cameraDevices: CameraDevices
    lateinit var directCameras: DirectCameraList  // direct mode (#124)
    private val deviceClient = org.camalert.core.DeviceClient(UrlTransport(4000))
    private val foscam = org.camalert.core.FoscamPoller(deviceClient) { m, l -> CamLog.log(m, l) }
    private var foscamThread: Thread? = null
    /** UniFi Protect consoles (#72), polled in their own thread every unifi_interval seconds. */
    val unifi = UnifiPoller(UrlTransport(), { m, l -> CamLog.log(m, l) })
    private var unifiThread: Thread? = null
    private val api = Api()
    private var server: HttpServer? = null
    private var serverPort = -1
    private var serverHttps = false
    private var mqtt: MqttClient? = null
    private var mqttKey = ""
    private var nsdListener: NsdManager.RegistrationListener? = null
    private var nsdKey: String? = null
    private val main = Handler(Looper.getMainLooper())
    val version: String by lazy {
        try { packageManager.getPackageInfo(packageName, 0).versionName ?: "0" } catch (e: Exception) { "0" }
    }
    val node: String by lazy { nodeId(this) }

    fun settings() = store.values()

    fun nodeName(s: Map<String, Any?> = settings()) = s["mqtt_name"]?.toString()?.trim()?.ifEmpty { null } ?: "CamAlert ${deviceName(this)}"

    @Volatile var composites: Set<String> = emptySet()  // own mosaic streams of the last camera list (#125)
    @Volatile var serverMap: Map<String, Pair<String, String>> = emptyMap()  // #15: camera -> (go2rtc server, stream)

    fun cameraNames(): List<String> {
        val s = settings()
        if (s["source"]?.toString() == "direct") {  // #124: the camera list, no go2rtc
            composites = emptySet()
            return directCameras.cameras().map { it.name }
        }
        val servers = Servers.serverList(s["server"]?.toString(), s["more_servers"]?.toString())
        if (servers.isEmpty()) return emptyList()
        val per = ArrayList<Triple<GoServer, List<String>, Set<String>>>()
        var error: Exception? = null
        for (srv in servers) {  // #15: every server on its own; one that does not answer only drops its own cameras
            try {
                val (names, comp) = Urls.streamInfoFromJson(String(Net.fetch("${srv.url}/api/streams", s["verify_ssl"] != false, 5000), Charsets.UTF_8))
                per.add(Triple(srv, names, comp))
            } catch (e: Exception) {
                if (servers.size == 1) throw e
                CamLog.log("go2rtc server ${srv.url} not reachable: ${e.message}")
                error = e
            }
        }
        if (per.isEmpty() && error != null) throw error
        val r = Servers.combine(per)
        composites = r.composites
        serverMap = r.mapping
        return Warm.visibleCameras(r.names, s["ready_cameras"]?.toString())  // #113: helper streams are not cameras
    }

    fun tile(name: String) = controller.tile(name)

    fun mqttConnected() = mqtt?.up == true

    private val env = object : PlayerEnv {
        override fun settings() = this@CamAlertService.settings()
        override fun setSetting(id: String, value: Any?) = store.set(id, value)
        override fun cameraNames() = this@CamAlertService.cameraNames()
        override fun compositeStreams() = this@CamAlertService.composites
        override fun serverMap() = this@CamAlertService.serverMap
        override fun directCameras() = this@CamAlertService.directCameras.cameras()
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
        override fun hasPtz(name: String) = name in cameraDevices.cameras()
        override fun ptzMove(move: String, name: String): Boolean {
            val dev = cameraDevices.cameras()[name] ?: return false
            return try {
                deviceClient.ptz(dev, move)
                true
            } catch (e: org.camalert.core.DeviceError) {
                CamLog.log("camera control $name: ${e.message}", "error")
                false
            }
        }
    }

    private val backend = object : Backend {
        override val platform = PLATFORM
        override val version get() = this@CamAlertService.version
        override fun settings() = this@CamAlertService.settings()
        override fun controller(): Controller = this@CamAlertService.controller
        override fun node() = Pair(node, nodeName())
        override fun speak(url: String?, text: String?, priority: String): Boolean = this@CamAlertService.speak(url, text)
        override fun cameras(): List<Map<String, Any?>> {
            val s = settings()
            if (s["source"]?.toString() == "direct")  // #124: title and snapshot from the camera list
                return directCameras.cameras().map { c -> mapOf("name" to c.name, "title" to c.title, "snapshot" to (c.snapshot != null)) }
            val titles = Cameras.parseMap(s["titles"]?.toString())
            return cameraNames().map { n -> mapOf("name" to n, "title" to Cameras.titleFor(n, titles), "snapshot" to true) }
        }
        override fun setWebhook(url: String, secret: String) {
            store.set("ha_webhook", url)
            store.set("ha_webhook_secret", secret)  // signs the colour keys (#82)
        }
        override fun setDisplay(key: String, value: String) = store.set(key, value)  // window position / size (#84)
        override fun setSetup(server: String, camera: String?) {  // go2rtc address from Home Assistant (#122)
            store.set("server", server)
            if (camera != null) store.set("camera", camera)
            val text = tr(present.data.setupReceived)
            Handler(Looper.getMainLooper()).post {
                android.widget.Toast.makeText(this@CamAlertService, text, android.widget.Toast.LENGTH_LONG).show()
            }
        }
        override fun logTail(lines: Int) = CamLog.tail(lines)
        override fun metrics() = controller.metrics(version, PLATFORM)
        override fun statusExtra() = mapOf("mqtt" to mqttConnected())
        override fun updateStatus() = updateState.asStatus()
        override fun startUpdate(version: String) = this@CamAlertService.startUpdate(version)
        override fun log(message: String, level: String) = CamLog.log(message, level)
    }

    // --- update from Home Assistant (#126) -------------------------------------------------------------------------
    private val updateState = SelfUpdate.UpdateState()

    /** Downloads the release APK from the fixed GitHub URL, checks it against SHA256SUMS and opens the system
     *  installer; someone confirms on the TV (Android never lets an app update itself silently). */
    fun startUpdate(version: String) {
        updateState.set("downloading", version)
        CamLog.log("update to $version: downloading")
        Thread({
            try {
                val (name, data) = SelfUpdate.fetch(PLATFORM, version) { url ->
                    Net.fetch(url, true, 60000, max = SelfUpdate.MAX_BYTES + 1)
                }
                val dir = UpdateFileProvider.dir(cacheDir).apply { mkdirs() }
                dir.listFiles()?.forEach { it.delete() }
                val file = java.io.File(dir, name)
                file.writeBytes(data)
                main.post { openInstaller(file, version) }
            } catch (e: Exception) {
                updateFailed(e.message ?: e.toString())
            }
        }, "camalert-update").start()
    }

    private fun updateFailed(why: String) {
        updateState.set("failed", error = why.take(200))
        CamLog.log("update failed: $why", "error")
    }

    private fun openInstaller(file: java.io.File, version: String) {
        if (Build.VERSION.SDK_INT >= 26 && !packageManager.canRequestPackageInstalls()) {
            // Android 8+: the user allows CamAlert to install apps once, then starts the update again
            startActivity(Intent(android.provider.Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                android.net.Uri.parse("package:$packageName")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            updateFailed("allow CamAlert to install apps on the TV (opened there), then install again")
            return
        }
        updateState.set("waiting", version)  // until someone confirms in the installer on the TV
        CamLog.log("update to $version: waiting for confirmation on the TV")
        try {
            startActivity(Intent(Intent.ACTION_VIEW)
                .setDataAndType(UpdateFileProvider.uri(file), UpdateFileProvider.APK_TYPE)
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK))
        } catch (e: Exception) {
            updateFailed("installer not available: ${e.message}")
            return
        }
        main.postDelayed({  // nobody confirmed (or cancelled): report it instead of waiting forever
            if (updateState.state == "waiting" && updateState.version == version) updateFailed("not confirmed on the TV")
        }, 10 * 60 * 1000L)
    }

    private val host = object : Overlay.Host {
        override fun settings() = this@CamAlertService.settings()
        override val present get() = this@CamAlertService.present
        override val tr get() = this@CamAlertService.tr
        override fun show(stream: String, mode: String, priority: String, source: String) {
            Thread { controller.show(stream, null, mode, priority, source, null) }.start()
        }
        override fun neighbour(current: String?, step: Int): Tile? = controller.neighbour(current, step)
        override fun hasPtz(camera: String?) = camera != null && env.hasPtz(camera)
        override fun ptz(camera: String, action: String) = env.ptzMove(action, camera)
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
                    val servers = Servers.serverList(s["server"]?.toString(), s["more_servers"]?.toString())
                    warm.update(s["server"]?.toString(), s["ready_cameras"]?.toString(), on) { Servers.resolve(it, servers, serverMap) }
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
                    val secret = s["ha_webhook_secret"]?.toString()?.ifEmpty { null }  // #82
                    Net.fetch(hook, true, 5000, MqttTopics.buttonEvent(node, camera, colour, secret).toByteArray())
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
        cameraDevices = CameraDevices(this)
        directCameras = DirectCameraList(this)
        CamLog.level = settings()["log_level"]?.toString() ?: "normal"
        foreground()
        store.prefs.registerOnSharedPreferenceChangeListener(this)
        CamLog.log("CamAlert $version started (node $node)")
        apply()
        startUnifi()
        startFoscam()
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
        announce(s)
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

    /** #121: Home Assistant finds this device while the API listens and is on (NsdManager, _camalert._tcp). */
    private fun announce(s: Map<String, Any?>) {
        val srv = server
        val info = if (srv != null && Discovery.shouldAdvertise(s))
            Discovery.serviceInfo(node, nodeName(s), "androidtv", version, api.data.apiVersion, serverPort, srv.https) else null
        val key = info?.toString()
        if (key == nsdKey) return
        unannounce()
        nsdKey = key
        if (info == null) return
        val nm = getSystemService(Context.NSD_SERVICE) as? NsdManager ?: return
        val si = NsdServiceInfo().apply {
            serviceName = info["instance"] as String
            serviceType = Discovery.SERVICE_TYPE
            port = info["port"] as Int
            @Suppress("UNCHECKED_CAST")
            for (kv in info["txt"] as List<List<String>>) setAttribute(kv[0], kv[1])
        }
        val listener = object : NsdManager.RegistrationListener {
            override fun onServiceRegistered(i: NsdServiceInfo) {
                CamLog.log("announced on the network as ${i.serviceName}", "verbose")
            }
            override fun onRegistrationFailed(i: NsdServiceInfo, code: Int) {
                CamLog.log("network announcement failed ($code)", "error")
            }
            override fun onServiceUnregistered(i: NsdServiceInfo) {}
            override fun onUnregistrationFailed(i: NsdServiceInfo, code: Int) {}
        }
        try {
            nm.registerService(si, NsdManager.PROTOCOL_DNS_SD, listener)
            nsdListener = listener
        } catch (e: Exception) {
            CamLog.log("network announcement failed: $e", "error")
        }
    }

    private fun unannounce() {
        val listener = nsdListener ?: return
        nsdListener = null
        nsdKey = null
        try {
            (getSystemService(Context.NSD_SERVICE) as NsdManager).unregisterService(listener)
        } catch (e: Exception) {  // already gone
        }
    }

    override fun onSharedPreferenceChanged(prefs: SharedPreferences?, key: String?) {
        main.removeCallbacks(applyLater)
        main.postDelayed(applyLater, 500)
    }

    private val applyLater = Runnable { apply() }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_STICKY

    override fun onBind(intent: Intent?): IBinder? = null

    /** Foscam motion and sound alarms (#66): every foscam_interval seconds while foscam_enabled is on. */
    private fun startFoscam() {
        foscamThread = Thread({
            while (!Thread.currentThread().isInterrupted) {
                var wait = 5
                try {
                    val s = settings()
                    if (s["foscam_enabled"] == true) {
                        foscam.once(s + ("foscam_label" to tr("Motion")), cameraDevices.cameras()) { t ->
                            controller.show(t.camera, t.seconds, t.mode, t.priority, "foscam", t.label, null)
                        }
                        wait = ((s["foscam_interval"] as? Number)?.toInt() ?: 2).coerceIn(1, 60)
                    }
                } catch (e: Exception) {  // never let the poller die silently
                    CamLog.log("Foscam: $e", "error")
                }
                try {
                    Thread.sleep(wait * 1000L)
                } catch (e: InterruptedException) {
                    break
                }
            }
        }, "camalert-foscam").apply { isDaemon = true; start() }
    }

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

    private var tts: TextToSpeech? = null
    private var ttsReady = false
    private var sayPlayer: MediaPlayer? = null

    /** #89: the WAV from Home Assistant (local network) on the music stream, or the text with Android's own speech
     *  engine when there is no audio url (or it fails). In a thread; true when something will be spoken. */
    private fun speak(url: String?, text: String?): Boolean {
        val am = getSystemService(Context.AUDIO_SERVICE) as AudioManager
        if (am.isStreamMute(AudioManager.STREAM_MUSIC)) {
            CamLog.log("spoken announcement skipped: muted")
            return false
        }
        Thread {
            try { Thread.sleep(1200) } catch (e: InterruptedException) { return@Thread }  // after the window and the chime
            var played = false
            if (url != null) {
                try {
                    val data = Net.fetch(url, true, 10000, null, Speech.MAX_AUDIO + 1)
                    if (data.size > Speech.MAX_AUDIO || !Speech.isWav(data)) throw IllegalArgumentException("not a WAV file")
                    val file = java.io.File(cacheDir, "camalert-say.wav")
                    file.writeBytes(data)
                    main.post { playWav(file.path) }
                    played = true
                } catch (e: Exception) {
                    CamLog.log("spoken announcement failed: $e")
                }
            }
            if (!played && text != null) main.post { sayText(text) }
        }.start()
        return true
    }

    @Suppress("DEPRECATION")  // setAudioStreamType: setAudioAttributes needs API 26, minSdk is 25
    private fun playWav(path: String) {
        try {
            sayPlayer?.release()
            sayPlayer = MediaPlayer().apply {
                setAudioStreamType(AudioManager.STREAM_MUSIC)
                setDataSource(path)
                setOnCompletionListener { it.release(); if (sayPlayer === it) sayPlayer = null }
                prepare()
                start()
            }
            CamLog.log("spoken announcement", "verbose")
        } catch (e: Exception) {
            CamLog.log("spoken announcement failed: $e")
        }
    }

    private fun sayText(text: String) {
        val engine = tts
        if (engine != null && ttsReady) {
            engine.speak(text, TextToSpeech.QUEUE_FLUSH, null, "camalert")
            return
        }
        tts = TextToSpeech(this) { status ->
            ttsReady = status == TextToSpeech.SUCCESS
            if (ttsReady) tts?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "camalert")
            else CamLog.log("spoken announcement failed: no speech engine on this device")
        }
    }

    override fun onDestroy() {
        tts?.shutdown(); tts = null
        sayPlayer?.release(); sayPlayer = null
        CamLog.log("CamAlert stopped")
        unifiThread?.interrupt()
        foscamThread?.interrupt()
        warmThread?.interrupt()
        warm.stop()
        store.prefs.unregisterOnSharedPreferenceChangeListener(this)
        unannounce()
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
