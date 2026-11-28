# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""QR codes without dependencies (#132): the players show a link to a pre-filled GitHub issue as a QR code that
a phone scans. Byte mode, error correction L or M, versions 1-40 (ISO/IEC 18004), plus a tiny PNG writer.

    encode(b"https://...", "M") -> [[bool]]   modules, True = dark (no quiet zone)
    png(matrix, scale=8, border=4) -> bytes   black on white
Ported to Kotlin (Qr.kt) and JavaScript (players/web/core/qr.js); the same test vectors run on all three."""
import struct
import zlib

# per version 1-40: error correction codewords per block and number of blocks (ISO/IEC 18004 table 9)
_ECC_PER_BLOCK = {
    "L": (7, 10, 15, 20, 26, 18, 20, 24, 30, 18, 20, 24, 26, 30, 22, 24, 28, 30, 28, 28, 28, 28, 30, 30, 26, 28, 30,
          30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),
    "M": (10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26, 26, 26, 28, 28, 28, 28, 28, 28,
          28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28),
}
_BLOCKS = {
    "L": (1, 1, 1, 1, 1, 2, 2, 2, 2, 4, 4, 4, 4, 4, 6, 6, 6, 6, 7, 8, 8, 9, 9, 10, 12, 12, 12, 13, 14, 15, 16, 17, 18,
          19, 19, 20, 21, 22, 24, 25),
    "M": (1, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5, 8, 9, 9, 10, 10, 11, 13, 14, 16, 17, 17, 18, 20, 21, 23, 25, 26, 28, 29, 31,
          33, 35, 37, 38, 40, 43, 45, 47, 49),
}
_FORMAT_LEVEL = {"L": 1, "M": 0}


class TooLong(ValueError):
    """The data does not fit in a version-40 code."""


def _raw_modules(ver):
    n = (16 * ver + 128) * ver + 64
    if ver >= 2:
        align = ver // 7 + 2
        n -= (25 * align - 10) * align - 55
        if ver >= 7:
            n -= 36
    return n


def data_codewords(ver, level):
    return _raw_modules(ver) // 8 - _ECC_PER_BLOCK[level][ver - 1] * _BLOCKS[level][ver - 1]


def _alignment(ver):
    if ver == 1:
        return []
    count = ver // 7 + 2
    step = 26 if ver == 32 else (ver * 4 + count * 2 + 1) // (count * 2 - 2) * 2
    size = ver * 4 + 17
    out = [size - 7 - i * step for i in range(count - 1)]
    return [6] + sorted(out)


# --- Reed-Solomon over GF(256), polynomial 0x11D ---------------------------------------------------------------------
def _mul(x, y):
    z = 0
    for i in range(7, -1, -1):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z & 0xFF


def _divisor(degree):
    result = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            result[j] = _mul(result[j], root)
            if j + 1 < degree:
                result[j] ^= result[j + 1]
        root = _mul(root, 0x02)
    return result


def _remainder(data, divisor):
    result = [0] * len(divisor)
    for b in data:
        factor = b ^ result.pop(0)
        result.append(0)
        for i, c in enumerate(divisor):
            result[i] ^= _mul(c, factor)
    return result


# --- encoding ----------------------------------------------------------------------------------------------------------
def _codewords(data, ver, level):
    capacity = data_codewords(ver, level)
    bits = []

    def put(value, length):
        bits.extend((value >> i) & 1 for i in range(length - 1, -1, -1))

    put(0b0100, 4)
    put(len(data), 8 if ver <= 9 else 16)
    for b in data:
        put(b, 8)
    put(0, min(4, capacity * 8 - len(bits)))
    put(0, (-len(bits)) % 8)
    words = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = 0xEC
    while len(words) < capacity:
        words.append(pad)
        pad ^= 0xEC ^ 0x11
    # split into blocks, add error correction, interleave
    blocks_n = _BLOCKS[level][ver - 1]
    ecc_len = _ECC_PER_BLOCK[level][ver - 1]
    raw = _raw_modules(ver) // 8
    short_n = blocks_n - raw % blocks_n
    short_len = raw // blocks_n
    div = _divisor(ecc_len)
    blocks, k = [], 0
    for i in range(blocks_n):
        dlen = short_len - ecc_len + (0 if i < short_n else 1)
        dat = words[k:k + dlen]
        k += dlen
        ecc = _remainder(dat, div)
        if i < short_n:
            dat = dat + [None]
        blocks.append(dat + ecc)
    out = []
    for i in range(len(blocks[0])):
        for j, blk in enumerate(blocks):
            if blk[i] is not None:
                out.append(blk[i])
    return out


def _version_for(n, level):
    for ver in range(1, 41):
        if 4 + (8 if ver <= 9 else 16) + n * 8 <= data_codewords(ver, level) * 8:
            return ver
    raise TooLong("%d bytes do not fit in a QR code" % n)


class _Grid(object):
    def __init__(self, ver):
        self.ver = ver
        self.size = ver * 4 + 17
        self.dark = [[False] * self.size for _ in range(self.size)]
        self.fixed = [[False] * self.size for _ in range(self.size)]

    def set(self, x, y, dark):
        self.dark[y][x] = dark
        self.fixed[y][x] = True

    def functions(self):
        n = self.size
        for i in range(n):
            self.set(6, i, i % 2 == 0)
            self.set(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < n and 0 <= y < n:
                        self.set(x, y, max(abs(dx), abs(dy)) not in (2, 4))
        pos = _alignment(self.ver)
        last = len(pos) - 1
        for i, a in enumerate(pos):
            for j, b in enumerate(pos):
                if (i == 0 and j == 0) or (i == 0 and j == last) or (i == last and j == 0):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self.set(a + dx, b + dy, max(abs(dx), abs(dy)) != 1)
        self.format_bits("L", 0)  # reserve
        if self.ver >= 7:
            rem = self.ver
            for _ in range(12):
                rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
            bits = self.ver << 12 | rem
            for i in range(18):
                bit = (bits >> i) & 1 == 1
                a, b = n - 11 + i % 3, i // 3
                self.set(a, b, bit)
                self.set(b, a, bit)

    def format_bits(self, level, mask):
        data = _FORMAT_LEVEL[level] << 3 | mask
        rem = data
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits = (data << 10 | rem) ^ 0x5412
        n = self.size
        for i in range(6):
            self.set(8, i, (bits >> i) & 1 == 1)
        self.set(8, 7, (bits >> 6) & 1 == 1)
        self.set(8, 8, (bits >> 7) & 1 == 1)
        self.set(7, 8, (bits >> 8) & 1 == 1)
        for i in range(9, 15):
            self.set(14 - i, 8, (bits >> i) & 1 == 1)
        for i in range(8):
            self.set(n - 1 - i, 8, (bits >> i) & 1 == 1)
        for i in range(8, 15):
            self.set(8, n - 15 + i, (bits >> i) & 1 == 1)
        self.set(8, n - 8, True)  # dark module

    def place(self, words):
        n = self.size
        i = 0
        total = len(words) * 8
        right = n - 1
        while right >= 1:
            if right == 6:
                right = 5
            for vert in range(n):
                for j in range(2):
                    x = right - j
                    upward = ((right + 1) & 2) == 0
                    y = n - 1 - vert if upward else vert
                    if not self.fixed[y][x] and i < total:
                        self.dark[y][x] = (words[i >> 3] >> (7 - (i & 7))) & 1 == 1
                        i += 1
            right -= 2

    def apply_mask(self, mask):
        for y in range(self.size):
            for x in range(self.size):
                if self.fixed[y][x]:
                    continue
                if mask == 0:
                    inv = (x + y) % 2 == 0
                elif mask == 1:
                    inv = y % 2 == 0
                elif mask == 2:
                    inv = x % 3 == 0
                elif mask == 3:
                    inv = (x + y) % 3 == 0
                elif mask == 4:
                    inv = (x // 3 + y // 2) % 2 == 0
                elif mask == 5:
                    inv = x * y % 2 + x * y % 3 == 0
                elif mask == 6:
                    inv = (x * y % 2 + x * y % 3) % 2 == 0
                else:
                    inv = ((x + y) % 2 + x * y % 3) % 2 == 0
                if inv:
                    self.dark[y][x] = not self.dark[y][x]

    def penalty(self):
        n, m = self.size, self.dark
        score = 0
        lines = [row for row in m] + [[m[y][x] for y in range(n)] for x in range(n)]
        finder = ([True, False, True, True, True, False, True, False, False, False, False],
                  [False, False, False, False, True, False, True, True, True, False, True])
        for line in lines:
            run = 1
            for i in range(1, n):
                if line[i] == line[i - 1]:
                    run += 1
                else:
                    if run >= 5:
                        score += run - 2
                    run = 1
            if run >= 5:
                score += run - 2
            padded = [False] * 4 + line + [False] * 4
            for i in range(len(padded) - 10):
                if padded[i:i + 11] in finder:
                    score += 40
        for y in range(n - 1):
            for x in range(n - 1):
                c = m[y][x]
                if c == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                    score += 3
        dark = sum(sum(row) for row in m)
        total = n * n
        k = (abs(dark * 20 - total * 10) + total - 1) // total - 1
        score += k * 10
        return score


def encode(data, level="M"):
    """Modules of the QR code for data (bytes or str, UTF-8), True = dark. level "L" or "M"."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    if level not in _ECC_PER_BLOCK:
        raise ValueError("level must be L or M")
    ver = _version_for(len(data), level)
    words = _codewords(list(bytearray(data)), ver, level)
    best, best_score = None, None
    for mask in range(8):
        g = _Grid(ver)
        g.functions()
        g.place(words)
        g.apply_mask(mask)
        g.format_bits(level, mask)
        s = g.penalty()
        if best_score is None or s < best_score:
            best, best_score = g, s
    return best.dark


def png(matrix, scale=8, border=4):
    """Black-on-white PNG (8-bit grey) of the modules, with a quiet zone of `border` modules."""
    n = len(matrix)
    side = (n + 2 * border) * scale
    rows = []
    for y in range(-border, n + border):
        line = bytearray()
        for x in range(-border, n + border):
            dark = 0 <= x < n and 0 <= y < n and matrix[y][x]
            line.extend((b"\x00" if dark else b"\xff") * scale)
        rows.extend([b"\x00" + bytes(line)] * scale)

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", side, side, 8, 0, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))


def text_rows(matrix, border=2):
    """The code as text rows of "#" and " " (for logs and tests)."""
    n = len(matrix)
    return ["".join("#" if 0 <= x < n and 0 <= y < n and matrix[y][x] else " " for x in range(-border, n + border))
            for y in range(-border, n + border)]
