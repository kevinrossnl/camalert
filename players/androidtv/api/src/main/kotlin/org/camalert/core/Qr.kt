// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
package org.camalert.core

/**
 * QR codes without dependencies (#132), the same as camalert_core.qr: byte mode, level L or M, versions 1-40.
 * The player shows the link to a pre-filled GitHub issue as a QR code that a phone scans.
 */
object Qr {
    private val ECC_PER_BLOCK = mapOf(
        "L" to intArrayOf(7, 10, 15, 20, 26, 18, 20, 24, 30, 18, 20, 24, 26, 30, 22, 24, 28, 30, 28, 28, 28, 28, 30, 30, 26,
            28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),
        "M" to intArrayOf(10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26, 26, 26, 28, 28, 28, 28,
            28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28))
    private val BLOCKS = mapOf(
        "L" to intArrayOf(1, 1, 1, 1, 1, 2, 2, 2, 2, 4, 4, 4, 4, 4, 6, 6, 6, 6, 7, 8, 8, 9, 9, 10, 12, 12, 12, 13, 14, 15, 16,
            17, 18, 19, 19, 20, 21, 22, 24, 25),
        "M" to intArrayOf(1, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5, 8, 9, 9, 10, 10, 11, 13, 14, 16, 17, 17, 18, 20, 21, 23, 25, 26, 28,
            29, 31, 33, 35, 37, 38, 40, 43, 45, 47, 49))
    private val FORMAT_LEVEL = mapOf("L" to 1, "M" to 0)

    class TooLong(message: String) : IllegalArgumentException(message)

    private fun rawModules(ver: Int): Int {
        var n = (16 * ver + 128) * ver + 64
        if (ver >= 2) {
            val align = ver / 7 + 2
            n -= (25 * align - 10) * align - 55
            if (ver >= 7) n -= 36
        }
        return n
    }

    fun dataCodewords(ver: Int, level: String): Int =
        rawModules(ver) / 8 - ECC_PER_BLOCK.getValue(level)[ver - 1] * BLOCKS.getValue(level)[ver - 1]

    private fun alignment(ver: Int): List<Int> {
        if (ver == 1) return emptyList()
        val count = ver / 7 + 2
        val step = if (ver == 32) 26 else (ver * 4 + count * 2 + 1) / (count * 2 - 2) * 2
        val size = ver * 4 + 17
        return listOf(6) + (0 until count - 1).map { size - 7 - it * step }.sorted()
    }

    private fun mul(x: Int, y: Int): Int {
        var z = 0
        for (i in 7 downTo 0) {
            z = (z shl 1) xor ((z ushr 7) * 0x11D)
            z = z xor (((y ushr i) and 1) * x)
        }
        return z and 0xFF
    }

    private fun divisor(degree: Int): IntArray {
        val result = IntArray(degree)
        result[degree - 1] = 1
        var root = 1
        repeat(degree) {
            for (j in 0 until degree) {
                result[j] = mul(result[j], root)
                if (j + 1 < degree) result[j] = result[j] xor result[j + 1]
            }
            root = mul(root, 0x02)
        }
        return result
    }

    private fun remainder(data: List<Int>, div: IntArray): List<Int> {
        val result = ArrayList<Int>(div.size).apply { repeat(div.size) { add(0) } }
        for (b in data) {
            val factor = b xor result.removeAt(0)
            result.add(0)
            for (i in div.indices) result[i] = result[i] xor mul(div[i], factor)
        }
        return result
    }

