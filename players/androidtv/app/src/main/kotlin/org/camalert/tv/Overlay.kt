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
import android.widget.LinearLayout
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
import org.camalert.core.Style
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
        /** Camera control (#66): does the camera have PTZ, and move it (blocking: call it from a thread). */
        fun hasPtz(camera: String?): Boolean = false
        fun ptz(camera: String, action: String): Boolean = false
        fun unreachable()
        fun changed()
        /** #111: the last picture of a ready camera when it is fresh, or null. */
        fun warmPicture(camera: String): ByteArray? = null
        /** #109: a fresh picture of a UniFi Protect camera, or null (use go2rtc). */
        fun protectPicture(camera: String, width: Int): ByteArray? = null
    }

    private val main = Handler(Looper.getMainLooper())
    private val wm = ctx.getSystemService(Context.WINDOW_SERVICE) as WindowManager
    @Volatile private var state = Screen(null, null)
    private var win: Win? = null  // main thread only
    private val extras = LinkedHashMap<String, PhotoWin>()  // #87: windows with their own id, main thread only
    @Volatile private var extraState: Map<String, String> = emptyMap()  // id -> camera, for any thread

    override fun screen() = state
    override fun windows() = extraState

    fun allowed() = Settings.canDrawOverlays(ctx)

    // --- Display -----------------------------------------------------------------------------------------------------
    override fun photo(tiles: List<Tile>, seconds: Int, label: String?, priority: String) {
        state = Screen(if (tiles.size > 1) "strip" else "photo", tiles[0].name, tiles.map { it.name })
        main.post { open(PhotoWin(tiles, seconds, label, priority = priority)) }
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

    // --- several windows (#87) ---------------------------------------------------------------------------------------
    override fun photoWindow(id: String, slot: Int, tile: Tile, seconds: Int, label: String?, priority: String) {
        extraState = extraState + (id to tile.name)
        main.post { openExtra(id, PhotoWin(listOf(tile), seconds, label, priority = priority, wid = id, slot = slot)) }
    }

    override fun extendWindow(id: String, seconds: Int) {
        main.post { extras[id]?.extend(seconds) }
    }

    override fun hideWindow(id: String) {
        extraState = extraState - id
        main.post {
            extras.remove(id)?.detach()
            host.changed()
        }
    }

    private fun openExtra(id: String, w: PhotoWin) {
        extras.remove(id)?.detach()
        if (!allowed()) {
            extraState = extraState - id
            host.changed()
            return
        }
        extras[id] = w
        try {
            w.attach()
        } catch (e: Exception) {
            CamLog.log("overlay failed: $e", "error")
            extras.remove(id)
            extraState = extraState - id
        }
        host.changed()
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
        val wid = (w as? PhotoWin)?.wid
        if (wid != null) {  // #87: a window with its own id ran out
            if (extras[wid] === w) {
                extras.remove(wid)
                w.detach()
                extraState = extraState - wid
                host.changed()
            }
            return
        }
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

    /** The text size setting (#48): every window scales its fonts with it. */
    private fun textSize() = host.settings()["text_size"]?.toString() ?: "normal"

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

        /** The priority frame (#48): a border in the priority colour over the whole window, steady or flashing at
         *  Style.flashMs (at most 3 flashes a second); the title carries the priority word too. */
        fun addFrame(mark: Style.Mark, w: Int, h: Int) {
            val b = maxOf(3, (6 * w / 640f).toInt().coerceAtMost(8))
            val frame = View(ctx).apply {
                background = android.graphics.drawable.GradientDrawable().apply {
                    setColor(Color.TRANSPARENT)
                    setStroke(b, Color.parseColor(mark.colour))
                }
            }
            root.addView(frame, FrameLayout.LayoutParams(w, h))
            if (mark.flash) {
                val blink = object : Runnable {
                    override fun run() {
                        if (stop.get()) return
                        frame.visibility = if (frame.visibility == View.VISIBLE) View.INVISIBLE else View.VISIBLE
                        main.postDelayed(this, Style.flashMs.toLong())
                    }
                }
                main.postDelayed(blink, Style.flashMs.toLong())
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

        /** "actions" while the action menu is open (#118), "ptz" during camera control (#66), else null. */
        var mode: String? = null
        var hintView: TextView? = null
        private var menuView: LinearLayout? = null
        private var entries: List<Pair<String, String?>> = emptyList()
        private var selected = 0
        private val ptzQueue = java.util.concurrent.LinkedBlockingQueue<String>()
        private var ptzWorker: Thread? = null

        fun ptzKey() = host.settings()["ptz_key"]?.toString() ?: "blue"
        fun hasPtz() = host.hasPtz(state.stream)
        fun hintText() = host.present.keyHint(mode ?: context, ptzKey(), hasPtz())
        /** Shows the key hint of the current mode; the live view puts it in its bar. */
        open fun showHint(text: String) { hintView?.text = text }

        fun onKey(name: String?, code: Int): Boolean {
            if (name != null && passKey(name)) return false
            if (mode == "actions") {
                menuKey(host.present.actionFor("actions", name))
                return true
            }
            if (mode == "ptz") {
                ptzAction(host.present.actionFor("ptz", name), name)
                return true
            }
            if (name != null && name in KeyNames.COLOURS) {
                val colour = KeyNames.COLOURS.getValue(name)
                if (colour == ptzKey() && hasPtz()) startPtz() else if (host.settings()["ha_buttons"] != false) host.colourKey(state.stream, colour)
                return true
            }
            val action = host.present.actionFor(context, name)
            if (action == "menu") {
                openMenu()
                return true
            }
            if (key(action, name)) return true
            if (code == KeyEvent.KEYCODE_HOME) return false
            closed(this)  // a key that is not ours closes the window (like on the other players)
            return true
        }

        // --- action menu (#118): Fire TV remotes have no colour keys -----------------------------------------------
        fun openMenu() {
            val s = host.settings()
            entries = host.present.actionMenu(hasPtz(), ptzKey(), s["ha_buttons"] != false)
            if (entries.isEmpty()) return
            val m = metrics()
            val font = Layout.titleFont("small", m.widthPixels).toFloat()
            val box = LinearLayout(ctx).apply {
                orientation = LinearLayout.VERTICAL
                setBackgroundColor(0xE0181818.toInt())
                setPadding((font / 2).toInt(), (font / 3).toInt(), (font / 2).toInt(), (font / 3).toInt())
            }
            for ((kind, colour) in entries) box.addView(text(font).apply { text = host.present.actionLabel(kind, colour) })
            root.addView(box, FrameLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.CENTER))
            menuView = box
            selected = 0
            mode = "actions"
            markSelected()
            showHint(hintText())
            extend(host.settings()["duration"] as? Int ?: 30)
        }

        private fun markSelected() {
            val box = menuView ?: return
            for (i in 0 until box.childCount) box.getChildAt(i).setBackgroundColor(if (i == selected) 0xFF2D6CDF.toInt() else Color.TRANSPARENT)
        }

        fun closeMenu() {
            menuView?.let { root.removeView(it) }
            menuView = null
            if (mode == "actions") mode = null
            showHint(hintText())
        }

        private fun menuKey(action: String?) {
            when (action) {
                "up" -> { selected = (selected + entries.size - 1) % entries.size; markSelected() }
                "down" -> { selected = (selected + 1) % entries.size; markSelected() }
                "close" -> closeMenu()
                "choose" -> {
                    val (kind, colour) = entries[selected]
                    closeMenu()
                    if (kind == "ptz") startPtz() else host.colourKey(state.stream, colour!!)
                }
            }
        }

        // --- camera control (#66): arrows move, FF/REW zoom, OK = home position; moves run one after the other -------
        fun startPtz() {
            if (!hasPtz()) return
            mode = "ptz"
            showHint(hintText())
            extend(host.settings()["duration"] as? Int ?: 30)
        }

        private fun ptzAction(action: String?, name: String?) {
            when (action) {
                "leave" -> { mode = null; showHint(hintText()); return }
                null -> {
                    if (name != null && KeyNames.COLOURS[name] == ptzKey()) { mode = null; showHint(hintText()) }  // the PTZ key ends it too
                    return
                }
            }
            val cam = state.stream ?: return
            extend(host.settings()["duration"] as? Int ?: 30)
            if (ptzQueue.size < 3) ptzQueue.offer(action)
            if (ptzWorker?.isAlive != true) {
                ptzWorker = Thread({
                    while (!stop.get()) {
                        val a = ptzQueue.poll(1, java.util.concurrent.TimeUnit.SECONDS) ?: break
                        host.ptz(cam, a)
                    }
                }, "camalert-ptz").apply { isDaemon = true; start() }
            }
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

        fun hintBar(m: DisplayMetrics, parent: ViewGroup, x: Int, y: Int, w: Int, h: Int): TextView {
            val tv = text(Layout.titleFont("small", m.widthPixels, textSize()).toFloat())
            tv.setBackgroundColor(0x99000000.toInt())
            tv.text = host.present.keyHint(context, ptzKey(), hasPtz())
            parent.addView(tv, FrameLayout.LayoutParams(w, h).apply { leftMargin = x; topMargin = y })
            hintView = tv
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
                        val bytes = host.warmPicture(tile.name)  // #111
                            ?: host.protectPicture(tile.name, width.coerceIn(160, 1920))  // #109
                            ?: Net.fetch(if (first) org.camalert.core.Urls.withCache(url, cache)!! else url, verify, 6000)
                        first = false
                        val bmp = BitmapFactory.decodeByteArray(bytes, 0, bytes.size) ?: throw java.io.IOException("not an image")
                        val shown = orient(bmp, orientation)
                        main.post {
                            if (!stop.get()) {
                                (view.tag as? MaskView)?.show(tile.name, shown.width, shown.height)  // #11, before the picture
                                view.setImageBitmap(shown); error.visibility = View.GONE
                            }
                        }
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
            val mask = MaskView(ctx) { host.settings() }  // #11: privacy masks on top of the picture
            parent.addView(mask, FrameLayout.LayoutParams(r.w, r.h).apply { leftMargin = r.x; topMargin = r.y })
            iv.tag = mask
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
    private inner class PhotoWin(var tiles: List<Tile>, val seconds: Int, val label: String?, val notify: Boolean = false,
                                 val priority: String = "normal", val wid: String? = null, val slot: Int = 0) :
        Win(wid == null && !notify && host.settings()["window_keys"] != false) {  // #87: id windows take no keys
        override val context = "window"
        lateinit var title: TextView
        var image: ImageView? = null
        var errorView: TextView? = null

        override fun build(m: DisplayMetrics): WindowManager.LayoutParams {
            val s = host.settings()
            val pos = s["position"]?.toString() ?: "top_right"
            val size = if (notify) "small" else s["size"]?.toString() ?: "medium"
            val ts = s["title_size"]?.toString() ?: "normal"
            val font = Layout.titleFont(ts, m.widthPixels, textSize()).toFloat()
            val hint = if (takesKeys) (font * 1.4f).toInt() else 0
            root.setBackgroundColor(0xFF202020.toInt())
            val g: Layout.Window
            val rects: List<Layout.Rect>
            if (tiles.size == 1) {
                g = Layout.window(pos, size, m.widthPixels, m.heightPixels, ts, textSize(), slot)
                rects = listOf(Layout.Rect(0, g.title, g.w, g.h))
            } else {
                g = Layout.strip(tiles.size, s["strip_layout"]?.toString() ?: "auto", pos, size, m.widthPixels, m.heightPixels, textSize())
                rects = g.tiles
            }
            title = text(font, true)
            val border = s["priority_border"]?.toString() ?: "steady"
            title.text = Style.markedTitle(if (tiles.size == 1) tiles[0].title else listOfNotNull(label, tiles.joinToString(" · ") { it.title }).joinToString(" · "),
                priority, border, host.tr)
            root.addView(title, FrameLayout.LayoutParams(g.w, g.title))
            for ((i, t) in tiles.withIndex()) {
                val iv = tileView(root, t, rects[i], font * 0.8f, tiles.size > 1)
                if (i == 0) {
                    image = iv
                    errorView = root.getChildAt(root.childCount - 1) as TextView
                }
            }
            val total = g.title + g.h
            Style.priorityMark(priority, border)?.let { addFrame(it, g.w, total + hint) }  // #48
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
                    showHint(hintText())  // the new camera may (not) have camera control
                    host.changed()
                    return true
                }
                "ptz" -> { startPtz(); return true }
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
        val still = org.camalert.core.LiveStill()  // #91: still picture until the first video frame
        var stillView: ImageView? = null
        var maskView: MaskView? = null  // #11: privacy masks over the video and the still picture
        private val stillTimeout = Runnable { if (still.expired()) stillView?.visibility = View.GONE }

        override fun build(m: DisplayMetrics): WindowManager.LayoutParams {
            root.setBackgroundColor(Color.BLACK)
            val view = PlayerView(ctx).apply { useController = false; isFocusable = false }
            root.addView(view, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
            stillView = ImageView(ctx).apply {
                scaleType = ImageView.ScaleType.FIT_CENTER
                setBackgroundColor(Color.BLACK)
                visibility = View.GONE
            }
            root.addView(stillView, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
            maskView = MaskView(ctx) { host.settings() }
            root.addView(maskView, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
            val font = Layout.titleFont("normal", m.widthPixels, textSize()).toFloat()
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
                override fun onVideoSizeChanged(videoSize: androidx.media3.common.VideoSize) {
                    if (videoSize.width > 0 && videoSize.height > 0) {
                        val w = (videoSize.width * videoSize.pixelWidthHeightRatio).toInt()
                        maskView?.show(tile.name, w, videoSize.height)
                    }
                }
                override fun onRenderedFirstFrame() {
                    errorView?.visibility = View.GONE
                    if (still.playing()) stillView?.visibility = View.GONE
                }
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
            maskView?.show(t.name)  // #11: before the first frame of this camera
            p.setMediaSource(source)
            p.prepare()
            p.playWhenReady = true
            showStill(t)
            showHint(hintText())
            CamLog.log("live view ${t.name} (volume ${(p.volume * 100).toInt()} %)", "verbose")
        }

        /** #91: a picture of the camera from the fastest source (warm feed, Protect, go2rtc cache, frame.jpeg) in a
         *  thread, shown on the UI thread only while the stream has no frame yet. */
        fun showStill(t: Tile) {
            main.removeCallbacks(stillTimeout)
            stillView?.visibility = View.GONE
            val token = still.start(t.name)
            val url = t.snapshot ?: return
            val s = host.settings()
            val verify = s["verify_ssl"] != false
            val orientation = Cameras.parseOrientation(s["orientation"]?.toString())[t.name]
            val width = metrics().widthPixels.coerceIn(160, 1920)
            val sized = url.replace(Regex("width=\\d+"), "width=$width")
            val cache = org.camalert.core.CoreData.load().frameCacheSeconds
            val th = Thread({
                val bmp = try {
                    val bytes = host.warmPicture(t.name) ?: host.protectPicture(t.name, width)
                        ?: Net.fetch(org.camalert.core.Urls.withCache(sized, cache)!!, verify, 6000)
                    BitmapFactory.decodeByteArray(bytes, 0, bytes.size)?.let { orient(it, orientation) }
                } catch (e: Exception) {
                    CamLog.log("still picture ${t.name} failed: ${e.message}", "verbose")
                    null
                }
                if (bmp != null) main.post {
                    if (!stop.get() && still.picture(token)) {
                        maskView?.show(t.name, bmp.width, bmp.height)  // #11
                        stillView?.setImageBitmap(bmp)
                        stillView?.visibility = View.VISIBLE
                        main.postDelayed(stillTimeout, (org.camalert.core.CoreData.load().stillMaxSeconds * 1000).toLong() + 100)
                    }
                }
            }, "camalert-still-${t.name}")
            loaders.add(th)
            th.start()
        }

        override fun showHint(text: String) { bar.text = tile.title + "     " + text }

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
                "ptz" -> startPtz()
                else -> return false
            }
            return true
        }

        override fun detach() {
            still.stop()
            main.removeCallbacks(stillTimeout)
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
            val font = Layout.titleFont("small", m.widthPixels, textSize()).toFloat()
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
            val font = Layout.titleFont("normal", m.widthPixels, textSize()).toFloat()
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
