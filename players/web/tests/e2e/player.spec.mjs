// The web player page (#92) in Chromium against the fake Home Assistant.
import { expect, test } from "@playwright/test";
import { FakeHA, TOKEN } from "../fake/server.mjs";

let fake;
test.beforeAll(async () => { fake = await new FakeHA().start(); });
test.afterAll(async () => { await fake.stop(); });

async function open(page, settings = {}) {
  await page.addInitScript(([token, s]) => {
    if (!localStorage.getItem("camalert.player")) {
      localStorage.setItem("camalert.hassTokens", JSON.stringify({ access_token: token, refresh_token: "r",
                                                                   expires: Date.now() + 3600000 }));
      localStorage.setItem("camalert.player", JSON.stringify({ id: "webtest0000001", name: "Wall tablet", settings: s }));
    }
  }, [TOKEN, Object.assign({ server: "http://192.168.1.10:1984", camera: "front_door" }, settings)]);
  fake.subs.clear();
  await page.goto(`${fake.url}/camalert_static/page/player.html`);
  return fake.connected();
}

test("connects, shows a photo window, a live window, a mosaic and hides", async ({ page }) => {
  const bid = await open(page);
  expect(bid).toBe("webtest0000001");
  expect(fake.hellos.at(-1)).toMatchObject({ name: "Wall tablet", server: "http://192.168.1.10:1984" });
  await expect(page.locator("#state")).toContainText("Wall tablet");

  let r = await fake.request("show", { cam: "garden", sec: 30, priority: "high", label: "Ring" });
  expect(r.body).toEqual({ result: true, action: "show", cam: "garden" });
  const win = page.locator("camalert-layer .win");
  await expect(win).toHaveAttribute("data-screen", "photo");
  await expect(win.locator(".bar")).toHaveText("Doorbell · Garden · Ring");
  await expect(win.locator("img")).toHaveAttribute("src", /^blob:/);
  expect(fake.go2rtcRequests.find((x) => x.includes("frame.jpeg"))).toContain("cache=10s");
  expect(await win.evaluate((el) => getComputedStyle(el).borderTopColor)).toBe("rgb(230, 159, 0)");
  expect((await fake.request("status")).body).toMatchObject({ screen: "photo", window: "garden", platform: "browser" });

  r = await fake.request("show", { cam: "front_door", mode: "live" });
  await expect(win).toHaveAttribute("data-screen", "live");
  await expect(win.locator("img")).toHaveAttribute("src", /stream\.mjpeg\?src=front_door.*authSig=fake/, { timeout: 15000 });

  await fake.request("mosaic", {});
  const tiles = page.locator("camalert-layer .mosaic .tile");
  await expect(tiles).toHaveCount(2);
  expect(await tiles.evaluateAll((els) => els.map((e) => e.dataset.camera))).toEqual(["front_door", "garden"]);

  await fake.request("hide");
  await expect(page.locator("camalert-layer .win, camalert-layer .mosaic")).toHaveCount(0);
  expect((await fake.request("status")).body.screen).toBe("none");
});

test("warm feed, notification, settings and setup from Home Assistant", async ({ page }) => {
  await open(page, { ready_cameras: "front_door=front_door_jpeg", server: "" });
  expect((await fake.request("status")).body.configured).toBe(false);
  let r = await fake.request("setup", { server: "http://192.168.1.10:1984", camera: "front_door" });
  expect(r.body).toEqual({ result: true });
  await expect(page.locator("camalert-layer .notice")).toHaveText("Settings received from Home Assistant");
  for (let i = 0; i < 50 && fake.hellos.at(-1).server !== "http://192.168.1.10:1984"; i++) await page.waitForTimeout(100);
  expect(fake.hellos.at(-1).server).toBe("http://192.168.1.10:1984");
  await fake.connected();

  await fake.request("show", {});
  await expect(page.locator("camalert-layer .win img")).toHaveAttribute("src", /stream\.mjpeg\?src=front_door_jpeg/);
  r = await fake.request("settings", { position: "bottom_left", size: "small" });
  expect(r.body).toEqual({ result: true, position: "bottom_left", size: "small" });
  await fake.request("show", { cam: "garden", mode: "notify" });
  await expect(page.locator("camalert-layer .note")).toContainText("Garden");
  expect((await fake.request("setup", { server: "http://198.51.100.7:1984" })).code).toBe(409);
});

test("settings panel and language", async ({ page }) => {
  await open(page);
  await page.click("#gear");
  await page.selectOption("#f-language", "nl");
  await page.selectOption("#f-position", "top_left");
  await page.check("#f-dashboard");
  await page.click("#save");
  await expect(page.locator("#panel")).not.toHaveClass(/open/);
  const saved = await page.evaluate(() => JSON.parse(localStorage.getItem("camalert.player")));
  expect(saved.settings).toMatchObject({ language: "nl", position: "top_left" });
  expect(await page.evaluate(() => localStorage.getItem("camalert.dashboard"))).toBe("1");
  await expect(page.locator("#state")).toContainText("Verbonden met Home Assistant");
  await fake.request("show", { cam: "garden" });
  await expect(page.locator("camalert-layer .win .msg, camalert-layer .win img").first()).toBeVisible();
});

test("dashboard module: only where it was turned on, through the dashboard's connection", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("camalert.player", JSON.stringify({ id: "webdash0000001", name: "Kitchen tablet",
                                                             settings: { server: "http://192.168.1.10:1984" } }));
  });
  await page.goto(`${fake.url}/test/dashboard.html`);
  await page.waitForFunction(() => window.deliver);
  expect(await page.evaluate(() => window.hello)).toMatchObject({ type: "camalert/browser/connect",
                                                                 browser_id: "webdash0000001", name: "Kitchen tablet" });
  await page.evaluate(() => window.deliver({ type: "request", id: 7, action: "show", params: { cam: "garden" } }));
  await expect(page.locator("camalert-layer .win")).toHaveAttribute("data-screen", "photo");
  const sent = await page.evaluate(() => window.sent.filter((m) => m.type === "camalert/browser/reply"));
  expect(sent[0]).toMatchObject({ request_id: 7, code: 200, body: { result: true, action: "show" } });
});
