// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
//
// CamAlert on Home Assistant dashboards (#92): loaded by the integration on every Home Assistant page
// (frontend.add_extra_js_url), but it only does something in a browser where "Also show alerts on Home Assistant
// dashboards in this browser" was turned on in the web player page (localStorage, per browser, never for every
// user). It then uses the dashboard's own connection and login: no token, no extra page.
import { Player } from "../core/player.js";
import { Store, localStorageBackend } from "../core/store.js";
import { FrontendLink } from "../core/transport.js";
import { DomView } from "../core/ui.js";

const DASHBOARD_KEY = "camalert.dashboard";

function hass() {
  const el = document.querySelector("home-assistant");
  return el && el.hass;
}

async function waitForHass(tries = 120) {
  for (let i = 0; i < tries; i++) {
    const h = hass();
    if (h && h.connection && h.auth) return h;
    await new Promise((r) => setTimeout(r, 500));
  }
  return null;
}

async function main() {
  if (localStorage.getItem(DASHBOARD_KEY) !== "1" || globalThis.__camalertDashboard) return;
  globalThis.__camalertDashboard = true;
  if (!(await waitForHass())) return;
  const store = new Store(localStorageBackend());
  const link = new FrontendLink(hass, { log: (m, l) => player.log(m, l) });
  const token = async () => {
    const h = hass();
    return h && h.auth ? (h.auth.accessToken || (h.auth.data && h.auth.data.access_token)) : null;
  };
  const player = new Player({ store, link, haUrl: location.origin, token });
  let soundOn = false;
  document.addEventListener("pointerdown", () => { soundOn = true; }, { once: true });
  const view = new DomView(document.body.appendChild(document.createElement("camalert-layer")), player, {
    link, haUrl: location.origin, chimeUrl: new URL("../chime.wav", import.meta.url).href, soundAllowed: () => soundOn,
  });
  player.setView(view);
  player.start();
  globalThis.camalert = { player, store, link, view };
}

main();
