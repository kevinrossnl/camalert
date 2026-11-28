// Settings store of the browser player (#92, #127).
import assert from "node:assert/strict";
import { test } from "node:test";
import { DATA } from "../../core/generated.js";
import { clean, defaults, localStorageBackend, Store } from "../../core/store.js";

function memory() {
  const m = new Map();
  return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, v), m };
}

test("defaults come from the shared schema", () => {
  const d = defaults();
  assert.equal(d.duration, DATA.settings.duration.default);
  assert.equal(d.position, DATA.settings.position.default);
  assert.equal(d.server, "");
});

test("clean() checks choices, numbers and booleans", () => {
  assert.deepEqual(clean({ position: "nowhere", size: "large", duration: "9999", dnd: "1", bogus: 1, server: " x " }),
                   { size: "large", duration: DATA.settings.duration.max, dnd: true, server: "x" });
});

test("the id is kept, changes are saved and announced", () => {
  const mem = memory();
  const a = new Store(localStorageBackend("k", mem));
  assert.match(a.id, /^web[0-9a-f]{12}$/);
  const seen = [];
  a.onChange((keys) => seen.push(keys));
  assert.deepEqual(a.set({ size: "small", position: "top_right" }), ["size"]);
  assert.deepEqual(a.set({ size: "small" }), []);
  a.setName("  Hall  ");
  const b = new Store(localStorageBackend("k", mem));
  assert.equal(b.id, a.id);
  assert.equal(b.name, "Hall");
  assert.equal(b.settings().size, "small");
  assert.deepEqual(seen, [["size"], ["name"]]);
  const broken = { getItem: () => "{not json", setItem: () => { throw new Error("full"); } };
  assert.ok(new Store(localStorageBackend("k", broken)).id);
});
