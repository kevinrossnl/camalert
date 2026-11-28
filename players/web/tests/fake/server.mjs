// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
//
// Fake Home Assistant for the web player tests (#92, #127), no dependencies: the WebSocket API (auth, the
// camalert/browser/* commands, auth/sign_path), the integration's static files (/camalert_static/ = www/), the
// go2rtc view (/api/camalert/go2rtc/<id>/...: fake streams, frames, MJPEG; WebRTC refused so the MJPEG fallback runs)
// and /auth/token. Tests call fake.request(action, params) and get the browser's answer.
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const WWW = path.resolve(HERE, "../../../../custom_components/camalert/www");
export const TOKEN = "test-token";
// a 16x9 grey JPEG
export const JPEG = Buffer.from("/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDABALDA4MChAODQ4SERATGCgaGBYWGDEjJR0oOjM9PDkzODdASFxOQERXRTc4UG1RV19iZ2hnPk1xeXBkeFxlZ2P/2wBDARESEhgVGC8aGi9jQjhCY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2P/wAARCAAJABADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDMooooA//Z", "base64");
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".wav": "audio/wav" };
export const STREAMS = {
  front_door: { producers: [{ url: "rtsp://192.168.1.10:554/stream1" }] },
  garden: { producers: [{ url: "rtsp://192.168.1.11:554/stream1" }] },
  front_door_jpeg: { producers: [{ url: "ffmpeg:front_door#video=mjpeg" }] },
  all: { producers: [{ url: "exec:ffmpeg -i rtsp://127.0.0.1:8554/front_door -i rtsp://127.0.0.1:8554/garden -filter_complex x" }] },
  front_door_talk: { producers: [{ url: "exec:ffmpeg -f alaw -ar 8000 -ac 1 -i - -c:a aac -f adts udp://192.168.1.14:7004#backchannel=1#audio=alaw/8000" }] },
};

function frame(text) {
  const body = Buffer.from(text);
  const len = body.length;
  const head = len < 126 ? Buffer.from([0x81, len])
    : len < 65536 ? Buffer.from([0x81, 126, len >> 8, len & 255])
      : Buffer.concat([Buffer.from([0x81, 127, 0, 0, 0, 0]), Buffer.from([len >>> 24, (len >> 16) & 255, (len >> 8) & 255, len & 255])]);
  return Buffer.concat([head, body]);
}

/** Splits the client's (masked) frames; returns [texts, rest, closed]. */
function parse(buf) {
  const out = [];
  let closed = false;
  while (buf.length >= 2) {
    const op = buf[0] & 15;
    let len = buf[1] & 127;
    let off = 2;
    if (len === 126) {
      if (buf.length < 4) break;
      len = buf.readUInt16BE(2);
      off = 4;
    } else if (len === 127) {
      if (buf.length < 10) break;
      len = Number(buf.readBigUInt64BE(2));
      off = 10;
    }
    const masked = buf[1] & 128;
    const need = off + (masked ? 4 : 0) + len;
    if (buf.length < need) break;
    let data = buf.subarray(off + (masked ? 4 : 0), need);
    if (masked) {
      const m = buf.subarray(off, off + 4);
      data = Buffer.from(data.map((b, i) => b ^ m[i % 4]));
    }
    if (op === 1) out.push(data.toString("utf8"));
    if (op === 8) closed = true;
    buf = buf.subarray(need);
  }
  return [out, buf, closed];
}

export class FakeHA {
  constructor() {
    this.sockets = new Set();
    this.subs = new Map(); // browser_id -> {sock, id, hello}
    this.pending = new Map();
    this.next = 1;
    this.hellos = [];
    this.go2rtcRequests = [];
    this.webrtc = 500;
    this.acceptToken = TOKEN;
  }

  async start(port = 0) {
    this.server = http.createServer((req, res) => this._http(req, res));
    this.server.on("upgrade", (req, sock) => this._upgrade(req, sock));
    await new Promise((r) => this.server.listen(port, "127.0.0.1", r));
    this.url = `http://127.0.0.1:${this.server.address().port}`;
    return this;
  }

  async stop() {
    for (const s of this.sockets) s.destroy();
    await new Promise((r) => this.server.close(r));
  }

  _send(sock, msg) {
    sock.write(frame(JSON.stringify(msg)));
  }

