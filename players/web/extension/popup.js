// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
import { language, translator } from "./core/ui.js";
import { ext } from "./ext.js";

const STATES = { connecting: "Connecting to Home Assistant...", connected: "Connected to Home Assistant",
                 auth_failed: "Sign in to Home Assistant", closed: "Not connected", not_set: "Not connected" };
const MQTT_STATES = { connecting: "Connecting to the MQTT broker...", connected: "Connected to the MQTT broker" };
const ask = (msg) => ext.runtime.sendMessage(Object.assign({ target: "background" }, msg));
const r = await ask({ type: "get_settings" });
const t = translator(language(r.settings && r.settings.language));
const st = await ask({ type: "state" });
document.getElementById("state").textContent = `${st.name}: ${t((r.ha && r.ha.mode === "mqtt" && MQTT_STATES[st.state]) || STATES[st.state] || STATES.closed)} (${st.version})`;
const a = document.getElementById("options");
a.textContent = t("Settings");
a.addEventListener("click", (e) => { e.preventDefault(); ext.runtime.openOptionsPage(); });
