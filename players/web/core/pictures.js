// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
//
// Cameras and pictures of the browser player (#92, #127), ported from core/camalert_core (cameras.py, urls.py,
// warm.py): camera names from go2rtc's /api/streams without helper streams (#117) and, for overviews, without
// composite streams (#125); titles; and the picture sources in the players' order where a browser can follow it:
// the warm MJPEG feed of a ready camera (#111), go2rtc's cached frame (#110), a new frame. Every go2rtc request goes
// through Home Assistant's view /api/camalert/go2rtc/<browser id>/... (no CORS or mixed content).
const NAME = /^[A-Za-z0-9_.-]+$/;
const LOOPBACK = ["127.0.0.1", "localhost", "::1", "[::1]"];

/** "front_door" -> "Front door" */
export function displayName(stream) {
  const s = String(stream || "").replace(/[_-]/g, " ").trim();
  return s.slice(0, 1).toUpperCase() + s.slice(1);
}

/** "front_door=Front door|garden=Garden" -> {front_door: "Front door", garden: "Garden"} */
export function parseTitles(text) {
  const out = {};
  for (const part of String(text || "").split("|")) {
    const i = part.indexOf("=");
    if (i < 0) continue;
    const k = part.slice(0, i).trim();
    const v = part.slice(i + 1).trim();
    if (NAME.test(k) && v) out[k] = v;
  }
  return out;
}

export function titleFor(name, titles) {
  return (titles || {})[name] || displayName(name);
}

/** Keep cameras ready (#111): "front_door=front_door_jpeg|garden" -> {front_door: "front_door_jpeg", garden: "garden"} */
export function parseReady(text) {
  const out = {};
  for (let part of String(text || "").replace(/,/g, "|").split("|")) {
    part = part.trim();
    if (!part) continue;
    const i = part.indexOf("=");
    const cam = (i < 0 ? part : part.slice(0, i)).trim();
    const stream = (i < 0 ? cam : part.slice(i + 1)).trim();
    if (cam && stream) out[cam] = stream;
  }
  return out;
}

function sourceStream(url) {
  if (typeof url !== "string") return null;
  if (url.startsWith("ffmpeg:")) return url.slice(7).split("#", 1)[0];
  let u;
  try {
    u = new URL(url);
  } catch (e) {
    return null;
  }
  if (!["rtsp:", "rtsps:"].includes(u.protocol) || !LOOPBACK.includes(u.hostname)) return null;
  const source = u.searchParams.get("source") || "";
  if (source.startsWith("ffmpeg:")) return source.slice(7).split("#", 1)[0];
  return decodeURIComponent(u.pathname.replace(/^\/+/, "")) || null;
}

function producers(info) {
  const p = info && typeof info === "object" ? info.producers : null;
  return Array.isArray(p) && p.length ? p : null;
}

/** True for a go2rtc producer that only takes audio towards a camera (exec:...#backchannel=1, #98). */
export function isBackchannel(url) {
  return typeof url === "string" && url.includes("#backchannel=1");
}

/** Helper streams (#117): every source transcodes another stream of the same go2rtc; and talk-back streams (#98). */
export function derivedStreams(data) {
  const out = new Set();
  if (!data || typeof data !== "object") return out;
  for (const [name, info] of Object.entries(data)) {
    const p = producers(info);
    if (!p) continue;
    if (p.every((x) => isBackchannel(x && x.url))) {
      out.add(name);
      continue;
    }
    const bases = p.map((x) => sourceStream(x && x.url));
    if (bases.every((b) => b !== null && b !== name && b in data)) out.add(name);
  }
  return out;
}

function inputs(url) {
  if (typeof url !== "string" || !(url.startsWith("exec:") || url.startsWith("ffmpeg:"))) return [];
  const parts = url.split(/\s+/);
  const out = [];
  for (let i = 0; i < parts.length - 1; i++) if (parts[i] === "-i") out.push(parts[i + 1].replace(/^['"]|['"]$/g, ""));
  return out;
}

/** Composite streams (#125): an own mosaic of two or more other streams of the same go2rtc. */
export function compositeStreams(data) {
  const out = new Set();
  if (!data || typeof data !== "object") return out;
  for (const [name, info] of Object.entries(data)) {
    const p = producers(info);
    if (!p) continue;
    let bases = [];
    for (const x of p) {
      const ins = inputs(x && x.url);
      if (!ins.length) {
        bases = null;
        break;
      }
      bases.push(...ins.map(sourceStream));
    }
    if (bases && bases.length && bases.every((b) => b !== null && b !== name && b in data) && new Set(bases).size >= 2) {
      out.add(name);
    }
  }
  return out;
}

/** {camera: talk stream} (#98, urls.talk_streams): "<camera>_talk" whose every source is a backchannel. */
export function talkStreams(data) {
  const out = {};
  if (!data || typeof data !== "object" || Array.isArray(data)) return out;
  for (const [name, info] of Object.entries(data)) {
    if (!name.endsWith("_talk")) continue;
    const base = name.slice(0, -5);
    const p = producers(info);
    if (base && base in data && p && p.every((x) => isBackchannel(x && x.url))) out[base] = name;
  }
  return out;
}

/** {names, composites, talks} from a go2rtc /api/streams answer: camera names sorted, helpers (#117 and Keep cameras
 *  ready helpers) left out. */
export function streamInfo(data, readyText = "") {
  if (!data || typeof data !== "object" || Array.isArray(data)) return { names: [], composites: new Set(), talks: {} };
  const skip = derivedStreams(data);
  for (const [cam, stream] of Object.entries(parseReady(readyText))) if (stream !== cam) skip.add(stream);
  const names = Object.keys(data).filter((k) => NAME.test(k) && !skip.has(k)).sort();
  const composites = new Set([...compositeStreams(data)].filter((n) => names.includes(n)));
  return { names, composites, talks: talkStreams(data) };
}

/** The default list of a mosaic or overview: every camera except composite streams (#125). */
export function overviewCameras(info) {
  return info.names.filter((n) => !info.composites.has(n));
}

function q(s) {
  return encodeURIComponent(s).replace(/%2C/g, ",");
}

/** URLs of one camera behind the Home Assistant view (base = https://ha.example:8123/api/camalert/go2rtc/<id>, or
 *  that plus /s<n> for another go2rtc server, #131; or go2rtc itself with MQTT, #131). stream(name) gives the go2rtc
 *  stream of a camera name (several servers: "garden.cam" -> "cam"); by default the name itself. */
export function urls(base, cam, readyText = "", stream = (n) => n) {
  const ready = parseReady(readyText)[cam];
  const src = stream(cam);
  return {
    warm: ready ? `${base}/api/stream.mjpeg?src=${q(stream(ready))}` : null,
    cached: `${base}/api/frame.jpeg?src=${q(src)}&cache=10s`,
    frame: `${base}/api/frame.jpeg?src=${q(src)}`,
    mjpeg: `${base}/api/stream.mjpeg?src=${q(src)}`,
    webrtc: `${base}/api/webrtc?src=${q(src)}`,
  };
}

/** The order in which a window asks for its pictures: warm feed first (a moving picture), else the cached frame
 *  once and new frames after it. */
export function pictureSources(base, cam, readyText = "", stream = (n) => n) {
  const u = urls(base, cam, readyText, stream);
  return u.warm ? { stream: u.warm, first: null, next: null } : { stream: null, first: u.cached, next: u.frame };
}
