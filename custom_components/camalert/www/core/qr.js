// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
//
// QR codes without dependencies (#132), the same as camalert_core.qr and Qr.kt: byte mode, level L or M,
// versions 1-40. The web player shows the link to a pre-filled GitHub issue as a QR code.

const ECC_PER_BLOCK = {
  L: [7, 10, 15, 20, 26, 18, 20, 24, 30, 18, 20, 24, 26, 30, 22, 24, 28, 30, 28, 28, 28, 28, 30, 30, 26, 28, 30, 30, 30,
    30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30],
  M: [10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26, 26, 26, 28, 28, 28, 28, 28, 28, 28, 28,
    28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28],
};
const BLOCKS = {
  L: [1, 1, 1, 1, 1, 2, 2, 2, 2, 4, 4, 4, 4, 4, 6, 6, 6, 6, 7, 8, 8, 9, 9, 10, 12, 12, 12, 13, 14, 15, 16, 17, 18, 19, 19,
    20, 21, 22, 24, 25],
  M: [1, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5, 8, 9, 9, 10, 10, 11, 13, 14, 16, 17, 17, 18, 20, 21, 23, 25, 26, 28, 29, 31, 33, 35,
    37, 38, 40, 43, 45, 47, 49],
};
const FORMAT_LEVEL = { L: 1, M: 0 };

function rawModules(ver) {
  let n = (16 * ver + 128) * ver + 64;
  if (ver >= 2) {
    const align = Math.floor(ver / 7) + 2;
    n -= (25 * align - 10) * align - 55;
    if (ver >= 7) n -= 36;
  }
  return n;
}

export function dataCodewords(ver, level) {
  return Math.floor(rawModules(ver) / 8) - ECC_PER_BLOCK[level][ver - 1] * BLOCKS[level][ver - 1];
}

function alignment(ver) {
  if (ver === 1) return [];
  const count = Math.floor(ver / 7) + 2;
  const step = ver === 32 ? 26 : Math.floor((ver * 4 + count * 2 + 1) / (count * 2 - 2)) * 2;
  const size = ver * 4 + 17;
  const out = [];
  for (let i = 0; i < count - 1; i++) out.push(size - 7 - i * step);
  return [6, ...out.sort((a, b) => a - b)];
}

function mul(x, y) {
  let z = 0;
  for (let i = 7; i >= 0; i--) {
    z = (z << 1) ^ ((z >>> 7) * 0x11d);
    z ^= ((y >>> i) & 1) * x;
  }
  return z & 0xff;
}

function divisor(degree) {
  const result = new Array(degree).fill(0);
  result[degree - 1] = 1;
  let root = 1;
  for (let r = 0; r < degree; r++) {
    for (let j = 0; j < degree; j++) {
      result[j] = mul(result[j], root);
      if (j + 1 < degree) result[j] ^= result[j + 1];
    }
    root = mul(root, 0x02);
  }
  return result;
}

function remainder(data, div) {
  const result = new Array(div.length).fill(0);
  for (const b of data) {
    const factor = b ^ result.shift();
    result.push(0);
    for (let i = 0; i < div.length; i++) result[i] ^= mul(div[i], factor);
  }
  return result;
}

function codewords(data, ver, level) {
  const capacity = dataCodewords(ver, level);
  const bits = [];
  const put = (value, length) => { for (let i = length - 1; i >= 0; i--) bits.push((value >>> i) & 1); };
  put(0b0100, 4);
  put(data.length, ver <= 9 ? 8 : 16);
  for (const b of data) put(b, 8);
  put(0, Math.min(4, capacity * 8 - bits.length));
  put(0, ((-bits.length % 8) + 8) % 8);
  const words = [];
  for (let i = 0; i < bits.length; i += 8) {
    let v = 0;
    for (let k = 0; k < 8; k++) v = (v << 1) | bits[i + k];
    words.push(v);
  }
  for (let pad = 0xec; words.length < capacity; pad ^= 0xec ^ 0x11) words.push(pad);
  const blocksN = BLOCKS[level][ver - 1];
  const eccLen = ECC_PER_BLOCK[level][ver - 1];
  const raw = Math.floor(rawModules(ver) / 8);
  const shortN = blocksN - (raw % blocksN);
  const shortLen = Math.floor(raw / blocksN);
  const div = divisor(eccLen);
  const blocks = [];
  let k = 0;
  for (let b = 0; b < blocksN; b++) {
    const dlen = shortLen - eccLen + (b < shortN ? 0 : 1);
    const dat = words.slice(k, k + dlen);
    k += dlen;
    const ecc = remainder(dat, div);
    blocks.push([...dat, ...(b < shortN ? [null] : []), ...ecc]);
  }
  const out = [];
  for (let p = 0; p < blocks[0].length; p++) for (const blk of blocks) if (blk[p] !== null) out.push(blk[p]);
  return out;
}

