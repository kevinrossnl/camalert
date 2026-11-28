// CamAlert for Android TV. Copyright (C) 2026 CamAlert developers. GPL v2.
package org.camalert.tv

import android.app.Activity
import android.os.Bundle
import android.widget.Toast
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView

/** A Frigate clip from the event list (#124): a normal film, full screen, with the player controls; BACK closes it. */
class ClipActivity : Activity() {
    override fun attachBaseContext(base: android.content.Context) = super.attachBaseContext(Lang.wrap(base))  // #10

    private var player: ExoPlayer? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val url = intent.getStringExtra("url") ?: return finish()
        title = intent.getStringExtra("title") ?: ""
        val view = PlayerView(this).apply { useController = true; keepScreenOn = true }
        setContentView(view)
        val p = ExoPlayer.Builder(this).build()
        p.addListener(object : Player.Listener {
            override fun onPlayerError(error: PlaybackException) {
                CamLog.log("Frigate clip failed: ${error.message}", "error")
                Toast.makeText(this@ClipActivity, error.message ?: "error", Toast.LENGTH_LONG).show()
                finish()
            }
            override fun onPlaybackStateChanged(state: Int) {
                if (state == Player.STATE_ENDED) finish()
            }
        })
        view.player = p
        p.setMediaItem(MediaItem.fromUri(url))
        p.prepare()
        p.playWhenReady = true
        player = p
        view.requestFocus()
    }

    override fun onStop() {
        super.onStop()
        finish()
    }

    override fun onDestroy() {
        player?.release()
        player = null
        super.onDestroy()
    }
}
