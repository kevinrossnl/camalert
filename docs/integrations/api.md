# HTTP API

CamAlert listens on port **8099** (configurable) on every player (Enigma2 receiver, Kodi and Android TV); all answer
exactly the same (one implementation in `core/camalert_core/api.py`, ported to Kotlin for Android TV and checked
against it by the contract tests). Answers are JSON (`metrics`: Prometheus text).

**API version 1:**
- Actions (they change something) use **`POST`**: `show`, `mosaic`, `tour`, `hide`, `dnd` with `on`, `ptz`,
  `webhook`. Parameters as a JSON object body, a form body or in the query string.
- Reads use **`GET`**: `status`, `cameras`, `dnd` (state), `events`, `log`, `metrics`.
- `GET` for an action still works for now, but is **deprecated**: the answer has the header `Deprecation: true`
  and the player logs it once per caller.
- The access token goes in the header **`X-CamAlert-Token`**. `?token=` in the URL still works but is deprecated
  (logged once, always removed from logs).

| Request | What it does |
|---|---|
| `POST /camalert/show` | Show the default camera with the default settings |
| `POST /camalert/show` `{"cam": "garden", "sec": 20, "mode": "live", "priority": "high"}` | Show a specific camera; every parameter is optional |
| `POST /camalert/show` `{"cam": "front_door,garden"}` | 2–4 cameras together in one multi-camera window (TV stays visible); more than 4 = mosaic |
| `POST /camalert/tour` `{"cam": "front_door,garden", "interval": 8}` | Full-screen camera tour (◀ ▶ = previous/next, OK = hold, GREEN/PLAY = live, EXIT/BACK) |
| `POST /camalert/mosaic` `{"cam": "front_door,garden", "sec": 60}` | Full-screen photo mosaic (up to 9 cameras; without `cam` the *Mosaic cameras* setting) |
| `POST /camalert/hide` | Close the photo window, multi-camera window, mosaic and tour / return from live view now |
| `POST /camalert/dnd` `{"on": 1}` / `{"on": 0}` | Do not disturb on/off; `GET /camalert/dnd` only reports the state |
| `POST /camalert/ptz` `{"cam": "garden", "move": "left"}` | Move a PTZ camera (`up`, `down`, `left`, `right`, `zoom_in`, `zoom_out`, `home`, `stop`); see [camera control](../user/devices.md) |
| `POST /camalert/settings` `{"position": "top_left", "size": "small"}` | Window position (`top_right`, `top_left`, `bottom_right`, `bottom_left`) and/or size (`small`, `medium`, `large`) of the photo window; saved on the player and used by the next window. `GET /camalert/settings` only reports them (capability `settings`) |
| `POST /camalert/webhook` `{"url": "..."}` | Where to post remote control colour keys (set automatically by the Home Assistant integration; empty `url` removes it). Must point into the local network |
| `GET /camalert/status` | What is on screen (`screen`: `none`, `photo`, `strip`, `notification`, `live`, `mosaic` or `tour`; `window` / `live`: the camera), do-not-disturb state, version, `platform` (`enigma2`/`kodi`), `api_version`, `capabilities`, `min_ha_version`, `mqtt`, `position`, `size` |
| `GET /camalert/cameras` | List of cameras (name, title, has snapshot) |
| `GET /camalert/events` | The last 20 requests: time, camera, label, source, priority, what CamAlert did and why |
| `GET /camalert/metrics` | Prometheus metrics (see [monitoring](monitoring.md)) |
| `GET /camalert/log?lines=200` | The end of `camalert.log` (passwords and tokens are always removed) |

Parameters: `cam` (go2rtc stream name, or several separated by commas; only letters, digits, `_`, `.`, `-`),
`sec` (5–300), `mode` (`photo`, `live`, `notify`, `strip` = multi-camera window), `label` (optional
who/what shown before the camera name in the title, e.g. `Person`), `priority` (`normal` follows the player's
active hours and rules, `high` always, `alarm` always and may wake the player / screen), `test` (`1` on any
request: a test, e.g. of the [end-to-end runner](../dev/e2e.md): never plays the doorbell chime and is shown with
the source *Test request* in the event list; Home Assistant automations can skip such events).

Errors: `400` `{"result": false, "error": "invalid camera name"}` (also invalid `mode`, `priority`, `on`, `test`, `position`, `size`, PTZ
move or webhook url), `403` forbidden (address or token), `404` unknown action, `405` other HTTP methods,
`429` too many requests (30 per 10 s per caller), `500` internal error. A disabled CamAlert answers
`{"result": false, "error": "disabled"}`.

