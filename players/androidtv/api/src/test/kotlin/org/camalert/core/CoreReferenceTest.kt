// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** The Kotlin port gives the same answers as the Python core (reference answers in contract/core.json). */
@Suppress("UNCHECKED_CAST")
class CoreReferenceTest {
    private val ref = Exported.core
    private fun cases(name: String) = ref[name] as List<Map<String, Any?>>

    @Test
    fun privacy() {  // #11
        @Suppress("UNCHECKED_CAST")
        val p = ref["privacy"] as Map<String, List<Map<String, Any?>>>
        for (c in p.getValue("parse_masks")) {
            val got = Privacy.parseMasks(c["text"] as String).mapValues { (_, v) -> v.map { listOf(it.x0, it.y0, it.x1, it.y1) } }
            val want = (c["out"] as Map<*, *>).entries.associate { (k, v) ->
                k.toString() to (v as List<*>).map { b -> (b as List<*>).map { (it as Number).toDouble() } } }
            assertEquals("parse_masks(${c["text"]})", want, got)
        }
        for (c in p.getValue("mask_rects")) {
            val box = (c["box"] as List<*>).map { (it as Number).toInt() }.toIntArray()
            val size = (c["size"] as List<*>).map { (it as Number).toInt() }
            val got = Privacy.maskRects(c["name"] as String, Privacy.parseMasks(c["text"] as String), box, size[0], size[1]).map { it.toList() }
            val want = (c["out"] as List<*>).map { r -> (r as List<*>).map { (it as Number).toInt() } }
            assertEquals("mask_rects($c)", want, got)
        }
        for (c in p.getValue("guest_hidden")) {
            assertEquals("guest_hidden($c)", c["out"], Privacy.guestHidden(c["name"] as String, c["on"] as Boolean, c["text"] as String))
        }
    }

    @Test
    fun redact() {
        for (c in cases("redact")) assertEquals("redact(${c["in"]})", c["out"], Obs.redact(c["in"] as String))
    }

    @Test
    fun urlTarget() {
        for (c in cases("url_target")) {
            assertEquals("url_target(${c["url"]})", c["why"], Access.urlTarget(c["url"] as String, c["caller"] as String?, Exported::resolve))
        }
    }

    @Test
    fun lanAddressAndLocalNames() {
        for (c in cases("lan_address")) assertEquals("lan_address(${c["ip"]})", c["lan"], Access.lanAddress(c["ip"] as String))
        for (c in cases("local_name")) assertEquals("local_name(${c["host"]})", c["local"], Access.localName(c["host"] as String))
    }

    @Test
    fun discovery() {  // #121: the same announcement as the Python players
        for (c in cases("discovery")) {
            val a = c["args"] as List<Any?>
            val got = Discovery.serviceInfo(a[0] as String, a[1] as String, a[2] as String, a[3] as String,
                (a[4] as Number).toInt(), (a[5] as Number).toInt(), a[6] as Boolean)
            assertEquals("discovery(${a[0]})", Json.write(c["info"]), Json.write(got))
            val adv = listOf(Pair(true, "lan"), Pair(true, "any"), Pair(false, "lan"), Pair(true, "x"))
                .map { Discovery.shouldAdvertise(mapOf("enabled" to it.first, "allow" to it.second)) }
            assertEquals(c["advertise"], adv)
        }
    }

    @Test
    fun parameters() {
        for (c in cases("clamp_seconds")) {
            assertEquals("clamp_seconds(${c["value"]})", (c["out"] as Number).toInt(), Rules.clampSeconds(c["value"], (c["default"] as Number).toInt()))
        }
        for (c in cases("show_seconds")) {  // #81: 0 = until hide
            assertEquals("show_seconds(${c["value"]})", (c["out"] as Number).toInt(), Rules.showSeconds(c["value"], (c["default"] as Number).toInt()))
            assertEquals("has_seconds(${c["value"]})", c["has"], Rules.hasSeconds(c["value"]))
        }
        for (c in cases("has_seconds")) {
            assertEquals("has_seconds(${c["value"]})", c["has"], Rules.hasSeconds(c["value"]))
        }
        for (c in cases("cameras_param")) {
            val got = try { mapOf("ok" to Api.camerasParam(c["value"] as String)) } catch (e: Invalid) { mapOf("error" to e.message) }
            assertEquals("cameras_param(${c["value"]})", Json.write(c["out"]), Json.write(got))
        }
        for (c in cases("parse_body")) {
            val got = try { mapOf("ok" to Api.parseBody(c["content_type"] as String, (c["body"] as String).toByteArray()).toSortedMap()) } catch (e: Invalid) { mapOf("error" to e.message) }
            assertEquals("parse_body(${c["body"]})", Json.write(c["out"], true), Json.write(got, true))
        }
        for (c in cases("caller_source")) assertEquals(c["source"], Events.callerSource(c["ua"] as String))
    }

    @Test
    fun syslogLinesAndTargets() {
        for (c in cases("syslog_line")) {
            val a = c["args"] as List<Any?>
            assertEquals(c["out"], Obs.syslogLine(a[0] as String, a[1] as String, a[2] as String?, (a[3] as Number).toDouble()))
        }
        for (c in cases("with_cache")) {
            assertEquals("with_cache(${c["url"]})", c["out"], Urls.withCache(c["url"] as String?, (c["seconds"] as Number).toInt()))
        }
        for (c in cases("parse_hostport")) {
            assertEquals("parse_hostport(${c["in"]})", Json.write(c["out"]), Json.write(Obs.parseHostPort(c["in"] as String?)?.toList()))
        }
    }

