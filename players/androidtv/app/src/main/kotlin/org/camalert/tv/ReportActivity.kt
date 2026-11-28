// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.tv

import android.app.Activity
import android.graphics.Bitmap
import android.graphics.Color
import android.os.Bundle
import android.util.TypedValue
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import org.camalert.core.CoreData
import org.camalert.core.Json
import org.camalert.core.Qr
import org.camalert.core.Report

/**
 * Report a problem (#132): a summary, a QR code that opens a pre-filled GitHub issue on a phone, and the full
 * report (without secrets) saved in the app's files folder and available at /camalert/report in the local network.
 */
class ReportActivity : Activity() {
    override fun attachBaseContext(base: android.content.Context) = super.attachBaseContext(Lang.wrap(base))  // #10

    private lateinit var text: TextView
    private lateinit var image: ImageView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        @Suppress("UNCHECKED_CAST")
        val texts = (CoreData.load().raw["report"] as Map<String, Any?>)["texts"] as Map<String, String>
        val tr = Tr(this)
        fun t(key: String): String = texts[key]?.let { tr(it) } ?: key
        title = t("title")
        text = TextView(this).apply {
            setTextColor(Color.WHITE)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
            setPadding(48, 48, 32, 48)
            this.text = t("help")
        }
        image = ImageView(this).apply { setBackgroundColor(Color.WHITE) }
        setContentView(LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setBackgroundColor(Color.rgb(16, 16, 16))
            addView(text, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, 1f))
            addView(image, LinearLayout.LayoutParams(480, 480).apply { setMargins(32, 96, 64, 32) })
        })
        Thread {
            val svc = CamAlertService.instance ?: return@Thread
            @Suppress("UNCHECKED_CAST")
            val out = try { svc.problemReport() } catch (e: Exception) { mapOf("error" to (e.message ?: e.toString())) }
            val rep = out["report"] as? Map<String, Any?>
            val url = out["issue_url"] as? String
            val lines = mutableListOf(t("help"), "")
            var bmp: Bitmap? = null
            if (rep != null && url != null) {
                val reports = Report()
                lines.addAll(reports.summary(rep))
                bmp = bitmap(Qr.encode(url, "M"))
                try {  // the full report, for adb pull or a file manager
                    val dir = getExternalFilesDir(null) ?: filesDir
                    val f = java.io.File(dir, "camalert-report.txt")
                    f.writeText(reports.summary(rep).joinToString("\n") + "\n\n" + Json.write(rep, sortKeys = true) + "\n")
                    lines.add("")
                    lines.add(t("saved").replace("%s", f.absolutePath))
                } catch (e: Exception) {
                    lines.add(t("save_failed").replace("%s", e.message ?: e.toString()))
                }
            } else lines.add(out["error"]?.toString() ?: "?")
            runOnUiThread {
                text.text = lines.joinToString("\n")
                if (bmp != null) image.setImageBitmap(bmp)
            }
        }.start()
    }

    /** Black modules on white with a 4-module quiet zone, scaled to whole pixels. */
    private fun bitmap(m: Array<BooleanArray>, border: Int = 4, scale: Int = 8): Bitmap {
        val n = m.size + 2 * border
        val bmp = Bitmap.createBitmap(n * scale, n * scale, Bitmap.Config.RGB_565)
        bmp.eraseColor(Color.WHITE)
        for (y in m.indices) for (x in m.indices) if (m[y][x])
            for (dy in 0 until scale) for (dx in 0 until scale) bmp.setPixel((x + border) * scale + dx, (y + border) * scale + dy, Color.BLACK)
        return bmp
    }
}
