// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

/**
 * Privacy masks per camera and guest mode (#11), the same as camalert_core.privacy: masks are rectangles in 0..1 of
 * the camera picture ("garden=0,0,0.3,0.5+0.7,0,1,0.4|front_door=0.6,0.6,1,1"), drawn as black boxes over every
 * CamAlert picture of that camera and over its live video. Guest mode hides cameras (empty list = all).
 */
object Privacy {
    const val MAX_MASKS = 8
    const val GUEST = "guest"

    data class Box(val x0: Double, val y0: Double, val x1: Double, val y1: Double)

    private fun num(t: String): Double {
        val v = t.trim().replace(',', '.').toDouble()
        if (v.isNaN() || v.isInfinite()) throw NumberFormatException(t)
        return v.coerceIn(0.0, 1.0)
    }

    fun parseMasks(text: String?): Map<String, List<Box>> {
        val out = LinkedHashMap<String, MutableList<Box>>()
        for (part in (text ?: "").split("|")) {
            val eq = part.indexOf('=')
            if (eq < 0) continue
            val name = part.substring(0, eq).trim()
            if (name.isEmpty()) continue
            val boxes = out[name] ?: mutableListOf()
            for (r in part.substring(eq + 1).replace(";", "+").split("+")) {
                val nums = r.replace(" ", "").split(",")
                if (nums.size != 4) continue
                val v = try { nums.map { num(it) } } catch (e: NumberFormatException) { continue }
                val x0 = minOf(v[0], v[2]); val x1 = maxOf(v[0], v[2])
                val y0 = minOf(v[1], v[3]); val y1 = maxOf(v[1], v[3])
                if (x1 > x0 && y1 > y0) boxes.add(Box(x0, y0, x1, y1))
            }
            if (boxes.isNotEmpty()) out[name] = boxes.take(MAX_MASKS).toMutableList()
        }
        return out
    }

    /** [x, y, w, h] where a picture of imageW x imageH is drawn in the box, aspect kept and centred. */
    fun fitRect(box: IntArray, imageW: Int = 0, imageH: Int = 0): IntArray {
        val (x, y, w, h) = box.toList()
        if (imageW <= 0 || imageH <= 0 || w <= 0 || h <= 0) return intArrayOf(x, y, w, h)
        val scale = minOf(w.toDouble() / imageW, h.toDouble() / imageH)
        val dw = Math.round(imageW * scale).toInt(); val dh = Math.round(imageH * scale).toInt()
        return intArrayOf(x + Math.floorDiv(w - dw, 2), y + Math.floorDiv(h - dh, 2), dw, dh)
    }

    /** Pixel rectangles [x, y, w, h] to cover for camera `name` drawn in box; rounded outwards. */
    fun maskRects(name: String, masks: Map<String, List<Box>>, box: IntArray, imageW: Int = 0, imageH: Int = 0): List<IntArray> {
        val boxes = masks[name] ?: return emptyList()
        val (fx, fy, fw, fh) = fitRect(box, imageW, imageH).toList()
        val out = ArrayList<IntArray>()
        for (b in boxes) {
            val a = Math.floor(fx + b.x0 * fw).toInt(); val c0 = Math.floor(fy + b.y0 * fh).toInt()
            val c = minOf(Math.ceil(fx + b.x1 * fw).toInt(), fx + fw); val d = minOf(Math.ceil(fy + b.y1 * fh).toInt(), fy + fh)
            if (c > a && d > c0) out.add(intArrayOf(a, c0, c - a, d - c0))
        }
        return out
    }

    fun guestCameras(text: String?): Set<String> =
        (text ?: "").replace(",", "|").replace(" ", "|").split("|").map { it.trim() }.filter { it.isNotEmpty() }.toSet()

    fun guestHidden(name: String, guestOn: Boolean, guestText: String?): Boolean {
        if (!guestOn) return false
        val cams = guestCameras(guestText)
        return cams.isEmpty() || name in cams
    }

    fun guestVisible(names: List<String>, guestOn: Boolean, guestText: String?): List<String> =
        names.filter { !guestHidden(it, guestOn, guestText) }
}