Answer of `show`: `{"result": true, "action": "show", "cam": "garden"}`. `action` is

- `show` – shown now,
- `wake` – priority alarm: the player is being woken up, the camera follows a few seconds later,
- `extend` – was already on screen, the time is extended,
- `ignore` – not shown: the player is in standby, you are already watching that camera, or a rule blocked it (do not disturb, active hours, recording, playing a recording or video). `/camalert/events` and `camalert.log` say which one,
- `error` – no valid go2rtc address configured.

Calling `show` again while the camera is on screen extends the time, so repeated motion events keep it open.

## HTTPS

Turn on **Use HTTPS for the API** in the settings. CamAlert then creates a self-signed certificate (Enigma2: `/etc/enigma2/camalert.crt`, Kodi: in the add-on data folder; valid 10 years) and answers on `https://<player>:8099/...`. Callers must accept that certificate: `curl -k`; in the Home Assistant integration turn off *Check certificates* (the REST command package already accepts it; set `https: true` in the action data).

If your go2rtc address starts with `https://` (for example behind a reverse proxy) and uses a self-signed certificate, turn off **Check certificates**.

## Security

- By default (*Allowed callers: local network only*) only these addresses are accepted: 10.0.0.0/8,
  172.16.0.0/12, 192.168.0.0/16, 100.64.0.0/10 (CGNAT, also used by Tailscale), loopback (127.0.0.0/8, ::1),
  link-local (169.254.0.0/16, fe80::/10) and IPv6 unique local addresses (fc00::/7). Everything else is refused,
  including the documentation ranges (192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24, 2001:db8::/32).
- Set an **access token** in the settings if other people use your network; send it in the `X-CamAlert-Token`
  header. Tokens are compared in constant time.
- `log`, `events` and `metrics` never answer callers outside the local network unless a token is set (even with
  *Allowed callers: any address*).
- CamAlert only fetches pictures and streams of the configured cameras (go2rtc server or camera file): requests
  name a camera, never a URL. The webhook must point into the local network: the caller's address, an address
  from the list above, a local host name (no dots, or ending in `.local`, `.lan`, `.home`, `.home.arpa`,
  `.internal`), or a host name that resolves **only** to such addresses (for example a split-DNS name of Home
  Assistant). The name is resolved when the webhook is set and again before every post; if it resolves to any
  other address, the request is refused (400) or the post is skipped.
- Never forward port 8099 to the internet.

### Where passwords and tokens are stored

| Secret | Enigma2 | Kodi | Android TV | Home Assistant |
|---|---|---|---|---|
| API access token | `/etc/enigma2/settings` | `settings.xml` in the add-on data folder | app settings (private app storage) | the integration's config entry (`.storage/core.config_entries`) |
| MQTT password | `/etc/enigma2/settings` | `settings.xml` in the add-on data folder | app settings (private app storage) | – |
| Camera logins (PTZ, Foscam, UniFi Protect console) | `/etc/enigma2/camalert_devices.conf` | `devices.conf` in the add-on data folder, including the default camera password (#55: a password typed in *Camera password (default)* is moved there and the field is emptied); only the default camera user name stays in `settings.xml` | – (no camera control yet) | – |

- These are plain text files on the player, like every other setting of the image, Kodi or Android. Anyone who can
  read them (root or ssh access to an Enigma2 receiver, the Kodi `userdata` folder, for example over a network share or in
  a Kodi backup) can read the secrets. The Android TV app keeps its settings in private storage and is excluded
  from Android backups.
- CamAlert never writes them to `camalert.log`, `/camalert/log`, the event list, diagnostics or MQTT: everything
  logged goes through one redaction function.
- Use separate logins with as few rights as possible: a camera user that may only view/move, a UniFi Protect user
  with *View Only* and *Restrict to local access only*, an MQTT user only for CamAlert. On Enigma2 make the devices
  file readable for root only (`chmod 600`); the Kodi add-on writes its `devices.conf` readable for Kodi's user only
  (0600 on Linux and LibreELEC). Locations of the Kodi add-on data folder per system:
  [Kodi](../players/kodi.md#where-things-are).

## Examples

```sh
curl -X POST -H "X-CamAlert-Token: $TOKEN" -d cam=front_door -d sec=30 http://192.168.1.30:8099/camalert/show
curl -H "X-CamAlert-Token: $TOKEN" http://192.168.1.30:8099/camalert/status
```

Node-RED: *http request* node, method POST, URL `http://192.168.1.30:8099/camalert/show`, payload
`{"cam": "front_door"}`, header `X-CamAlert-Token`.
