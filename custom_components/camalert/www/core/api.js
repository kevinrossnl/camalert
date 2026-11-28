// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
//
// The CamAlert API of the browser player (#92, #127): the same actions, parameters and answers as the HTTP API of
// the other players (core/camalert_core/api.py), delivered over the Home Assistant WebSocket instead of HTTP.
// handle() never throws: it answers {code, body} like an HTTP status and JSON body.
import { DATA } from "./generated.js";

const NAME = /^[A-Za-z0-9_.-]+$/;
const TRUE = ["1", "true", "on", "yes"];
const FALSE = ["0", "false", "off", "no"];
const LAN = [
  [[10, 0, 0, 0], 8], [[172, 16, 0, 0], 12], [[192, 168, 0, 0], 16], [[100, 64, 0, 0], 10],
  [[127, 0, 0, 0], 8], [[169, 254, 0, 0], 16],
];
const LOCAL_SUFFIXES = [".local", ".lan", ".home", ".home.arpa", ".internal"];

export class Invalid extends Error {}

/** null (= default) or "a,b" with only valid camera names; Invalid otherwise. */
export function camerasParam(value, many = true) {
  if (value === undefined || value === null || !String(value).trim()) return null;
  const names = String(value).trim().split(/[,\s]+/).filter(Boolean);
  if (!names.length || names.some((n) => !NAME.test(n)) || (!many && names.length > 1)) {
    throw new Invalid("invalid camera name");
  }
  return names.join(",");
}

export function choiceParam(args, key, allowed) {
  const v = args[key];
  if (v === undefined || v === null || v === "") return null;
  if (!allowed.includes(v)) throw new Invalid(`invalid ${key}`);
  return v;
}

export function boolParam(value, name = "on") {
  const t = String(value).trim().toLowerCase();
  if (TRUE.includes(t)) return true;
  if (FALSE.includes(t)) return false;
  throw new Invalid(`${name} must be 1 or 0`);
}

export function clampSeconds(value, dflt = 30) {
  const s = typeof value === "number" ? value : parseInt(String(value).trim(), 10);
  if (!Number.isFinite(s) || (typeof value !== "number" && !/^\s*[+-]?\d+\s*$/.test(String(value)))) return dflt;
  return Math.max(DATA.minSeconds, Math.min(DATA.maxSeconds, Math.trunc(s)));
}

/** True when a request gives a duration (0 counts: until hide, #81). */
export function hasSeconds(value) {
  return value !== undefined && value !== null && value !== false && String(value).trim() !== "";
}

/** Duration of a show request: 0 = until hide (at most holdSeconds), otherwise clampSeconds. */
export function showSeconds(value, dflt = 30) {
  if (String(value).trim() === "0") return DATA.holdSeconds;
  return clampSeconds(value, dflt);
}

function ipv4(host) {
  const m = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(host);
  if (!m) return null;
  const p = m.slice(1).map(Number);
  return p.every((x) => x <= 255) ? p : null;
}

/** True for an address in the local network: private IPv4/IPv6, or a local host name (no dots, .local, ...). */
export function localHost(host) {
  host = String(host || "").toLowerCase().replace(/^\[|\]$/g, "");
  if (!host) return false;
  const v4 = ipv4(host);
  if (v4) {
    return LAN.some(([net, bits]) => {
      const a = (v4[0] << 24 | v4[1] << 16 | v4[2] << 8 | v4[3]) >>> 0;
      const n = (net[0] << 24 | net[1] << 16 | net[2] << 8 | net[3]) >>> 0;
      const mask = bits === 0 ? 0 : (0xffffffff << (32 - bits)) >>> 0;
      return (a & mask) === (n & mask);
    });
  }
  if (host.includes(":")) return host === "::1" || /^fe[89ab]/.test(host) || /^f[cd]/.test(host);
  if (!host.includes(".")) return /^[a-z0-9-]+$/.test(host);
  return LOCAL_SUFFIXES.some((s) => host.endsWith(s));
}

