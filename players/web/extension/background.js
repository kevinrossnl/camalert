// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
//
// The browser extension's player (#127): the shared core in the Manifest V3 service worker. It keeps the Home
// Assistant WebSocket open (an active WebSocket keeps the worker alive, Chrome 116+), answers the CamAlert API and
// shows windows as small popup windows (alert.html). The chime plays from an offscreen document.
import { DATA } from "./core/generated.js";
import { Player } from "./core/player.js";
import { Store } from "./core/store.js";
import { HaSocket } from "./core/transport.js";
import { windowGeometry } from "./core/ui.js";

const KEY = "player"; // settings of the player (no token)
const HA_KEY = "ha"; // {url, token}: chrome.storage.local only, never synced

let cache = {};
let ha = {};
let player = null;
let link = null;
let popup = null; // {id, spec}
let state = "closed";

async function ensureOffscreen() {
  if (await chrome.offscreen.hasDocument()) return;
  await chrome.offscreen.createDocument({ url: "offscreen.html", reasons: ["AUDIO_PLAYBACK"],
                                          justification: "doorbell chime of a CamAlert alert" });
}

async function closePopup() {
  if (!popup) return;
  const id = popup.id;
  popup = null;
  try {
    await chrome.windows.remove(id);
  } catch (e) {
    /* closed by the user */
  }
}

async function openPopup(spec) {
  const s = player.settings();
  let screen = { left: 0, top: 0, width: 1920, height: 1080 };
  try {
    const w = await chrome.windows.getLastFocused();
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
    w = await chrome.windows.create(Object.assign({}, base, box));
  } catch (e) { // bounds outside the visible screen (another monitor layout): let the browser place it
    w = await chrome.windows.create(Object.assign({}, base, { width: box.width, height: box.height }));
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
    await ensureOffscreen();
    chrome.runtime.sendMessage({ target: "offscreen", type: "chime" }).catch(() => {});
  },
  toast: () => {},
};

async function start() {
  const got = await chrome.storage.local.get([KEY, HA_KEY]);
  cache = got[KEY] || null;
  ha = got[HA_KEY] || {};
  if (link) link.stop();
  if (!ha.url || !ha.token) {
    state = "not_set";
    return;
  }
  const store = new Store({ load: () => cache, save: (obj) => { cache = obj; chrome.storage.local.set({ [KEY]: obj }); } });
  const haUrl = ha.url.replace(/\/$/, "");
  link = new HaSocket({
    url: haUrl.replace(/^http/, "ws") + "/api/websocket", token: async () => ha.token, WebSocket,
    log: (m, l) => player && player.log(m, l), onState: (s) => { state = s; },
  });
  player = new Player({ store, link, haUrl, token: async () => ha.token });
  player.setView(view);
  player.start();
}

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  if (!msg || msg.target !== "background") return false;
  if (msg.type === "screen") {
    reply(popup && sender.tab && sender.tab.windowId === popup.id ? {
      spec: popup.spec, settings: player.settings(), titles: Object.fromEntries((popup.spec.cams || [popup.spec.cam])
        .filter(Boolean).map((c) => [c, player.title(c)])), base: player.base(), haUrl: ha.url, token: ha.token,
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
    reply(player ? { settings: player.settings(), name: player.store.name, ha: { url: ha.url || "" } }
      : { settings: null, name: "", ha: { url: ha.url || "" } });
    return false;
  }
  if (msg.type === "set_settings") {
    if (player) {
      if (typeof msg.name === "string" && msg.name !== player.store.name) player.store.setName(msg.name);
      player.set(msg.settings || {});
    } else {
      cache = Object.assign({}, cache || {}, { name: msg.name || "", settings: msg.settings || {} });
      chrome.storage.local.set({ [KEY]: cache });
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

chrome.windows.onRemoved.addListener((id) => {
  if (popup && popup.id === id) {
    popup = null;
    if (player && player.controller.screen !== "none") player.controller.hide();
  }
});
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes[HA_KEY]) start();
});
chrome.alarms.create("camalert-keepalive", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener(() => {
  if (!link || link.stopped) start();
});
start();
globalThis.camalert = { get player() { return player; }, get state() { return state; }, start };
