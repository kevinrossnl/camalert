// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
import { language, translator } from "./core/ui.js";

const STATES = { connecting: "Connecting to Home Assistant...", connected: "Connected to Home Assistant",
                 auth_failed: "Sign in to Home Assistant", closed: "Not connected", not_set: "Not connected" };
const ask = (msg) => chrome.runtime.sendMessage(Object.assign({ target: "background" }, msg));
const r = await ask({ type: "get_settings" });
const t = translator(language(r.settings && r.settings.language));
const st = await ask({ type: "state" });
document.getElementById("state").textContent = `${st.name}: ${t(STATES[st.state] || STATES.closed)} (${st.version})`;
const a = document.getElementById("options");
a.textContent = t("Settings");
a.addEventListener("click", (e) => { e.preventDefault(); chrome.runtime.openOptionsPage(); });
