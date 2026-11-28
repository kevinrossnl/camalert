// The Home Assistant link of the browser player (#92, #127) against the fake Home Assistant.
import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { Player } from "../../core/player.js";
import { Store } from "../../core/store.js";
import { HaSocket } from "../../core/transport.js";
import { FakeHA, TOKEN } from "../fake/server.mjs";

const haveWs = typeof globalThis.WebSocket === "function";
let fake;

before(async () => { fake = await new FakeHA().start(); });
after(async () => { await fake.stop(); });

function mem() {
  let v = null;
  return { load: () => v, save: (o) => { v = o; } };
}

test("connect, answer requests, reconnect with a new hello", { skip: !haveWs && "needs Node 22 (WebSocket)" }, async () => {
  const store = new Store(mem());
  store.setName("Test player");
  store.set({ server: "http://192.168.1.10:1984", camera: "front_door" });
  const states = [];
  const link = new HaSocket({ url: fake.url.replace("http", "ws") + "/api/websocket", token: async () => TOKEN,
                              WebSocket, onState: (s) => states.push(s) });
  const player = new Player({ store, link, haUrl: fake.url, token: async () => TOKEN });
  const shown = [];
  player.setView({ window: (x) => shown.push(x), mosaic: () => {}, notification: () => {}, hide: () => shown.push("hide"),
                   chime: () => {}, toast: () => {} });
  player.start();
  const bid = await fake.connected();
  assert.equal(bid, store.id);
  assert.equal(fake.hellos[0].name, "Test player");
  assert.equal(fake.hellos[0].server, "http://192.168.1.10:1984");
  const st = await fake.request("status");
  assert.equal(st.code, 200);
  assert.equal(st.body.platform, "browser");
  const r = await fake.request("show", { cam: "garden", sec: 10 });
  assert.deepEqual(r.body, { result: true, action: "show", cam: "garden" });
  assert.equal(shown[0].cams[0], "garden");
  const cams = await fake.request("cameras");
  assert.deepEqual(cams.body.cameras.map((c) => c.name), ["all", "front_door", "garden"]);
  assert.equal(await link.sign("/api/x"), "/api/x?authSig=fake");
  store.set({ server: "http://192.168.1.20:1984" });
  for (let i = 0; i < 100 && fake.hellos.length < 2; i++) await new Promise((res) => setTimeout(res, 50));
  assert.equal(fake.hellos.at(-1).server, "http://192.168.1.20:1984");
  assert.ok(states.includes("connected"));
  player.stop();
});

test("a refused token is auth_failed, not a reconnect loop", { skip: !haveWs && "needs Node 22 (WebSocket)" }, async () => {
  const states = [];
  const link = new HaSocket({ url: fake.url.replace("http", "ws") + "/api/websocket", token: async () => "wrong",
                              WebSocket, onState: (s) => states.push(s) });
  link.start(() => ({ browser_id: "web000000000001" }), async () => ({ code: 200, body: {} }));
  for (let i = 0; i < 100 && !states.includes("auth_failed"); i++) await new Promise((res) => setTimeout(res, 50));
  assert.ok(states.includes("auth_failed"));
  link.stop();
  const none = new HaSocket({ url: fake.url.replace("http", "ws") + "/api/websocket", token: async () => null,
                              WebSocket, onState: (s) => states.push(s) });
  none.start(() => ({ browser_id: "web000000000002" }), async () => ({ code: 200, body: {} }));
  for (let i = 0; i < 100 && states.filter((s) => s === "auth_failed").length < 2; i++) {
    await new Promise((res) => setTimeout(res, 50));
  }
  none.stop();
  assert.equal(states.filter((s) => s === "auth_failed").length, 2);
});
