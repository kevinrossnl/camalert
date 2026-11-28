// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

/**
 * Data that comes from the Python core, never typed in twice: API constants, the settings schema of the Android TV
 * player, the key map, hints and labels. Generated into resources/camalert/core.json by tools/export_contract.py.
 */
@Suppress("UNCHECKED_CAST")
class CoreData(val raw: Map<String, Any?>) {
    val apiVersion = (raw["api_version"] as Number).toInt()
    val minHaVersion = raw["min_ha_version"] as String
    val capabilities = raw["capabilities"] as List<String>
    val ptzActions = raw["ptz_actions"] as List<String>
    val screens = raw["screens"] as List<String>
    val testSource = raw["test_source"] as String
    val schemaVersion = (raw["schema_version"] as Number).toInt()
    val sections = raw["sections"] as List<String>
    val levels = raw["levels"] as List<String>
    val settings: List<Setting> = (raw["settings"] as List<Map<String, Any?>>).map { Setting(it) }
    val byId = settings.associateBy { it.id }
    /** #130: setting id -> (setting it depends on, values of that setting for which it applies). */
    val settingsDepends: Map<String, Pair<String, List<Any?>>> =
        ((raw["settings_depends"] as Map<String, List<Any?>>?) ?: emptyMap()).mapValues { (_, v) ->
            Pair(v[0] as String, (v[1] as List<Any?>))
        }
    val settingsHttpsOnly = (raw["settings_https_only"] as List<String>?) ?: emptyList()
    val settingsShortNames = (raw["settings_short_names"] as Map<String, String>?) ?: emptyMap()
    val keymap = (raw["keymap"] as Map<String, Map<String, List<String>>>)
    val contexts = raw["contexts"] as List<String>
    val keyNames = raw["key_names"] as Map<String, String>
    val colourNames = raw["colour_names"] as Map<String, String>
    val ascii = raw["ascii"] as Map<String, String>
    val hints = (raw["hints"] as Map<String, List<List<Any>>>).mapValues { (_, items) ->
        items.map { Pair(it[0] as List<String>, it[1] as String) }
    }
    val hintSeparator = raw["hint_separator"] as String
    val actionLabels = raw["action_labels"] as Map<String, String>
    val reasonLabels = raw["reason_labels"] as Map<String, String>
    val sourceLabels = raw["source_labels"] as Map<String, String>
    val priorityLabels = raw["priority_labels"] as Map<String, String>
    val resultLabels = raw["result_labels"] as Map<String, String>
    val tileLabels = raw["tile_labels"] as Map<String, String>
    val frameCacheSeconds = (raw["frame_cache_seconds"] as Number).toInt()
    val stillMaxSeconds = (raw["still_max_seconds"] as Number).toDouble()
    val setupReceived = raw["setup_received"] as String
    val textSizes = (raw["text_sizes"] as Map<String, Number>).mapValues { it.value.toDouble() }
    val borderModes = raw["border_modes"] as List<String>
    val priorityColours = raw["priority_colours"] as Map<String, String>
    val priorityMarks = raw["priority_marks"] as Map<String, String>
    val flashMs = (raw["flash_ms"] as Number).toInt()
    val presets = (raw["presets"] as Map<String, Map<String, Any?>>).mapValues { (_, p) ->
        p.mapValues { (_, v) -> if (v is Long) v.toInt() else v } }
    val presetLabels = raw["preset_labels"] as Map<String, String>
    val languages = raw["languages"] as List<String>
    val languageNames = raw["language_names"] as Map<String, String>
    val systemLanguage = raw["system_language"] as String

    companion object {
        @Volatile private var cached: CoreData? = null

        fun load(): CoreData = cached ?: synchronized(this) {
            cached ?: run {
                val stream = CoreData::class.java.getResourceAsStream("/camalert/core.json")
                    ?: throw IllegalStateException("camalert/core.json missing (run tools/export_contract.py update)")
                CoreData(Json.obj(stream.use { String(it.readBytes(), Charsets.UTF_8) })).also { cached = it }
            }
        }
    }
}

/** One setting of the shared schema (core/camalert_core/schema.py). */
class Setting(m: Map<String, Any?>) {
    val id = m["id"] as String
    val section = m["section"] as String
    val level = m["level"] as String
    val type = m["type"] as String
    val default: Any? = m["default"].let { if (it is Long) it.toInt() else it }
    val min = (m["min"] as? Number)?.toInt()
    val max = (m["max"] as? Number)?.toInt()
    val step = (m["step"] as? Number)?.toInt()
    val unit = m["unit"] as String?
    @Suppress("UNCHECKED_CAST")
    val choices = m["choices"] as List<String>?
    val label = m["label"] as String?
    val help = m["help"] as String?

    /** The value as this setting's type, or IllegalArgumentException (schema.coerce). */
    fun coerce(value: Any?): Any {
        when (type) {
            "bool" -> {
                if (value is Boolean) return value
                val t = value.toString().trim().lowercase()
                if (t in listOf("true", "1", "yes", "on")) return true
                if (t in listOf("false", "0", "no", "off", "")) return false
                throw IllegalArgumentException(t)
            }
            "int" -> {
                val n = value.toString().trim().toDoubleOrNull()?.toInt() ?: throw IllegalArgumentException("$value")
                if ((min != null && n < min) || (max != null && n > max)) throw IllegalArgumentException("$value")
                return n
            }
            "choice" -> {
                val v = value.toString().trim()
                if (v !in choices!!) throw IllegalArgumentException(v)
                return v
            }
            "time" -> {
                val p = value.toString().trim().split(":")
                if (p.size != 2 || p.any { it.isEmpty() || !it.all { c -> c.isDigit() } }) throw IllegalArgumentException("$value")
                val h = p[0].toInt()
                val mi = p[1].toInt()
                if (h !in 0..23 || mi !in 0..59) throw IllegalArgumentException("$value")
                return String.format(java.util.Locale.ROOT, "%02d:%02d", h, mi)
            }
            "password" -> return value?.toString() ?: ""
            else -> return value?.toString()?.trim() ?: ""
        }
    }
}

object Schema {
    /** (clean values, problems): every setting with a valid value; broken or missing ones get the default. */
    fun validate(values: Map<String, Any?>, data: CoreData = CoreData.load()): Pair<Map<String, Any?>, List<String>> {
        val clean = LinkedHashMap<String, Any?>()
        val problems = ArrayList<String>()
        for (s in data.settings) {
            if (s.id !in values) {
                clean[s.id] = s.default
                continue
            }
            try {
                clean[s.id] = s.coerce(values[s.id])
            } catch (e: Exception) {
                clean[s.id] = s.default
                problems.add(s.id)
            }
        }
        return Pair(clean, problems)
    }
}
