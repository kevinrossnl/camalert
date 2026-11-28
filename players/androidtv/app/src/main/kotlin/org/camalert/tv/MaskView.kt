// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.tv

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.view.View
import org.camalert.core.Privacy
import java.util.concurrent.ConcurrentHashMap

/**
 * Privacy masks (#11): black boxes over one camera picture or the live video, as large as the view under it. The
 * picture or video is drawn centred with its aspect ratio kept (FIT_CENTER / the player's FIT mode), so the boxes
 * follow Privacy.maskRects with the picture size; without a known size the camera's last picture, else 16:9.
 */
class MaskView(ctx: Context, private val settings: () -> Map<String, Any?>) : View(ctx) {
    private var camera: String? = null
    private var imageW = 0
    private var imageH = 0
    private val paint = Paint().apply { color = Color.BLACK; style = Paint.Style.FILL }

    /** The camera shown under this view now and the size of its picture (0 = not known: last size or 16:9). */
    fun show(name: String, w: Int = 0, h: Int = 0) {
        camera = name
        if (w > 0 && h > 0) {
            imageW = w; imageH = h
            SIZES[name] = Pair(w, h)
        } else {
            val last = SIZES[name] ?: Pair(16, 9)
            imageW = last.first; imageH = last.second
        }
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        val name = camera ?: return
        val masks = masks(settings()["privacy_masks"]?.toString())
        for (r in Privacy.maskRects(name, masks, intArrayOf(0, 0, width, height), imageW, imageH)) {
            canvas.drawRect(r[0].toFloat(), r[1].toFloat(), (r[0] + r[2]).toFloat(), (r[1] + r[3]).toFloat(), paint)
        }
    }

    companion object {
        /** camera -> size of its last picture: where the boxes go over live video. */
        val SIZES = ConcurrentHashMap<String, Pair<Int, Int>>()
        @Volatile private var cached: Pair<String, Map<String, List<Privacy.Box>>> = Pair("", emptyMap())

        fun masks(text: String?): Map<String, List<Privacy.Box>> {
            val t = text ?: ""
            val c = cached
            if (c.first == t) return c.second
            val parsed = Privacy.parseMasks(t)
            cached = Pair(t, parsed)
            return parsed
        }
    }
}
