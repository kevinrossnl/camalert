// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

/** When a live view may show its still picture and when it has to go (#91); port of frames.LiveStill.
 *  The player opens the live stream and fetches a picture (warm feed, Protect, go2rtc cache, frame.jpeg) at the
 *  same time; the picture is shown only while the stream has no frame yet. Tokens from start() make a picture or
 *  a first frame of an earlier camera harmless. Not thread-safe: call it on the UI thread. */
class LiveStill(private val clock: () -> Double = { System.currentTimeMillis() / 1000.0 },
                private val maxSeconds: Double = CoreData.load().stillMaxSeconds) {
    var token = 0
        private set
    var showing = false
        private set
    private var camera: String? = null
    private var started = 0.0
    private var live = false

    fun start(camera: String): Int {
        token += 1
        this.camera = camera
        started = clock()
        showing = false
        live = false
        return token
    }

    /** A picture for token arrived: true when the player shows it now. */
    fun picture(token: Int): Boolean {
        if (token != this.token || camera == null || live || clock() - started > maxSeconds) return false
        showing = true
        return true
    }

    /** The live stream shows its first frame: true when a shown still has to go. */
    fun playing(token: Int? = null): Boolean {
        if (token != null && token != this.token) return false
        live = true
        val was = showing
        showing = false
        return was
    }

    /** True once when a shown still has been up for maxSeconds without a frame. */
    fun expired(): Boolean {
        if (showing && clock() - started > maxSeconds) { showing = false; return true }
        return false
    }

    /** The live view ends: true when a shown still has to go. */
    fun stop(): Boolean {
        token += 1
        camera = null
        val was = showing
        showing = false
        return was
    }
}
