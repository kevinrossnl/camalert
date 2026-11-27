// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

/**
 * Accessibility and personal settings (#48, #10), core style.py: priority marking (Okabe-Ito colours, never colour
 * alone), presets and the language setting. The values come from core.json.
 */
object Style {
    data class Mark(val colour: String, val label: String, val flash: Boolean)

    private val data get() = CoreData.load()
    val flashMs get() = data.flashMs

    /** The mark of a window with this priority, or null (normal priority, or border "off"). */
    fun priorityMark(priority: String?, border: String?): Mark? {
        if (border != "steady" && border != "flash") return null
        val colour = data.priorityColours[priority] ?: return null
        return Mark(colour, data.priorityMarks.getValue(priority!!), border == "flash")
    }

    /** 'ALARM · Front door' (translated with tr); the title unchanged without a mark. */
    fun markedTitle(title: String, priority: String?, border: String?, tr: (String) -> String): String {
        val mark = priorityMark(priority, border) ?: return title
        val word = tr(mark.label)
        return if (title.isNotEmpty()) "$word · $title" else word
    }

    /** The settings a preset changes compared to current; keys limits it to the settings this player has. */
    fun presetChanges(name: String, current: Map<String, Any?>, keys: Collection<String>? = null): Map<String, Any?> {
        val out = LinkedHashMap<String, Any?>()
        for ((k, v) in data.presets[name] ?: emptyMap()) {
            if (keys != null && k !in keys) continue
            if (current[k] != v) out[k] = v
        }
        return out
    }

    /** The language CamAlert shows: the setting unless "system", else the system language; "en" when nothing fits. */
    fun effectiveLanguage(setting: String?, system: String?): String {
        if (setting != null && setting in data.languageNames) return setting
        val code = (system ?: "").replace("-", "_").split("_")[0].lowercase()
        return if (code in data.languageNames) code else "en"
    }

    fun languageLabel(code: String, tr: (String) -> String) = if (code == "system") tr(data.systemLanguage) else data.languageNames[code] ?: code
}