    @Test
    fun actionMenuLikeTheCore() {  // #118
        val p = Present()
        for (c in cases("action_menu")) {
            val got = p.actionMenu(c["has_ptz"] as Boolean, c["ptz_key"] as String?, c["ha_buttons"] as Boolean)
            val what = "has_ptz=${c["has_ptz"]} ptz_key=${c["ptz_key"]} ha_buttons=${c["ha_buttons"]}"
            assertEquals(what, Json.write(c["out"]), Json.write(got.map { listOf(it.first, it.second) }))
            assertEquals(what, c["labels"], got.map { p.actionLabel(it.first, it.second) })
        }
    }

    @Test
    fun keyHintsComeFromTheCoreKeyMap() {
        val p = Present()
        for (c in cases("key_hints")) {
            val got = p.keyHint(c["context"] as String, c["ptz_key"] as String?, c["has_ptz"] as Boolean, c["glyphs"] as Boolean)
            assertEquals("${c["context"]} ptz_key=${c["ptz_key"]} has_ptz=${c["has_ptz"]} glyphs=${c["glyphs"]}", c["hint"], got)
        }
    }

    @Test
    fun geometry() {
        for (c in cases("geometry")) {
            val a = c["args"] as List<Any?>
            fun i(k: Int) = (a[k] as Number).toInt()
            val got: Any = when (c["kind"]) {
                "window" -> Layout.window(a[0] as String, a[1] as String, i(2), i(3), a[4] as String).let { listOf(it.x, it.y, it.w, it.h, it.title) }
                "strip" -> Layout.strip(i(0), a[1] as String, a[2] as String, a[3] as String, i(4), i(5)).let { w ->
                    listOf(w.x, w.y, w.w, w.h, w.title, w.tiles.map { listOf(it.x, it.y, it.w, it.h) }) }
                "grid" -> Layout.grid(i(0), i(1), i(2)).map { listOf(it.x, it.y, it.w, it.h) }
                "window_text" -> Layout.window(a[0] as String, a[1] as String, i(2), i(3), a[4] as String, a[5] as String).let { listOf(it.x, it.y, it.w, it.h, it.title) }
                "strip_text" -> Layout.strip(i(0), a[1] as String, a[2] as String, a[3] as String, i(4), i(5), a[6] as String).let { w ->
                    listOf(w.x, w.y, w.w, w.h, w.title, w.tiles.map { listOf(it.x, it.y, it.w, it.h) }) }
                "title_font_text" -> Layout.titleFont(a[0] as String, i(1), a[2] as String)
                else -> Layout.titleFont(a[0] as String, i(1))
            }
            assertEquals("${c["kind"]} $a", Json.write(c["out"]), Json.write(got))
        }
    }

    @Test
    fun style() {  // #48, #10
        fun sorted(m: Any?): String = Json.write((m as Map<String, Any?>?)?.let { java.util.TreeMap(it.mapValues { (_, v) -> if (v is Number) v.toLong() else v }) })
        val s = ref["style"] as Map<String, List<Map<String, Any?>>>
        for (c in s.getValue("marked_title")) {
            val a = c["args"] as List<String>
            assertEquals("$a", c["out"], Style.markedTitle(a[0], a[1], a[2]) { it })
        }
        for (c in s.getValue("priority_mark")) {
            val a = c["args"] as List<String>
            val got = Style.priorityMark(a[0], a[1])?.let { mapOf("colour" to it.colour, "label" to it.label, "flash" to it.flash) }
            assertEquals("$a", sorted(c["out"]), sorted(got))
        }
        for (c in s.getValue("preset_changes")) {
            val a = c["args"] as List<Any?>
            val got = Style.presetChanges(a[0] as String, (a[1] as Map<String, Any?>).mapValues { (_, v) -> if (v is Long) v.toInt() else v }, a[2] as List<String>?)
            assertEquals("$a", sorted(c["out"]), sorted(got))
        }
        for (c in s.getValue("effective_language")) {
            val a = c["args"] as List<String>
            assertEquals("$a", c["out"], Style.effectiveLanguage(a[0], a[1]))
        }
    }

    @Test
    fun metricsText() {
        for (c in cases("metrics")) {
            val m = (c["metrics"] as Map<String, List<Any?>>).mapValues { (_, v) -> Obs.Metric(v[0] as String, v[1] as String, v[2]!!) }
            assertEquals(c["text"], Obs.metricsText(m, c["labels"] as Map<String, String>?))
        }
    }

    @Test
    fun settingsValidation() {
        for (c in cases("settings")) {
            val (clean, problems) = Schema.validate(c["values"] as Map<String, Any?>)
            assertEquals(Json.write(c["clean"], true), Json.write(clean, true))
            assertEquals(c["problems"], problems.sorted())
        }
    }

    @Test
    fun runtimeDataMatchesTheSchema() {
        val d = CoreData.load()
        assertTrue(d.capabilities.containsAll(listOf("post", "header_token", "show", "status")))
        assertEquals(1, d.apiVersion)
        val ids = d.settings.map { it.id }
        assertEquals(ids.size, ids.toSet().size)
        for (s in d.settings) {
            assertEquals(s.id, s.default, s.coerce(s.default))
            assertTrue(s.id, s.level in d.levels && s.section in d.sections)
        }
        // the basic level of the UI guideline (#2); the go2rtc/direct choice is on Android TV too since #124
        assertEquals(setOf("enabled", "source", "server", "camera", "mode", "duration", "position", "size", "dnd", "limit_hours", "from_time", "until_time"),
            d.settings.filter { it.level == "basic" }.map { it.id }.toSet())
    }
}
