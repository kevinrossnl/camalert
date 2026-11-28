// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
//
// Options of the extension (#127, #131): the connection (Home Assistant address + token, or an MQTT broker over
// WebSocket with user + password; ext.storage.local only) and the player settings (kept by the background).
import { DATA } from "./core/generated.js";
import { ext } from "./ext.js";
import { language, translator } from "./core/ui.js";

const $ = (id) => document.getElementById(id);
const ask = (msg) => ext.runtime.sendMessage(Object.assign({ target: "background" }, msg));
const LABELS = {
  position: { top_right: "Top right", top_left: "Top left", bottom_right: "Bottom right", bottom_left: "Bottom left" },
  size: { small: "Small", medium: "Medium", large: "Large" },
  text_size: { normal: "Normal", large: "Large", xlarge: "Extra large" },
  chime: { off: "Off", high: "Doorbell and alarm", all: "Every request" },
};
const STATES = { connecting: "Connecting to Home Assistant...", connected: "Connected to Home Assistant",
                 auth_failed: "Sign in to Home Assistant", closed: "Not connected", not_set: "Not connected" };
const MQTT_STATES = { connecting: "Connecting to the MQTT broker...", connected: "Connected to the MQTT broker",
                      auth_failed: "Not connected", closed: "Not connected", not_set: "Not connected" };
const FIELDS = ["server", "more_servers", "camera", "duration", "position", "size", "text_size", "chime", "language"];

let saved = {}; // the stored connection, read when the page loads

function showMode() {
  $("ha-box").hidden = $("mode").value !== "ha";
  $("mqtt-box").hidden = $("mode").value !== "mqtt";
}

function fill(t, s) {
  for (const key of Object.keys(LABELS)) {
    $(key).textContent = "";
    for (const v of DATA.settings[key].choices) $(key).append(new Option(t(LABELS[key][v]), v));
  }
  $("language").textContent = "";
  for (const v of DATA.settings.language.choices) {
    $("language").append(new Option(v === "system" ? t("System language") : DATA.languageNames[v], v));
  }
  for (const key of FIELDS) $(key).value = s[key] ?? "";
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
  saved = (await ext.storage.local.get("ha")).ha || {};
  $("mode").value = r.ha.mode || "ha";
  $("mqtt_url").value = (r.ha.mqtt && r.ha.mqtt.url) || "";
  $("mqtt_user").value = (r.ha.mqtt && r.ha.mqtt.user) || "";
  showMode();
  const st = await ask({ type: "state" });
  $("state").textContent = t(((r.ha.mode === "mqtt" ? MQTT_STATES : STATES)[st.state]) || STATES.closed);
}

/** The origin of an address ("ws://host:1884/mqtt" -> "http://host:1884" for the permission), or null. */
function origin(text, ws = false) {
  try {
    const u = new URL(text);
    if (ws ? !["ws:", "wss:"].includes(u.protocol) : !["http:", "https:"].includes(u.protocol)) return null;
    return u.origin.replace(/^ws/, "http");
  } catch (e) {
    return null;
  }
}

$("mode").addEventListener("change", showMode);
$("f").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  // permissions.request first, before any await: Firefox only allows it directly in the click (#131)
  const mode = $("mode").value === "mqtt" ? "mqtt" : "ha";
  const url = $("url").value.trim().replace(/\/$/, "");
  const token = $("token").value.trim();
  const mqttUrl = $("mqtt_url").value.trim();
  const origins = [];
  if (mode === "ha") {
    if (!origin(url)) return $("url").focus();
    if (!token && !saved.token) return $("token").focus();
    origins.push(`${origin(url)}/*`);
  } else {
    if (!origin(mqttUrl, true)) return $("mqtt_url").focus();
    origins.push(`${origin(mqttUrl, true)}/*`);
    // pictures come straight from go2rtc then: the extension needs access to every go2rtc server
    for (const text of [$("server").value].concat($("more_servers").value.split(/[,\n;]+/))) {
      const addr = text.includes("=") && !text.split("=")[0].includes("://") ? text.split("=").slice(1).join("=") : text;
      const o = origin(/^[a-z]+:\/\//i.test(addr.trim()) ? addr.trim() : `http://${addr.trim()}`);
      if (addr.trim() && o) origins.push(`${o}/*`);
    }
  }
  if (!(await ext.permissions.request({ origins }))) return;
  const old = (await ext.storage.local.get("ha")).ha || {};
  const settings = Object.fromEntries(FIELDS.map((k) => [k, $(k).value]));
  settings.dnd = $("dnd").checked;
  await ask({ type: "set_settings", name: $("name").value.trim(), settings });
  const mqtt = { url: mqttUrl, user: $("mqtt_user").value.trim(),
                 password: $("mqtt_password").value || (old.mqtt && old.mqtt.password) || "" };
  await ext.storage.local.set({ ha: { mode, url: url || old.url || "", token: token || old.token || "", mqtt } });
  $("token").value = "";
  $("mqtt_password").value = "";
  setTimeout(load, 1500);
});
load();