    private fun codewords(data: ByteArray, ver: Int, level: String): IntArray {
        val capacity = dataCodewords(ver, level)
        val bits = ArrayList<Int>()
        fun put(value: Int, length: Int) { for (i in length - 1 downTo 0) bits.add((value ushr i) and 1) }
        put(0b0100, 4)
        put(data.size, if (ver <= 9) 8 else 16)
        for (b in data) put(b.toInt() and 0xFF, 8)
        put(0, minOf(4, capacity * 8 - bits.size))
        put(0, ((-bits.size) % 8 + 8) % 8)
        val words = ArrayList<Int>()
        var i = 0
        while (i < bits.size) { var v = 0; for (k in 0 until 8) v = (v shl 1) or bits[i + k]; words.add(v); i += 8 }
        var pad = 0xEC
        while (words.size < capacity) { words.add(pad); pad = pad xor (0xEC xor 0x11) }
        val blocksN = BLOCKS.getValue(level)[ver - 1]
        val eccLen = ECC_PER_BLOCK.getValue(level)[ver - 1]
        val raw = rawModules(ver) / 8
        val shortN = blocksN - raw % blocksN
        val shortLen = raw / blocksN
        val div = divisor(eccLen)
        val blocks = ArrayList<List<Int?>>()
        var k = 0
        for (b in 0 until blocksN) {
            val dlen = shortLen - eccLen + (if (b < shortN) 0 else 1)
            val dat = words.subList(k, k + dlen).toList()
            k += dlen
            val ecc = remainder(dat, div)
            val blk = ArrayList<Int?>(dat)
            if (b < shortN) blk.add(null)
            blk.addAll(ecc)
            blocks.add(blk)
        }
        val out = ArrayList<Int>()
        for (p in blocks[0].indices) for (blk in blocks) blk[p]?.let { out.add(it) }
        return out.toIntArray()
    }

    private fun versionFor(n: Int, level: String): Int {
        for (ver in 1..40) if (4 + (if (ver <= 9) 8 else 16) + n * 8 <= dataCodewords(ver, level) * 8) return ver
        throw TooLong("$n bytes do not fit in a QR code")
    }

    private class Grid(val ver: Int) {
        val size = ver * 4 + 17
        val dark = Array(size) { BooleanArray(size) }
        val fixed = Array(size) { BooleanArray(size) }

        fun set(x: Int, y: Int, d: Boolean) { dark[y][x] = d; fixed[y][x] = true }

        fun functions() {
            val n = size
            for (i in 0 until n) { set(6, i, i % 2 == 0); set(i, 6, i % 2 == 0) }
            for ((cx, cy) in listOf(3 to 3, n - 4 to 3, 3 to n - 4)) {
                for (dy in -4..4) for (dx in -4..4) {
                    val x = cx + dx; val y = cy + dy
                    if (x in 0 until n && y in 0 until n) set(x, y, maxOf(Math.abs(dx), Math.abs(dy)) !in setOf(2, 4))
                }
            }
            val pos = alignment(ver)
            val last = pos.size - 1
            for ((i, a) in pos.withIndex()) for ((j, b) in pos.withIndex()) {
                if ((i == 0 && j == 0) || (i == 0 && j == last) || (i == last && j == 0)) continue
                for (dy in -2..2) for (dx in -2..2) set(a + dx, b + dy, maxOf(Math.abs(dx), Math.abs(dy)) != 1)
            }
            formatBits("L", 0)
            if (ver >= 7) {
                var rem = ver
                repeat(12) { rem = (rem shl 1) xor ((rem ushr 11) * 0x1F25) }
                val bits = (ver shl 12) or rem
                for (i in 0 until 18) {
                    val bit = ((bits ushr i) and 1) == 1
                    val a = n - 11 + i % 3; val b = i / 3
                    set(a, b, bit); set(b, a, bit)
                }
            }
        }

        fun formatBits(level: String, mask: Int) {
            val data = (FORMAT_LEVEL.getValue(level) shl 3) or mask
            var rem = data
            repeat(10) { rem = (rem shl 1) xor ((rem ushr 9) * 0x537) }
            val bits = ((data shl 10) or rem) xor 0x5412
            fun bit(i: Int) = ((bits ushr i) and 1) == 1
            val n = size
            for (i in 0 until 6) set(8, i, bit(i))
            set(8, 7, bit(6)); set(8, 8, bit(7)); set(7, 8, bit(8))
            for (i in 9 until 15) set(14 - i, 8, bit(i))
            for (i in 0 until 8) set(n - 1 - i, 8, bit(i))
            for (i in 8 until 15) set(8, n - 15 + i, bit(i))
            set(8, n - 8, true)
        }

