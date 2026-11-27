// CamAlert for Android TV. Copyright (C) 2026 CamAlert developers. GPL v2.
package org.camalert.tv

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.graphics.Matrix
import android.graphics.PixelFormat
import android.graphics.Typeface
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.util.DisplayMetrics
import android.util.TypedValue
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.TextView
import androidx.media3.common.MediaItem
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.hls.HlsMediaSource
import androidx.media3.exoplayer.rtsp.RtspMediaSource
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import androidx.media3.ui.PlayerView
import org.camalert.core.Cameras
import org.camalert.core.Display
import org.camalert.core.Layout
import org.camalert.core.Present
import org.camalert.core.Screen
import org.camalert.core.Tile
import java.util.concurrent.atomic.AtomicBoolean

/**
 * The screen of the Android TV player: windows drawn over every app with SYSTEM_ALERT_WINDOW
 * (TYPE_APPLICATION_OVERLAY on Android 8+, TYPE_PHONE on 7.1 / Fire OS 6).
 *
 *     photo     one camera in a corner (photo window); 2-4 cameras = multi-camera window ("strip")
 *     notify    a small corner window without keys
 *     live      the camera full screen (Media3 ExoPlayer, muted unless live_volume > 0)
 *     mosaic    up to 9 cameras full screen
 *     tour      one camera after the other, full screen
 *
 * Only one window at a time. The Display methods are called from any thread: the state is updated at once (the
 * controller reads it right after), the views are built on the main thread.
 */
class Overlay(private val ctx: Context, private val host: Host) : Display {
    interface Host {
        fun settings(): Map<String, Any?>
        val present: Present
        val tr: Tr
        fun show(stream: String, mode: String, priority: String, source: String)
        fun neighbour(current: String?, step: Int): Tile?
        fun colourKey(camera: String?, colour: String)
        fun unreachable()
        fun changed()
    }

    private val main = Handler(Looper.getMainLooper())
    private val wm = ctx.getSystemService(Context.WINDOW_SERVICE) as WindowManager
    @Volatile private var state = Screen(null, null)
    private var win: Win? = null  // main thread only

    override fun screen() = state

    fun allowed() = Settings.canDrawOverlays(ctx)

    // --- Display -----------------------------------------------------------------------------------------------------
    override fun photo(tiles: List<Tile>, seconds: Int, label: String?) {
        state = Screen(if (tiles.size > 1) "strip" else "photo", tiles[0].name, tiles.map { it.name })
        main.post { open(PhotoWin(tiles, seconds, label)) }
    }

    override fun extend(seconds: Int) {
        main.post { win?.extend(seconds) }
    }

    override fun notify(tile: Tile, seconds: Int) {
        state = Screen("notify", tile.name, listOf(tile.name))
        main.post { open(PhotoWin(listOf(tile), seconds, null, notify = true)) }
    }

    override fun live(tile: Tile, seconds: Int, volumePercent: Int) {
        state = Screen("live", tile.name, listOf(tile.name))
        main.post { open(LiveWin(tile, seconds, volumePercent)) }
    }

    override fun mosaic(tiles: List<Tile>, seconds: Int) {
        state = Screen("mosaic", null, tiles.map { it.name })
        main.post { open(MosaicWin(tiles, seconds)) }
    }

    override fun tour(tiles: List<Tile>, interval: Int) {
        state = Screen("tour", tiles[0].name, tiles.map { it.name })
        main.post { open(TourWin(tiles, interval)) }
    }

    override fun hide() {
        state = Screen(null, null)
        main.post { close() }
    }

    // --- windows -------------------------------------------------------------------------------------------------------
    private fun open(w: Win) {
        close()
        if (!allowed()) {
            CamLog.log("cannot show the camera: CamAlert may not draw over other apps (adb shell appops set " +
                ctx.packageName + " SYSTEM_ALERT_WINDOW allow)", "error")
            state = Screen(null, null)
            host.changed()
            return
        }
        win = w
        try {
            w.attach()
        } catch (e: Exception) {
            CamLog.log("overlay failed: $e", "error")
            win = null
            state = Screen(null, null)
        }
        host.changed()
    }

    private fun close() {
        val w = win ?: return
        win = null
        w.detach()
    }

    /** Called by a window that closes itself (timeout, BACK). */
    private fun closed(w: Win) {
        if (win !== w) return
        win = null
        w.detach()
        state = Screen(null, null)
        host.changed()
    }