function versionFor(n, level) {
  for (let ver = 1; ver <= 40; ver++) if (4 + (ver <= 9 ? 8 : 16) + n * 8 <= dataCodewords(ver, level) * 8) return ver;
  throw new RangeError(`${n} bytes do not fit in a QR code`);
}

class Grid {
  constructor(ver) {
    this.ver = ver;
    this.size = ver * 4 + 17;
    this.dark = Array.from({ length: this.size }, () => new Array(this.size).fill(false));
    this.fixed = Array.from({ length: this.size }, () => new Array(this.size).fill(false));
  }

  set(x, y, d) { this.dark[y][x] = d; this.fixed[y][x] = true; }

  functions() {
    const n = this.size;
    for (let i = 0; i < n; i++) { this.set(6, i, i % 2 === 0); this.set(i, 6, i % 2 === 0); }
    for (const [cx, cy] of [[3, 3], [n - 4, 3], [3, n - 4]]) {
      for (let dy = -4; dy <= 4; dy++) {
        for (let dx = -4; dx <= 4; dx++) {
          const x = cx + dx, y = cy + dy;
          const dist = Math.max(Math.abs(dx), Math.abs(dy));
          if (x >= 0 && x < n && y >= 0 && y < n) this.set(x, y, dist !== 2 && dist !== 4);
        }
      }
    }
    const pos = alignment(this.ver);
    const last = pos.length - 1;
    pos.forEach((a, i) => pos.forEach((b, j) => {
      if ((i === 0 && j === 0) || (i === 0 && j === last) || (i === last && j === 0)) return;
      for (let dy = -2; dy <= 2; dy++) {
        for (let dx = -2; dx <= 2; dx++) this.set(a + dx, b + dy, Math.max(Math.abs(dx), Math.abs(dy)) !== 1);
      }
    }));
    this.formatBits("L", 0);
    if (this.ver >= 7) {
      let rem = this.ver;
      for (let i = 0; i < 12; i++) rem = (rem << 1) ^ ((rem >>> 11) * 0x1f25);
      const bits = (this.ver << 12) | rem;
      for (let i = 0; i < 18; i++) {
        const bit = ((bits >>> i) & 1) === 1;
        const a = n - 11 + (i % 3), b = Math.floor(i / 3);
        this.set(a, b, bit);
        this.set(b, a, bit);
      }
    }
  }

  formatBits(level, mask) {
    const data = (FORMAT_LEVEL[level] << 3) | mask;
    let rem = data;
    for (let i = 0; i < 10; i++) rem = (rem << 1) ^ ((rem >>> 9) * 0x537);
    const bits = ((data << 10) | rem) ^ 0x5412;
    const bit = (i) => ((bits >>> i) & 1) === 1;
    const n = this.size;
    for (let i = 0; i < 6; i++) this.set(8, i, bit(i));
    this.set(8, 7, bit(6)); this.set(8, 8, bit(7)); this.set(7, 8, bit(8));
    for (let i = 9; i < 15; i++) this.set(14 - i, 8, bit(i));
    for (let i = 0; i < 8; i++) this.set(n - 1 - i, 8, bit(i));
    for (let i = 8; i < 15; i++) this.set(8, n - 15 + i, bit(i));
    this.set(8, n - 8, true);
  }

  place(words) {
    const n = this.size;
    const total = words.length * 8;
    let i = 0;
    for (let right = n - 1; right >= 1; right -= 2) {
      if (right === 6) right = 5;
      for (let vert = 0; vert < n; vert++) {
        for (let j = 0; j < 2; j++) {
          const x = right - j;
          const upward = ((right + 1) & 2) === 0;
          const y = upward ? n - 1 - vert : vert;
          if (!this.fixed[y][x] && i < total) {
            this.dark[y][x] = ((words[i >>> 3] >>> (7 - (i & 7))) & 1) === 1;
            i++;
          }
        }
      }
    }
  }

