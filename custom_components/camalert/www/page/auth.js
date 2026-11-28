// CamAlert - show IP cameras on your TV.
// Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
//
// Sign-in of the web player page (#92): Home Assistant's own login (OAuth 2 authorization code, IndieAuth), so no
// long-lived token is needed. The page is served by Home Assistant itself, so client_id is this origin. When the
// browser is already signed in to Home Assistant ("Keep me logged in"), its tokens are reused.
const KEY = "camalert.hassTokens";
const HA_KEY = "hassTokens"; // the Home Assistant frontend's own tokens (same origin)

function load(storage, key) {
  try {
    return JSON.parse(storage.getItem(key) || "null");
  } catch (e) {
    return null;
  }
}

export class HaAuth {
  constructor(origin = location.origin, storage = localStorage, fetchImpl = (...a) => fetch(...a), loc = location) {
    this.origin = origin.replace(/\/$/, "");
    this.clientId = `${this.origin}/`;
    this.storage = storage;
    this.fetch = fetchImpl;
    this.loc = loc;
  }

  _save(t) {
    const tokens = Object.assign({}, t, { expires: Date.now() + (t.expires_in || 1800) * 1000 });
    this.storage.setItem(KEY, JSON.stringify(tokens));
    return tokens;
  }

  async _token(body) {
    const r = await this.fetch(`${this.origin}/auth/token`, {
      method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams(Object.assign({ client_id: this.clientId }, body)).toString(),
    });
    if (!r.ok) throw new Error(`login refused (HTTP ${r.status})`);
    return r.json();
  }

  redirectUri() {
    return `${this.origin}${this.loc.pathname}`;
  }

  /** Sends the browser to Home Assistant's login page. */
  login() {
    const state = Math.random().toString(36).slice(2);
    sessionStorage.setItem("camalert.state", state);
    const q = new URLSearchParams({ response_type: "code", client_id: this.clientId,
                                    redirect_uri: this.redirectUri(), state });
    this.loc.assign(`${this.origin}/auth/authorize?${q}`);
  }

  /** A valid access token, or null when the user must sign in first (call login()). */
  async accessToken() {
    const params = new URLSearchParams(this.loc.search);
    if (params.get("code")) {
      const ok = params.get("state") && params.get("state") === sessionStorage.getItem("camalert.state");
      history.replaceState(null, "", this.loc.pathname);
      if (ok) {
        const t = await this._token({ grant_type: "authorization_code", code: params.get("code") });
        return this._save(t).access_token;
      }
    }
    let t = load(this.storage, KEY);
    if (!t) {
      const ha = load(this.storage, HA_KEY);
      if (ha && ha.refresh_token && ha.clientId === this.clientId) t = { refresh_token: ha.refresh_token, expires: 0 };
    }
    if (!t || !t.refresh_token) return null;
    if (t.access_token && t.expires > Date.now() + 60000) return t.access_token;
    try {
      const fresh = await this._token({ grant_type: "refresh_token", refresh_token: t.refresh_token });
      return this._save(Object.assign({ refresh_token: t.refresh_token }, fresh)).access_token;
    } catch (e) {
      this.storage.removeItem(KEY);
      return null;
    }
  }

  logout() {
    this.storage.removeItem(KEY);
  }
}
