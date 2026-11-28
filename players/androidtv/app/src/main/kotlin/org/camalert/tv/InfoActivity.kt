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
    override fun attachBaseContext(base: android.content.Context) = super.attachBaseContext(Lang.wrap(base))  // #10

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

    /** The event list (#124): OK on an event shows its camera, or offers its Frigate clip when there is one. */
    private fun events() {
        val svc = CamAlertService.instance
        val list = (svc?.controller?.events ?: emptyList()).reversed()  // newest first
        if (svc == null || list.isEmpty()) {
            view.text = getString(R.string.events) + "\n\n" + getString(R.string.no_events)
            return
        }
        val lines = list.map { svc.present.eventLine(it) }
        val lv = android.widget.ListView(this).apply {
            adapter = object : android.widget.ArrayAdapter<String>(this@InfoActivity, android.R.layout.simple_list_item_1, lines) {
                override fun getView(position: Int, convertView: android.view.View?, parent: android.view.ViewGroup): android.view.View =
                    (super.getView(position, convertView, parent) as TextView).apply {
                        setTextColor(Color.WHITE)
                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
                        typeface = android.graphics.Typeface.MONOSPACE
                    }
            }
            setPadding(48, 32, 48, 32)
            setOnItemClickListener { _, _, pos, _ -> pick(list[pos]) }
        }
        setContentView(lv)
        lv.requestFocus()
    }

    private fun pick(e: Map<String, Any?>) {
        val svc = CamAlertService.instance ?: return
        val cam = e["camera"]?.toString() ?: return
        val clip = org.camalert.core.Frigate.clipUrl(svc.settings()["frigate_url"]?.toString(), e["frigate_id"]?.toString())
        fun showCamera() = Thread { svc.controller.show(cam, null, null, "normal", "menu", null, null) }.start()
        if (clip == null) {
            showCamera()
            return
        }
        android.app.AlertDialog.Builder(this)
            .setTitle(cam)
            .setItems(arrayOf(getString(R.string.event_show), getString(R.string.event_clip))) { _, which ->
                if (which == 0) showCamera()
                else startActivity(android.content.Intent(this, ClipActivity::class.java)
                    .putExtra("url", clip).putExtra("title", "$cam ${e["label"] ?: ""}".trim()))
            }
            .show()
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
        if (s["source"]?.toString() == "direct") {  // #124: cameras without go2rtc
            val cams = svc.directCameras.cameras()
            line(cams.isNotEmpty(), "direct mode: ${cams.size} cameras")
            for (c in cams.take(12)) {
                val snap = c.snapshot
                if (snap == null) { line(null, "snapshot ${c.name}: none (live only)"); continue }
                val ok = try { Net.fetch(snap, s["verify_ssl"] != false, 6000).isNotEmpty() } catch (e: Exception) { false }
                line(ok, "snapshot ${c.name}")
            }
        } else if (server == null) {
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
        for ((ok, text) in svc.warm.lines(svc.tr)) line(ok, text)  // #111
        val last = svc.controller.lastCaller
        line(null, if (last == null) "no API call yet" else "last API call from ${last.second} (${last.third})")
    }
}
