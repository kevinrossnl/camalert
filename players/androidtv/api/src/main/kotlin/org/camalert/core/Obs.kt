// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

/** Log levels, redaction of secrets and the Prometheus text format (core/camalert_core/obs/log.py + metrics.py). */
object Obs {
    val LOG_LEVELS = listOf("off", "errors", "normal", "verbose")
    private val RANK = mapOf("error" to 1, "normal" to 2, "verbose" to 3)

    fun logAllowed(setting: String, level: String): Boolean {
        val limit = LOG_LEVELS.indexOf(setting).let { if (it < 0) 2 else it }
        return (RANK[level] ?: 2) <= limit
    }

    // the same patterns, in the same order, as _REDACT in the Python core
    private val REDACT = listOf(
        Regex("(?i)(\\b[a-z][a-z0-9+.-]*://)[^/\\s:@]*:[^/\\s@]*@") to "$1***:***@",
        Regex("(?i)(\\b[a-z][a-z0-9+.-]*://)[^/\\s:@]+@") to "$1***@",
        Regex("(?i)([?&](?:token|pwd|pass|password|passwd|usr|user|key|apikey|api_key|access_token|auth)=)[^&\\s\"']*") to "$1***",
        Regex("(?i)(\\bauthorization\\s*[:=]\\s*)(?:bearer\\s+|basic\\s+)?[^\\s,;\"']+") to "$1***",
        Regex("(?i)(\"(?:token|password|pwd|access_token|api_key)\"\\s*:\\s*\")[^\"]*(\")") to "$1***$2",
        Regex("(?i)(<(?:\\w+:)?(?:Password|Nonce|Username)[^>]*>)[^<]*") to "$1***",
        Regex("(?i)\\b((?:password|passwd|token|pwd)\\s*[=:]\\s*)[^\\s&,;|\"']+") to "$1***",
    )

    /** Removes passwords, tokens and user:pass@ from anything that goes to a log, a status page or diagnostics. */
    fun redact(text: String?): String {
        var t = text ?: ""
        for ((rx, repl) in REDACT) t = rx.replace(t, repl)
        return t
    }

    /** One metric: Prometheus type, help text and a number (or {label value: number}). */
    class Metric(val kind: String, val help: String, val value: Any)

    fun metricsText(m: Map<String, Metric>, labels: Map<String, String>? = null): String {
        val extra = (labels ?: emptyMap()).toSortedMap().entries.joinToString(",") { "${it.key}=\"${it.value.replace('"', '\'')}\"" }
        val out = ArrayList<String>()
        for (name in m.keys.sorted()) {
            val x = m.getValue(name)
            out.add("# HELP camalert_$name ${x.help}")
            out.add("# TYPE camalert_$name ${x.kind}")
            val v = x.value
            if (v is Map<*, *>) {
                for (lv in v.keys.map { it.toString() }.sorted()) {
                    val lab = listOf(extra, "key=\"${lv.replace('"', '\'')}\"").filter { it.isNotEmpty() }.joinToString(",")
                    out.add("camalert_$name{$lab} ${num(v[lv] ?: v.entries.first { it.key.toString() == lv }.value)}")
                }
            } else {
                out.add("camalert_$name${if (extra.isNotEmpty()) "{$extra}" else ""} ${num(v)}")
            }
        }
        return out.joinToString("\n") + "\n"
    }

    /** Python "%d" for whole numbers and booleans, "%.6g" otherwise. */
    fun num(v: Any?): String {
        if (v is Boolean) return if (v) "1" else "0"
        val d = (v as? Number)?.toDouble() ?: 0.0
        if (d == Math.floor(d) && !d.isInfinite()) return java.math.BigDecimal(d).toBigInteger().toString()
        return g6(d)
    }

    /** C printf %.6g. */
    fun g6(d: Double): String {
        if (d == 0.0) return "0"
        val exp = Math.floor(Math.log10(Math.abs(d))).toInt()
        val s: String
        if (exp < -4 || exp >= 6) {
            s = String.format(java.util.Locale.ROOT, "%.5e", d)
            val (mant, e) = s.split("e")
            val m = mant.trimEnd('0').trimEnd('.')
            val ei = e.toInt()
            return m + "e" + (if (ei < 0) "-" else "+") + String.format(java.util.Locale.ROOT, "%02d", Math.abs(ei))
        }
        s = String.format(java.util.Locale.ROOT, "%." + (5 - exp).coerceAtLeast(0) + "f", d)
        return if (s.contains('.')) s.trimEnd('0').trimEnd('.') else s
    }
}
