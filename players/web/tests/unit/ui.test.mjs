// Geometry and texts of the browser player's screen (#92): the same numbers as layout.py and style.py.
import assert from "node:assert/strict";
import { test } from "node:test";
import { grid, language, markedTitle, translator, windowGeometry } from "../../core/ui.js";

test("window geometry like layout.window_geometry", () => {
  assert.deepEqual(windowGeometry("top_right", "medium", 1920, 1080), { x: 1240, y: 40, w: 640, h: 360, title: 40 });
  assert.deepEqual(windowGeometry("bottom_left", "small", 1280, 720, "large"),
                   { x: 27, y: 720 - (180 + 33) - 27, w: 320, h: 180, title: 33 });
});

test("grid like layout.grid", () => {
  assert.equal(grid(1, 1920, 1080).length, 1);
  const g = grid(5, 1920, 1080);
  assert.equal(g.length, 5);
  assert.ok(g.every((t) => t.w > 0 && t.h > 0 && t.x >= 0 && t.y >= 0));
});

test("marked title and language", () => {
  const nl = translator("nl");
  assert.equal(markedTitle("Front door", "high", "steady", nl), `${nl("Doorbell")} · Front door`);
  assert.equal(markedTitle("Front door", "normal", "steady", nl), "Front door");
  assert.equal(markedTitle("Front door", "alarm", "off", nl), "Front door");
  assert.equal(language("de"), "de");
  assert.equal(language("system", { language: "fr-FR" }), "fr");
  assert.equal(language("system", { language: "xx" }), "en");
  assert.notEqual(nl("Loading picture..."), "Loading picture...");
  assert.equal(translator("en")("Loading picture..."), "Loading picture...");
});

test("clock in the player's language: 24 hours except English (#98 screenshot)", async () => {
  const { clockText } = await import("../../core/ui.js");
  const d = new Date(2026, 10, 28, 14, 8);
  for (const lang of ["nl", "de", "fr", "it", "pl"]) assert.match(clockText(d, lang), /^14[:.]08$/, lang);
  assert.ok(!/PM|AM/.test(clockText(d, "nl")));
});

test("talk-back (#98): microphone to go2rtc's talk stream over WebRTC, stops by itself and on stop()", async () => {
  const { Talk } = await import("../../core/ui.js");
  assert.equal(Talk.possible(undefined, true), false);
  assert.equal(Talk.possible({ getUserMedia() {} }, false), false); // http page: no microphone
  assert.equal(Talk.possible({ getUserMedia() {} }, true), true);
  const stopped = [];
  const track = { kind: "audio", stop: () => stopped.push("mic") };
  const media = { getUserMedia: async (c) => { assert.ok(c.audio); return { getAudioTracks: () => [track], getTracks: () => [track] }; } };
  const peers = [];
  class Peer {
    constructor() { this.tx = []; this.iceGatheringState = "complete"; peers.push(this); }
    addTransceiver(t, o) { this.tx.push([t, o.direction]); }
    async createOffer() { return { type: "offer", sdp: "v=0 offer" }; }
    async setLocalDescription(d) { this.localDescription = d; }
    async setRemoteDescription(d) { this.remote = d; }
    close() { this.closed = true; }
  }
  const calls = [];
  const player = { base: () => "http://ha/api/camalert/go2rtc/web1",
                   authFetch: async (url, o) => { calls.push([url, o.method, o.body]); return { ok: true, text: async () => "v=0 answer" }; } };
  const t = new Talk(player, "front_door_talk", { media, Peer });
  await t.start();
  assert.equal(t.on, true);
  assert.deepEqual(peers[0].tx, [[track, "sendonly"]]);
  assert.deepEqual(calls, [["http://ha/api/camalert/go2rtc/web1/api/webrtc?src=front_door_talk", "POST", "v=0 offer"]]);
  assert.equal(peers[0].remote.sdp, "v=0 answer");
  t.stop();
  assert.equal(t.on, false);
  assert.ok(peers[0].closed);
  assert.deepEqual(stopped, ["mic"]);
  const bad = new Talk({ base: player.base, authFetch: async () => ({ ok: false, status: 403 }) }, "x_talk", { media, Peer });
  await assert.rejects(bad.start(), /403/);
  assert.equal(bad.on, false);
});
