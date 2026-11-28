// Unit tests of the browser player's API (#92, #127): the same validation and answers as core/camalert_core/api.py.
import assert from "node:assert/strict";
import { test } from "node:test";
import { boolParam, camerasParam, clampSeconds, handle, hasSeconds, Invalid, localHost, normalizeServer, setupRefused,
         showSeconds } from "../../core/api.js";
import { Controller } from "../../core/controller.js";
import { DATA } from "../../core/generated.js";
import { defaults } from "../../core/store.js";

function fakePlayer(over = {}) {
  let s = Object.assign(defaults(), { camera: "front_door", server: "http://192.168.1.10:1984" }, over);
  const calls = [];
  const view = { window: (x) => calls.push(["window", x]), mosaic: (c, n) => calls.push(["mosaic", c, n]),
                 notification: (x) => calls.push(["notification", x]), hide: () => calls.push(["hide"]),
                 chime: () => calls.push(["chime"]), toast: (c) => calls.push(["toast", c]) };
  const clock = { setTimeout: () => 1, clearTimeout: () => {}, now: () => 1000000 };
  const p = {
    calls, lines: [],
    controller: new Controller(() => s, view, clock),
    settings: () => Object.assign({}, s),
    set: (v) => { s = Object.assign({}, s, v); },
    node: () => ["web0123456789ab", "Hall tablet"],
    configured: () => !!s.server,
    cameras: async () => [{ name: "front_door", title: "Front door", snapshot: true }],
    events: () => p.controller.events,
    logTail: (n) => p.lines.slice(-n),
    log: (m) => p.lines.push(m),
  };
  return p;
}

test("parameters like the core", () => {
  assert.equal(camerasParam(" front_door, garden "), "front_door,garden");
  assert.equal(camerasParam(""), null);
  assert.throws(() => camerasParam("a b/c"), Invalid);
  assert.throws(() => camerasParam("a,b", false), Invalid);
  assert.equal(boolParam("Yes"), true);
  assert.equal(boolParam("0"), false);
  assert.throws(() => boolParam("maybe"), Invalid);
  assert.equal(clampSeconds("2"), DATA.minSeconds);
  assert.equal(clampSeconds("9999"), DATA.maxSeconds);
  assert.equal(clampSeconds("1.5", 30), 30);
  assert.equal(clampSeconds("x", 12), 12);
  assert.equal(showSeconds("0"), DATA.holdSeconds);
  assert.equal(hasSeconds(0), true);
  assert.equal(hasSeconds(""), false);
  assert.equal(hasSeconds(undefined), false);
});

test("local network rule (#53, #122)", () => {
  for (const h of ["192.168.1.10", "10.1.2.3", "172.20.0.1", "100.64.1.1", "homeassistant", "nas.local", "x.home.arpa",
                   "[fd00::1]", "::1", "fe80::1"]) assert.ok(localHost(h), h);
  for (const h of ["203.0.113.5", "8.8.8.8", "example.com", "", "172.32.0.1"]) assert.ok(!localHost(h), h);
  assert.equal(normalizeServer("192.168.1.10:1984/"), "http://192.168.1.10:1984");
  assert.equal(normalizeServer("ftp://x"), null);
  assert.equal(normalizeServer("http://user:pw@x"), null);
  assert.equal(setupRefused("http://203.0.113.5:1984", false), null);
  assert.equal(setupRefused("http://203.0.113.5:1984", true), "already set up");
  assert.equal(setupRefused("http://192.168.1.10:1984", true), null);
  assert.equal(setupRefused("nonsense://", false), "invalid server");
});

test("status has the contract keys", async () => {
  const p = fakePlayer();
  const r = await handle(p, "status");
  assert.equal(r.code, 200);
  for (const k of ["result", "version", "id", "name", "window", "live", "paused", "dnd", "platform", "api_version",
                   "capabilities", "min_ha_version", "mqtt", "screen", "configured", "position", "size"]) {
    assert.ok(k in r.body, k);
  }
  assert.equal(r.body.platform, "browser");
  assert.equal(r.body.screen, "none");
  assert.deepEqual(r.body.capabilities, DATA.capabilities);
});

