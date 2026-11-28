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
