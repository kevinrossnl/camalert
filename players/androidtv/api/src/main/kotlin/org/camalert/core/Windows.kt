// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

/**
 * Several photo windows at the same time, each with its own id (#87, core windows.py). The normal window (id "")
 * always keeps the corner (place 0); a window with an id takes the next free place 1..maxWindows-1, and when all
 * are taken the oldest id window of the lowest priority makes room. maxWindows 1 = no id windows.
 */
object Windows {
    const val DEFAULT_MAX = 2
    private val ID = Regex("^[A-Za-z0-9_.-]{1,32}$")
    val RANK = mapOf("low" to 0, "normal" to 1, "high" to 2, "alarm" to 3)

    /** null (no id) or a valid window id; IllegalArgumentException otherwise. */
    fun idParam(value: Any?): String? {
        if (value == null) return null
        val t = value.toString().trim()
        if (t.isEmpty()) return null
        require(ID.matches(t)) { "invalid window id" }
        return t
    }

    /** A valid id or null, never an exception (MQTT payloads). */
    fun idOrNull(value: Any?): String? = if (value is String) try { idParam(value) } catch (e: IllegalArgumentException) { null } else null

    fun maxWindows(value: Any?): Int {
        val n = when (value) { is Number -> value.toInt(); is String -> value.trim().toIntOrNull(); else -> null } ?: return DEFAULT_MAX
        return n.coerceIn(1, 3)
    }
}

class WindowSlots(limit: Int = Windows.DEFAULT_MAX) {
    var limit: Int = Windows.maxWindows(limit)
        set(v) { field = Windows.maxWindows(v) }
    private data class Entry(val slot: Int, val rank: Int, val seq: Int)
    private val open = LinkedHashMap<String, Entry>()
    private var seq = 0

    /** Triple(slot, evicted id or null, existing). */
    @Synchronized
    fun place(id: String?, priority: String = "normal"): Triple<Int, String?, Boolean> {
        val wid = if (!id.isNullOrEmpty() && limit > 1) id else ""
        seq++
        val rank = Windows.RANK[priority] ?: 1
        open[wid]?.let { e ->
            open[wid] = Entry(e.slot, maxOf(rank, e.rank), seq)
            return Triple(e.slot, null, true)
        }
        var evicted: String? = null
        val slot: Int
        if (wid.isEmpty()) {
            slot = 0
        } else {
            val used = open.filterKeys { it.isNotEmpty() }.values.map { it.slot }.toSet()
            val free = (1 until limit).firstOrNull { it !in used }
            if (free != null) {
                slot = free
            } else {
                evicted = open.filterKeys { it.isNotEmpty() }.minWithOrNull(compareBy({ it.value.rank }, { it.value.seq }))!!.key
                slot = open.remove(evicted)!!.slot
            }
        }
        open[wid] = Entry(slot, rank, seq)
        return Triple(slot, evicted, false)
    }

    @Synchronized fun remove(id: String?) { open.remove(id ?: "") }
    @Synchronized fun clear() = open.clear()
    @Synchronized fun slot(id: String?): Int? = open[id ?: ""]?.slot
    @Synchronized fun ids(): List<String> = open.entries.sortedBy { it.value.slot }.map { it.key }
}
