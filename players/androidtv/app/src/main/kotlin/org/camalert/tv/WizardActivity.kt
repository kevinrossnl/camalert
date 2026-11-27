// CamAlert for Android TV. Copyright (C) 2026 CamAlert developers. GPL v2.
package org.camalert.tv

import android.app.Activity
import android.app.AlertDialog
import android.os.Bundle
import android.text.InputType
import android.widget.EditText
import org.camalert.core.CoreData
import org.camalert.core.Urls
import org.camalert.core.Wizard
import java.util.concurrent.atomic.AtomicBoolean

/**
 * The first-start wizard (#120) with plain dialogs (D-pad: lists, yes/no, the Fire TV keyboard): find go2rtc,
 * choose the default camera (with a preview), a test (no chime) and how to add this player in Home Assistant.
 * The logic is org.camalert.core.Wizard; every network call runs in a thread. Leaving it at any point marks it done.
 */
class WizardActivity : Activity() {
    private val stop = AtomicBoolean(false)
    private lateinit var store: Store
    private var found: List<Pair<String, List<String>>> = emptyList()
    private var server: String? = null
    private var cameras: List<String> = emptyList()
    private var camera: String? = null
    private var finished = false

    private fun dialog() = AlertDialog.Builder(this, android.R.style.Theme_DeviceDefault_Dialog_Alert)
        .setTitle(R.string.wizard_title)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = Store(this)
        CamAlertService.start(this)
        search()
    }

    override fun onDestroy() {
        stop.set(true)
        super.onDestroy()
    }

    private fun search() {
        val searching = dialog().setMessage(R.string.wizard_searching)
            .setOnCancelListener { stop.set(true) }.show()
        val s = store.values()
        Thread {
            val list = Wizard.uniqueServers(Wizard.scan(Wizard.candidates(Wizard.ownIp(), Wizard.haHost(s)),
                { srv -> probe(srv, Wizard.TIMEOUT_MS) }, stop = stop))
            runOnUiThread {
                if (isFinishing) return@runOnUiThread
                searching.dismiss()
                found = list
                if (list.isEmpty()) noneFound() else chooseServer()
            }
        }.start()
    }

    private fun probe(srv: String, timeoutMs: Int): List<String>? = try {
        Wizard.camerasFrom(String(Net.fetch("$srv/api/streams", store.values()["verify_ssl"] != false, timeoutMs,
            max = 512 shl 10), Charsets.UTF_8))
    } catch (e: Exception) {
        null
    }

    private fun chooseServer() {
        val labels = found.map { (srv, cams) -> "$srv (${getString(R.string.wizard_cameras, cams.size)})" } +
            getString(R.string.wizard_manual)
        dialog().setItems(labels.toTypedArray()) { _, i ->
            if (i < found.size) useServer(found[i].first, found[i].second) else typeAddress()
        }.setOnCancelListener { leave(null) }.show()
    }

    private fun noneFound() {
        dialog().setMessage(R.string.wizard_none).setPositiveButton(android.R.string.ok) { _, _ -> chooseServer() }
            .setOnCancelListener { chooseServer() }.show()
    }

    private fun typeAddress() {
        val input = EditText(this).apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
            setText(store.values()["server"]?.toString()?.ifEmpty { null } ?: "http://")
        }
        dialog().setTitle(R.string.wizard_address).setView(input)
            .setPositiveButton(android.R.string.ok) { _, _ ->
                val srv = Wizard.serverFromInput(input.text.toString())
                if (srv == null) noAnswer(input.text.toString()) else Thread {
                    val cams = probe(srv, 5000)
                    runOnUiThread { if (cams == null) noAnswer(srv) else useServer(srv, cams) }
                }.start()
            }
            .setOnCancelListener { chooseServer() }
            .setNegativeButton(android.R.string.cancel) { _, _ -> chooseServer() }.show()
    }

    private fun noAnswer(srv: String) {
        dialog().setMessage(getString(R.string.wizard_no_answer, srv))
            .setPositiveButton(android.R.string.ok) { _, _ -> chooseServer() }
            .setOnCancelListener { chooseServer() }.show()
    }

    private fun useServer(srv: String, cams: List<String>) {
        server = srv
        cameras = cams
        store.set("server", srv)  // the preview needs the address
        if (cams.isEmpty()) {
            leave(null, R.string.wizard_no_cameras)
            return
        }
        chooseCamera()
    }

    private fun chooseCamera() {
        val current = store.values()["camera"]?.toString()
        dialog().setTitle(R.string.wizard_which)
            .setSingleChoiceItems(cameras.toTypedArray(), cameras.indexOf(current).coerceAtLeast(0)) { d, i ->
                d.dismiss()
                camera = cameras[i]
                show(cameras[i], 15, "photo")  // preview, as a test: no chime
                askRightCamera()
            }
            .setOnCancelListener { leave(null) }.show()
    }

    private fun askRightCamera() {
        dialog().setMessage(R.string.wizard_right)
            .setPositiveButton(R.string.wizard_yes) { _, _ ->
                hide()
                store.set("camera", camera)
                askTest()
            }
            .setNegativeButton(R.string.wizard_no) { _, _ -> hide(); chooseCamera() }
            .setOnCancelListener { hide(); chooseCamera() }.show()
    }

    private fun askTest() {
        dialog().setMessage(R.string.wizard_test)
            .setPositiveButton(R.string.wizard_yes) { _, _ -> show(camera!!, 10, "notify"); done() }
            .setNegativeButton(R.string.wizard_no) { _, _ -> done() }
            .setOnCancelListener { done() }.show()
    }

    private fun done() {
        val values = Wizard.result(server, camera)
        val s = store.values()
        val name = CamAlertService.instance?.nodeName(s)
        Thread {
            val (player, address) = Wizard.addText(name, Wizard.ownIp(), Urls.validPort(s["http_port"], 8099))
            runOnUiThread {
                save(values)
                dialog().setMessage(listOf(getString(R.string.wizard_ready), getString(R.string.wizard_name, player),
                    getString(R.string.wizard_addr, address)).joinToString("\n"))
                    .setPositiveButton(android.R.string.ok) { _, _ -> close() }
                    .setOnCancelListener { close() }.show()
            }
        }.start()
    }

    private fun show(cam: String, seconds: Int, mode: String) {
        val svc = CamAlertService.instance ?: return
        Thread { svc.controller.show(cam, seconds, mode, "high", "test", null, null) }.start()
    }

    private fun hide() {
        val svc = CamAlertService.instance ?: return
        Thread { svc.controller.hide() }.start()
    }

    /** Saves what was chosen (only settings this player has); wizard_done in any case. */
    private fun save(values: Map<String, Any?>) {
        if (finished) return
        finished = true
        stop.set(true)
        val known = CoreData.load().byId
        for ((k, v) in values) if (k in known) store.set(k, v)
    }

    private fun leave(values: Map<String, Any?>?, message: Int? = null) {
        save(values ?: Wizard.result())
        if (message == null) {
            close()
            return
        }
        dialog().setMessage(message).setPositiveButton(android.R.string.ok) { _, _ -> close() }
            .setOnCancelListener { close() }.show()
    }

    private fun close() {
        stop.set(true)
        super.finish()
    }
}
