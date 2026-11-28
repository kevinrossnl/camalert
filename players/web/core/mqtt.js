// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
//
// MQTT over WebSocket (#131): a browser player that talks to an MQTT broker instead of Home Assistant's WebSocket,
// with the same topics as the other players (core/camalert_core/mqtt):
//   camalert/<node>/show      payload: camera name, or JSON {"cam", "sec", "mode", "priority", "label"}
//   camalert/<node>/mosaic    payload: empty or "cam1,cam2"
//   camalert/<node>/hide
//   camalert/<node>/dnd/set   ON / OFF; the player publishes camalert/<node>/dnd
//   camalert/<node>/state     published: the camera on screen, or "none"
//   camalert/<node>/availability  online / offline (retained, last will)
// plus Home Assistant MQTT discovery (buttons per camera, mosaic, hide, on screen, do not disturb). The link has the
// interface of HaSocket (transport.js): start(hello, onRequest), stop(), restart(), sign(path), state. Pictures
// come straight from go2rtc then (Player option direct), so `direct` is true and sign() changes nothing.
import { RETRY } from "./transport.js";

const enc = new TextEncoder();
const dec = new TextDecoder();

function len(n) {
  const out = [];
  do {
    let b = n % 128;
    n = Math.floor(n / 128);
    if (n) b |= 0x80;
    out.push(b);
  } while (n);
  return out;
}

function str(s) {
  const b = typeof s === "string" ? enc.encode(s) : s;
  return [b.length >> 8, b.length & 0xff, ...b];
}

function packet(head, body) {
  return new Uint8Array([head, ...len(body.length), ...body]);
}

/** MQTT 3.1.1 CONNECT (clean session, will retained QoS 0). */
export function connect(clientId, o = {}) {
  let flags = 0x02;
  let payload = str(clientId);
  if (o.willTopic) {
    flags |= 0x04 | 0x20;
    payload = payload.concat(str(o.willTopic), str(o.willPayload || "offline"));
  }
  if (o.user) {
    flags |= 0x80;
    payload = payload.concat(str(o.user));
    if (o.password) {
      flags |= 0x40;
      payload = payload.concat(str(o.password));
    }
  }
  const keepalive = o.keepalive || 60;
  return packet(0x10, str("MQTT").concat([4, flags, keepalive >> 8, keepalive & 0xff], payload));
}

export function publish(topic, payload, retain = false) {
  const p = typeof payload === "string" ? enc.encode(payload) : payload || new Uint8Array(0);
  return packet(0x30 | (retain ? 1 : 0), str(topic).concat(Array.from(p)));
}

export function subscribe(packetId, topics) {
  let body = [packetId >> 8, packetId & 0xff];
  for (const t of topics) body = body.concat(str(t), [0]);
  return packet(0x82, body);
}

export const PING = new Uint8Array([0xc0, 0]);
export const DISCONNECT = new Uint8Array([0xe0, 0]);

/** Complete packets of a byte buffer: {packets: [{type, flags, body}], rest}. */
export function split(buffer) {
  const packets = [];
  let i = 0;
  for (;;) {
    if (buffer.length - i < 2) break;
    let mult = 1;
    let length = 0;
    let j = i + 1;
    let done = false;
    while (j < buffer.length) {
      const b = buffer[j++];
      length += (b & 0x7f) * mult;
      mult *= 128;
      if (!(b & 0x80)) {
        done = true;
        break;
      }
    }
    if (!done || buffer.length - j < length) break;
    packets.push({ type: buffer[i] >> 4, flags: buffer[i] & 0x0f, body: buffer.subarray(j, j + length) });
    i = j + length;
  }
  return { packets, rest: buffer.slice(i) };
}

/** {topic, payload (string)} of an incoming PUBLISH. */
export function parsePublish(flags, body) {
  const n = (body[0] << 8) | body[1];
  const topic = dec.decode(body.subarray(2, 2 + n));
  let rest = body.subarray(2 + n);
  if ((flags >> 1) & 0x03) rest = rest.subarray(2); // QoS > 0 has a packet id
  return { topic, payload: dec.decode(rest) };
}

/** The parameters of a show command (topics.mqtt_command): "front_door" or JSON. */
export function showParams(payload) {
  const text = String(payload || "").trim();
  if (text.startsWith("{")) {
    let d;
    try {
      d = JSON.parse(text);
    } catch (e) {
      return {};
    }
    if (!d || typeof d !== "object") return {};
    const out = {};
    for (const k of ["cam", "sec", "mode", "priority", "label"]) if (k in d && d[k] !== null) out[k] = String(d[k]);
    return out;
  }
  return text ? { cam: text } : {};
}

