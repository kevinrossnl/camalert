# HTTP API

CamAlert listens on port **8099** (configurable) on every player (Enigma2 receiver and Kodi); both answer exactly
the same (one implementation in `core/camalert_core/api.py`). Answers are JSON (`metrics`: Prometheus text).

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
| `POST /camalert/show` `{"cam": "front_door,garden"}` | 2–4 cameras together in one corner window (TV stays visible); more than 4 = mosaic |
| `POST /camalert/tour` `{"cam": "front_door,garden", "interval": 8}` | Full-screen camera tour (◀ ▶ = previous/next, OK = hold, GREEN/PLAY = live, EXIT/BACK) |
| `POST /camalert/mosaic` `{"cam": "front_door,garden", "sec": 60}` | Full-screen photo mosaic (up to 9 cameras; without `cam` the *Mosaic cameras* setting) |
| `POST /camalert/hide` | Close the photo window / return from live view now |
| `POST /camalert/dnd` `{"on": 1}` / `{"on": 0}` | Do not disturb on/off; `GET /camalert/dnd` only reports the state |
| `POST /camalert/ptz` `{"cam": "garden", "move": "left"}` | Move a PTZ camera (`up`, `down`, `left`, `right`, `zoom_in`, `zoom_out`, `home`, `stop`); see [cameras with PTZ](devices.md) |
| `POST /camalert/webhook` `{"url": "..."}` | Where to post remote control colour keys (set automatically by the Home Assistant integration; empty `url` removes it). Must point into the local network |
| `GET /camalert/status` | What is on screen, do-not-disturb state, version, `platform` (`enigma2`/`kodi`), `api_version`, `capabilities`, `min_ha_version`, `mqtt` |
| `GET /camalert/cameras` | List of cameras (name, title, has snapshot) |
| `GET /camalert/events` | The last 20 requests: time, camera, label, source, priority, what CamAlert did and why |
| `GET /camalert/metrics` | Prometheus metrics (see [recipes](recipes.md#monitoring)) |
| `GET /camalert/log?lines=200` | The end of `camalert.log` (passwords and tokens are always removed) |

Parameters: `cam` (go2rtc stream name, or several separated by commas; only letters, digits, `_`, `.`, `-`),
`sec` (5–300), `mode` (`photo`, `live`, `notify`, `strip` = several cameras in one window), `label` (optional
who/what shown before the camera name in the title, e.g. `Person`), `priority` (`normal` follows the player's
active hours and rules, `high` always, `alarm` always and may wake the receiver / screen).

Errors: `400` `{"result": false, "error": "invalid camera name"}` (also invalid `mode`, `priority`, `on`, PTZ
move or webhook url), `403` forbidden (address or token), `404` unknown action, `405` other HTTP methods,
`429` too many requests (30 per 10 s per caller), `500` internal error. A disabled CamAlert answers
`{"result": false, "error": "disabled"}`.

Answer of `show`: `{"result": true, "action": "show", "cam": "garden"}`. `action` is

- `show` – shown now,
- `wake` – priority alarm: the receiver is being woken up, the camera follows a few seconds later,
- `extend` – was already on screen, the time is extended,
- `ignore` – not shown: the receiver is in standby, you are already watching that camera, or a rule blocked it (do not disturb, active hours, recording, playing a recording or video). `/camalert/events` and `camalert.log` say which one,
- `error` – no valid go2rtc address configured.

Calling `show` again while the camera is on screen extends the time, so repeated motion events keep it open.

## HTTPS

Turn on **Use HTTPS for the API** in the settings. CamAlert then creates a self-signed certificate (`/etc/enigma2/camalert.crt`, valid 10 years) and answers on `https://<receiver>:8099/...`. Callers must accept that certificate: `curl -k`, or `verify_ssl: false` in Home Assistant (already set in the CamAlert package; set `https: true` in the action data).

If your go2rtc address starts with `https://` (for example behind a reverse proxy) and uses a self-signed certificate, turn off **Check go2rtc certificate**.

## Security

- By default only callers from private networks (192.168.x.x, 10.x.x.x, 172.16–31.x.x, IPv6 ULA) are accepted.
- Set an **access token** in the settings if other people use your network; send it in the `X-CamAlert-Token`
  header. Tokens are compared in constant time.
- `log`, `events` and `metrics` never answer callers outside the local network unless a token is set (even with
  *Allowed callers: any address*).
- CamAlert only fetches pictures and streams of the configured cameras (go2rtc server or camera file): requests
  name a camera, never a URL. The webhook must point into the local network (caller address, private address or a
  local host name such as `homeassistant.local`).
- Never forward port 8099 to the internet.

## Examples

```sh
curl -X POST -H "X-CamAlert-Token: $TOKEN" -d cam=front_door -d sec=30 http://192.168.1.30:8099/camalert/show
curl -H "X-CamAlert-Token: $TOKEN" http://192.168.1.30:8099/camalert/status
```

Node-RED: *http request* node, method POST, URL `http://192.168.1.30:8099/camalert/show`, payload
`{"cam": "front_door"}`, header `X-CamAlert-Token`.
