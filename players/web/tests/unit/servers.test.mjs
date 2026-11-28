// Several go2rtc servers in the browser player (#15, #131): ported from core/camalert_core/servers.py.
import assert from "node:assert/strict";
import { test } from "node:test";
import { Player } from "../../core/player.js";
import { combine, normalizeServer, parseMore, resolve, serverList } from "../../core/servers.js";
import { Store } from "../../core/store.js";

test("addresses and the more_servers text like servers.py", () => {
  assert.equal(normalizeServer("192.168.1.10"), "http://192.168.1.10");
  assert.equal(normalizeServer("nas:1984/"), "http://nas:1984");
  assert.equal(normalizeServer("fd00::10"), "http://[fd00::10]");
  assert.equal(normalizeServer("ftp://x"), null);
  assert.equal(normalizeServer(""), null);
  const { entries, problems } = parseMore("garden=192.168.1.20:1984, http://192.168.1.30:1984\nS2=x;bad prefix=y;;");
  assert.deepEqual(entries, [["garden", "http://192.168.1.20:1984"], [null, "http://192.168.1.30:1984"]]);
  assert.deepEqual(problems, ["s2=x", "bad prefix=y"]);
  const list = serverList("192.168.1.10:1984", "garden=192.168.1.20:1984, 192.168.1.10:1984, garden=h:1, 192.168.1.30:1984");
  assert.deepEqual(list, [{ id: "s1", url: "http://192.168.1.10:1984", prefix: null },
                          { id: "s2", url: "http://192.168.1.20:1984", prefix: "garden" },
                          { id: "s3", url: "http://192.168.1.30:1984", prefix: null }]);
  assert.deepEqual(serverList("", ""), []);
});

test("camera names: prefix, s<n> on a clash, and back to server and stream", () => {
  const list = serverList("a:1984", "garden=b:1984, c:1984");
  const all = combine([[list[0], ["front_door", "all"], new Set(["all"])], [list[1], ["cam"], new Set()],
                       [list[2], ["front_door", "side"], new Set()]]);
  assert.deepEqual(all.names, ["all", "front_door", "garden.cam", "s3.front_door", "side"]);
  assert.deepEqual([...all.composites], ["all"]);
  assert.deepEqual(resolve("garden.cam", list, all.mapping), [list[1], "cam"]);
  assert.deepEqual(resolve("s3.front_door", list, all.mapping), [list[2], "front_door"]);
  assert.deepEqual(resolve("side", list, all.mapping), [list[2], "side"]);
  // without a list: prefix or s<n> to that server, everything else to the main one
  assert.deepEqual(resolve("garden.x", list), [list[1], "x"]);
  assert.deepEqual(resolve("s3.y", list), [list[2], "y"]);
  assert.deepEqual(resolve("s1.z", list), [list[0], "s1.z"]);
  assert.deepEqual(resolve("plain", list), [list[0], "plain"]);
  assert.deepEqual(resolve("x", []), [null, "x"]);
});

function mem() {
  let v = null;
  return { load: () => v, save: (o) => { v = o; } };
}

test("a player with several servers: camera list, URLs and hello (#131)", async () => {
  const store = new Store(mem());
  store.set({ server: "http://a:1984", more_servers: "garden=http://b:1984, http://down:1984" });
  const answers = {
    "http://ha/api/camalert/go2rtc/ID/api/streams": { front_door: {}, front_door_jpeg: {} },
    "http://ha/api/camalert/go2rtc/ID/s2/api/streams": {
      cam: {}, cam_talk: { producers: [{ url: "exec:ffmpeg -i - #backchannel=1" }] } },
  };
  const seen = [];
  const fetch = async (url, opts) => {
    seen.push([url, opts.headers.Authorization]);
    if (!(url in answers)) return { ok: false, status: 502 };
    return { ok: true, json: async () => answers[url] };
  };
  store.set({ ready_cameras: "front_door=front_door_jpeg" });
  const link = { start() {}, stop() {}, restart() {} };
  const p = new Player({ store, link, haUrl: "http://ha/", token: async () => "T", fetch });
  store.id = "ID";
  assert.deepEqual((await p.cameras()).map((c) => c.name), ["front_door", "garden.cam"]);
  assert.equal(seen.length, 3);
  assert.ok(seen.every(([, auth]) => auth === "Bearer T"));
  assert.equal(p.src("garden.cam").base, "http://ha/api/camalert/go2rtc/ID/s2");
  assert.equal(p.src("garden.cam").stream("garden.cam"), "cam");
  assert.equal(p.src("front_door").base, "http://ha/api/camalert/go2rtc/ID");
  assert.equal(await p.talkStream("garden.cam"), "cam_talk");
  assert.equal(p.hello().more_servers, "http://b:1984,http://down:1984");
  // one server: no more_servers in the hello (older integrations refuse unknown keys)
  store.set({ more_servers: "" });
  assert.equal("more_servers" in p.hello(), false);
  // no server answers at all: an error, like one server
  store.set({ more_servers: "http://y:1" });
  for (const k of Object.keys(answers)) delete answers[k];
  await assert.rejects(p.streamInfo(), /no server reachable/);
});

test("direct pictures (MQTT, #131): go2rtc itself, no token", async () => {
  const store = new Store(mem());
  store.set({ server: "http://a:1984", more_servers: "garden=http://b:1984" });
  const seen = [];
  const fetch = async (url, opts) => {
    seen.push([url, opts.headers.Authorization]);
    return { ok: true, json: async () => ({ cam: {} }) };
  };
  const p = new Player({ store, link: { start() {}, stop() {}, restart() {} }, haUrl: "", direct: true,
                         token: async () => "never", fetch });
  assert.deepEqual((await p.cameras()).map((c) => c.name), ["cam", "garden.cam"]);
  assert.deepEqual(seen, [["http://a:1984/api/streams", undefined], ["http://b:1984/api/streams", undefined]]);
  assert.equal(p.base(), "http://a:1984");
  assert.equal(p.src("garden.cam").base, "http://b:1984");
});
