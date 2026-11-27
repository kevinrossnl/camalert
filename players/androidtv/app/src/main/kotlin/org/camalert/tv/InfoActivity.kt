// CamAlert for Android TV. Copyright (C) 2026 CamAlert developers. GPL v2.
package org.camalert.tv

import android.app.Activity
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.util.TypedValue
import android.widget.ScrollView
import android.widget.TextView
import org.camalert.core.Events
import org.camalert.core.Obs
import org.camalert.core.Urls

/** Diagnostics (checks go2rtc, every camera's snapshot, API, MQTT, overlay permission) and the event list. */
class InfoActivity : Activity() {
    private lateinit var view: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        view = TextView(this).apply {
            setTextColor(Color.WHITE)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
            setPadding(64, 48, 64, 48)
            typeface = android.graphics.Typeface.MONOSPACE
        }
        setContentView(ScrollView(this).apply { addView(view); isFocusable = true })
        val what = intent.getStringExtra("what") ?: "events"
        title = getString(if (what == "events") R.string.events else R.string.diagnostics)
        if (what == "events") events() else Thread { diagnostics() }.start()
    }

    private fun events() {
        val svc = CamAlertService.instance
        val list = svc?.controller?.events ?: emptyList()
        view.text = getString(R.string.events) + "\n\n" +
            if (list.isEmpty()) getString(R.string.no_events) else list.joinToString("\n") { svc!!.present.eventLine(it) }
    }

    private fun diagnostics() {
        val out = ArrayList<String>()
        fun line(ok: Boolean?, text: String) {
            out.add(Events.diagLine(ok, text))
            runOnUiThread { view.text = getString(R.string.diagnostics) + "\n\n" + out.joinToString("\n") }
        }
        val svc = CamAlertService.instance
        line(null, "Android ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT}), ${Build.MANUFACTURER} ${Build.MODEL}")
        if (svc == null) {
            line(false, "CamAlert service is not running")
            return
        }
        val s = svc.settings()
        line(null, "CamAlert ${svc.version}, node ${svc.node}")
        line(Settings.canDrawOverlays(this), "draw over other apps (SYSTEM_ALERT_WINDOW)")
        line(true, "API on port ${Urls.validPort(s["http_port"], 8099)}${if (s["api_https"] == true) " (https)" else ""}, allowed callers: ${s["allow"]}")
        val server = Urls.normalizeServer(s["server"]?.toString())
        if (server == null) {
            line(false, "go2rtc address missing or invalid: ${s["server"]}")
        } else {
            val names = try { svc.cameraNames() } catch (e: Exception) { line(false, "go2rtc $server: ${e.message}"); null }
            if (names != null) {
                line(names.isNotEmpty(), "go2rtc $server: ${names.size} cameras")
                for (n in names.take(12)) {
                    val t = svc.tile(n)
                    val ok = try { Net.fetch(t!!.snapshot!!, s["verify_ssl"] != false, 6000).isNotEmpty() } catch (e: Exception) { false }
                    line(ok, "snapshot $n")
                }
            }
        }
        Obs.parseHostPort(s["log_syslog"]?.toString())?.let { line(null, "syslog ${it.first}:${it.second} (UDP)") }
        if (s["mqtt_enabled"] == true) line(svc.mqttConnected(), "MQTT ${s["mqtt_host"]}:${s["mqtt_port"]}")
        else line(null, "MQTT off")
        if (s["unifi_enabled"] == true) {
            if (svc.unifiLogin.consoles().isEmpty()) line(false, getString(R.string.unifi_no_console))
            else for ((ok, text) in svc.unifi.status.lines(svc.tr) { ts ->
                java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.ROOT).format(java.util.Date((ts * 1000).toLong()))
            }) line(ok, text)
        }
        val last = svc.controller.lastCaller
        line(null, if (last == null) "no API call yet" else "last API call from ${last.second} (${last.third})")
    }
}
