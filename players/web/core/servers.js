// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
//
// Several go2rtc servers in a browser player (#15, #131), ported from core/camalert_core/servers.py: the setting
// `server` is the main server (s1), `more_servers` lists the others, comma or newline separated, each
// `[prefix=]address`. Cameras of the main server keep their names; a server with a prefix shows its cameras as
// `<prefix>.<stream>`; a server without one keeps the stream names unless an earlier server already has that name,
// then the camera becomes `s<n>.<stream>`.
export const PREFIX = /^[a-z0-9_-]{1,16}$/;
export const SEP = ".";

/** "192.168.1.10", "host:1984" or "http://host:1984/" -> "http://host:1984", else null (urls.normalize_server). */
export function normalizeServer(text) {
  let s = String(text || "").trim().replace(/\/+$/, "");
  if (!s) return null;
  if (!s.includes("://")) {
    if ((s.match(/:/g) || []).length > 1 && !s.startsWith("[")) s = `[${s}]`; // bare IPv6 literal
    s = "http://" + s;
  }
  let u;
  try {
    u = new URL(s);
  } catch (e) {
    return null;
  }
  if (!["http:", "https:"].includes(u.protocol) || !u.hostname || u.username || u.password) return null;
  return `${u.protocol}//${u.host}`;
}

/** {entries: [[prefix | null, url]], problems: [text]} from the `more_servers` text. */
export function parseMore(text) {
  const entries = [];
  const problems = [];
  for (let part of String(text || "").split(/[,\n;]+/)) {
    part = part.trim();
    if (!part) continue;
    let prefix = null;
    const i = part.indexOf("=");
    if (i >= 0 && !part.slice(0, i).includes("://")) {
      prefix = part.slice(0, i).trim().toLowerCase();
      part = part.slice(i + 1).trim();
      if (!PREFIX.test(prefix) || /^s\d+$/.test(prefix)) {
        problems.push(`${prefix}=${part}`);
        continue;
      }
    }
    const url = normalizeServer(part);
    if (!url) {
      problems.push(part);
      continue;
    }
    entries.push([prefix, url]);
  }
  return { entries, problems };
}

/** [{id: "s1", url, prefix: null}, ...]: the main server (when valid) and the valid `more_servers` entries; the
 *  same address twice counts once, a prefix used twice keeps the first server. */
export function serverList(main, moreText = "") {
  const out = [];
  const seen = new Set();
  const prefixes = new Set();
  const m = normalizeServer(main);
  if (m) {
    out.push({ id: "s1", url: m, prefix: null });
    seen.add(m);
  }
  for (const [prefix, url] of parseMore(moreText).entries) {
    if (seen.has(url) || (prefix && prefixes.has(prefix))) continue;
    seen.add(url);
    if (prefix) prefixes.add(prefix);
    out.push({ id: `s${out.length + 1}`, url, prefix });
  }
  return out;
}

/** perServer: [[server, [stream names], Set of composite streams]] in server order (a server that did not answer is
 *  left out). -> {names (sorted), composites (Set of camera names), mapping: {camera: [server url, stream]}} */
export function combine(perServer) {
  const names = [];
  const composites = new Set();
  const mapping = {};
  for (const [srv, streams, comp] of perServer) {
    for (const stream of streams) {
      let name;
      if (srv.prefix) name = srv.prefix + SEP + stream;
      else if (stream in mapping) name = srv.id + SEP + stream;
      else name = stream;
      if (name in mapping) continue; // s2.x may exist as a real stream name: keep the first
      mapping[name] = [srv.url, stream];
      names.push(name);
      if (comp && comp.has(stream)) composites.add(name);
    }
  }
  return { names: names.sort(), composites, mapping };
}

/** [server, stream] for a camera name; mapping from the last camera list (an entry for a server that is no longer
 *  configured is ignored). Without a list: `<prefix or sN>.<rest>` goes to that server, everything else to s1. */
export function resolve(name, servers, mapping = null) {
  if (!servers.length) return [null, name];
  if (mapping && name in mapping) {
    const srv = servers.find((s) => s.url === mapping[name][0]);
    if (srv) return [srv, mapping[name][1]];
  }
  const i = String(name || "").indexOf(SEP);
  if (i > 0) {
    const head = name.slice(0, i);
    const rest = name.slice(i + 1);
    for (const srv of servers) if (rest && srv.id !== "s1" && (head === srv.prefix || head === srv.id)) return [srv, rest];
  }
  return [servers[0], name];
}
