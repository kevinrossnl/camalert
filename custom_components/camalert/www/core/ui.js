// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
//
// The browser player's screen (#92, #127): photo window, live window, several cameras, mosaic, notification and a
// short notice, drawn into a shadow root so the page's own styles (a Home Assistant dashboard) never mix in.
// Geometry, colours and texts come from the core (generated.js, i18n.js): the same window as on the TV.
import { DATA } from "./generated.js";
import { TEXTS } from "./i18n.js";
import { pictureSources, urls } from "./pictures.js";

const FRAME_EVERY_MS = 1000; // a new frame.jpeg while no warm feed exists
const LIVE_TIMEOUT_MS = 6000; // WebRTC must show video by then, else MJPEG
const NOTICE_MS = 4000;

/** The language of the player's texts: the setting, else the browser's, else English. */
export function language(setting, nav = globalThis.navigator) {
  if (setting && setting !== "system" && TEXTS[setting]) return setting;
  const l = String((nav && nav.language) || "en").slice(0, 2).toLowerCase();
  return TEXTS[l] ? l : "en";
}

/** The clock text "14:08" in the player's language (24 hours except English), not the browser's locale. */
export function clockText(date, lang) {
  const opts = { hour: "2-digit", minute: "2-digit" };
  if (lang !== "en") opts.hourCycle = "h23";
  return date.toLocaleTimeString(lang || "en", opts);
}

export function translator(lang) {
  const t = TEXTS[lang] || {};
  return (msgid) => t[msgid] || msgid;
}

/** (x, y, w, h, titleH) of the window for a screen size, as layout.window_geometry() in the core. */
export function windowGeometry(position, size, screenW, screenH, textSize = "normal") {
  const f = screenW / 1920;
  const [bw, bh] = DATA.sizes[size] || DATA.sizes.medium;
  const w = Math.round(bw * f);
  const h = Math.round(bh * f);
  const title = Math.round(DATA.titleSizes.normal[0] * f * (DATA.textSizes[textSize] || 1));
  const margin = Math.round(40 * f);
  const x = ["top_left", "bottom_left"].includes(position) ? margin : screenW - w - margin;
  const y = ["top_left", "top_right"].includes(position) ? margin : screenH - (h + title) - margin;
  return { x, y, w, h, title };
}

/** Tiles {x, y, w, h} for n cameras in a 1x1, 2x2 or 3x3 grid with 16:9 tiles, centred (layout.grid()). */
export function grid(n, screenW, screenH, gap = 8) {
  const cols = n <= 1 ? 1 : n <= 4 ? 2 : 3;
  const rows = Math.ceil(n / cols);
  let w = Math.floor((screenW - gap * (cols + 1)) / cols);
  let h = Math.floor(w * 9 / 16);
  if (h * rows + gap * (rows + 1) > screenH) {
    h = Math.floor((screenH - gap * (rows + 1)) / rows);
    w = Math.floor(h * 16 / 9);
  }
  const x0 = Math.floor((screenW - (w * cols + gap * (cols - 1))) / 2);
  const y0 = Math.floor((screenH - (h * rows + gap * (rows - 1))) / 2);
  return Array.from({ length: n }, (_, i) => ({
    x: x0 + (i % cols) * (w + gap), y: y0 + Math.floor(i / cols) * (h + gap), w, h,
  }));
}

/** The title with the priority word in front (style.marked_title). */
export function markedTitle(title, priority, border, tr) {
  if (!["steady", "flash"].includes(border) || !DATA.priorityMarks[priority]) return title;
  const word = tr(DATA.priorityMarks[priority]);
  return title ? `${word} · ${title}` : word;
}

