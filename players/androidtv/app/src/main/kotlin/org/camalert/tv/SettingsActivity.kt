// CamAlert for Android TV. Copyright (C) 2026 CamAlert developers. GPL v2.
package org.camalert.tv

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.text.InputType
import androidx.fragment.app.FragmentActivity
import androidx.leanback.preference.LeanbackPreferenceFragmentCompat
import androidx.leanback.preference.LeanbackSettingsFragmentCompat
import androidx.preference.EditTextPreference
import androidx.preference.ListPreference
import androidx.preference.Preference
import androidx.preference.PreferenceCategory
import androidx.preference.PreferenceDataStore
import androidx.preference.PreferenceFragmentCompat
import androidx.preference.PreferenceScreen
import androidx.preference.SwitchPreference
import android.content.SharedPreferences
import org.camalert.core.CoreData
import org.camalert.core.SettingsUi
import org.camalert.core.Style
import org.camalert.core.Setting

/**
 * The on-TV settings (leanback): one screen per section of the shared schema (same ids, defaults and levels as on
 * the other players, #38/#39), plus diagnostics, the event list and a test. Expert settings are hidden until
 * "Show expert settings" is on; internal settings are never shown. Opening the app also starts the service.
 */
class SettingsActivity : FragmentActivity() {
    override fun attachBaseContext(base: android.content.Context) = super.attachBaseContext(Lang.wrap(base))  // #10

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        CamAlertService.start(this)
        if (savedInstanceState == null && org.camalert.core.Wizard.shouldStart(Store(this).values())) {
            startActivity(Intent(this, WizardActivity::class.java))  // first start without go2rtc address (#120)
        }
        if (savedInstanceState == null) {
            supportFragmentManager.beginTransaction().replace(android.R.id.content, Root()).commit()
        }
    }

    class Root : LeanbackSettingsFragmentCompat() {
        override fun onPreferenceStartInitialScreen() = startPreferenceFragment(Sections())

        override fun onPreferenceStartFragment(caller: PreferenceFragmentCompat, pref: Preference): Boolean {
            val section = pref.extras.getString("section") ?: return false
            startPreferenceFragment(Section().apply { arguments = Bundle().apply { putString("section", section) } })
            return true
        }

        override fun onPreferenceStartScreen(caller: PreferenceFragmentCompat, pref: PreferenceScreen): Boolean = false
    }

    /** The first screen: sections, overlay permission, diagnostics, event list, test. */
    class Sections : LeanbackPreferenceFragmentCompat() {
        override fun onCreatePreferences(savedInstanceState: Bundle?, rootKey: String?) {
            val ctx = preferenceManager.context
            preferenceManager.sharedPreferencesName = ctx.packageName + "_preferences"
            val tr = Tr(ctx)
            val screen = preferenceManager.createPreferenceScreen(ctx)
            screen.title = "CamAlert"
            val overlayOk = Settings.canDrawOverlays(ctx)
            if (!overlayOk) {
                screen.addPreference(Preference(ctx).apply {
                    title = getString(R.string.overlay_missing)
                    setOnPreferenceClickListener {
                        try {
                            startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:" + ctx.packageName)))
                        } catch (e: Exception) {
                            CamLog.log("no overlay permission screen on this device: use adb (docs/players/androidtv.md)")
                        }
                        true
                    }
                })
            }
            val data = CoreData.load()
            for (section in data.sections) {
                if (data.settings.none { it.section == section && it.level != "internal" }) continue
                screen.addPreference(Preference(ctx).apply {
                    key = "section.$section"
                    title = tr.named("section.$section", section)
                    fragment = Section::class.java.name
                    extras.putString("section", section)
                })
            }
            screen.addPreference(SwitchPreference(ctx).apply {
                key = "ui_show_expert"
                title = getString(R.string.show_expert)
                setDefaultValue(false)
            })
            screen.addPreference(Preference(ctx).apply {
                title = getString(R.string.test_show)
                setOnPreferenceClickListener {
                    val svc = CamAlertService.instance
                    Thread { svc?.controller?.show(null, null, null, null, "menu", null) }.start()
                    true
                }
            })
            screen.addPreference(Preference(ctx).apply {
                title = getString(R.string.wizard_again)
                intent = Intent(ctx, WizardActivity::class.java)
            })
            screen.addPreference(Preference(ctx).apply {
                title = getString(R.string.diagnostics)
                intent = Intent(ctx, InfoActivity::class.java).putExtra("what", "diagnostics")
            })
            screen.addPreference(Preference(ctx).apply {
                title = getString(R.string.events)
                intent = Intent(ctx, InfoActivity::class.java).putExtra("what", "events")
            })
            screen.addPreference(Preference(ctx).apply {  // #132
                title = Tr(ctx)("Report a problem")
                intent = Intent(ctx, ReportActivity::class.java)
            })
            preferenceScreen = screen
            summaries()
        }

        override fun onResume() {
            super.onResume()
            summaries()  // back from a section: its line says what changed (#130)
        }

        /** Each section's line: the switches that are on there, else how many settings differ from the default. */
        private fun summaries() {
            val ctx = context ?: return
            val tr = Tr(ctx)
            val ui = SettingsUi()
            val values = Store(ctx).values()
            for (section in CoreData.load().sections) {
                val p = findPreference<Preference>("section.$section") ?: continue
                val (on, changed) = ui.summary(section, values)
                val parts = on.map { tr(it) }.toMutableList()
                if (changed > 0) parts.add(getString(R.string.summary_changed, changed))
                p.summary = if (parts.isEmpty()) getString(R.string.summary_default) else parts.joinToString(", ")
            }
        }
    }

    /** One section of the schema. */
    class Section : LeanbackPreferenceFragmentCompat() {
        override fun onCreatePreferences(savedInstanceState: Bundle?, rootKey: String?) {
            val ctx = preferenceManager.context
            preferenceManager.sharedPreferencesName = ctx.packageName + "_preferences"
            val tr = Tr(ctx)
            val section = arguments?.getString("section") ?: "general"
            val expert = preferenceManager.sharedPreferences?.getBoolean("ui_show_expert", false) == true
            val screen = preferenceManager.createPreferenceScreen(ctx)
            screen.title = tr.named("section.$section", section)
            for (s in CoreData.load().settings.filter { it.section == section }) {
                if (s.level == "internal" || (s.level == "expert" && !expert)) continue
                screen.addPreference(widget(s, tr))
            }
            if (section == "triggers") unifiConsole(screen)
            if (section == "camera_control") cameraDevices(screen)
            if (section == "general") directCameras(screen)
            if (section == "display") screen.addPreference(Preference(ctx).apply {  // #48: a preset fills in settings
                title = tr(CoreData.load().presetLabels.getValue("simple"))
                isIconSpaceReserved = false
                setOnPreferenceClickListener {
                    val store = Store(ctx)
                    val ids = CoreData.load().settings.map { it.id }
                    for ((k, v) in Style.presetChanges("simple", store.values(), ids)) store.set(k, v)
                    activity?.recreate()
                    true
                }
            })
            screen.findPreference<ListPreference>("language")?.setOnPreferenceChangeListener { _, _ ->
                view?.post { activity?.recreate() }  // #10: the settings at once in the new language
                true
            }
            preferenceScreen = screen
            visibility()
        }

        private val changed = SharedPreferences.OnSharedPreferenceChangeListener { _, _ -> view?.post { visibility() } }

        override fun onResume() {
            super.onResume()
            preferenceManager.sharedPreferences?.registerOnSharedPreferenceChangeListener(changed)
            visibility()
        }

        override fun onPause() {
            preferenceManager.sharedPreferences?.unregisterOnSharedPreferenceChangeListener(changed)
            super.onPause()
        }

        /** #130: hide what does not apply (Frigate's fields while Frigate is off ...), the same rules everywhere. */
        private fun visibility() {
            val ctx = context ?: return
            val ui = SettingsUi()
            val values = Store(ctx).values()
            for (s in CoreData.load().settings) {
                findPreference<Preference>(s.id)?.isVisible = ui.applies(s.id, values)
            }
        }

        /** UniFi Protect console (#72): kept in its own private file (UnifiLogin), never with the settings. */
        private fun unifiConsole(screen: PreferenceScreen) {
            val ctx = preferenceManager.context
            val login = UnifiLogin(ctx)
            val store = object : PreferenceDataStore() {
                override fun getString(key: String?, defValue: String?) = login.prefs.getString(key, defValue)
                override fun putString(key: String?, value: String?) {
                    login.prefs.edit().putString(key, value?.let { if (key == "password") it else it.trim() }).apply()
                }
            }
            val cat = PreferenceCategory(ctx).apply { title = getString(R.string.unifi_console); isIconSpaceReserved = false }
            screen.addPreference(cat)
            for ((key, res) in listOf("address" to R.string.unifi_console_address, "user" to R.string.unifi_console_user,
                    "password" to R.string.unifi_console_password)) {
                cat.addPreference(EditTextPreference(ctx).apply {
                    preferenceDataStore = store
                    this.key = key
                    title = getString(res)
                    dialogTitle = title
                    isIconSpaceReserved = false
                    setOnBindEditTextListener { e ->
                        e.inputType = if (key == "password") InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
                        else InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
                    }
                    summaryProvider = Preference.SummaryProvider<EditTextPreference> { p ->
                        val v = p.text ?: ""
                        if (v.isEmpty()) "–" else if (key == "password") "••••••" else v
                    }
                })
            }
        }

        /** Camera devices (#66): their own private file (CameraDevices), never with the settings. */
        private fun cameraDevices(screen: PreferenceScreen) {
            val ctx = preferenceManager.context
            val devices = CameraDevices(ctx)
            val store = object : PreferenceDataStore() {
                override fun getString(key: String?, defValue: String?) = devices.prefs.getString(key, defValue)
                override fun putString(key: String?, value: String?) {
                    devices.prefs.edit().putString(key, value?.let { if (key == "password") it else it.trim() }).apply()
                }
            }
            val cat = PreferenceCategory(ctx).apply { title = getString(R.string.devices_title); isIconSpaceReserved = false }
            screen.addPreference(cat)
            for ((key, res) in listOf("devices" to R.string.devices_list, "user" to R.string.devices_user,
                    "password" to R.string.devices_password)) {
                cat.addPreference(EditTextPreference(ctx).apply {
                    preferenceDataStore = store
                    this.key = key
                    title = getString(res)
                    dialogTitle = title
                    if (key == "devices") dialogMessage = getString(R.string.devices_help)
                    isIconSpaceReserved = false
                    setOnBindEditTextListener { e ->
                        e.inputType = when (key) {
                            "password" -> InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
                            "devices" -> InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
                            else -> InputType.TYPE_CLASS_TEXT
                        }
                    }
                    summaryProvider = Preference.SummaryProvider<EditTextPreference> { p ->
                        val v = p.text ?: ""
                        when {
                            v.isEmpty() -> "–"
                            key == "password" -> "••••••"
                            key == "devices" -> devices.cameras().keys.joinToString(", ").ifEmpty { getString(R.string.devices_none) }
                            else -> v
                        }
                    }
                })
            }
        }

        /** Cameras without go2rtc (#124): the camera list in its own private file (DirectCameraList). */
        private fun directCameras(screen: PreferenceScreen) {
            val ctx = preferenceManager.context
            val list = DirectCameraList(ctx)
            val store = object : PreferenceDataStore() {
                override fun getString(key: String?, defValue: String?) = list.prefs.getString(key, defValue)
                override fun putString(key: String?, value: String?) {
                    list.prefs.edit().putString(key, value?.trim()).apply()
                    CamAlertService.instance?.controller?.refreshNames()
                }
            }
            val cat = PreferenceCategory(ctx).apply { title = getString(R.string.cameras_title); isIconSpaceReserved = false }
            screen.addPreference(cat)
            cat.addPreference(EditTextPreference(ctx).apply {
                preferenceDataStore = store
                key = "cameras"
                title = getString(R.string.cameras_list)
                dialogTitle = title
                dialogMessage = getString(R.string.cameras_help)
                isIconSpaceReserved = false
                setOnBindEditTextListener { e ->
                    e.inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
                }
                summaryProvider = Preference.SummaryProvider<EditTextPreference> { _ ->
                    list.cameras().joinToString(", ") { it.title }.ifEmpty { getString(R.string.cameras_none) }
                }
            })
        }

        /** %s in a label or help: the place of the cameras (go2rtc), the camera devices (Foscam, PTZ) or, for UniFi
         *  Protect, the console settings. */
        private fun fill(s: Setting, text: String) =
            text.replace("%s", when {
                s.id.startsWith("unifi_") -> getString(R.string.unifi_where)
                s.id.startsWith("foscam_") || s.id.startsWith("ptz_") -> getString(R.string.devices_where)
                s.id == "source" -> getString(R.string.cameras_where)
                else -> "go2rtc"
            })

        private fun label(s: Setting, tr: Tr) = fill(s, tr(s.label ?: s.id))

        private fun widget(s: Setting, tr: Tr): Preference {
            val ctx = preferenceManager.context
            val p: Preference = when (s.type) {
                "bool" -> SwitchPreference(ctx).apply { setDefaultValue(s.default) }
                "choice" -> ListPreference(ctx).apply {
                    val values = s.choices!!
                    entryValues = values.toTypedArray()
                    entries = values.map { if (s.id == "language") Style.languageLabel(it, tr) else tr.named("choice.${s.id}.$it", it) }.toTypedArray()
                    setDefaultValue(s.default)
                    summaryProvider = ListPreference.SimpleSummaryProvider.getInstance()
                    dialogTitle = label(s, tr)
                }
                else -> EditTextPreference(ctx).apply {
                    setDefaultValue(s.default?.toString() ?: "")
                    dialogTitle = label(s, tr)
                    val numeric = s.type == "int"
                    val secret = s.type == "password"
                    setOnBindEditTextListener { e ->
                        e.inputType = when {
                            numeric -> InputType.TYPE_CLASS_NUMBER
                            secret -> InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
                            else -> InputType.TYPE_CLASS_TEXT
                        }
                    }
                    summaryProvider = Preference.SummaryProvider<EditTextPreference> { pref ->
                        val v = pref.text ?: ""
                        when {
                            secret || s.id == "token" -> if (v.isEmpty()) "–" else "••••••"
                            v.isEmpty() -> "–"
                            else -> v + (if (s.unit != null && s.unit != "%") " " + s.unit else s.unit ?: "")
                        }
                    }
                    setOnPreferenceChangeListener { _, value ->
                        try { s.coerce(value); true } catch (e: Exception) { false }  // refuse invalid values (schema range)
                    }
                }
            }
            p.key = s.id
            p.title = label(s, tr)
            p.isPersistent = true
            p.isIconSpaceReserved = false
            if (s.type == "bool" && s.help != null) p.summary = fill(s, tr(s.help!!))
            return p
        }
    }
}