        fun place(words: IntArray) {
            val n = size
            var i = 0
            val total = words.size * 8
            var right = n - 1
            while (right >= 1) {
                if (right == 6) right = 5
                for (vert in 0 until n) for (j in 0 until 2) {
                    val x = right - j
                    val upward = ((right + 1) and 2) == 0
                    val y = if (upward) n - 1 - vert else vert
                    if (!fixed[y][x] && i < total) {
                        dark[y][x] = ((words[i ushr 3] ushr (7 - (i and 7))) and 1) == 1
                        i++
                    }
                }
                right -= 2
            }
        }

        fun applyMask(mask: Int) {
            for (y in 0 until size) for (x in 0 until size) {
                if (fixed[y][x]) continue
                val inv = when (mask) {
                    0 -> (x + y) % 2 == 0
                    1 -> y % 2 == 0
                    2 -> x % 3 == 0
                    3 -> (x + y) % 3 == 0
                    4 -> (x / 3 + y / 2) % 2 == 0
                    5 -> x * y % 2 + x * y % 3 == 0
                    6 -> (x * y % 2 + x * y % 3) % 2 == 0
                    else -> ((x + y) % 2 + x * y % 3) % 2 == 0
                }
                if (inv) dark[y][x] = !dark[y][x]
            }
        }

        fun penalty(): Int {
            val n = size
            var score = 0
            val lines = ArrayList<BooleanArray>()
            for (y in 0 until n) lines.add(dark[y].copyOf())
            for (x in 0 until n) lines.add(BooleanArray(n) { dark[it][x] })
            val f1 = booleanArrayOf(true, false, true, true, true, false, true, false, false, false, false)
            val f2 = booleanArrayOf(false, false, false, false, true, false, true, true, true, false, true)
            for (line in lines) {
                var run = 1
                for (i in 1 until n) {
                    if (line[i] == line[i - 1]) run++ else { if (run >= 5) score += run - 2; run = 1 }
                }
                if (run >= 5) score += run - 2
                val padded = BooleanArray(n + 8)
                for (i in 0 until n) padded[i + 4] = line[i]
                for (i in 0 until padded.size - 10) {
                    var a = true; var b = true
                    for (k in 0 until 11) { if (padded[i + k] != f1[k]) a = false; if (padded[i + k] != f2[k]) b = false }
                    if (a || b) score += 40
                }
            }
            for (y in 0 until n - 1) for (x in 0 until n - 1) {
                val c = dark[y][x]
                if (c == dark[y][x + 1] && c == dark[y + 1][x] && c == dark[y + 1][x + 1]) score += 3
            }
            var d = 0
            for (row in dark) for (v in row) if (v) d++
            val total = n * n
            val k = (Math.abs(d * 20 - total * 10) + total - 1) / total - 1
            return score + k * 10
        }
    }

    /** Modules of the QR code for [text] (UTF-8), true = dark, without quiet zone. */
    fun encode(text: String, level: String = "M"): Array<BooleanArray> {
        require(level in ECC_PER_BLOCK) { "level must be L or M" }
        val data = text.toByteArray(Charsets.UTF_8)
        val ver = versionFor(data.size, level)
        val words = codewords(data, ver, level)
        var best: Grid? = null
        var bestScore = Int.MAX_VALUE
        for (mask in 0 until 8) {
            val g = Grid(ver)
            g.functions(); g.place(words); g.applyMask(mask); g.formatBits(level, mask)
            val s = g.penalty()
            if (s < bestScore) { best = g; bestScore = s }
        }
        return best!!.dark
    }

    /** The code as text rows of "#" and " " with a quiet zone of [border] modules (tests compare these). */
    fun textRows(m: Array<BooleanArray>, border: Int = 2): List<String> {
        val n = m.size
        return (-border until n + border).map { y ->
            (-border until n + border).joinToString("") { x -> if (x in 0 until n && y in 0 until n && m[y][x]) "#" else " " }
        }
    }
}