const CSS = `
:host { all: initial; }
.layer { position: fixed; inset: 0; pointer-events: none; z-index: 2147483000; font-family: sans-serif; }
.win, .mosaic, .note, .notice { position: fixed; background: ${DATA.background}; color: ${DATA.textColour};
  pointer-events: auto; box-sizing: border-box; overflow: hidden; }
.win { border: 4px solid transparent; box-shadow: 0 4px 24px rgba(0,0,0,.6); }
.win.flash { animation: flash ${DATA.flashMs * 2}ms step-end infinite; }
@keyframes flash { 50% { border-color: transparent; } }
.bar { display: flex; align-items: center; padding: 0 .6em; white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis; }
.body { position: relative; display: grid; gap: 2px; background: #000; }
.tile { position: relative; background: #000; overflow: hidden; }
.tile img, .tile video { width: 100%; height: 100%; object-fit: contain; display: block; }
.tile .msg { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  color: #ccc; font-size: 1.1em; text-align: center; padding: .5em; }
.tile .name { position: absolute; left: 0; right: 0; bottom: 0; padding: .2em .5em; background: rgba(0,0,0,.55); }
.mosaic { inset: 0; background: #000; }
.note { right: 2vw; bottom: 3vh; width: 28vw; min-width: 260px; border-radius: 6px; padding: .5em;
  border: 4px solid transparent; }
.note img { width: 100%; display: block; margin-top: .4em; }
.talk { margin-left: auto; padding: .1em .8em; border-radius: 1em; border: 0; font: inherit; font-size: .8em;
  background: #444; color: #fff; cursor: pointer; }
.talk.on { background: #c0392b; }
.notice { left: 50%; bottom: 6vh; transform: translateX(-50%); padding: .6em 1.2em; border-radius: 6px; }
`;

class Tile {
  constructor(view, cam, el, live) {
    this.view = view;
    this.cam = cam;
    this.el = el;
    this.live = live;
    this.stopped = false;
    this.timer = null;
    this.urlObj = null;
    this.pc = null;
    this.fails = 0;
    this.msg = document.createElement("div");
    this.msg.className = "msg";
    this.msg.textContent = view.tr("Loading picture...");
    el.appendChild(this.msg);
  }

  async start() {
    const p = this.view.player;
    if (!p.configured()) {
      this.msg.textContent = this.view.tr("go2rtc address not set");
      return;
    }
    if (this.live) {
      try {
        await this._webrtc();
        return;
      } catch (e) {
        p.log(`live ${this.cam}: WebRTC failed (${e.message}), MJPEG instead`);
      }
      const at = source(p, this.cam);
      await this._stream(urls(at.base, this.cam, "", at.stream).mjpeg);
      return;
    }
    const at = source(p, this.cam);
    const src = pictureSources(at.base, this.cam, p.settings().ready_cameras, at.stream);
    if (src.stream) await this._stream(src.stream);
    else this._frames(src.first, src.next);
  }

  async _stream(url) {
    if (this.stopped) return;
    const img = document.createElement("img");
    img.alt = "";
    img.onload = () => this.msg.remove();
    img.onerror = () => { this.msg.textContent = this.view.tr("Camera not reachable"); };
    if (this.view.link.direct) {
      img.src = url; // straight from go2rtc (MQTT, #131): nothing to sign
    } else {
      const path = url.slice(url.indexOf("/api/"));
      img.src = this.view.absolute(await this.view.link.sign(path));
    }
    this.el.insertBefore(img, this.msg);
  }

  _frames(first, next) {
    const img = document.createElement("img");
    img.alt = "";
    this.el.insertBefore(img, this.msg);
    const load = async (url) => {
      if (this.stopped) return;
      const t0 = Date.now();
      try {
        const r = await this.view.player.authFetch(url);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const blob = await r.blob();
        if (this.stopped) return;
        const obj = URL.createObjectURL(blob);
        img.src = obj;
        if (this.urlObj) URL.revokeObjectURL(this.urlObj);
        this.urlObj = obj;
        this.fails = 0;
        this.msg.remove();
      } catch (e) {
        this.fails += 1;
        if (this.fails === 2) this.msg.textContent = this.view.tr("Camera not reachable");
      }
      if (!this.stopped) this.timer = setTimeout(() => load(next), Math.max(50, FRAME_EVERY_MS - (Date.now() - t0)));
    };
    load(first);
  }

