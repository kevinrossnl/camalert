// The browser extension (#127) loaded in Chromium against the fake Home Assistant.
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium, expect, test } from "@playwright/test";
import { FakeHA, TOKEN } from "../fake/server.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
let fake;
let ctx;
let sw;

test.beforeAll(async () => {
  fake = await new FakeHA().start();
  const dir = mkdtempSync(path.join(os.tmpdir(), "camalert-ext-"));
  execFileSync("python3", [path.join(ROOT, "tools", "build_web.py"), "unpacked", dir]);
  // test only: grant the fake Home Assistant without the options page's permission prompt
  const m = JSON.parse(readFileSync(path.join(dir, "manifest.json"), "utf8"));
  m.host_permissions = ["http://127.0.0.1/*"];
  writeFileSync(path.join(dir, "manifest.json"), JSON.stringify(m));
  ctx = await chromium.launchPersistentContext("", {
    channel: "chromium", headless: true,
    args: [`--disable-extensions-except=${dir}`, `--load-extension=${dir}`],
  });
  sw = ctx.serviceWorkers()[0] || (await ctx.waitForEvent("serviceworker"));
});

test.afterAll(async () => {
  await ctx.close();
  await fake.stop();
});

test("the extension connects, opens an alert window and closes it", async () => {
  await sw.evaluate(([url, token]) => chrome.storage.local.set({
    player: { id: "webext00000001", name: "Desk", settings: { server: "http://192.168.1.10:1984", camera: "front_door" } },
    ha: { url, token },
  }), [fake.url, TOKEN]);
  expect(await fake.connected()).toBe("webext00000001");
  expect(fake.hellos.at(-1)).toMatchObject({ name: "Desk", server: "http://192.168.1.10:1984" });
  const st = await fake.request("status");
  expect(st.body).toMatchObject({ platform: "browser", screen: "none", id: "webext00000001" });

  const popup = ctx.waitForEvent("page");
  const r = await fake.request("show", { cam: "garden", priority: "alarm" });
  expect(r.body).toEqual({ result: true, action: "show", cam: "garden" });
  const page = await popup;
  expect(page.url()).toMatch(/alert\.html$/);
  const win = page.locator("camalert-layer .win");
  await expect(win).toHaveAttribute("data-screen", "photo");
  await expect(win.locator(".bar")).toHaveText("ALARM · Garden");
  await expect(win.locator("img")).toHaveAttribute("src", /^blob:/);

  const closed = page.waitForEvent("close");
  await fake.request("hide");
  await closed;
  expect((await fake.request("status")).body.screen).toBe("none");

  const mosaic = ctx.waitForEvent("page");
  await fake.request("mosaic", {});
  const mp = await mosaic;
  await expect(mp.locator("camalert-layer .mosaic .tile")).toHaveCount(2);
  await fake.request("hide");
});

test("options page saves the player settings", async () => {
  const id = sw.url().split("/")[2];
  const page = await ctx.newPage();
  await page.goto(`chrome-extension://${id}/options.html`);
  await expect(page.locator("#url")).toHaveValue(fake.url);
  await expect(page.locator("#state")).toHaveText("Connected to Home Assistant");
  await page.selectOption("#size", "large");
  await page.fill("#name", "Desk 2");
  await page.click("button[type=submit]");
  await expect.poll(async () => sw.evaluate(async () => (await chrome.storage.local.get("player")).player))
    .toMatchObject({ name: "Desk 2", settings: { size: "large" } });
  await page.close();
});