    private fun metrics(): DisplayMetrics {
        val m = DisplayMetrics()
        @Suppress("DEPRECATION") wm.defaultDisplay.getRealMetrics(m)
        return m
    }

    private fun text(size: Float, bold: Boolean = false) = TextView(ctx).apply {
        setTextColor(Color.WHITE)
        setTextSize(TypedValue.COMPLEX_UNIT_PX, size)
        if (bold) typeface = Typeface.DEFAULT_BOLD
        maxLines = 1
        setPadding((size / 3).toInt(), 0, (size / 3).toInt(), 0)
        gravity = Gravity.CENTER_VERTICAL
    }

    /** A window: its root view, the key handling and timers. */
    private abstract inner class Win(val takesKeys: Boolean) {
        val root = object : FrameLayout(ctx) {
            override fun dispatchKeyEvent(event: KeyEvent): Boolean {
                if (!takesKeys) return super.dispatchKeyEvent(event)
                val name = KeyNames.of(event.keyCode)
                if (event.action == KeyEvent.ACTION_DOWN && event.repeatCount == 0) return onKey(name, event.keyCode)
                return name != null && !passKey(name) || event.keyCode == KeyEvent.KEYCODE_BACK
            }
        }
        val stop = AtomicBoolean(false)
        private val timeout = Runnable { closed(this) }
        val loaders = ArrayList<Thread>()
        abstract val context: String
        abstract fun build(m: DisplayMetrics): WindowManager.LayoutParams
        abstract fun key(action: String?, name: String?): Boolean

        fun attach() {
            val m = metrics()
            val lp = build(m)
            wm.addView(root, lp)
            if (takesKeys) {
                root.isFocusable = true
                root.isFocusableInTouchMode = true
                root.requestFocus()
            }
        }

        open fun detach() {
            stop.set(true)
            main.removeCallbacks(timeout)
            loaders.forEach { it.interrupt() }
            try { wm.removeView(root) } catch (e: Exception) { }
        }

        fun extend(seconds: Int) {
            main.removeCallbacks(timeout)
            if (seconds > 0) main.postDelayed(timeout, seconds * 1000L)
        }

        fun passKey(name: String) = host.present.actionFor(context, name) == "pass"

        fun onKey(name: String?, code: Int): Boolean {
            if (name != null && passKey(name)) return false
            if (name != null && name in KeyNames.COLOURS) {
                host.colourKey(state.stream, KeyNames.COLOURS.getValue(name))
                return true
            }
            val action = host.present.actionFor(context, name)
            if (key(action, name)) return true
            if (code == KeyEvent.KEYCODE_HOME) return false
            closed(this)  // a key that is not ours closes the window (like on the other players)
            return true
        }

        fun params(x: Int, y: Int, w: Int, h: Int): WindowManager.LayoutParams {
            @Suppress("DEPRECATION")
            val type = if (Build.VERSION.SDK_INT >= 26) WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY else WindowManager.LayoutParams.TYPE_PHONE
            var flags = WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL or
                WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON
            if (!takesKeys) flags = flags or WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE
            return WindowManager.LayoutParams(w, h, type, flags, PixelFormat.TRANSLUCENT).apply {
                gravity = Gravity.TOP or Gravity.START
                this.x = x
                this.y = y
                title = "CamAlert"
            }
        }

        fun hintBar(m: DisplayMetrics, parent: ViewGroup, x: Int, y: Int, w: Int, h: Int, ptz: Boolean = false): TextView {
            val tv = text(Layout.titleFont("small", m.widthPixels).toFloat())
            tv.setBackgroundColor(0x99000000.toInt())
            tv.text = host.present.keyHint(context, null, ptz)
            parent.addView(tv, FrameLayout.LayoutParams(w, h).apply { leftMargin = x; topMargin = y })
            return tv
        }

        /** Loads the snapshot of a tile again and again into view (its own interval, at least 1 s on a TV stick). */
        fun load(tile: Tile, view: ImageView, error: TextView, width: Int) {
            val s = host.settings()
            val refresh = Cameras.parseRefresh(s["refresh"]?.toString())[tile.name] ?: 1.0
            val orientation = Cameras.parseOrientation(s["orientation"]?.toString())[tile.name]
            val verify = s["verify_ssl"] != false
            val url = tile.snapshot?.replace(Regex("width=\\d+"), "width=" + width.coerceIn(160, 1920)) ?: return
            val cache = org.camalert.core.CoreData.load().frameCacheSeconds
            val t = Thread({
                var failed = false
                var first = true  // #110: the first picture may come from go2rtc's cache
                while (!stop.get()) {
                    try {
                        val bytes = Net.fetch(if (first) org.camalert.core.Urls.withCache(url, cache)!! else url, verify, 6000)
                        first = false
                        val bmp = BitmapFactory.decodeByteArray(bytes, 0, bytes.size) ?: throw java.io.IOException("not an image")
                        val shown = orient(bmp, orientation)
                        main.post { if (!stop.get()) { view.setImageBitmap(shown); error.visibility = View.GONE } }
                        failed = false
                    } catch (e: InterruptedException) {
                        break
                    } catch (e: Exception) {
                        if (!failed) {
                            CamLog.log("camera ${tile.name} not reachable: ${e.message}", "normal")
                            host.unreachable()
                        }
                        failed = true
                        main.post { if (!stop.get()) { error.text = host.tr(org.camalert.core.CoreData.load().tileLabels.getValue("unreachable")); error.visibility = View.VISIBLE } }
                    }
                    try { Thread.sleep((refresh * 1000).toLong().coerceAtLeast(500L) * (if (failed) 3 else 1)) } catch (e: InterruptedException) { break }
                }
            }, "camalert-snapshot-${tile.name}")
            t.isDaemon = true
            loaders.add(t)
            t.start()
        }

        fun tileView(parent: FrameLayout, tile: Tile, r: Layout.Rect, font: Float, label: Boolean): ImageView {
            val iv = ImageView(ctx).apply { scaleType = ImageView.ScaleType.FIT_CENTER; setBackgroundColor(Color.BLACK) }
            parent.addView(iv, FrameLayout.LayoutParams(r.w, r.h).apply { leftMargin = r.x; topMargin = r.y })
            if (label) {
                val l = text(font)
                l.text = tile.title
                l.setBackgroundColor(0x99000000.toInt())
                val lh = (font * 1.6f).toInt()
                parent.addView(l, FrameLayout.LayoutParams(r.w, lh).apply { leftMargin = r.x; topMargin = r.y + r.h - lh })
            }
            val err = text(font, true).apply {
                text = host.tr(org.camalert.core.CoreData.load().tileLabels.getValue("loading"))  // #110, until the first picture
                gravity = Gravity.CENTER
                setBackgroundColor(0xC0000000.toInt())
            }
            parent.addView(err, FrameLayout.LayoutParams(r.w, r.h).apply { leftMargin = r.x; topMargin = r.y })
            load(tile, iv, err, r.w)
            return iv
        }
    }

