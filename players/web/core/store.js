// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
//
// Settings of a browser player (#92, #127): the shared schema's defaults (generated.js), kept in localStorage (web
// page) or chrome.storage.local (extension). Never a token here: the page signs in with Home Assistant's own login,
// the extension keeps its token in chrome.storage.local apart from these settings.
import { DATA } from "./generated.js";

export function defaults() {
  const out = {};
  for (const [k, v] of Object.entries(DATA.settings)) out[k] = v.default;
  return out;
}

/** values coerced to the schema: unknown keys dropped, choices checked, numbers clamped. */
export function clean(values) {
  const out = {};
  for (const [k, v] of Object.entries(values || {})) {
    const spec = DATA.settings[k];
    if (!spec) continue;
    if (spec.choices) {
      if (spec.choices.includes(v)) out[k] = v;
    } else if (typeof spec.default === "boolean") {
      out[k] = v === true || v === "true" || v === "1" || v === 1;
    } else if (typeof spec.default === "number") {
      const n = parseInt(v, 10);
      if (Number.isFinite(n)) out[k] = Math.max(spec.min ?? n, Math.min(spec.max ?? n, n));
    } else {
      out[k] = String(v ?? "").trim();
    }
  }
  return out;
}

function randomId() {
  const b = new Uint8Array(6);
  globalThis.crypto.getRandomValues(b);
  return "web" + Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
}

/** backend: {load() -> object|null, save(object)} (synchronous; the extension loads chrome.storage first). */
export class Store {
  constructor(backend) {
    this.backend = backend;
    const raw = backend.load() || {};
    this.id = /^[a-z0-9]{6,32}$/.test(raw.id || "") ? raw.id : randomId();
    this.name = String(raw.name || "").trim();
    this.values = Object.assign(defaults(), clean(raw.settings));
    this.listeners = [];
    if (raw.id !== this.id) this._save();
  }

  _save() {
    this.backend.save({ id: this.id, name: this.name, settings: this.values });
  }

  settings() {
    return Object.assign({}, this.values);
  }

  /** Changes settings; returns the keys that changed. */
  set(values) {
    const c = clean(values);
    const changed = Object.keys(c).filter((k) => c[k] !== this.values[k]);
    if (!changed.length) return [];
    Object.assign(this.values, c);
    this._save();
    for (const f of this.listeners) f(changed);
    return changed;
  }

  setName(name) {
    this.name = String(name || "").trim().slice(0, 64);
    this._save();
    for (const f of this.listeners) f(["name"]);
  }

  onChange(f) {
    this.listeners.push(f);
  }
}

export function localStorageBackend(key = "camalert.player", storage = globalThis.localStorage) {
  return {
    load() {
      try {
        return JSON.parse(storage.getItem(key) || "null");
      } catch (e) {
        return null;
      }
    },
    save(obj) {
      try {
        storage.setItem(key, JSON.stringify(obj));
      } catch (e) {
        /* private mode or storage full: the player keeps working with the values in memory */
      }
    },
  };
}