/** The go2rtc address normalised ("http://host:1984", no path), or null when it is not an http(s) URL. */
export function normalizeServer(text) {
  let s = String(text || "").trim();
  if (!s) return null;
  if (!/^[a-z]+:\/\//i.test(s)) s = "http://" + s;
  let u;
  try {
    u = new URL(s);
  } catch (e) {
    return null;
  }
  if (!["http:", "https:"].includes(u.protocol) || !u.hostname || u.username || u.password) return null;
  return `${u.protocol}//${u.host}`;
}

/** Why a setup request is refused, or null (#122): a player that was never set up takes any address, a player
 *  that is set up only one in the local network. */
export function setupRefused(server, configured) {
  const s = normalizeServer(server);
  if (!s) return "invalid server";
  if (configured && !localHost(new URL(s).hostname)) return "already set up";
  return null;
}

function answer(code, body) {
  return { code, body };
}

/**
 * Handles one request. player: {settings(), set(values), controller, cameras(), events(), logTail(n), log(msg),
 * configured(), node()} (see player.js).
 */
export async function handle(player, action, params = {}) {
  const a = {};
  for (const [k, v] of Object.entries(params || {})) {
    if (v !== undefined && v !== null) a[k] = typeof v === "boolean" ? String(v) : String(v);
  }
  let source = "ha";
  try {
    if ("test" in a) {
      if (boolParam(a.test, "test")) source = "test";
      delete a.test;
    }
    const s = player.settings();
    const ctl = player.controller;
    switch (action) {
      case "status": {
        const [id, name] = player.node();
        return answer(200, Object.assign(ctl.status(), {
          result: true, version: DATA.version, id, name, platform: "browser", api_version: DATA.apiVersion,
          capabilities: DATA.capabilities, min_ha_version: DATA.minHaVersion, configured: player.configured(),
          position: s.position, size: s.size, dnd: !!s.dnd, mqtt: !!(player.link && player.link.direct),
        }));
      }
      case "show":
      case "camalert": {
        const cam = camerasParam(a.cam);
        const mode = choiceParam(a, "mode", DATA.modes.concat(["strip"]));
        const priority = choiceParam(a, "priority", DATA.priorities);
        const sec = hasSeconds(a.sec) ? showSeconds(a.sec, s.duration) : null;
        const res = ctl.show(cam, sec, mode, priority, source, a.label || null);
        player.log(`request from ${source}: camera=${cam || s.camera || "-"} priority=${priority || "normal"} ` +
          `mode=${mode || "photo"} -> ${res}`);
        return answer(200, { result: ["show", "extend"].includes(res), action: res, cam: cam || s.camera });
      }
      case "hide":
        ctl.hide();
        return answer(200, { result: true, action: "hide" });
      case "mosaic": {
        const cam = camerasParam(a.cam);
        const sec = a.sec ? clampSeconds(a.sec, DATA.mosaicSeconds) : DATA.mosaicSeconds;
        const res = ctl.mosaic(cam, sec);
        player.log(`mosaic from ${source}: cameras=${cam || "-"} -> ${res}`);
        return answer(200, { result: res === "show", action: res });
      }
      case "dnd": {
        let dnd = !!s.dnd;
        if ("on" in a) {
          dnd = boolParam(a.on);
          player.set({ dnd });
        }
        return answer(200, { result: true, action: "dnd", dnd });
      }
      case "settings": {
        const changes = {};
        for (const key of ["position", "size"]) {
          const v = choiceParam(a, key, DATA.settings[key].choices);
          if (v !== null && v !== s[key]) changes[key] = v;
        }
        if (Object.keys(changes).length) {
          player.set(changes);
          player.log(`settings from ${source}: ${Object.entries(changes).map(([k, v]) => `${k}=${v}`).join(" ")}`);
        }
        const now = player.settings();
        return answer(200, { result: true, position: now.position, size: now.size });
      }
      case "setup": {
        const why = setupRefused(a.server, player.configured());
        if (why === "already set up") return answer(409, { result: false, error: why });
        if (why) throw new Invalid(why);
        const camera = camerasParam(a.camera, false);
        const values = { server: normalizeServer(a.server) };
        if (camera) values.camera = camera;
        player.set(values);
        player.log("settings received from Home Assistant");
        ctl.notice("settings_received");
        return answer(200, { result: true });
      }
      case "cameras": {
        try {
          return answer(200, { result: true, cameras: await player.cameras() });
        } catch (e) {
          player.log(`camera list failed: ${e.message}`, "error");
          return answer(200, { result: false, error: "camera source not reachable" });
        }
      }
      case "events":
        return answer(200, { result: true, events: player.events() });
      case "log": {
        const n = /^\d+$/.test(a.lines || "") ? Math.min(parseInt(a.lines, 10), 2000) : 200;
        return answer(200, { result: true, lines: player.logTail(n) });
      }
      default:
        return answer(404, { result: false, error: "unknown action" });
    }
  } catch (e) {
    if (e instanceof Invalid) return answer(400, { result: false, error: e.message });
    player.log(`request failed: ${e && e.message}`, "error");
    return answer(500, { result: false, error: "internal error" });
  }
}