function sorted(v) {
  if (Array.isArray(v)) return v.map(sorted);
  if (v && typeof v === "object") return Object.fromEntries(Object.keys(v).sort().map((k) => [k, sorted(v[k])]));
  return v;
}

/** Home Assistant discovery messages [[topic, JSON]] (topics.discovery, without the remote button). */
export function discovery(node, name, cameras, prefix = "camalert", base = "homeassistant") {
  const avail = `${prefix}/${node}/availability`;
  const device = { identifiers: [`camalert_${node}`], name, manufacturer: "CamAlert", model: "Browser player" };
  const out = [];
  const add = (kind, oid, conf) => {
    Object.assign(conf, { unique_id: `camalert_${node}_${oid}`, object_id: `camalert_${node}_${oid}`,
                          availability_topic: avail, device });
    out.push([`${base}/${kind}/camalert_${node}/${oid}/config`, JSON.stringify(sorted(conf))]);
  };
  for (const [cam, title] of cameras) {
    add("button", `show_${cam}`, { name: `Show ${title}`, icon: "mdi:cctv", command_topic: `${prefix}/${node}/show`,
                                   payload_press: cam });
  }
  add("button", "mosaic", { name: "Mosaic", icon: "mdi:view-grid", command_topic: `${prefix}/${node}/mosaic`,
                            payload_press: "" });
  add("button", "hide", { name: "Hide camera", icon: "mdi:close-box", command_topic: `${prefix}/${node}/hide`,
                          payload_press: "" });
  add("sensor", "on_screen", { name: "Camera on screen", icon: "mdi:television", state_topic: `${prefix}/${node}/state` });
  add("switch", "dnd", { name: "Do not disturb", icon: "mdi:bell-off", command_topic: `${prefix}/${node}/dnd/set`,
                         state_topic: `${prefix}/${node}/dnd`, payload_on: "ON", payload_off: "OFF" });
  return out;
}

/** A discovery config of this node that is no longer valid (#116): a camera button of a camera that is gone. */
function stale(topic, node, cameras) {
  const p = topic.split("/");
  if (p.length !== 5 || p[2] !== `camalert_${node}` || p[4] !== "config") return false;
  return p[1] === "button" && p[3].startsWith("show_") && !cameras.has(p[3].slice(5));
}

export class MqttLink {
  /**
   * @param {object} o  url (ws(s)://broker:port/path), user, password: async () => password, WebSocket (class),
   *                    cameras: async () => [[name, title]], screen: () => camera on screen or "none",
   *                    dnd: () => bool, discovery (default true), log(msg, level), onState(state), clock
   */
  constructor(o) {
    this.o = Object.assign({ log: () => {}, onState: () => {}, discovery: true, screen: () => "none", dnd: () => false,
                             cameras: async () => [],
                             clock: { setTimeout: (f, ms) => setTimeout(f, ms), clearTimeout: (t) => clearTimeout(t),
                                      setInterval: (f, ms) => setInterval(f, ms), clearInterval: (t) => clearInterval(t) } }, o);
    this.direct = true;
    this.ws = null;
    this.buffer = new Uint8Array(0);
    this.failures = 0;
    this.timer = null;
    this.ticker = null;
    this.stopped = true;
    this.state = "closed";
    this.last = {};
    this.seen = new Set();
    this.cams = null;
  }

  _state(s) {
    if (s !== this.state) {
      this.state = s;
      this.o.onState(s);
    }
  }

  get node() {
    return this.hello().browser_id;
  }

  get prefix() {
    return `camalert/${this.node}/`;
  }

  start(hello, onRequest) {
    this.hello = hello;
    this.onRequest = onRequest;
    this.stopped = false;
    this._open();
  }

  stop() {
    this.stopped = true;
    if (this.timer !== null) this.o.clock.clearTimeout(this.timer);
    this.timer = null;
    this._close(true);
    this._state("closed");
  }

  restart() {
    if (this.stopped) return;
    this._close(true);
    this._open();
  }

  async sign(path) {
    return path;
  }

  _close(clean) {
    if (this.ticker !== null) this.o.clock.clearInterval(this.ticker);
    this.ticker = null;
    const ws = this.ws;
    this.ws = null;
    if (!ws) return;
    if (clean && ws.readyState === 1) {
      ws.send(publish(this.prefix + "availability", "offline", true));
      ws.send(DISCONNECT);
    }
    ws.close();
  }

  _retry() {
    if (this.stopped || this.timer !== null) return;
    const wait = RETRY[Math.min(this.failures, RETRY.length - 1)];
    this.failures += 1;
    this.timer = this.o.clock.setTimeout(() => {
      this.timer = null;
      this._open();
    }, wait * 1000);
  }

  _send(bytes) {
    if (this.ws && this.ws.readyState === 1) this.ws.send(bytes);
  }