    private fun orient(bmp: Bitmap, how: String?): Bitmap {
        if (how == null) return bmp
        val m = Matrix()
        when (how) {
            "mirror" -> m.preScale(-1f, 1f)
            "flip" -> m.preScale(1f, -1f)
            "rot180" -> m.postRotate(180f)
        }
        return Bitmap.createBitmap(bmp, 0, 0, bmp.width, bmp.height, m, true)
    }

    // --- photo window, multi-camera window, notification ---------------------------------------------------------------
    private inner class PhotoWin(var tiles: List<Tile>, val seconds: Int, val label: String?, val notify: Boolean = false) :
        Win(!notify && host.settings()["window_keys"] != false) {
        override val context = "window"
        lateinit var title: TextView
        var image: ImageView? = null
        var errorView: TextView? = null

        override fun build(m: DisplayMetrics): WindowManager.LayoutParams {
            val s = host.settings()
            val pos = s["position"]?.toString() ?: "top_right"
            val size = if (notify) "small" else s["size"]?.toString() ?: "medium"
            val ts = s["title_size"]?.toString() ?: "normal"
            val font = Layout.titleFont(ts, m.widthPixels).toFloat()
            val hint = if (takesKeys) (font * 1.4f).toInt() else 0
            root.setBackgroundColor(0xFF202020.toInt())
            val g: Layout.Window
            val rects: List<Layout.Rect>
            if (tiles.size == 1) {
                g = Layout.window(pos, size, m.widthPixels, m.heightPixels, ts)
                rects = listOf(Layout.Rect(0, g.title, g.w, g.h))
            } else {
                g = Layout.strip(tiles.size, s["strip_layout"]?.toString() ?: "auto", pos, size, m.widthPixels, m.heightPixels)
                rects = g.tiles
            }
            title = text(font, true)
            title.text = if (tiles.size == 1) tiles[0].title else listOfNotNull(label, tiles.joinToString(" · ") { it.title }).joinToString(" · ")
            root.addView(title, FrameLayout.LayoutParams(g.w, g.title))
            for ((i, t) in tiles.withIndex()) {
                val iv = tileView(root, t, rects[i], font * 0.8f, tiles.size > 1)
                if (i == 0) {
                    image = iv
                    errorView = root.getChildAt(root.childCount - 1) as TextView
                }
            }
            val total = g.title + g.h
            if (hint > 0) hintBar(m, root, 0, total, g.w, hint)
            extend(seconds)
            val y = if (pos.startsWith("bottom")) g.y - hint else g.y
            return params(g.x, y, g.w, total + hint)
        }

        override fun key(action: String?, name: String?): Boolean {
            when (action) {
                "close" -> { closed(this); return true }
                "live" -> {
                    val cam = state.stream ?: return true
                    closed(this)
                    host.show(cam, "live", "high", "menu")
                    return true
                }
                "prev", "next" -> {
                    if (tiles.size != 1) return true
                    val t = host.neighbour(tiles[0].name, if (action == "next") 1 else -1) ?: return true
                    tiles = listOf(t)
                    state = Screen("photo", t.name, listOf(t.name))
                    title.text = t.title
                    loaders.forEach { it.interrupt() }
                    loaders.clear()
                    val iv = image ?: return true
                    val err = errorView ?: return true
                    restartLoader(t, iv, err)
                    extend(host.settings()["duration"] as? Int ?: 30)
                    host.changed()
                    return true
                }
                "ptz" -> return true  // camera control: not on Android TV yet (#64)
            }
            return false
        }

        fun restartLoader(t: Tile, iv: ImageView, err: TextView) {
            stop.set(false)
            iv.setImageDrawable(null)
            load(t, iv, err, iv.width)
        }
    }

