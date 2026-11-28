// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

/** Window and tile geometry, designed for 1920x1080 and scaled to the screen (core layout.py). */
object Layout {
    data class Rect(val x: Int, val y: Int, val w: Int, val h: Int)
    data class Window(val x: Int, val y: Int, val w: Int, val h: Int, val title: Int, val tiles: List<Rect> = emptyList())

    private val SIZES = mapOf("small" to Pair(480, 270), "medium" to Pair(640, 360), "large" to Pair(960, 540))
    private val TITLE_SIZES = mapOf("small" to Pair(32, 22), "normal" to Pair(40, 26), "large" to Pair(56, 38))

    /** Factor for every font and the title bar (#48, core layout.TEXT_SIZES); 1.0 for an unknown value. */
    fun textScale(textSize: String?): Double = CoreData.load().textSizes[textSize] ?: 1.0

    /** A font size designed at 1080p, scaled to the screen and the text size (#48). */
    fun fontPx(px1080: Int, screenW: Int, textSize: String? = "normal") = (px1080 * screenW / 1920.0 * textScale(textSize)).toInt()

    fun titleFont(titleSize: String, screenW: Int, textSize: String? = "normal") =
        fontPx((TITLE_SIZES[titleSize] ?: TITLE_SIZES.getValue("normal")).second, screenW, textSize)

    private fun left(p: String) = p == "top_left" || p == "bottom_left"
    private fun top(p: String) = p == "top_left" || p == "top_right"

    /** slot > 0 (#87): the next place from the corner towards the centre (core layout.slot_position). */
    fun window(position: String, size: String, sw: Int, sh: Int, titleSize: String = "normal", textSize: String? = "normal", slot: Int = 0): Window {
        val f = sw / 1920.0
        val (w0, h0) = SIZES[size] ?: SIZES.getValue("medium")
        val w = (w0 * f).toInt()
        val h = (h0 * f).toInt()
        val title = ((TITLE_SIZES[titleSize] ?: TITLE_SIZES.getValue("normal")).first * f * textScale(textSize)).toInt()
        val margin = (40 * f).toInt()
        val x = if (left(position)) margin else sw - w - margin
        val y = if (top(position)) margin else sh - (h + title) - margin
        if (slot > 0) {
            val (sx, sy) = slotPosition(slot, position, x, y, w, h + title, sw, sh, margin, (16 * f).toInt())
            return Window(sx, sy, w, h, title)
        }
        return Window(x, y, w, h, title)
    }

    fun slotPosition(slot: Int, position: String, x: Int, y: Int, w: Int, totalH: Int, sw: Int, sh: Int, margin: Int, gap: Int): Pair<Int, Int> {
        val rows = maxOf(1, Math.floorDiv(sh - 2 * margin + gap, totalH + gap))
        val col = Math.floorDiv(slot, rows)
        val row = Math.floorMod(slot, rows)
        val ny = if (top(position)) y + row * (totalH + gap) else y - row * (totalH + gap)
        val nx = if (left(position)) x + col * (w + gap) else x - col * (w + gap)
        return Pair(maxOf(0, minOf(nx, sw - w)), maxOf(0, minOf(ny, sh - totalH)))
    }

    fun grid(n: Int, sw: Int, sh: Int, gap: Int = 8): List<Rect> {
        val cols = if (n <= 1) 1 else if (n <= 4) 2 else 3
        val rows = (n + cols - 1) / cols
        var w = Math.floorDiv(sw - gap * (cols + 1), cols)
        var h = Math.floorDiv(w * 9, 16)
        if (h * rows + gap * (rows + 1) > sh) {
            h = Math.floorDiv(sh - gap * (rows + 1), rows)
            w = Math.floorDiv(h * 16, 9)
        }
        val x0 = Math.floorDiv(sw - (w * cols + gap * (cols - 1)), 2)
        val y0 = Math.floorDiv(sh - (h * rows + gap * (rows - 1)), 2)
        return (0 until n).map { Rect(x0 + (it % cols) * (w + gap), y0 + (it / cols) * (h + gap), w, h) }
    }

    fun stripLayout(n: Int, layout: String) = if (layout in listOf("vertical", "horizontal", "grid")) layout else if (n >= 4) "grid" else "vertical"

    fun strip(n0: Int, layout: String, position: String, size: String, sw: Int, sh: Int, textSize: String? = "normal"): Window {
        val n = n0.coerceIn(1, 4)
        val (cols, rows) = when (stripLayout(n, layout)) { "vertical" -> Pair(1, n); "horizontal" -> Pair(n, 1); else -> Pair(2, (n + 1) / 2) }
        val f = sw / 1920.0
        val (tw0, th0) = SIZES[size] ?: SIZES.getValue("medium")
        var tw = (tw0 * f).toInt()
        var th = (th0 * f).toInt()
        val gap = maxOf(2, (6 * f).toInt())
        val title = (40 * f * textScale(textSize)).toInt()
        val margin = (40 * f).toInt()
        val maxW = (sw * 0.9).toInt() - margin
        val maxH = (sh * 0.9).toInt() - margin
        val scale = minOf(1.0, (maxW - gap * (cols - 1)) / (tw * cols).toDouble(), (maxH - title - gap * (rows - 1)) / (th * rows).toDouble())
        tw = (tw * scale).toInt()
        th = (th * scale).toInt()
        val w = tw * cols + gap * (cols - 1)
        val h = th * rows + gap * (rows - 1)
        val x = if (left(position)) margin else sw - w - margin
        val y = if (top(position)) margin else sh - h - title - margin
        return Window(x, y, w, h, title, (0 until n).map { Rect((it % cols) * (tw + gap), title + (it / cols) * (th + gap), tw, th) })
    }
}