  applyMask(mask) {
    for (let y = 0; y < this.size; y++) {
      for (let x = 0; x < this.size; x++) {
        if (this.fixed[y][x]) continue;
        let inv;
        switch (mask) {
          case 0: inv = (x + y) % 2 === 0; break;
          case 1: inv = y % 2 === 0; break;
          case 2: inv = x % 3 === 0; break;
          case 3: inv = (x + y) % 3 === 0; break;
          case 4: inv = (Math.floor(x / 3) + Math.floor(y / 2)) % 2 === 0; break;
          case 5: inv = ((x * y) % 2) + ((x * y) % 3) === 0; break;
          case 6: inv = (((x * y) % 2) + ((x * y) % 3)) % 2 === 0; break;
          default: inv = (((x + y) % 2) + ((x * y) % 3)) % 2 === 0;
        }
        if (inv) this.dark[y][x] = !this.dark[y][x];
      }
    }
  }

  penalty() {
    const n = this.size, m = this.dark;
    let score = 0;
    const lines = [...m.map((r) => r.slice())];
    for (let x = 0; x < n; x++) lines.push(m.map((r) => r[x]));
    const f1 = [true, false, true, true, true, false, true, false, false, false, false];
    const f2 = [false, false, false, false, true, false, true, true, true, false, true];
    for (const line of lines) {
      let run = 1;
      for (let i = 1; i < n; i++) {
        if (line[i] === line[i - 1]) run++;
        else { if (run >= 5) score += run - 2; run = 1; }
      }
      if (run >= 5) score += run - 2;
      const padded = [false, false, false, false, ...line, false, false, false, false];
      for (let i = 0; i < padded.length - 10; i++) {
        let a = true, b = true;
        for (let k = 0; k < 11; k++) {
          if (padded[i + k] !== f1[k]) a = false;
          if (padded[i + k] !== f2[k]) b = false;
        }
        if (a || b) score += 40;
      }
    }
    for (let y = 0; y < n - 1; y++) {
      for (let x = 0; x < n - 1; x++) {
        const c = m[y][x];
        if (c === m[y][x + 1] && c === m[y + 1][x] && c === m[y + 1][x + 1]) score += 3;
      }
    }
    let d = 0;
    for (const row of m) for (const v of row) if (v) d++;
    const total = n * n;
    const k = Math.floor((Math.abs(d * 20 - total * 10) + total - 1) / total) - 1;
    return score + k * 10;
  }
}

/** Modules of the QR code for text (UTF-8), true = dark, without quiet zone. */
export function encode(text, level = "M") {
  if (!(level in ECC_PER_BLOCK)) throw new RangeError("level must be L or M");
  const data = Array.from(new TextEncoder().encode(text));
  const ver = versionFor(data.length, level);
  const words = codewords(data, ver, level);
  let best = null, bestScore = Infinity;
  for (let mask = 0; mask < 8; mask++) {
    const g = new Grid(ver);
    g.functions(); g.place(words); g.applyMask(mask); g.formatBits(level, mask);
    const s = g.penalty();
    if (s < bestScore) { best = g; bestScore = s; }
  }
  return best.dark;
}

/** The code as text rows of "#" and " " with a quiet zone (tests compare these with Python and Kotlin). */
export function textRows(m, border = 2) {
  const n = m.length;
  const rows = [];
  for (let y = -border; y < n + border; y++) {
    let s = "";
    for (let x = -border; x < n + border; x++) s += x >= 0 && x < n && y >= 0 && y < n && m[y][x] ? "#" : " ";
    rows.push(s);
  }
  return rows;
}

/** Draws the code on a canvas (black on white, quiet zone of 4 modules). */
export function draw(canvas, m, px = 6) {
  const n = m.length, side = (n + 8) * px;
  canvas.width = side;
  canvas.height = side;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, side, side);
  ctx.fillStyle = "#000";
  for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) if (m[y][x]) ctx.fillRect((x + 4) * px, (y + 4) * px, px, px);
}
