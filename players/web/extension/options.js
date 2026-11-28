// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
//
// Options of the extension (#127): Home Assistant address + token (chrome.storage.local) and the player settings
// (kept by the service worker).
import { DATA } from "./core/generated.js";
import { language, translator } from "./core/ui.js";

const $ = (id) => document.getElementById(id);
const ask = (msg) => chrome.runtime.sendMessage(Object.assign({ target: "background" }, msg));
const LABELS = {
  position: { top_right: "Top right", top_left: "Top left", bottom_right: "Bottom right", bottom_left: "Bottom left" },
  size: { small: "Small", medium: "Medium", large: "Large" },
  text_size: { normal: "Normal", large: "Large", xlarge: "Extra large" },
  chime: { off: "Off", high: "Doorbell and alarm", all: "Every request" },
};
const STATES = { connecting: "Connecting to Home Assistant...", connected: "Connected to Home Assistant",
                 auth_failed: "Sign in to Home Assistant", closed: "Not connected", not_set: "Not connected" };

function fill(t, s) {
  for (const key of Object.keys(LABELS)) {
    $(key).textContent = "";
    for (const v of DATA.settings[key].choices) $(key).append(new Option(t(LABELS[key][v]), v));
  }
  $("language").textContent = "";
  for (const v of DATA.settings.language.choices) {
    $("language").append(new Option(v === "system" ? t("System language") : DATA.languageNames[v], v));
  }
  for (const key of ["server", "camera", "duration", "position", "size", "text_size", "chime", "language"]) $(key).value = s[key];
  $("dnd").checked = !!s.dnd;
}

async function load() {
  const r = await ask({ type: "get_settings" });
  const s = r.settings || Object.fromEntries(Object.entries(DATA.settings).map(([k, v]) => [k, v.default]));
  const t = translator(language(s.language));
  for (const el of document.querySelectorAll("[data-t]")) el.textContent = t(el.dataset.t);
  fill(t, s);
  $("name").value = r.name || "";
  $("url").value = r.ha.url || "";
  const st = await ask({ type: "state" });
  $("state").textContent = t(STATES[st.state] || STATES.closed);
}

$("f").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const url = $("url").value.trim().replace(/\/$/, "");
  let origin;
  try {
    origin = new URL(url).origin;
  } catch (e) {
    $("url").focus();
    return;
  }
  const token = $("token").value.trim();
  const old = (await chrome.storage.local.get("ha")).ha || {};
  if (!token && !old.token) {
    $("token").focus();
    return;
  }
  if (!(await chrome.permissions.request({ origins: [`${origin}/*`] }))) return;
  await ask({ type: "set_settings", name: $("name").value.trim(), settings: {
    server: $("server").value, camera: $("camera").value, duration: $("duration").value, position: $("position").value,
    size: $("size").value, text_size: $("text_size").value, chime: $("chime").value, language: $("language").value,
    dnd: $("dnd").checked } });
  await chrome.storage.local.set({ ha: { url, token: token || old.token || "" } });
  $("token").value = "";
  setTimeout(load, 1500);
});
load();
