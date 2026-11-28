// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
//
// The extension's alert window (#127): asks the service worker what to show and draws it with the shared DomView.
import { DomView } from "./core/ui.js";
import { ext } from "./ext.js";

const ask = (msg) => ext.runtime.sendMessage(Object.assign({ target: "background" }, msg));

async function main() {
  const r = await ask({ type: "screen" });
  if (!r) return window.close();
  const token = r.token;
  const shim = {
    settings: () => r.settings,
    configured: () => !!r.settings.server,
    title: (c) => r.titles[c] || c,
    base: () => r.base,
    src: (c) => { // the go2rtc server of a camera (#131)
      const at = (r.sources || {})[c] || { base: r.base, streams: {} };
      return { base: at.base, stream: (n) => at.streams[n] || n };
    },
    log: () => {},
    authFetch: (url, opts = {}) => fetch(url, Object.assign({}, opts, {
      headers: Object.assign({}, opts.headers || {}, token ? { Authorization: `Bearer ${token}` } : {}) })),
    talkStream: async () => null,
    overview: async () => r.spec.cams || [],
    controller: { hide: () => ask({ type: "hide" }) },
  };
  const link = { direct: !!r.direct, sign: async (path) => {
    const s = await ask({ type: "sign", path });
    if (!s || s.error) throw new Error((s && s.error) || "sign failed");
    return s.path;
  } };
  const view = new DomView(document.body.appendChild(document.createElement("camalert-layer")), shim, {
    link, haUrl: r.haUrl, fill: true, soundAllowed: () => true,
  });
  const spec = r.spec;
  if (spec.kind === "mosaic") view.mosaic(spec.cams, spec.seconds);
  else if (spec.kind === "notification") view.window({ cams: [spec.cam], mode: "photo", priority: spec.priority,
                                                       label: spec.label });
  else view.window(spec);
  document.title = spec.cams ? spec.cams.map((c) => shim.title(c)).join(", ") : "CamAlert";
  globalThis.camalert = { view, spec };
}

main();
