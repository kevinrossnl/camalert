// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
//
// The web player page (#92): signs in with Home Assistant, connects as a browser player, draws the CamAlert
// windows and has a small settings panel. Served by the integration at /camalert_static/page/player.html.
import { DATA } from "../core/generated.js";
import { encode, draw } from "../core/qr.js";
import * as report from "../core/report.js";
import { Player } from "../core/player.js";
import { Store, localStorageBackend } from "../core/store.js";
import { HaSocket } from "../core/transport.js";
import { DomView, clockText, language, translator } from "../core/ui.js";
import { HaAuth } from "./auth.js";

export const DASHBOARD_KEY = "camalert.dashboard";
const $ = (id) => document.getElementById(id);
const CHOICE_LABELS = {
  position: { top_right: "Top right", top_left: "Top left", bottom_right: "Bottom right", bottom_left: "Bottom left" },
  size: { small: "Small", medium: "Medium", large: "Large" },
  text_size: { normal: "Normal", large: "Large", xlarge: "Extra large" },
  chime: { off: "Off", high: "Doorbell and alarm", all: "Every request" },
};
const STATES = {
  connecting: "Connecting to Home Assistant...",
  connected: "Connected to Home Assistant",
  auth_failed: "Sign in to Home Assistant",
  closed: "Not connected",
};

const origin = location.origin;
const auth = new HaAuth(origin);
const store = new Store(localStorageBackend());
let state = "closed";
let soundOn = false;

const link = new HaSocket({
  url: origin.replace(/^http/, "ws") + "/api/websocket",
  token: () => auth.accessToken(),
  WebSocket,
  log: (m, l) => player.log(m, l),
  onState: (s) => {
    state = s;
    render();
    if (s === "auth_failed") auth.login();
  },
});
const player = new Player({ store, link, haUrl: origin, token: () => auth.accessToken() });
const view = new DomView(document.body.appendChild(document.createElement("camalert-layer")), player, {
  link, haUrl: origin, chimeUrl: new URL("../chime.wav", import.meta.url).href, soundAllowed: () => soundOn,
});
player.setView(view);

function tr() {
  return translator(language(store.settings().language));
}

function fillSelect(el, key, labels, t) {
  el.textContent = "";
  for (const v of DATA.settings[key].choices) {
    const o = document.createElement("option");
    o.value = v;
    o.textContent = key === "language" ? (v === "system" ? t("System language") : DATA.languageNames[v]) : t(labels[v]);
    el.appendChild(o);
  }
}

function render() {
  const t = tr();
  document.documentElement.lang = language(store.settings().language);
  for (const el of document.querySelectorAll("[data-t]")) el.textContent = t(el.dataset.t);
  const text = t(STATES[state] || STATES.closed);
  const hint = state === "connected" && !player.configured() ? ` — ${t("go2rtc address not set")}` : "";
  $("state").textContent = `${store.name || player.node()[1]}: ${text}${hint}`;
  $("panel-state").textContent = text + hint;
  $("sound").hidden = soundOn;
  $("sound").textContent = t("Tap to enable sound");
}

function openPanel() {
  const t = tr();
  const s = store.settings();
  for (const key of ["position", "size", "text_size", "chime"]) fillSelect($(`f-${key}`), key, CHOICE_LABELS[key], t);
  fillSelect($("f-language"), "language", null, t);
  $("f-name").value = store.name;
  for (const key of ["server", "more_servers", "camera", "duration", "position", "size", "text_size", "chime", "language"]) {
    $(`f-${key}`).value = s[key] ?? "";
  }
  $("f-dnd").checked = !!s.dnd;
  $("f-dashboard").checked = localStorage.getItem(DASHBOARD_KEY) === "1";
  $("panel").classList.add("open");
  player.cameras().then((cams) => {
    $("cams").textContent = "";
    for (const c of cams) {
      const o = document.createElement("option");
      o.value = c.name;
      o.label = c.title;
      $("cams").appendChild(o);
    }
  }, () => {});
}

$("gear").addEventListener("click", openPanel);
$("close").addEventListener("click", () => $("panel").classList.remove("open"));
$("panel").addEventListener("submit", (ev) => {
  ev.preventDefault();
  if ($("f-name").value.trim() !== store.name) store.setName($("f-name").value);
  store.set({
    server: $("f-server").value, more_servers: $("f-more_servers").value, camera: $("f-camera").value, duration: $("f-duration").value,
    position: $("f-position").value, size: $("f-size").value, text_size: $("f-text_size").value,
    chime: $("f-chime").value, language: $("f-language").value, dnd: $("f-dnd").checked,
  });
  localStorage.setItem(DASHBOARD_KEY, $("f-dashboard").checked ? "1" : "0");
  $("panel").classList.remove("open");
  render();
});
$("sound").addEventListener("click", () => {
  soundOn = true; // a tap is what browsers need before a page may play sound
  new Audio(new URL("../chime.wav", import.meta.url).href).play().then((a) => a, () => {});
  render();
});
store.onChange(render);

setInterval(() => {
  $("clock").textContent = clockText(new Date(), language(store.settings().language));
}, 1000);
render();
if (new URLSearchParams(location.search).has("settings")) openPanel();
player.start();
// for the end-to-end tests and the browser console
globalThis.camalert = { player, store, link, view };

// #132: Report a problem. A summary, a QR code that opens a pre-filled GitHub issue on a phone, and the full
// report (without secrets) to download and paste into the issue.
let lastReport = null;

function browserName() {
  const m = /(Edg|Chrome|Firefox|Version)\/(\d+)/.exec(navigator.userAgent || "");
  if (!m) return "browser";
  return `${{ Edg: "Edge", Version: "Safari" }[m[1]] || m[1]} ${m[2]}`;
}

async function openReport() {
  const t = tr();
  const status = (await player.request("status")).body || {};
  lastReport = report.build(status, store.settings(), player.logTail(DATA.report.log_lines),
                            { browser: browserName() });
  draw($("report-qr"), encode(report.issueUrl(lastReport), "M"), 6);
  $("report-text").textContent = [t(DATA.report.texts.help), "", ...report.summary(lastReport)].join("\n");
  $("panel").classList.remove("open");
  $("report").classList.add("open");
}

$("report-open").addEventListener("click", () => { openReport().catch((e) => player.log(`report failed: ${e}`, "error")); });
$("report-close").addEventListener("click", () => $("report").classList.remove("open"));
$("report-save").addEventListener("click", () => {
  if (!lastReport) return;
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([report.text(lastReport)], { type: "text/plain" }));
  a.download = DATA.report.file_name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
});