  _open() {
    this._state("connecting");
    let ws;
    try {
      ws = new this.o.WebSocket(this.o.url, ["mqtt"]);
    } catch (e) {
      this.o.log(`MQTT: ${e.message}`, "error");
      this._retry();
      return;
    }
    ws.binaryType = "arraybuffer";
    this.ws = ws;
    this.buffer = new Uint8Array(0);
    ws.onopen = async () => {
      if (this.ws !== ws) return;
      let password = "";
      try {
        password = (this.o.password && (await this.o.password())) || "";
      } catch (e) {
        password = "";
      }
      ws.send(connect(`camalert-${this.node}`, { user: this.o.user, password, willTopic: this.prefix + "availability" }));
    };
    ws.onmessage = (ev) => this._data(ws, ev.data);
    ws.onclose = () => {
      if (this.ws !== ws) return;
      this.ws = null;
      if (this.ticker !== null) this.o.clock.clearInterval(this.ticker);
      this.ticker = null;
      if (this.state !== "auth_failed") this._state("connecting");
      this._retry();
    };
    ws.onerror = () => {};
  }

  async _data(ws, data) {
    if (ws !== this.ws) return;
    const chunk = new Uint8Array(data instanceof ArrayBuffer ? data : data.buffer || data);
    const all = new Uint8Array(this.buffer.length + chunk.length);
    all.set(this.buffer);
    all.set(chunk, this.buffer.length);
    const { packets, rest } = split(all);
    this.buffer = rest;
    for (const p of packets) {
      if (p.type === 2) await this._connack(ws, p.body);
      else if (p.type === 3) {
        const { topic, payload } = parsePublish(p.flags, p.body);
        await this._publish(topic, payload);
      }
    }
  }

  async _connack(ws, body) {
    const rc = body[1];
    if (rc !== 0) {
      this.o.log(`MQTT broker refused the connection (code ${rc})`, "error");
      if (rc === 4 || rc === 5) this._state("auth_failed");
      ws.close();
      return;
    }
    this.failures = 0;
    this.last = {};
    this.seen = new Set();
    this._send(publish(this.prefix + "availability", "online", true));
    const topics = ["show", "mosaic", "hide", "dnd/set"].map((t) => this.prefix + t);
    if (this.o.discovery) topics.push(`homeassistant/+/camalert_${this.node}/+/config`);
    this._send(subscribe(1, topics));
    this._state("connected");
    this.ticker = this.o.clock.setInterval(() => this._tick(), 1000);
    this._tick();
    this.announce();
  }

  /** Publishes the state topics when they changed, and a ping now and then (keepalive 60 s). */
  _tick() {
    const now = { state: this.o.screen() || "none", dnd: this.o.dnd() ? "ON" : "OFF" };
    for (const [k, v] of Object.entries(now)) {
      if (this.last[k] !== v) {
        this._send(publish(this.prefix + k, v, true));
        this.last[k] = v;
      }
    }
    this.pings = ((this.pings || 0) + 1) % 30;
    if (!this.pings) this._send(PING);
  }

  /** Home Assistant discovery for the current camera list (after connecting and when the cameras change). */
  async announce() {
    if (!this.o.discovery || this.state !== "connected") return;
    let cams;
    try {
      cams = await this.o.cameras();
    } catch (e) {
      this.o.log(`MQTT discovery: camera list failed (${e.message})`, "error");
      return;
    }
    this.cams = new Set(cams.map(([n]) => n));
    const name = this.hello().name || `CamAlert browser ${this.node.slice(-4)}`;
    for (const [topic, payload] of discovery(this.node, name, cams)) this._send(publish(topic, payload, true));
    for (const topic of this.seen) if (stale(topic, this.node, this.cams)) this._send(publish(topic, "", true));
  }

  async _publish(topic, payload) {
    if (topic.startsWith("homeassistant/")) {
      if (!payload) return;
      this.seen.add(topic);
      if (this.cams && stale(topic, this.node, this.cams)) this._send(publish(topic, "", true));
      return;
    }
    if (!topic.startsWith(this.prefix)) return;
    const action = topic.slice(this.prefix.length);
    let out;
    if (action === "show") {
      const params = showParams(payload);
      out = await this.onRequest("show", params);
    } else if (action === "mosaic") {
      out = await this.onRequest("mosaic", payload.trim() ? { cam: payload.trim() } : {});
    } else if (action === "hide") {
      out = await this.onRequest("hide", {});
    } else if (action === "dnd/set") {
      const on = payload.trim().toUpperCase();
      if (on === "ON" || on === "OFF") out = await this.onRequest("dnd", { on: on === "ON" ? "true" : "false" });
      this._tick();
    }
    if (out && out.code !== 200) this.o.log(`MQTT ${action}: ${(out.body && out.body.error) || out.code}`, "error");
  }
}
