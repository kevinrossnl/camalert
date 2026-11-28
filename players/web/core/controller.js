// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
//
// What the browser player shows and for how long (#92, #127): the same decisions as the other players' controllers
// (priority, Do not disturb, extend the same camera, sec 0 = until hide), without any DOM. The view does the drawing:
//   view.window({cams, mode, priority, label, seconds})   photo window / live window / several cameras
//   view.mosaic(cams|null, seconds)                         full-screen grid (null = the default camera list)
//   view.notification({cam, priority, label, seconds})      small toast with a picture
//   view.hide()   view.chime()   view.toast(code)
import { DATA } from "./generated.js";

const EVENTS_MAX = 50;

export class Controller {
  constructor(settings, view, clock = {
    setTimeout: (f, ms) => setTimeout(f, ms), clearTimeout: (t) => clearTimeout(t), now: () => Date.now(),
  }) {
    this.settings = settings; // () => current settings
    this.view = view;
    this.clock = clock;
    this.timer = null;
    this.screen = "none";
    this.current = null; // {cam, mode, priority}
    this.events = [];
    this.lastCaller = null;
  }

  _arm(seconds) {
    if (this.timer !== null) this.clock.clearTimeout(this.timer);
    this.timer = this.clock.setTimeout(() => this.hide(), seconds * 1000);
  }

  _event(cam, priority, source, label, action) {
    this.events.unshift({
      time: Math.floor(this.clock.now() / 1000), camera: cam, priority, source, label: label || null, result: action,
    });
    this.events.length = Math.min(this.events.length, EVENTS_MAX);
  }

  _chime(priority, source) {
    const c = this.settings().chime;
    if (source === "test" || c === "off") return;
    if (c === "all" || (c === "high" && priority !== "normal")) this.view.chime();
  }

  /** "show", "extend", "ignore" (Do not disturb) or "error" (no camera). */
  show(cam, seconds, mode, priority, source = "ha", label = null) {
    const s = this.settings();
    cam = cam || s.camera;
    priority = priority || "normal";
    mode = mode || "photo";
    seconds = seconds || s.duration || DATA.settings.duration.default;
    this.lastCaller = [this.clock.now() / 1000, source];
    if (!cam) {
      this._event(null, priority, source, label, "error");
      return "error";
    }
    if (s.dnd && priority === "normal") {
      this._event(cam, priority, source, label, "ignore");
      return "ignore";
    }
    const cams = cam.split(",");
    if (mode === "notify") {
      this.view.notification({ cam: cams[0], priority, label, seconds });
      this._chime(priority, source);
      this._event(cam, priority, source, label, "show");
      return "show";
    }
    const screen = mode === "live" ? "live" : cams.length > 1 || mode === "strip" ? "strip" : "photo";
    if (this.current && this.current.cam === cam && this.screen === screen && this.screen !== "mosaic") {
      this._arm(seconds);
      if (priority !== this.current.priority && DATA.priorities.indexOf(priority) > DATA.priorities.indexOf(this.current.priority)) {
        this.current.priority = priority;
        this.view.window({ cams, mode, priority, label, seconds });
      }
      this._event(cam, priority, source, label, "extend");
      return "extend";
    }
    this.view.window({ cams, mode, priority, label, seconds });
    this.current = { cam, mode, priority };
    this.screen = screen;
    this._arm(seconds);
    this._chime(priority, source);
    this._event(cam, priority, source, label, "show");
    return "show";
  }

  mosaic(cam, seconds) {
    this.view.mosaic(cam ? cam.split(",") : null, seconds);
    this.current = { cam: cam || "*", mode: "mosaic", priority: "normal" };
    this.screen = "mosaic";
    this._arm(seconds);
    return "show";
  }

  hide() {
    if (this.timer !== null) this.clock.clearTimeout(this.timer);
    this.timer = null;
    this.current = null;
    this.screen = "none";
    this.view.hide();
  }

  notice(code) {
    this.view.toast(code);
  }

  status() {
    const c = this.current;
    return {
      window: c && ["photo", "strip"].includes(this.screen) ? c.cam : null,
      live: c && this.screen === "live" ? c.cam : null,
      paused: false,
      screen: this.screen,
      dnd: !!this.settings().dnd,
    };
  }
}
