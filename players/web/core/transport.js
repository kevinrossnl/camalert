// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
//
// How a browser player talks to Home Assistant (#92, #127): the Home Assistant WebSocket API. The player
// subscribes with `camalert/browser/connect`; Home Assistant sends the CamAlert API requests as events of that
// subscription ({type: "request", id, action, params}) and the player answers with `camalert/browser/reply`.
// Two links with the same interface:
//   HaSocket       own WebSocket (web page outside the dashboard, extension): auth with an access token
//   FrontendLink   inside Home Assistant's own frontend (dashboard module): hass.connection, no extra login
// Interface: start(hello, onRequest), stop(), restart(), sign(path) -> signed path, state ("connecting",
// "connected", "auth_failed", "closed").
export const RETRY = [1, 2, 5, 10, 30]; // seconds between attempts after an error

export class HaSocket {
  /**
   * @param {object} o  url (ws(s)://host/api/websocket), token: async () => access token, WebSocket (class),
   *                    log(msg, level), onState(state), clock {setTimeout, clearTimeout}
   */
  constructor(o) {
    this.o = Object.assign({ log: () => {}, onState: () => {},
                             clock: { setTimeout: (f, ms) => setTimeout(f, ms), clearTimeout: (t) => clearTimeout(t) } }, o);
    this.ws = null;
    this.nextId = 1;
    this.pending = new Map();
    this.subId = null;
    this.failures = 0;
    this.timer = null;
    this.stopped = true;
    this.state = "closed";
  }

  _state(s) {
    if (s !== this.state) {
      this.state = s;
      this.o.onState(s);
    }
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
    if (this.ws) this.ws.close();
    this.ws = null;
    this._state("closed");
  }

  /** New hello (name or go2rtc address changed): reconnect at once. */
  restart() {
    if (this.stopped) return;
    if (this.ws) {
      const ws = this.ws;
      this.ws = null;
      ws.close();
    }
    this._open();
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

  _send(msg) {
    if (this.ws && this.ws.readyState === 1) this.ws.send(JSON.stringify(msg));
  }

  _call(msg) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this._send(Object.assign({ id }, msg));
    });
  }

  _open() {
    this._state("connecting");
    let ws;
    try {
      ws = new this.o.WebSocket(this.o.url);
    } catch (e) {
      this.o.log(`Home Assistant: ${e.message}`, "error");
      this._retry();
      return;
    }
    this.ws = ws;
    this.nextId = 1;
    this.pending.clear();
    ws.onmessage = (ev) => this._message(ws, ev.data);
    ws.onclose = () => {
      if (this.ws !== ws) return;
      this.ws = null;
      for (const p of this.pending.values()) p.reject(new Error("connection closed"));
      this.pending.clear();
      if (this.state !== "auth_failed") this._state("connecting");
      this._retry();
    };
    ws.onerror = () => {};
  }

  async _message(ws, raw) {
    if (ws !== this.ws) return;
    let msg;
    try {
      msg = JSON.parse(typeof raw === "string" ? raw : String(raw));
    } catch (e) {
      return;
    }
    if (msg.type === "auth_required") {
      let token;
      try {
        token = await this.o.token();
      } catch (e) {
        token = null;
      }
      if (!token) {
        this._state("auth_failed");
        ws.close();
        return;
      }
      this._send({ type: "auth", access_token: token });
    } else if (msg.type === "auth_invalid") {
      this.o.log("Home Assistant refused the login", "error");
      this._state("auth_failed");
    } else if (msg.type === "auth_ok") {
      this.failures = 0;
      this.subId = this.nextId;
      this._call(Object.assign({ type: "camalert/browser/connect" }, this.hello())).then(
        () => this._state("connected"),
        (e) => {
          this.o.log(`Home Assistant: ${e.message}`, "error");
          ws.close();
        });
    } else if (msg.type === "result") {
      const p = this.pending.get(msg.id);
      this.pending.delete(msg.id);
      if (p) {
        if (msg.success) p.resolve(msg.result);
        else p.reject(new Error((msg.error && msg.error.message) || "failed"));
      }
    } else if (msg.type === "event" && msg.id === this.subId && msg.event && msg.event.type === "request") {
      const r = msg.event;
      const out = await this.onRequest(r.action, r.params || {});
      this._send({ id: this.nextId++, type: "camalert/browser/reply", request_id: r.id, code: out.code, body: out.body });
    }
  }

  /** A signed path for an <img> (Home Assistant's auth/sign_path), valid for `expires` seconds. */
  async sign(path, expires = 86400) {
    const r = await this._call({ type: "auth/sign_path", path, expires });
    return r.path;
  }
}

/** Inside Home Assistant's frontend: the dashboard's own connection (hass.connection). */
export class FrontendLink {
  constructor(getHass, o = {}) {
    this.getHass = getHass;
    this.o = Object.assign({ log: () => {}, onState: () => {} }, o);
    this.unsub = null;
    this.state = "closed";
  }

  async start(hello, onRequest) {
    this.hello = hello;
    this.onRequest = onRequest;
    await this._subscribe();
  }

  async _subscribe() {
    const hass = this.getHass();
    this.o.onState((this.state = "connecting"));
    try {
      this.unsub = await hass.connection.subscribeMessage(async (r) => {
        if (!r || r.type !== "request") return;
        const out = await this.onRequest(r.action, r.params || {});
        await this.getHass().connection.sendMessagePromise({
          type: "camalert/browser/reply", request_id: r.id, code: out.code, body: out.body,
        });
      }, Object.assign({ type: "camalert/browser/connect" }, this.hello()), { resubscribe: true });
      this.o.onState((this.state = "connected"));
    } catch (e) {
      this.o.log(`Home Assistant: ${e.message || e.code}`, "error");
      this.o.onState((this.state = "closed"));
    }
  }

  async stop() {
    if (this.unsub) await this.unsub();
    this.unsub = null;
    this.o.onState((this.state = "closed"));
  }

  async restart() {
    await this.stop();
    await this._subscribe();
  }

  async sign(path, expires = 86400) {
    const r = await this.getHass().connection.sendMessagePromise({ type: "auth/sign_path", path, expires });
    return r.path;
  }
}
