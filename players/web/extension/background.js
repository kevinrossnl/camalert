// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
//
// The browser extension's player (#127): the shared core in the Manifest V3 service worker (Chrome, Edge) or the
// background page (Firefox, #131). It keeps the Home Assistant WebSocket open (an active WebSocket keeps the worker
// alive, Chrome 116+), or with MQTT over WebSocket the broker connection (#131), answers the CamAlert API and shows
// windows as small popup windows (alert.html). The chime plays from an offscreen document (Chrome) or from the
// background page itself (Firefox has no offscreen documents but its background page may play sound).
import { DATA } from "./core/generated.js";
import { ext } from "./ext.js";
import { Player } from "./core/player.js";
import { Store } from "./core/store.js";
import { MqttLink } from "./core/mqtt.js";
import { HaSocket } from "./core/transport.js";
import { windowGeometry } from "./core/ui.js";

const KEY = "player"; // settings of the player (no token)
const HA_KEY = "ha"; // {mode: "ha" | "mqtt", url, token, mqtt: {url, user, password}}: local only, never synced

let cache = {};
let ha = {};
let player = null;
let link = null;
let popup = null; // {id, spec}
let state = "closed";

async function ensureOffscreen() {
  if (await ext.offscreen.hasDocument()) return;
  await ext.offscreen.createDocument({ url: "offscreen.html", reasons: ["AUDIO_PLAYBACK"],
                                          justification: "doorbell chime of a CamAlert alert" });
}

async function closePopup() {
  if (!popup) return;
  const id = popup.id;
  popup = null;
  try {
    await ext.windows.remove(id);
  } catch (e) {
    /* closed by the user */
  }
}

async function openPopup(spec) {
  const s = player.settings();
  let screen = { left: 0, top: 0, width: 1920, height: 1080 };
  try {
    const w = await ext.windows.getLastFocused();
    screen = { left: w.left, top: w.top, width: w.width, height: w.height };
  } catch (e) {
    /* no window yet */
  }
  let box;
  if (spec.kind === "mosaic") {
    box = { left: screen.left, top: screen.top, width: screen.width, height: screen.height };
  } else {
    const size = spec.kind === "notification" ? "small" : s.size;
    const g = windowGeometry(s.position, size, screen.width, screen.height, s.text_size);
    box = { left: screen.left + g.x, top: screen.top + g.y, width: g.w + 16, height: g.h + g.title + 48 };
  }
  await closePopup();
  const base = { url: "alert.html", type: "popup", focused: spec.priority === "alarm" };
  let w;
  try {
    w = await ext.windows.create(Object.assign({}, base, box));
  } catch (e) { // bounds outside the visible screen (another monitor layout): let the browser place it
    w = await ext.windows.create({ url: base.url, type: base.type, width: box.width, height: box.height });
  }
  popup = { id: w.id, spec };
}

function shown(p) {
  return p.catch((e) => player && player.log(`alert window: ${e.message}`, "error"));
}

const view = {
  window: (x) => shown(openPopup(Object.assign({ kind: "window" }, x))),
  mosaic: async (cams, seconds) => {
    let names = cams;
    if (!names) names = await player.overview().catch(() => []);
    await shown(openPopup({ kind: "mosaic", cams: names, seconds, priority: "normal" }));
  },
  notification: (x) => {
    shown(openPopup(Object.assign({ kind: "notification" }, x)));
    setTimeout(() => popup && popup.spec.kind === "notification" && closePopup(), (x.seconds || 10) * 1000);
  },
  hide: () => closePopup(),
  chime: async () => {
    if (!ext.offscreen) { // Firefox (#131): the background page plays it
      new Audio(ext.runtime.getURL("chime.wav")).play().catch(() => {});
      return;
    }
    await ensureOffscreen();
    ext.runtime.sendMessage({ target: "offscreen", type: "chime" }).catch(() => {});
  },
  toast: () => {},
};

/** The way to Home Assistant: its WebSocket (default) or an MQTT broker over WebSocket (#131). */
function mode() {
  return ha.mode === "mqtt" ? "mqtt" : "ha";
}

