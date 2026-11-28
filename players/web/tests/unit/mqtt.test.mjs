// MQTT over WebSocket (#131): the codec like core/camalert_core/mqtt/codec.py and the link with a fake broker.
import assert from "node:assert/strict";
import { test } from "node:test";
import { connect, discovery, MqttLink, parsePublish, PING, publish, showParams, split, subscribe } from "../../core/mqtt.js";

const hex = (b) => Buffer.from(b).toString("hex");

test("packets byte for byte like codec.py", () => {
  // the hex strings are what codec.mqtt_connect("cid", "u", "p", will_topic="t/a") and friends return
  assert.equal(hex(connect("cid", { user: "u", password: "p", willTopic: "t/a" })),
               "102300044d51545404e6003c00036369640003742f6100076f66666c696e65000175000170");
  assert.equal(hex(connect("c")), "100d00044d5154540402003c000163");
  assert.equal(hex(publish("a/b", "on", true)), "31070003612f626f6e");
  assert.equal(hex(subscribe(1, ["x", "yz"])), "820b0001000178000002797a00");
  assert.equal(hex(PING), "c000");
  const long = publish("t", "x".repeat(200));
  assert.equal(hex(long.subarray(0, 3)), "30cb01"); // two-byte remaining length
});

test("split and parse incoming packets, also when they come in pieces", () => {
  const a = publish("camalert/n/show", "front_door");
  const b = publish("camalert/n/hide", "");
  const both = new Uint8Array([...a, ...b]);
  const { packets, rest } = split(both.subarray(0, both.length - 3));
  assert.equal(packets.length, 1);
  assert.equal(rest.length, b.length - 3);
  assert.deepEqual(parsePublish(packets[0].flags, packets[0].body), { topic: "camalert/n/show", payload: "front_door" });
  const qos1 = new Uint8Array([0x32, 7, 0, 1, 0x74, 0, 9, 0x6f, 0x6b]); // topic "t", packet id 9, "ok"
  const p = split(qos1).packets[0];
  assert.deepEqual(parsePublish(p.flags, p.body), { topic: "t", payload: "ok" });
  assert.equal(split(new Uint8Array([0x30, 0x80])).packets.length, 0); // length not complete yet
});

test("show payloads like topics.mqtt_command", () => {
  assert.deepEqual(showParams("front_door"), { cam: "front_door" });
  assert.deepEqual(showParams(' {"cam": "garden", "sec": 20, "mode": "live", "x": 1} '),
                   { cam: "garden", sec: "20", mode: "live" });
  assert.deepEqual(showParams("{broken"), {});
  assert.deepEqual(showParams(""), {});
});

test("discovery like topics.discovery (browser model, no remote button)", () => {
  const msgs = discovery("web1", "Desk", [["front_door", "Front door"]]);
  assert.deepEqual(msgs.map(([t]) => t), [
    "homeassistant/button/camalert_web1/show_front_door/config", "homeassistant/button/camalert_web1/mosaic/config",
    "homeassistant/button/camalert_web1/hide/config", "homeassistant/sensor/camalert_web1/on_screen/config",
    "homeassistant/switch/camalert_web1/dnd/config"]);
  const show = JSON.parse(msgs[0][1]);
  assert.equal(show.command_topic, "camalert/web1/show");
  assert.equal(show.payload_press, "front_door");
  assert.equal(show.availability_topic, "camalert/web1/availability");
  assert.equal(show.device.model, "Browser player");
  assert.deepEqual(Object.keys(show), Object.keys(show).slice().sort());
});

class FakeWS {
  static last = null;
  constructor(url, protocols) {
    this.url = url;
    this.protocols = protocols;
    this.readyState = 1;
    this.sent = [];
    FakeWS.last = this;
    setTimeout(() => this.onopen && this.onopen(), 0);
  }
  send(b) {
    this.sent.push(...split(new Uint8Array(b)).packets);
  }
  close() {
    this.readyState = 3;
    this.closed = true;
  }
  feed(bytes) {
    this.onmessage({ data: new Uint8Array(bytes).buffer });
  }
  published() {
    return this.sent.filter((p) => p.type === 3).map((p) => Object.assign(parsePublish(p.flags, p.body),
                                                                          { retain: !!(p.flags & 1) }));
  }
}

