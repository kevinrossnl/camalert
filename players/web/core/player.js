// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
//
// One browser player (#92, #127): settings store + controller + view + link to Home Assistant. The web page, the
// dashboard module and the extension build one of these; only the store backend, the view and the link differ.
import { handle } from "./api.js";
import { Controller } from "./controller.js";
import { DATA } from "./generated.js";
import { overviewCameras, parseReady, streamInfo, titleFor, parseTitles } from "./pictures.js";
import { combine, resolve, serverList } from "./servers.js";

const LOG_MAX = 500;

export class Player {
  /**
   * @param {object} o  store (Store), link (HaSocket | FrontendLink), haUrl (http(s)://host:port of Home Assistant),
   *                    token: async () => access token (for the go2rtc view), fetch, view (set later with setView),
   *                    clock, direct (true: pictures straight from go2rtc, without Home Assistant: MQTT, #131)
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
      if (["server", "more_servers", "name"].some((k) => keys.includes(k))) setTimeout(() => this.link.restart(), 500);
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
    const out = { browser_id: this.store.id, name: this.store.name || "", version: DATA.version,
                  server: this.store.settings().server || "" };
    // #131: the other go2rtc servers in the order of their ids (s2, s3, ...); Home Assistant's view forwards
    // /api/camalert/go2rtc/<id>/s<n>/... to the n-th. Only sent when there are any (older integrations refuse it).
    const more = this.servers().slice(1).map((x) => x.url);
    if (more.length) out.more_servers = more.join(",");
    return out;
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

  // --- go2rtc through Home Assistant (or straight, with MQTT) ---------------------------------------------------
  /** The go2rtc servers (#15, #131): [{id, url, prefix}], the main one first. */
  servers() {
    const s = this.store.settings();
    return serverList(s.server, s.more_servers);
  }

  /** Base URL of the main go2rtc server: Home Assistant's go2rtc view for this player, or go2rtc itself. */
  base() {
    return this._base(this.servers()[0] || null);
  }

  _base(srv) {
    if (this.o.direct) return srv ? srv.url : "";
    const root = `${this.o.haUrl.replace(/\/$/, "")}/api/camalert/go2rtc/${this.store.id}`;
    return !srv || srv.id === "s1" ? root : `${root}/${srv.id}`;
  }

  /** {base, stream(name)} of a camera: the base URL of its go2rtc server and its stream name there. */
  src(cam) {
    const servers = this.servers();
    const mapping = this._info ? this._info.mapping : null;
    const [srv] = resolve(cam, servers, mapping);
    return { base: this._base(srv), stream: (n) => resolve(n, servers, mapping)[1] };
  }

  async authFetch(url, opts = {}) {
    const token = this.o.direct ? null : await this.o.token();
    const headers = Object.assign({}, opts.headers || {}, token ? { Authorization: `Bearer ${token}` } : {});
    return this.o.fetch(url, Object.assign({}, opts, { headers }));
  }

  async _streams(srv) {
    const r = await this.authFetch(`${this._base(srv)}/api/streams`);
    if (!r.ok) throw new Error(`go2rtc: HTTP ${r.status}`);
    return r.json();
  }

  async streamInfo() {
    if (!this.configured()) return { names: [], composites: new Set(), talks: {} };
    const ready = this.store.settings().ready_cameras;
    const servers = this.servers();
    if (servers.length <= 1) {
      const info = streamInfo(await this._streams(servers[0]), ready);
      this._info = { at: Date.now(), info, mapping: null };
      return info;
    }
    // several servers (#131): every server at once; one that does not answer is left out, all down is an error
    const got = await Promise.allSettled(servers.map((srv) => this._streams(srv)));
    const per = [];
    got.forEach((g, i) => {
      if (g.status === "fulfilled") per.push([servers[i], streamInfo(g.value, "")]);
      else this.log(`go2rtc ${servers[i].url}: ${g.reason && g.reason.message}`, "error");
    });
    if (!per.length) throw new Error("go2rtc: no server reachable");
    const all = combine(per.map(([srv, x]) => [srv, x.names, x.composites]));
    const helpers = new Set(Object.entries(parseReady(ready)).filter(([c, st]) => st !== c).map(([, st]) => st));
    const names = all.names.filter((n) => !helpers.has(n));
    const talks = {};
    for (const [srv, x] of per) {
      for (const [stream, talk] of Object.entries(x.talks)) {
        const name = Object.keys(all.mapping).find((k) => all.mapping[k][0] === srv.url && all.mapping[k][1] === stream);
        if (name) talks[name] = talk;
      }
    }
    const info = { names, composites: new Set([...all.composites].filter((n) => names.includes(n))), talks };
    this._info = { at: Date.now(), info, mapping: all.mapping };
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
