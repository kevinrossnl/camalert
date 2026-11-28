// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
//
// One browser player (#92, #127): settings store + controller + view + link to Home Assistant. The web page, the
// dashboard module and the extension build one of these; only the store backend, the view and the link differ.
import { handle } from "./api.js";
import { Controller } from "./controller.js";
import { DATA } from "./generated.js";
import { overviewCameras, streamInfo, titleFor, parseTitles } from "./pictures.js";

const LOG_MAX = 500;

export class Player {
  /**
   * @param {object} o  store (Store), link (HaSocket | FrontendLink), haUrl (http(s)://host:port of Home Assistant),
   *                    token: async () => access token (for the go2rtc view), fetch, view (set later with setView),
   *                    clock
   */
  constructor(o) {
    this.o = Object.assign({ fetch: (...a) => globalThis.fetch(...a) }, o);
    this.store = o.store;
    this.link = o.link;
    this.lines = [];
    this.view = null;
    this.controller = new Controller(() => this.store.settings(), {
      window: (x) => this.view && this.view.window(x),
      mosaic: (c, s) => this.view && this.view.mosaic(c, s),
      notification: (x) => this.view && this.view.notification(x),
      hide: () => this.view && this.view.hide(),
      chime: () => this.view && this.view.chime(),
      toast: (c) => this.view && this.view.toast(c),
    }, o.clock);
    this.store.onChange((keys) => {
      // new hello for Home Assistant: after the answer to the request that changed it has gone out
      if (keys.includes("server") || keys.includes("name")) setTimeout(() => this.link.restart(), 500);
      if (this.view && this.view.settingsChanged) this.view.settingsChanged(keys);
    });
  }

  setView(view) {
    this.view = view;
  }

  start() {
    this.log(`CamAlert ${DATA.version} (browser) started`);
    this.link.start(() => this.hello(), (action, params) => this.request(action, params));
  }

  stop() {
    this.link.stop();
    this.controller.hide();
  }

  hello() {
    return { browser_id: this.store.id, name: this.store.name || "", version: DATA.version,
             server: this.store.settings().server || "" };
  }

  request(action, params) {
    return handle(this, action, params);
  }

  // --- what api.handle() needs ---------------------------------------------------------------------------------
  node() {
    return [this.store.id, this.store.name || `CamAlert browser ${this.store.id.slice(-4)}`];
  }

  settings() {
    return this.store.settings();
  }

  set(values) {
    return this.store.set(values);
  }

  configured() {
    return !!this.store.settings().server;
  }

  events() {
    return this.controller.events.slice();
  }

  log(message, level = "normal") {
    const t = new Date().toISOString().replace("T", " ").slice(0, 19);
    this.lines.push(`${t} ${level === "error" ? "ERROR" : "INFO "} ${message}`);
    if (this.lines.length > LOG_MAX) this.lines.splice(0, this.lines.length - LOG_MAX);
  }

  logTail(n) {
    return this.lines.slice(-n);
  }

  // --- go2rtc through Home Assistant -----------------------------------------------------------------------------
  /** Base URL of Home Assistant's go2rtc view for this player. */
  base() {
    return `${this.o.haUrl.replace(/\/$/, "")}/api/camalert/go2rtc/${this.store.id}`;
  }

  async authFetch(url, opts = {}) {
    const token = await this.o.token();
    const headers = Object.assign({}, opts.headers || {}, token ? { Authorization: `Bearer ${token}` } : {});
    return this.o.fetch(url, Object.assign({}, opts, { headers }));
  }

  async streamInfo() {
    if (!this.configured()) return { names: [], composites: new Set(), talks: {} };
    const r = await this.authFetch(`${this.base()}/api/streams`);
    if (!r.ok) throw new Error(`go2rtc: HTTP ${r.status}`);
    const info = streamInfo(await r.json(), this.store.settings().ready_cameras);
    this._info = { at: Date.now(), info };
    return info;
  }

  /** The talk-back stream of a camera (#98: "<camera>_talk" in go2rtc), or null. Uses a list at most 60 s old. */
  async talkStream(cam) {
    try {
      const fresh = this._info && Date.now() - this._info.at < 60000 ? this._info.info : await this.streamInfo();
      return (fresh.talks || {})[cam] || null;
    } catch (e) {
      return null;
    }
  }

  /** [{name, title, snapshot}] like the other players' /camalert/cameras. */
  async cameras() {
    const titles = parseTitles(this.store.settings().titles);
    const info = await this.streamInfo();
    return info.names.map((name) => ({ name, title: titleFor(name, titles), snapshot: true }));
  }

  /** The cameras of a mosaic without an explicit list (#125: no composite streams). */
  async overview() {
    return overviewCameras(await this.streamInfo());
  }

  title(name) {
    return titleFor(name, parseTitles(this.store.settings().titles));
  }
}