test("show, extend, hide, Do not disturb", async () => {
  const p = fakePlayer({ chime: "high" });
  let r = await handle(p, "show", { cam: "front_door", sec: "20", priority: "high", label: "Ring" });
  assert.deepEqual(r.body, { result: true, action: "show", cam: "front_door" });
  assert.equal(p.calls[0][0], "window");
  assert.equal(p.calls[0][1].priority, "high");
  assert.deepEqual(p.calls[1], ["chime"]);
  assert.equal((await handle(p, "status")).body.window, "front_door");
  r = await handle(p, "show", { cam: "front_door" });
  assert.equal(r.body.action, "extend");
  r = await handle(p, "hide");
  assert.deepEqual(r.body, { result: true, action: "hide" });
  assert.equal((await handle(p, "status")).body.screen, "none");
  r = await handle(p, "dnd", { on: "1" });
  assert.deepEqual(r.body, { result: true, action: "dnd", dnd: true });
  r = await handle(p, "show", { cam: "garden" });
  assert.equal(r.body.action, "ignore");
  assert.equal(r.body.result, false);
  r = await handle(p, "show", { cam: "garden", priority: "alarm", test: "1" });
  assert.equal(r.body.action, "show");
  assert.ok(!p.calls.slice(-1).some((c) => c[0] === "chime"), "test=1 never chimes");
  assert.equal(p.controller.events[0].source, "test");
});

test("modes: live, notify, strip, mosaic", async () => {
  const p = fakePlayer();
  await handle(p, "show", { cam: "garden", mode: "live" });
  assert.equal((await handle(p, "status")).body.live, "garden");
  await handle(p, "show", { cam: "front_door,garden" });
  assert.equal((await handle(p, "status")).body.screen, "strip");
  await handle(p, "show", { cam: "garden", mode: "notify" });
  assert.equal(p.calls.at(-1)[0], "notification");
  const r = await handle(p, "mosaic", { sec: "15" });
  assert.deepEqual(r.body, { result: true, action: "show" });
  assert.deepEqual(p.calls.at(-1), ["mosaic", null, 15]);
  assert.equal((await handle(p, "status")).body.screen, "mosaic");
});

test("errors are 400 / 404 like the HTTP players", async () => {
  const p = fakePlayer();
  assert.equal((await handle(p, "show", { cam: "../etc" })).code, 400);
  assert.equal((await handle(p, "show", { mode: "fly" })).code, 400);
  assert.equal((await handle(p, "dnd", { on: "x" })).code, 400);
  assert.equal((await handle(p, "settings", { position: "middle" })).code, 400);
  assert.equal((await handle(p, "ptz", { cam: "x", move: "up" })).code, 404);
  assert.equal((await handle(p, "nonsense")).code, 404);
  const noCam = fakePlayer({ camera: "" });
  assert.equal((await handle(noCam, "show")).body.action, "error");
});

test("settings and setup (#84, #122)", async () => {
  const p = fakePlayer({ server: "" });
  let r = await handle(p, "settings", { position: "bottom_left", size: "small" });
  assert.deepEqual(r.body, { result: true, position: "bottom_left", size: "small" });
  r = await handle(p, "setup", { server: "203.0.113.5:1984", camera: "garden" });
  assert.deepEqual(r.body, { result: true });
  assert.equal(p.settings().server, "http://203.0.113.5:1984");
  assert.equal(p.settings().camera, "garden");
  assert.deepEqual(p.calls.at(-1), ["toast", "settings_received"]);
  r = await handle(p, "setup", { server: "http://198.51.100.7:1984" });
  assert.equal(r.code, 409);
  r = await handle(p, "setup", { server: "http://192.168.1.10:1984" });
  assert.equal(r.code, 200);
  assert.equal((await handle(p, "setup", { server: "" })).code, 400);
});

test("cameras, events, log", async () => {
  const p = fakePlayer();
  assert.deepEqual((await handle(p, "cameras")).body.cameras[0].name, "front_door");
  p.cameras = async () => { throw new Error("down"); };
  assert.deepEqual((await handle(p, "cameras")).body, { result: false, error: "camera source not reachable" });
  await handle(p, "show", {});
  assert.equal((await handle(p, "events")).body.events[0].camera, "front_door");
  assert.ok((await handle(p, "log", { lines: "5" })).body.lines.length <= 5);
});

test("unexpected errors are 500 and never throw", async () => {
  const p = fakePlayer();
  p.settings = () => { throw new Error("boom"); };
  assert.equal((await handle(p, "status")).code, 500);
});