  _upgrade(req, sock) {
    const key = req.headers["sec-websocket-key"];
    const accept = createHash("sha1").update(key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest("base64");
    sock.write("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n" +
               `Sec-WebSocket-Accept: ${accept}\r\n\r\n`);
    this.sockets.add(sock);
    let buf = Buffer.alloc(0);
    let authed = false;
    sock.on("data", (d) => {
      const [texts, rest, closed] = parse(Buffer.concat([buf, d]));
      buf = rest;
      for (const t of texts) {
        const msg = JSON.parse(t);
        if (msg.type === "auth") {
          authed = msg.access_token === this.acceptToken;
          this._send(sock, { type: authed ? "auth_ok" : "auth_invalid" });
          continue;
        }
        if (!authed) continue;
        this._command(sock, msg);
      }
      if (closed) sock.end();
    });
    sock.on("close", () => this._gone(sock));
    sock.on("error", () => this._gone(sock));
    this._send(sock, { type: "auth_required" });
  }

  _gone(sock) {
    this.sockets.delete(sock);
    for (const [bid, s] of this.subs) if (s.sock === sock) this.subs.delete(bid);
  }

  _command(sock, msg) {
    if (msg.type === "camalert/browser/connect") {
      this.subs.set(msg.browser_id, { sock, id: msg.id, hello: msg });
      this.hellos.push(msg);
      this._send(sock, { id: msg.id, type: "result", success: true, result: null });
    } else if (msg.type === "camalert/browser/reply") {
      const p = this.pending.get(msg.request_id);
      this._send(sock, { id: msg.id, type: "result", success: !!p, result: null });
      if (p) {
        this.pending.delete(msg.request_id);
        p({ code: msg.code, body: msg.body });
      }
    } else if (msg.type === "auth/sign_path") {
      this._send(sock, { id: msg.id, type: "result", success: true, result: { path: `${msg.path}${msg.path.includes("?") ? "&" : "?"}authSig=fake` } });
    } else {
      this._send(sock, { id: msg.id, type: "result", success: false, error: { code: "unknown_command", message: "unknown" } });
    }
  }

  /** Waits for a browser to subscribe; returns its browser_id. */
  async connected(timeout = 10000) {
    const t0 = Date.now();
    while (!this.subs.size) {
      if (Date.now() - t0 > timeout) throw new Error("no browser connected");
      await new Promise((r) => setTimeout(r, 50));
    }
    return [...this.subs.keys()][0];
  }

  /** Sends a CamAlert API request to the (first) connected browser; resolves with {code, body}. */
  request(action, params = {}, browserId = null) {
    const bid = browserId || [...this.subs.keys()][0];
    const s = this.subs.get(bid);
    if (!s) return Promise.reject(new Error("browser not connected"));
    const id = this.next++;
    return new Promise((resolve) => {
      this.pending.set(id, resolve);
      this._send(s.sock, { id: s.id, type: "event", event: { type: "request", id, action, params } });
    });
  }

  async _http(req, res) {
    const u = new URL(req.url, "http://x");
    if (u.pathname.startsWith("/camalert_static/")) {
      try {
        const file = path.join(WWW, u.pathname.slice("/camalert_static/".length));
        if (!file.startsWith(WWW)) throw new Error("outside");
        const body = await readFile(file);
        res.writeHead(200, { "Content-Type": TYPES[path.extname(file)] || "application/octet-stream" });
        res.end(body);
      } catch (e) {
        res.writeHead(404).end();
      }
      return;
    }
    if (u.pathname === "/test/dashboard.html") {
      res.writeHead(200, { "Content-Type": "text/html" }).end(await readFile(path.join(HERE, "dashboard.html")));
      return;
    }
    const m = /^\/api\/camalert\/go2rtc\/([a-z0-9]+)\/(.+)$/.exec(u.pathname);
    if (m) {
      const signed = u.searchParams.get("authSig") === "fake";
      if (req.headers.authorization !== `Bearer ${TOKEN}` && !signed) {
        res.writeHead(401).end();
        return;
      }
      this.go2rtcRequests.push(`${req.method} ${m[2]}?${u.searchParams.toString()}`);
      if (m[2] === "api/streams") {
        res.writeHead(200, { "Content-Type": "application/json" }).end(JSON.stringify(STREAMS));
      } else if (m[2] === "api/frame.jpeg") {
        res.writeHead(200, { "Content-Type": "image/jpeg" }).end(JPEG);
      } else if (m[2] === "api/stream.mjpeg") {
        res.writeHead(200, { "Content-Type": "multipart/x-mixed-replace; boundary=frame" });
        const part = () => res.write(Buffer.concat([
          Buffer.from(`--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ${JPEG.length}\r\n\r\n`), JPEG, Buffer.from("\r\n")]));
        part();
        const t = setInterval(part, 200);
        req.on("close", () => clearInterval(t));
      } else if (m[2] === "api/webrtc") {
        res.writeHead(this.webrtc).end();
      } else {
        res.writeHead(404).end();
      }
      return;
    }
    if (u.pathname === "/auth/token" && req.method === "POST") {
      res.writeHead(200, { "Content-Type": "application/json" })
        .end(JSON.stringify({ access_token: TOKEN, expires_in: 1800, token_type: "Bearer" }));
      return;
    }
    res.writeHead(404).end();
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const f = await new FakeHA().start(Number(process.argv[2] || 8123));
  console.log(`fake Home Assistant on ${f.url}`);
}