async function start() {
  const got = await ext.storage.local.get([KEY, HA_KEY]);
  cache = got[KEY] || null;
  ha = got[HA_KEY] || {};
  if (link) link.stop();
  const mq = ha.mqtt || {};
  if (mode() === "mqtt" ? !mq.url : !ha.url || !ha.token) {
    state = "not_set";
    return;
  }
  const store = new Store({ load: () => cache, save: (obj) => { cache = obj; ext.storage.local.set({ [KEY]: obj }); } });
  const haUrl = (ha.url || "").replace(/\/$/, "");
  const log = (m, l) => player && player.log(m, l);
  const onState = (s) => { state = s; };
  if (mode() === "mqtt") {
    link = new MqttLink({
      url: mq.url, user: mq.user || "", password: async () => mq.password || "", WebSocket, log, onState,
      cameras: async () => (await player.cameras()).map((c) => [c.name, c.title]),
      screen: () => { const st = player.controller.status(); return st.window || st.live || "none"; },
      dnd: () => !!player.settings().dnd,
    });
  } else {
    link = new HaSocket({ url: haUrl.replace(/^http/, "ws") + "/api/websocket", token: async () => ha.token, WebSocket,
                          log, onState });
  }
  player = new Player({ store, link, haUrl, token: async () => ha.token, direct: mode() === "mqtt" });
  player.setView(view);
  player.start();
}

function cams(spec) {
  return (spec.cams || [spec.cam]).filter(Boolean);
}

/** {camera: {base, streams: {name: stream}}} for the alert window (#131): every camera's go2rtc server and the
 *  stream names it needs (the camera and its Keep cameras ready stream). */
function sources(names) {
  const ready = player.settings().ready_cameras || "";
  const out = {};
  for (const c of names) {
    const at = player.src(c);
    const streams = { [c]: at.stream(c) };
    for (const part of ready.replace(/,/g, "|").split("|")) {
      const [cam, st] = part.split("=").map((x) => (x || "").trim());
      if (cam === c && st) streams[st] = at.stream(st);
    }
    out[c] = { base: at.base, streams };
  }
  return out;
}

ext.runtime.onMessage.addListener((msg, sender, reply) => {
  if (!msg || msg.target !== "background") return false;
  if (msg.type === "screen") {
    reply(popup && sender.tab && sender.tab.windowId === popup.id ? {
      spec: popup.spec, settings: player.settings(), titles: Object.fromEntries(cams(popup.spec).map((c) => [c, player.title(c)])),
      sources: sources(cams(popup.spec)), base: player.base(), haUrl: ha.url, token: mode() === "mqtt" ? "" : ha.token,
      direct: mode() === "mqtt",
    } : null);
    return false;
  }
  if (msg.type === "sign") {
    link.sign(msg.path).then((p) => reply({ path: p }), (e) => reply({ error: e.message }));
    return true;
  }
  if (msg.type === "hide") {
    player.controller.hide();
    return false;
  }
  if (msg.type === "get_settings") {
    const conn = { mode: mode(), url: ha.url || "", mqtt: { url: (ha.mqtt || {}).url || "", user: (ha.mqtt || {}).user || "" } };
    reply(player ? { settings: player.settings(), name: player.store.name, ha: conn } : { settings: null, name: "", ha: conn });
    return false;
  }
  if (msg.type === "set_settings") {
    if (player) {
      if (typeof msg.name === "string" && msg.name !== player.store.name) player.store.setName(msg.name);
      player.set(msg.settings || {});
      if (link && link.announce) setTimeout(() => link.announce(), 1000); // MQTT discovery of the cameras (#131)
    } else {
      cache = Object.assign({}, cache || {}, { name: msg.name || "", settings: msg.settings || {} });
      ext.storage.local.set({ [KEY]: cache });
    }
    reply({ ok: true });
    return false;
  }
  if (msg.type === "state") {
    reply({ state, name: player ? player.node()[1] : "", version: DATA.version });
    return false;
  }
  return false;
});

ext.windows.onRemoved.addListener((id) => {
  if (popup && popup.id === id) {
    popup = null;
    if (player && player.controller.screen !== "none") player.controller.hide();
  }
});
ext.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes[HA_KEY]) start();
});
ext.alarms.create("camalert-keepalive", { periodInMinutes: 0.5 });
ext.alarms.onAlarm.addListener(() => {
  if (!link || link.stopped) start();
});
start();
globalThis.camalert = { get player() { return player; }, get state() { return state; }, start };