    // --- live view ---------------------------------------------------------------------------------------------------------
    @androidx.annotation.OptIn(markerClass = [UnstableApi::class])
    private inner class LiveWin(var tile: Tile, val seconds: Int, val volume: Int) : Win(true) {
        override val context = "live"
        var player: ExoPlayer? = null
        var errorView: TextView? = null
        lateinit var bar: TextView

        override fun build(m: DisplayMetrics): WindowManager.LayoutParams {
            root.setBackgroundColor(Color.BLACK)
            val view = PlayerView(ctx).apply { useController = false; isFocusable = false }
            root.addView(view, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
            val font = Layout.titleFont("normal", m.widthPixels).toFloat()
            bar = text(font)
            bar.setBackgroundColor(0x99000000.toInt())
            val h = (font * 1.6f).toInt()
            root.addView(bar, FrameLayout.LayoutParams(m.widthPixels, h).apply { topMargin = m.heightPixels - h })
            errorView = text(font, true).apply {
                text = host.tr("Camera not reachable")
                gravity = Gravity.CENTER
                visibility = View.GONE
            }
            root.addView(errorView, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
            val p = ExoPlayer.Builder(ctx).build()
            p.volume = volume.coerceIn(0, 100) / 100f   // 0 = muted (the Android TV default, #64)
            p.addListener(object : androidx.media3.common.Player.Listener {
                override fun onPlayerError(error: androidx.media3.common.PlaybackException) {
                    CamLog.log("live view ${tile.name} failed: ${error.errorCodeName}", "error")
                    host.unreachable()
                    errorView?.visibility = View.VISIBLE
                }
                override fun onRenderedFirstFrame() { errorView?.visibility = View.GONE }
            })
            view.player = p
            player = p
            play(tile)
            extend(seconds)
            return params(0, 0, m.widthPixels, m.heightPixels)
        }

        fun play(t: Tile) {
            val url = t.live ?: return
            val p = player ?: return
            val item = MediaItem.fromUri(Uri.parse(url))
            val source = when {
                url.startsWith("rtsp") -> RtspMediaSource.Factory().setForceUseRtpTcp(true).createMediaSource(item)
                url.contains(".m3u8") -> HlsMediaSource.Factory(androidx.media3.datasource.DefaultHttpDataSource.Factory()).createMediaSource(item)
                else -> DefaultMediaSourceFactory(ctx).createMediaSource(item)
            }
            errorView?.visibility = View.GONE
            p.setMediaSource(source)
            p.prepare()
            p.playWhenReady = true
            bar.text = t.title + "     " + host.present.keyHint(context)
            CamLog.log("live view ${t.name} (volume ${(p.volume * 100).toInt()} %)", "verbose")
        }

        override fun key(action: String?, name: String?): Boolean {
            when (action) {
                "close" -> closed(this)
                "pause" -> player?.let { it.playWhenReady = !it.playWhenReady }
                "prev", "next" -> {
                    val t = host.neighbour(tile.name, if (action == "next") 1 else -1) ?: return true
                    tile = t
                    state = Screen("live", t.name, listOf(t.name))
                    play(t)
                    extend(seconds)
                    host.changed()
                }
                "ptz" -> {}
                else -> return false
            }
            return true
        }

        override fun detach() {
            player?.release()
            player = null
            super.detach()
        }
    }

    // --- mosaic and tour -------------------------------------------------------------------------------------------------
    private inner class MosaicWin(val tiles: List<Tile>, val seconds: Int) : Win(true) {
        override val context = "mosaic"

        override fun build(m: DisplayMetrics): WindowManager.LayoutParams {
            root.setBackgroundColor(Color.BLACK)
            val font = Layout.titleFont("small", m.widthPixels).toFloat()
            val rects = Layout.grid(tiles.size, m.widthPixels, m.heightPixels)
            for ((i, t) in tiles.withIndex()) tileView(root, t, rects[i], font, true)
            val hint = text(font).apply {
                setBackgroundColor(0x99000000.toInt())
                text = host.present.keyHint(this@MosaicWin.context)
            }
            root.addView(hint, FrameLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, (font * 1.5f).toInt(),
                Gravity.TOP or Gravity.END))
            extend(seconds)
            return params(0, 0, m.widthPixels, m.heightPixels)
        }

        override fun key(action: String?, name: String?): Boolean {
            if (action == "close") { closed(this); return true }
            return action != null || name in listOf("UP", "DOWN", "LEFT", "RIGHT")
        }
    }

    private inner class TourWin(val tiles: List<Tile>, val interval: Int) : Win(true) {
        override val context = "tour"
        var index = 0
        var paused = false
        lateinit var image: ImageView
        lateinit var err: TextView
        lateinit var title: TextView
        private val next = Runnable { step(1) }

        override fun build(m: DisplayMetrics): WindowManager.LayoutParams {
            root.setBackgroundColor(Color.BLACK)
            val font = Layout.titleFont("normal", m.widthPixels).toFloat()
            val th = (font * 1.5f).toInt()
            title = text(font, true)
            title.setBackgroundColor(0x99000000.toInt())
            image = tileView(root, tiles[0], Layout.Rect(0, 0, m.widthPixels, m.heightPixels), font, false)
            err = root.getChildAt(root.childCount - 1) as TextView
            root.addView(title, FrameLayout.LayoutParams(m.widthPixels, th))
            hintBar(m, root, 0, m.heightPixels - th, m.widthPixels, th)
            update()
            main.postDelayed(next, interval * 1000L)
            return params(0, 0, m.widthPixels, m.heightPixels)
        }

        fun update() {
            title.text = host.present.tourStatus(tiles[index].title, index + 1, tiles.size, paused)
        }

        fun step(delta: Int) {
            if (stop.get() && win !== this) return
            main.removeCallbacks(next)
            index = (index + delta).mod(tiles.size)
            state = Screen("tour", tiles[index].name, tiles.map { it.name })
            loaders.forEach { it.interrupt() }
            loaders.clear()
            stop.set(false)
            image.setImageDrawable(null)
            load(tiles[index], image, err, image.width)
            update()
            if (!paused) main.postDelayed(next, interval * 1000L)
        }

        override fun key(action: String?, name: String?): Boolean {
            when (action) {
                "close" -> closed(this)
                "prev" -> step(-1)
                "next" -> step(1)
                "hold" -> {
                    paused = !paused
                    main.removeCallbacks(next)
                    if (!paused) main.postDelayed(next, interval * 1000L)
                    update()
                }
                "live" -> {
                    val cam = tiles[index].name
                    closed(this)
                    host.show(cam, "live", "high", "menu")
                }
                else -> return name in listOf("UP", "DOWN")
            }
            return true
        }

        override fun detach() {
            main.removeCallbacks(next)
            super.detach()
        }
    }
}