  async _webrtc() {
    const video = document.createElement("video");
    video.autoplay = true;
    video.playsInline = true;
    video.muted = !this.view.soundAllowed();
    const pc = new RTCPeerConnection({ iceServers: [] });
    this.pc = pc;
    pc.addTransceiver("video", { direction: "recvonly" });
    pc.addTransceiver("audio", { direction: "recvonly" });
    const shown = new Promise((resolve, reject) => {
      pc.ontrack = (e) => {
        if (!video.srcObject) video.srcObject = e.streams[0] || new MediaStream([e.track]);
      };
      video.onplaying = resolve;
      setTimeout(() => reject(new Error("no video")), LIVE_TIMEOUT_MS);
    });
    await pc.setLocalDescription(await pc.createOffer());
    await new Promise((r) => {
      if (pc.iceGatheringState === "complete") return r();
      pc.onicegatheringstatechange = () => pc.iceGatheringState === "complete" && r();
      setTimeout(r, 1500);
    });
    const at = source(this.view.player, this.cam);
    const r = await this.view.player.authFetch(urls(at.base, this.cam, "", at.stream).webrtc, {
      method: "POST", headers: { "Content-Type": "application/sdp" }, body: pc.localDescription.sdp,
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    await pc.setRemoteDescription({ type: "answer", sdp: await r.text() });
    this.el.insertBefore(video, this.msg);
    try {
      await shown;
      this.msg.remove();
    } catch (e) {
      video.remove();
      pc.close();
      this.pc = null;
      throw e;
    }
  }

  stop() {
    this.stopped = true;
    if (this.timer) clearTimeout(this.timer);
    if (this.urlObj) URL.revokeObjectURL(this.urlObj);
    if (this.pc) this.pc.close();
    for (const m of this.el.querySelectorAll("img,video")) {
      m.removeAttribute("src");
      if (m.srcObject) m.srcObject = null;
    }
  }
}

/** {base, stream(name)} of a camera: its go2rtc server (#131); a player without src() has one server. */
export function source(player, cam) {
  return player.src ? player.src(cam) : { base: player.base(), stream: (n) => n };
}

const TALK_MAX_MS = 60000; // talking stops by itself after a minute

/** Talking to a camera from the browser's microphone (#98): WebRTC to go2rtc's "<camera>_talk" stream, whose
 *  exec backchannel sends the audio to the camera's speaker. Needs a secure page (HTTPS) for the microphone. */
export class Talk {
  constructor(player, stream, deps = {}) {
    this.player = player;
    this.stream = stream;
    this.base = deps.base || null; // the go2rtc server of the camera (#131); default the main one
    this.media = deps.media || (globalThis.navigator && globalThis.navigator.mediaDevices);
    this.Peer = deps.Peer || globalThis.RTCPeerConnection;
    this.pc = null;
    this.mic = null;
    this.timer = null;
  }

  static possible(media = globalThis.navigator && globalThis.navigator.mediaDevices, secure = globalThis.isSecureContext) {
    return Boolean(secure && media && media.getUserMedia);
  }

  get on() {
    return this.pc !== null;
  }

  async start() {
    if (this.pc) return;
    this.mic = await this.media.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    const pc = new this.Peer({ iceServers: [] });
    this.pc = pc;
    for (const t of this.mic.getAudioTracks()) pc.addTransceiver(t, { direction: "sendonly" });
    await pc.setLocalDescription(await pc.createOffer());
    await new Promise((r) => {
      if (pc.iceGatheringState === "complete") return r();
      pc.onicegatheringstatechange = () => pc.iceGatheringState === "complete" && r();
      setTimeout(r, 1500);
    });
    const r = await this.player.authFetch(urls(this.base || this.player.base(), this.stream).webrtc, {
      method: "POST", headers: { "Content-Type": "application/sdp" }, body: pc.localDescription.sdp,
    });
    if (!r.ok) {
      this.stop();
      throw new Error(`HTTP ${r.status}`);
    }
    await pc.setRemoteDescription({ type: "answer", sdp: await r.text() });
    this.timer = setTimeout(() => this.stop(), TALK_MAX_MS);
  }

  stop() {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    if (this.mic) for (const t of this.mic.getTracks()) t.stop();
    this.mic = null;
    if (this.pc) this.pc.close();
    this.pc = null;
  }
}

export class DomView {
  /**
   * @param {HTMLElement} host   element that gets the shadow root (appended to document.body when not attached)
   * @param {Player} player
   * @param {object} deps        link (sign), chimeUrl, soundAllowed(), haUrl
   */
  constructor(host, player, deps) {
    this.player = player;
    this.link = deps.link;
    this.deps = deps;
    this.root = host.shadowRoot || host.attachShadow({ mode: "open" });
    const style = document.createElement("style");
    style.textContent = CSS;
    this.layer = document.createElement("div");
    this.layer.className = "layer";
    this.root.append(style, this.layer);
    this.tiles = [];
    this.current = null;
    this.noteTimer = null;
  }

  get tr() {
    return translator(language(this.player.settings().language));
  }

  soundAllowed() {
    return this.deps.soundAllowed ? this.deps.soundAllowed() : false;
  }

  absolute(path) {
    return /^https?:/.test(path) ? path : `${this.deps.haUrl.replace(/\/$/, "")}${path}`;
  }

  _clear() {
    if (this.talk) this.talk.stop();
    this.talk = null;
    for (const t of this.tiles) t.stop();
    this.tiles = [];
    if (this.current) this.current.remove();
    this.current = null;
  }

  _tiles(body, cams, live, names) {
    for (const cam of cams) {
      const el = document.createElement("div");
      el.className = "tile";
      el.dataset.camera = cam;
      if (names) {
        const n = document.createElement("div");
        n.className = "name";
        n.textContent = this.player.title(cam);
        el.appendChild(n);
      }
      body.appendChild(el);
      const t = new Tile(this, cam, el, live);
      this.tiles.push(t);
      t.start();
    }
  }

  window({ cams, mode, priority, label }) {
    this._clear();
    const s = this.player.settings();
    const W = globalThis.innerWidth || 1920;
    const H = globalThis.innerHeight || 1080;
    let g = windowGeometry(s.position, s.size, W, H, s.text_size);
    if (this.deps.fill) {  // the extension's own popup window: the window fills it
      const t = Math.round(DATA.titleSizes.normal[0] * (DATA.textSizes[s.text_size] || 1) * 0.75);
      g = { x: 0, y: 0, w: W - 8, h: H - t - 8, title: t };
    }
    const el = document.createElement("div");
    el.className = "win";
    el.dataset.screen = mode === "live" ? "live" : cams.length > 1 ? "strip" : "photo";
    el.dataset.priority = priority;
    Object.assign(el.style, { left: `${g.x}px`, top: `${g.y}px`, width: `${g.w + 8}px` });
    const colour = DATA.priorityColours[priority];
    if (colour && s.priority_border !== "off") {
      el.style.borderColor = colour;
      if (s.priority_border === "flash") el.classList.add("flash");
    }
    const bar = document.createElement("div");
    bar.className = "bar";
    Object.assign(bar.style, { height: `${g.title}px`, fontSize: `${Math.round(g.title * 0.62)}px` });
    const title = cams.map((c) => this.player.title(c)).join(", ");
    bar.textContent = markedTitle(label ? `${title} · ${label}` : title, priority, s.priority_border, this.tr);
    const body = document.createElement("div");
    body.className = "body";
    const cols = cams.length <= 1 ? 1 : cams.length <= 4 ? 2 : 3;
    Object.assign(body.style, { height: `${g.h}px`, gridTemplateColumns: `repeat(${cols}, 1fr)` });
    el.append(bar, body);
    el.addEventListener("click", () => this.player.controller.hide());
    this.layer.appendChild(el);
    this.current = el;
    this._tiles(body, cams, mode === "live", cams.length > 1);
    if (cams.length === 1) this._talkButton(el, bar, cams[0]);
  }

  /** #98: a "Talk" button in the title bar when go2rtc has a talk-back stream for the camera. */
  async _talkButton(el, bar, cam) {
    const stream = await this.player.talkStream(cam);
    if (!stream || this.current !== el) return;
    const btn = document.createElement("button");
    btn.className = "talk";
    btn.textContent = this.tr("Talk");
    btn.addEventListener("click", async (e) => {
      e.stopPropagation(); // a click on the window closes it; this one must not
      if (!Talk.possible(this.deps.media, this.deps.secure ?? globalThis.isSecureContext)) {
        this.toast(this.tr("Talking needs the page over HTTPS"));
        return;
      }
      if (this.talk && this.talk.on) {
        this.talk.stop();
      } else {
        this.talk = new Talk(this.player, stream, { media: this.deps.media, Peer: this.deps.Peer,
                                                    base: source(this.player, cam).base });
        try {
          await this.talk.start();
        } catch (err) {
          this.player.log(`talk ${cam}: ${err.message}`);
          this.toast(this.tr("Talking did not start"));
        }
      }
      const on = Boolean(this.talk && this.talk.on);
      btn.classList.toggle("on", on);
      btn.textContent = this.tr(on ? "Stop talking" : "Talk");
    });
    bar.appendChild(btn);
  }

  async mosaic(cams, _seconds) {
    this._clear();
    const el = document.createElement("div");
    el.className = "mosaic";
    el.dataset.screen = "mosaic";
    el.addEventListener("click", () => this.player.controller.hide());
    this.layer.appendChild(el);
    this.current = el;
    let names = cams;
    if (!names) {
      try {
        names = await this.player.overview();
      } catch (e) {
        names = [];
      }
    }
    if (this.current !== el) return;
    const W = globalThis.innerWidth || 1920;
    const H = globalThis.innerHeight || 1080;
    const cells = grid(names.length, W, H);
    names.forEach((cam, i) => {
      const c = cells[i];
      const tile = document.createElement("div");
      tile.className = "tile";
      tile.dataset.camera = cam;
      Object.assign(tile.style, { position: "absolute", left: `${c.x}px`, top: `${c.y}px`, width: `${c.w}px`,
                                   height: `${c.h}px` });
      const n = document.createElement("div");
      n.className = "name";
      n.textContent = this.player.title(cam);
      tile.appendChild(n);
      el.appendChild(tile);
      const t = new Tile(this, cam, tile, false);
      this.tiles.push(t);
      t.start();
    });
  }

  async notification({ cam, priority, label, seconds }) {
    if (this.note) this.note.remove();
    if (this.noteTimer) clearTimeout(this.noteTimer);
    const s = this.player.settings();
    const el = document.createElement("div");
    el.className = "note";
    el.dataset.screen = "notification";
    const colour = DATA.priorityColours[priority];
    if (colour && s.priority_border !== "off") el.style.borderColor = colour;
    const title = this.player.title(cam);
    el.textContent = markedTitle(label ? `${title} · ${label}` : title, priority, s.priority_border, this.tr);
    el.addEventListener("click", () => this._closeNote());
    this.layer.appendChild(el);
    this.note = el;
    this.noteTimer = setTimeout(() => this._closeNote(), (seconds || 10) * 1000);
    try {
      const at = source(this.player, cam);
      const r = await this.player.authFetch(urls(at.base, cam, "", at.stream).cached);
      if (r.ok && this.note === el) {
        const img = document.createElement("img");
        img.alt = "";
        img.src = URL.createObjectURL(await r.blob());
        el.appendChild(img);
      }
    } catch (e) {
      /* the text alone */
    }
  }

  _closeNote() {
    if (this.note) this.note.remove();
    this.note = null;
  }

  hide() {
    this._clear();
  }

  chime() {
    if (!this.deps.chimeUrl) return;
    try {
      const a = new Audio(this.deps.chimeUrl);
      const p = a.play();
      if (p && p.catch) p.catch(() => {});
    } catch (e) {
      /* sound blocked until the page was tapped once */
    }
  }

  toast(code) {
    const text = code === "settings_received" ? this.tr("Settings received from Home Assistant") : code;
    const el = document.createElement("div");
    el.className = "notice";
    el.textContent = text;
    this.layer.appendChild(el);
    setTimeout(() => el.remove(), NOTICE_MS);
  }

  status() {
    return this.current ? this.current.dataset.screen : this.note ? "notification" : "none";
  }
}
