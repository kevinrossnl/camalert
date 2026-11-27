// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

/** What the player shows as text (core present.py, #41): key hints from the key map, labels, tour status. */
class Present(val data: CoreData = CoreData.load(), val tr: (String) -> String = { it }) {
    /** Logical action of a key name in a context, or null. */
    fun actionFor(context: String, key: String?): String? {
        for ((action, keys) in data.keymap[context] ?: emptyMap()) if (key in keys) return action
        return null
    }

    private fun keysText(context: String, actions: List<String>, glyphs: Boolean): String {
        val names = ArrayList<String>()
        for (action in actions) {
            for (key in data.keymap[context]?.get(action) ?: emptyList()) {
                var name = data.keyNames[key] ?: continue
                if (name == name.uppercase() && name.any { it.isLetter() } && name.lowercase() in data.colourNames) name = tr(name)
                if (!glyphs) name = data.ascii[name] ?: name
                if (name !in names) names.add(name)
            }
        }
        if (actions.size == 1) return names.take(2).joinToString("/")
        return names.joinToString(" ")
    }

    /** 'OK = live   ◀ ▶ = other camera   BACK = close' (translated). */
    fun keyHint(context: String, ptzKey: String? = null, hasPtz: Boolean = false, glyphs: Boolean = true): String {
        if (data.keymap[context].isNullOrEmpty()) return ""
        val colour = data.colourNames[ptzKey]?.let { tr(it) }
        val parts = ArrayList<String>()
        for ((actions, label) in data.hints[context] ?: emptyList()) {
            var keys = keysText(context, actions, glyphs)
            if (actions == listOf("ptz")) {
                if (!hasPtz) continue
                keys = listOfNotNull(colour, keys.ifEmpty { null }).joinToString("/")
            } else if (actions == listOf("leave")) {
                keys = listOfNotNull(keys.ifEmpty { null }, colour).joinToString("/")
            }
            if (keys.isNotEmpty()) parts.add("$keys = ${tr(label)}")
        }
        return parts.joinToString(data.hintSeparator)
    }

    /** Entries of the on-screen action menu (#118, core keymap.action_menu): ("ptz", null) for camera control on a
     *  camera with PTZ, then ("button", colour) for every colour key that goes to Home Assistant. */
    fun actionMenu(hasPtz: Boolean = false, ptzKey: String? = "blue", haButtons: Boolean = true): List<Pair<String, String?>> {
        val out = ArrayList<Pair<String, String?>>()
        if (hasPtz) out.add(Pair("ptz", null))
        if (haButtons) for (c in listOf("red", "green", "yellow", "blue")) if (!(hasPtz && c == ptzKey)) out.add(Pair("button", c))
        return out
    }

    /** 'Camera control' / 'GREEN to Home Assistant' (translated). */
    fun actionLabel(kind: String, colour: String?): String =
        if (kind == "button") tr(data.actionLabels.getValue("button")).replace("%s", tr(data.colourNames.getValue(colour!!)))
        else tr(data.actionLabels.getValue(kind))

    fun tourStatus(title: String, index: Int, total: Int, paused: Boolean) =
        "$title   ($index/$total, ${if (paused) tr("paused") else tr("tour")})"

    fun sourceLabel(code: String?) = data.sourceLabels[code]?.let(tr) ?: (code ?: "")
    fun priorityLabel(code: String?) = data.priorityLabels[code]?.let(tr) ?: (code ?: "")
    fun resultLabel(code: String?) = data.resultLabels[code]?.let(tr) ?: (code ?: "")

    fun reasonLabel(text: String?): String {
        val t = (text ?: "").trim()
        if (t.isEmpty()) return ""
        val code = t.substringBefore(':')
        val label = data.reasonLabels[code] ?: return t
        if (code == "cooldown") return tr(label).replace("%d", (t.substringAfter(':', "0").toIntOrNull() ?: 0).toString())
        return tr(label)
    }

    /** One line of the event list: '14:03:05  front_door · Person  (Frigate, High) -> Shown'. */
    fun eventLine(e: Map<String, Any?>): String {
        val ts = ((e["time"] as? Number)?.toDouble() ?: 0.0)
        val clock = java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.ROOT).format(java.util.Date((ts * 1000).toLong()))
        val who = (e["label"] as? String)?.takeIf { it.isNotEmpty() }?.let { " · $it" } ?: ""
        val why = reasonLabel(e["reason"] as? String).let { if (it.isEmpty()) "" else ": $it" }
        return "$clock  ${e["camera"]}$who  (${sourceLabel(e["source"] as? String)}, ${priorityLabel(e["priority"] as? String)}) -> ${resultLabel(e["action"] as? String)}$why"
    }
}