const tick = () => new Promise((r) => setTimeout(r, 5));
const clock = { setTimeout: () => 0, clearTimeout: () => {}, setInterval: () => 1, clearInterval: () => {} };

test("the link: connect, commands to the API, state, discovery and cleanup", async () => {
  const calls = [];
  let screen = "none";
  let dnd = false;
  const link = new MqttLink({ url: "ws://broker:1884/mqtt", user: "u", password: async () => "p", WebSocket: FakeWS,
                              cameras: async () => [["front_door", "Front door"], ["garden", "Garden"]],
                              screen: () => screen, dnd: () => dnd, clock });
  const states = [];
  link.o.onState = (s) => states.push(s);
  link.start(() => ({ browser_id: "web1", name: "Desk" }), async (action, params) => {
    calls.push([action, params]);
    if (action === "dnd") dnd = params.on === "true";
    return { code: 200, body: { result: true } };
  });
  await tick();
  const ws = FakeWS.last;
  assert.deepEqual(ws.protocols, ["mqtt"]);
  assert.equal(ws.sent[0].type, 1); // CONNECT with user, password and the last will
  assert.ok(Buffer.from(ws.sent[0].body).includes("camalert/web1/availability"));
  ws.feed([0x20, 2, 0, 0]); // CONNACK accepted
  await tick();
  assert.equal(link.state, "connected");
  const pub = ws.published();
  assert.deepEqual(pub[0], { topic: "camalert/web1/availability", payload: "online", retain: true });
  assert.ok(pub.some((m) => m.topic === "camalert/web1/state" && m.payload === "none"));
  assert.ok(pub.some((m) => m.topic === "homeassistant/button/camalert_web1/show_garden/config" && m.retain));
  const sub = ws.sent.find((p) => p.type === 8);
  assert.ok(Buffer.from(sub.body).includes("camalert/web1/dnd/set"));
  // commands
  ws.feed(publish("camalert/web1/show", '{"cam": "garden", "sec": 15}'));
  ws.feed(publish("camalert/web1/mosaic", "front_door,garden"));
  ws.feed(publish("camalert/web1/hide", ""));
  ws.feed(publish("camalert/web1/dnd/set", "ON"));
  ws.feed(publish("camalert/other/show", "x")); // another player's topic
  await tick();
  assert.deepEqual(calls, [["show", { cam: "garden", sec: "15" }], ["mosaic", { cam: "front_door,garden" }],
                           ["hide", {}], ["dnd", { on: "true" }]]);
  assert.ok(ws.published().some((m) => m.topic === "camalert/web1/dnd" && m.payload === "ON"));
  screen = "garden";
  link._tick();
  assert.ok(ws.published().some((m) => m.topic === "camalert/web1/state" && m.payload === "garden"));
  // a retained button of a camera that is gone is cleared; a current one is kept
  ws.feed(publish("homeassistant/button/camalert_web1/show_old/config", "{}", true));
  ws.feed(publish("homeassistant/button/camalert_web1/show_garden/config", "{}", true));
  await tick();
  const cleared = ws.published().filter((m) => m.payload === "" && m.topic.startsWith("homeassistant/"));
  assert.deepEqual(cleared.map((m) => m.topic), ["homeassistant/button/camalert_web1/show_old/config"]);
  // stop: offline, DISCONNECT
  link.stop();
  assert.ok(ws.published().some((m) => m.topic === "camalert/web1/availability" && m.payload === "offline"));
  assert.equal(ws.sent[ws.sent.length - 1].type, 14);
  assert.equal(await link.sign("/api/x"), "/api/x");
  assert.equal(link.direct, true);
  assert.equal(states[states.length - 1], "closed");
});

test("a refused login is auth_failed", async () => {
  const link = new MqttLink({ url: "ws://b/mqtt", WebSocket: FakeWS, clock });
  link.start(() => ({ browser_id: "web2", name: "" }), async () => ({ code: 200 }));
  await tick();
  FakeWS.last.feed([0x20, 2, 0, 5]);
  await tick();
  assert.equal(link.state, "auth_failed");
  assert.ok(FakeWS.last.closed);
  link.stop();
});
