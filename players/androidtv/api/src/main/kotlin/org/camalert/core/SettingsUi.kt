// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

/**
 * How the settings screens are laid out (#130), the same rules as camalert_core.settingsui: a setting that only
 * matters while another one has a certain value is hidden otherwise (Frigate needs MQTT, UniFi Protect's fields
 * need UniFi Protect on ...), and each section's line on the first screen says what is on there.
 */
class SettingsUi(private val data: CoreData = CoreData.load()) {
    private fun value(values: Map<String, Any?>, id: String): Any? =
        if (values.containsKey(id)) values[id] else data.byId[id]?.default

    /** Whether setting id matters with these values; follows the chain. A parent this player lacks: applies. */
    fun applies(id: String, values: Map<String, Any?>): Boolean {
        var sid = id
        val seen = HashSet<String>()
        while (seen.add(sid)) {
            if (sid in data.settingsHttpsOnly && value(values, "source") == "go2rtc" &&
                !(value(values, "server")?.toString() ?: "").trim().lowercase().startsWith("https")) return false
            val (parent, allowed) = data.settingsDepends[sid] ?: return true
            if (parent !in data.byId) return true
            if (value(values, parent) !in allowed) return false
            sid = parent
        }
        return true
    }

    private fun shown() = data.settings.filter { it.level != "internal" }

    /** On/off settings of a section that others depend on: listed in the section's line when they are on. */
    fun switches(section: String): List<Setting> {
        val parents = data.settingsDepends.values.map { it.first }.toSet()
        return shown().filter { it.section == section && it.type == "bool" && it.id in parents && it.level != "basic" }
    }

    /** (labels of the switches that are on, number of other non-basic settings that differ from the default). */
    fun summary(section: String, values: Map<String, Any?>): Pair<List<String>, Int> {
        val sw = switches(section)
        val on = sw.filter { value(values, it.id) == true }.map { it.label ?: it.id }
        val ids = sw.map { it.id }.toSet()
        val changed = shown().count {
            it.section == section && it.level != "basic" && it.id !in ids && value(values, it.id) != it.default
        }
        return Pair(on, changed)
    }

    /** Sections with settings besides the basic ones, in schema order. */
    fun sections(): List<String> {
        val have = shown().filter { it.level != "basic" }.map { it.section }.toSet()
        return data.sections.filter { it in have }
    }
}
