// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

/**
 * Minimal JSON (RFC 8259) reader and writer, so the API module needs no library and runs on the JVM and on
 * Android alike. Values: null, Boolean, Long, Double, String, List<Any?>, Map<String, Any?> (insertion order).
 * The writer formats like Python's json.dumps (", " and ": " separators, ASCII only), so answers look the same
 * as on the Python players.
 */
object Json {
    class ParseError(message: String) : Exception(message)

    fun parse(text: String): Any? {
        val p = Parser(text)
        p.ws()
        val v = p.value()
        p.ws()
        if (p.i != text.length) throw ParseError("trailing data at ${p.i}")
        return v
    }

    @Suppress("UNCHECKED_CAST")
    fun obj(text: String): Map<String, Any?> = parse(text) as? Map<String, Any?> ?: throw ParseError("not an object")

    fun write(value: Any?, sortKeys: Boolean = false): String = StringBuilder().also { w(it, value, sortKeys) }.toString()

    private fun w(sb: StringBuilder, v: Any?, sort: Boolean) {
        when (v) {
            null -> sb.append("null")
            is Boolean -> sb.append(if (v) "true" else "false")
            is Int, is Long, is Short, is Byte -> sb.append(v.toString())
            is Double, is Float -> sb.append(num(v.toDouble()))
            is Number -> sb.append(v.toString())
            is String -> str(sb, v)
            is Map<*, *> -> {
                sb.append('{')
                val keys = v.keys.map { it.toString() }.let { if (sort) it.sorted() else it }
                keys.forEachIndexed { n, k ->
                    if (n > 0) sb.append(", ")
                    str(sb, k)
                    sb.append(": ")
                    w(sb, v[k], sort)
                }
                sb.append('}')
            }
            is Iterable<*> -> {
                sb.append('[')
                v.forEachIndexed { n, x ->
                    if (n > 0) sb.append(", ")
                    w(sb, x, sort)
                }
                sb.append(']')
            }
            is Array<*> -> w(sb, v.toList(), sort)
            else -> str(sb, v.toString())
        }
    }

    /** Python repr of a float: 2.5, 12.0, 1e-07. */
    fun num(d: Double): String {
        if (d.isNaN()) return "NaN"
        if (d.isInfinite()) return if (d > 0) "Infinity" else "-Infinity"
        if (d == Math.floor(d) && Math.abs(d) < 1e16) return String.format(java.util.Locale.ROOT, "%.1f", d)
        val a = Math.abs(d)
        if (a >= 1e-4 && a < 1e16) return java.math.BigDecimal(d.toString()).toPlainString()  // 1795536963.528, not 1.795536963528E9
        return d.toString()
    }

    private fun str(sb: StringBuilder, s: String) {
        sb.append('"')
        for (c in s) {
            when {
                c == '"' -> sb.append("\\\"")
                c == '\\' -> sb.append("\\\\")
                c == '\n' -> sb.append("\\n")
                c == '\r' -> sb.append("\\r")
                c == '\t' -> sb.append("\\t")
                c == '\b' -> sb.append("\\b")
                c == '\u000c' -> sb.append("\\f")
                c.code < 0x20 || c.code > 0x7e -> sb.append(String.format(java.util.Locale.ROOT, "\\u%04x", c.code))
                else -> sb.append(c)
            }
        }
        sb.append('"')
    }

    private class Parser(val s: String) {
        var i = 0

        fun ws() {
            while (i < s.length && s[i] in " \t\r\n") i++
        }

        fun value(): Any? {
            if (i >= s.length) throw ParseError("unexpected end")
            return when (val c = s[i]) {
                '{' -> obj()
                '[' -> arr()
                '"' -> string()
                't' -> lit("true", true)
                'f' -> lit("false", false)
                'n' -> lit("null", null)
                else -> if (c == '-' || c.isDigit()) number() else throw ParseError("unexpected '$c' at $i")
            }
        }

        fun lit(word: String, v: Any?): Any? {
            if (!s.startsWith(word, i)) throw ParseError("bad literal at $i")
            i += word.length
            return v
        }

        fun number(): Any {
            val start = i
            if (s[i] == '-') i++
            while (i < s.length && s[i].isDigit()) i++
            var real = false
            if (i < s.length && s[i] == '.') {
                real = true
                i++
                while (i < s.length && s[i].isDigit()) i++
            }
            if (i < s.length && (s[i] == 'e' || s[i] == 'E')) {
                real = true
                i++
                if (i < s.length && (s[i] == '+' || s[i] == '-')) i++
                while (i < s.length && s[i].isDigit()) i++
            }
            val t = s.substring(start, i)
            if (t == "-" || t.isEmpty()) throw ParseError("bad number at $start")
            return if (real) t.toDouble() else t.toLongOrNull() ?: t.toDouble()
        }

        fun string(): String {
            i++
            val sb = StringBuilder()
            while (true) {
                if (i >= s.length) throw ParseError("unterminated string")
                val c = s[i++]
                when (c) {
                    '"' -> return sb.toString()
                    '\\' -> {
                        if (i >= s.length) throw ParseError("bad escape")
                        when (val e = s[i++]) {
                            '"' -> sb.append('"'); '\\' -> sb.append('\\'); '/' -> sb.append('/')
                            'b' -> sb.append('\b'); 'f' -> sb.append('\u000c'); 'n' -> sb.append('\n')
                            'r' -> sb.append('\r'); 't' -> sb.append('\t')
                            'u' -> {
                                if (i + 4 > s.length) throw ParseError("bad unicode escape")
                                sb.append(s.substring(i, i + 4).toInt(16).toChar())
                                i += 4
                            }
                            else -> throw ParseError("bad escape \\$e")
                        }
                    }
                    else -> sb.append(c)
                }
            }
        }

        fun arr(): List<Any?> {
            i++
            val out = ArrayList<Any?>()
            ws()
            if (i < s.length && s[i] == ']') { i++; return out }
            while (true) {
                ws(); out.add(value()); ws()
                if (i >= s.length) throw ParseError("unterminated array")
                if (s[i] == ',') { i++; continue }
                if (s[i] == ']') { i++; return out }
                throw ParseError("expected , or ] at $i")
            }
        }

        fun obj(): Map<String, Any?> {
            i++
            val out = LinkedHashMap<String, Any?>()
            ws()
            if (i < s.length && s[i] == '}') { i++; return out }
            while (true) {
                ws()
                if (i >= s.length || s[i] != '"') throw ParseError("expected key at $i")
                val k = string()
                ws()
                if (i >= s.length || s[i] != ':') throw ParseError("expected : at $i")
                i++
                ws(); out[k] = value(); ws()
                if (i >= s.length) throw ParseError("unterminated object")
                if (s[i] == ',') { i++; continue }
                if (s[i] == '}') { i++; return out }
                throw ParseError("expected , or } at $i")
            }
        }
    }
}

/** Python str() of a JSON value as the core's parse_body() does it (bool -> "true"/"false", None -> ""). */
fun pyStr(v: Any?): String = when (v) {
    null -> ""
    is Boolean -> if (v) "true" else "false"
    is Double -> Json.num(v)
    else -> v.toString()
}
