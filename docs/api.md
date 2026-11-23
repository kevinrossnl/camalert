# HTTP API

CamAlert listens on port **8099** (configurable). All requests are `GET` and return JSON.

| Request | What it does |
|---|---|
| `/camalert/show` | Show the default camera with the default settings |
| `/camalert/show?cam=garden&sec=20&mode=live` | Show a specific camera; every parameter is optional |
| `/camalert/mosaic?cam=front_door,garden&sec=60` | Full-screen photo mosaic (up to 9 cameras; without `cam` the *Mosaic cameras* setting) |
| `/camalert/hide` | Close the photo window / return from live view now |
| `/camalert/status` | What is on screen, and the plugin version |

Parameters: `cam` (go2rtc stream name), `sec` (5–300), `mode` (`photo`, `live`, `notify`), `token` (only if you set an access token; can also be sent as header `X-CamAlert-Token`).

Answer of `show`: `{"result": true, "action": "show", "cam": "garden"}`. `action` is

- `show` – shown now,
- `extend` – was already on screen, the time is extended,
- `ignore` – not shown, because the receiver is in standby or you are already watching that camera,
- `error` – no valid go2rtc address configured.

Calling `show` again while the camera is on screen extends the time, so repeated motion events keep it open.

## HTTPS

Turn on **Use HTTPS for the API** in the settings. CamAlert then creates a self-signed certificate (`/etc/enigma2/camalert.crt`, valid 10 years) and answers on `https://<receiver>:8099/...`. Callers must accept that certificate: `curl -k`, or `verify_ssl: false` in Home Assistant (already set in the CamAlert package; set `https: true` in the action data).

If your go2rtc address starts with `https://` (for example behind a reverse proxy) and uses a self-signed certificate, turn off **Check go2rtc certificate**.

## Security

- By default only callers from private networks (192.168.x.x, 10.x.x.x, 172.16–31.x.x, IPv6 ULA) are accepted.
- Set an **access token** in the settings if other people use your network.
- Never forward port 8099 to the internet.

## Examples

```sh
curl "http://192.168.1.30:8099/camalert/show?cam=front_door&sec=30"
```

Node-RED: *http request* node, method GET, URL as above.
