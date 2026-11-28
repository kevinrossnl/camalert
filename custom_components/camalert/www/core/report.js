// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
//
// The problem report of the browser player (#132), the same as camalert_core.report: status, settings without
// secrets and the last log lines, scrubbed of passwords, tokens, e-mail addresses, public IP addresses and non-local
// host names, plus a pre-filled GitHub issue link short enough for a QR code. Constants: DATA.report.
import { DATA } from "./generated.js";

const R = DATA.report;
const EMAIL = /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g;
const IPV4 = /(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?![\d.])/g;
const URL_HOST = /(\b[a-z][a-z0-9+.-]*:\/\/(?:\*\*\*(?::\*\*\*)?@)?)(\[[0-9a-f:]+\]|[^/\s:?#\][]+)/gi;
const WEBHOOK = /(\/api\/webhook\/)[A-Za-z0-9_-]+/gi;
const ERROR = /\b(error|failed|traceback|exception)\b/i;
const LOCAL_SUFFIX = R.local_suffixes;
// obs.log.redact (the same patterns as the Python core)
const REDACT = [
  [/(\b[a-z][a-z0-9+.-]*:\/\/)[^/\s:@]*:[^/\s@]*@/gi, "$1***:***@"],
  [/(\b[a-z][a-z0-9+.-]*:\/\/)[^/\s:@]+@/gi, "$1***@"],
  [/([?&](?:token|pwd|pass|password|passwd|usr|user|key|apikey|api_key|access_token|auth|secret)=)[^&\s"']*/gi, "$1***"],
  [/(\bauthorization\s*[:=]\s*)(?:bearer\s+|basic\s+)?[^\s,;"']+/gi, "$1***"],
  [/("(?:token|password|pwd|access_token|api_key|secret)"\s*:\s*")[^"]*(")/gi, "$1***$2"],
  [/(<(?:\w+:)?(?:Password|Nonce|Username)[^>]*>)[^<]*/gi, "$1***"],
  [/\b((?:password|passwd|token|pwd|secret)\s*[=:]\s*)[^\s&,;|"']+/gi, "$1***"],
];

/** The local network (camalert_core.access.LAN_NETWORKS), IPv4 and the usual IPv6 ranges. */
export function lanAddress(text) {
  const h = String(text || "").toLowerCase();
  const m = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(h);
  if (m) {
    const [a, b] = [Number(m[1]), Number(m[2])];
    if (m.slice(1).some((x) => Number(x) > 255)) return false;
    return a === 10 || a === 127 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168)
      || (a === 169 && b === 254) || (a === 100 && b >= 64 && b <= 127);
  }
  if (h.includes(":")) return h === "::1" || /^f[cd][0-9a-f]{2}:/.test(h) || /^fe[89ab][0-9a-f]:/.test(h);
  return false;
}

function hostOk(host) {
  const h = host.replace(/^\[|\]$/g, "").toLowerCase();
  if (lanAddress(h)) return true;
  if (h.includes(":")) return false; // an IPv6 address outside the local network
  if (!h.includes(".")) return true;
  return LOCAL_SUFFIX.some((s) => h.endsWith(s));
}

export function redact(text) {
  let t = text == null ? "" : String(text);
  for (const [rx, rep] of REDACT) t = t.replace(rx, rep);
  return t;
}

export function scrub(text) {
  let t = redact(text);
  t = t.replace(WEBHOOK, "$1***");
  t = t.replace(EMAIL, "<e-mail>");
  t = t.replace(URL_HOST, (all, pre, host) => pre + (hostOk(host) ? host : "<host>"));
  return t.replace(IPV4, (all, ip) => (ip.split(".").some((p) => Number(p) > 255) ? ip : lanAddress(ip) ? ip : "<public-ip>"));
}

function scrubValue(v) {
  if (typeof v === "string") return scrub(v);
  if (Array.isArray(v)) return v.map(scrubValue);
  if (v && typeof v === "object") return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, scrubValue(x)]));
  return v;
}

export function settingsPart(settings) {
  const out = {};
  for (const k of Object.keys(settings || {}).sort()) if (!R.secret_ids.includes(k)) out[k] = scrubValue(settings[k]);
  return out;
}

function shortId(node) {
  const s = [...String(node ?? "")];
  return s.length > 6 ? s.slice(0, 4).join("") + "…" : s.join("");
}

export function build(status, settings, log, extra, now = Date.now() / 1000) {
  const st = {};
  for (const [k, v] of Object.entries(status || {})) if (!R.status_dropped.includes(k) && k !== "result") st[k] = v;
  if ("id" in st) st.id = shortId(st.id);
  const lines = (log || []).map(scrub).slice(-R.log_lines);
  const errors = lines.filter((x) => ERROR.test(x)).slice(-R.error_lines);
  return {
    report: R.version,
    created: new Date(Math.floor(now) * 1000).toISOString().replace(/\.\d{3}Z$/, "Z"),
    camalert: (status || {}).version ?? "",
    platform: (status || {}).platform ?? "",
    player: scrubValue({ ...(extra || {}) }),
    status: scrubValue(st),
    settings: settingsPart(settings),
    errors,
    log: lines,
  };
}

export function playerVersion(report) {
  const p = report.player || {};
  const s = ["model", "image", "os", "kodi", "android", "browser"].filter((k) => p[k]).map((k) => String(p[k])).join(", ");
  return [...s].slice(0, 120).join("");
}

function pyStr(v) {
  if (v === true) return "True";
  if (v === false) return "False";
  if (v === null || v === undefined) return "None";
  return String(v);
}

export function summary(report) {
  const st = report.status || {};
  const label = R.player_labels[report.platform] || report.platform || "?";
  const out = [`CamAlert ${report.camalert || "?"} on ${label}`];
  const pv = playerVersion(report);
  if (pv) out.push(pv);
  const state = [];
  for (const k of ["go2rtc", "mqtt", "home_assistant", "protect", "screen"]) {
    const v = st[k];
    if (v === undefined || v === null || v === "") continue;
    state.push(`${k}: ${v && typeof v === "object" ? JSON.stringify(v) : pyStr(v)}`);
  }
  if (state.length) out.push(state.join(", "));
  const errors = report.errors || [];
  if (errors.length) out.push("Last error: " + errors[errors.length - 1].slice(0, 160));
  return out;
}

function quote(s) {
  let out = "";
  for (const b of new TextEncoder().encode(s)) {
    const c = String.fromCharCode(b);
    out += b < 128 && /[A-Za-z0-9\-._~]/.test(c) ? c : "%" + b.toString(16).toUpperCase().padStart(2, "0");
  }
  return out;
}

export function issueUrl(report) {
  const pv = playerVersion(report);
  const fields = [["template", "bug_report.yml"], ["player", R.player_labels[report.platform] || "Other / not sure"],
    ["camalert_version", String(report.camalert || "")], ["player_version", pv]];
  let what = summary(report).slice(1).filter((x) => x !== pv).join("\n");
  const make = (w) => R.issues_url + "?" + [...fields, ...(w ? [["logs", w]] : [])]
    .filter(([, v]) => v).map(([k, v]) => `${k}=${quote(v)}`).join("&");
  let url = make(what);
  while (new TextEncoder().encode(url).length > R.url_max && what) {
    what = what.slice(0, Math.max(0, what.length - Math.max(10, Math.floor((url.length - R.url_max) / 3)))).trimEnd();
    url = make(what);
  }
  return url;
}

/** The whole report as text: the summary, then the JSON. */
export function text(report) {
  return summary(report).join("\n") + "\n\n" + JSON.stringify(report, null, 2) + "\n";
}
