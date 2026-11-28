// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
//
// Raw screenshots for the Chrome Web Store listing (#131): the real extension in Chromium against the fake Home
// Assistant, with the drawn demo cameras of tools/readme_images.py (never a real camera picture). Run from
// players/web after `npm ci && npx playwright install chromium`:
//     node tests/webstore/capture.mjs <dir with front_door.jpg, garden.jpg, driveway.jpg, backyard.jpg> <out dir>
// It writes raw-doorbell.png (the alert window at its own size), raw-mosaic.png, raw-options.png, raw-options-mqtt.png.
// tools/webstore_images.py makes the demo cameras, runs this and composes the 1280x800 store images.
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";
import { FakeHA, TOKEN } from "../fake/server.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const [cams, out] = process.argv.slice(2);
const img = Object.fromEntries(["front_door", "garden", "driveway", "backyard"].map((c) => [c, readFileSync(path.join(cams, `${c}.jpg`))]));
const STREAMS = { front_door: {}, garden: {}, driveway: {}, backyard: {} };

const fake = await new FakeHA().start();
const dir = mkdtempSync(path.join(os.tmpdir(), "camalert-store-"));
execFileSync("python3", [path.join(ROOT, "tools", "build_web.py"), "unpacked", dir]);
const m = JSON.parse(readFileSync(path.join(dir, "manifest.json"), "utf8"));
m.host_permissions = ["http://127.0.0.1/*"]; // only for the capture: no permission prompt
writeFileSync(path.join(dir, "manifest.json"), JSON.stringify(m));
const ctx = await chromium.launchPersistentContext("", {
  channel: "chromium", headless: true, viewport: { width: 1280, height: 800 },
  args: [`--disable-extensions-except=${dir}`, `--load-extension=${dir}`],
});
await ctx.route(/\/api\/camalert\/go2rtc\/.*\/api\/(streams|frame\.jpeg|stream\.mjpeg)/, async (route) => {
  const u = new URL(route.request().url());
  if (u.pathname.endsWith("/streams")) return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(STREAMS) });
  const body = img[u.searchParams.get("src")] || img.front_door;
  return route.fulfill({ status: 200, contentType: "image/jpeg", body });
});
const sw = ctx.serviceWorkers()[0] || (await ctx.waitForEvent("serviceworker"));
await sw.evaluate(([url, token]) => chrome.storage.local.set({
  player: { id: "webstore000001", name: "Office PC", settings: { server: "http://192.168.1.10:1984", camera: "front_door",
            size: "large", titles: "front_door=Front door|garden=Garden|driveway=Driveway|backyard=Backyard" } },
  ha: { url, token },
}), [fake.url, TOKEN]);
await fake.connected();

async function shot(request, name, size = null) {
  const popup = ctx.waitForEvent("page");
  await fake.request(...request);
  const page = await popup;
  if (size) await page.setViewportSize(size); // the size of the real alert window
  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(out, name) });
  const closed = page.waitForEvent("close");
  await fake.request("hide");
  await closed;
}

await shot(["show", { cam: "front_door", sec: 60, priority: "high", label: "Ring" }], "raw-doorbell.png", { width: 640, height: 400 });
await shot(["mosaic", { cam: "front_door,garden,driveway,backyard", sec: 60 }], "raw-mosaic.png");
const id = sw.url().split("/")[2];
const opts = await ctx.newPage();
await opts.goto(`chrome-extension://${id}/options.html`);
await opts.waitForTimeout(1500);
await opts.fill("#url", "http://192.168.1.20:8123"); // shown only, not saved
await opts.screenshot({ path: path.join(out, "raw-options.png") });
await opts.selectOption("#mode", "mqtt");
await opts.fill("#mqtt_url", "ws://192.168.1.20:1884/mqtt");
await opts.fill("#mqtt_user", "camalert");
await opts.screenshot({ path: path.join(out, "raw-options-mqtt.png") });
await ctx.close();
await fake.stop();
console.log("ok");
