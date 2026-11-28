# Web player and browser extension

Two more players for screens without an Enigma2 receiver, Kodi or Android TV app (#92, #127). They are served and
driven by the **CamAlert Home Assistant integration**: there is nothing else to install on a server.

| | Web player | Browser extension |
|---|---|---|
| For | wall tablets (Fully Kiosk), smart-TV browsers, any browser | desktop PCs (Chrome, Edge) |
| Shows alerts | while the page (or a Home Assistant dashboard tab) is open | while the browser runs, no tab needed |
| Sign-in | Home Assistant's own login | a long-lived access token |
| Sound | after one tap on the page | yes |

Both are players like the others: Home Assistant shows them as devices with the same buttons, selects, actions and
blueprints. Their platform is `browser`, their model "Web browser".

## How it works

- The browser connects to Home Assistant's WebSocket and subscribes as a CamAlert player. Home Assistant sends the
  normal CamAlert requests (show, hide, mosaic, Do not disturb, settings, ...) over that connection and the browser
  answers like the other players do (see the [HTTP API](../integrations/api.md)).
- A browser that connects for the first time is listed under **Settings › Devices & services** as discovered.
  Nothing is shown in a browser that was not added.
- Camera pictures come from go2rtc through Home Assistant (`/api/camalert/go2rtc/...`, with login). Home Assistant
  only forwards to a go2rtc address in the local network, the same rule as for the webhook. So the browser needs
  neither direct access to go2rtc nor plain HTTP next to an HTTPS Home Assistant.
- Pictures come in the same order as on the other players where a browser can follow it: the warm feed of a
  camera in *Keep cameras ready*, go2rtc's cached frame, then new frames. UniFi Protect pictures are not used in a
  browser, because the Protect login would have to be in the browser.
- Live view uses go2rtc's WebRTC (smooth, with sound after a tap); when that does not start within a few seconds,
  the MJPEG stream.
- A camera that is an own mosaic in go2rtc (#125) and the helper streams of *Keep cameras ready* (#117) are left out
  of the mosaic, as on the other players.

## Web player

1. Open `http://<home-assistant>:8123/camalert_static/page/player.html` in the browser of the tablet or TV.
2. Sign in to Home Assistant when asked. A browser that is already signed in to Home Assistant on the same address
   uses that login.
3. Press **⚙** and give the player a name. Enter the go2rtc address, or leave it empty and let Home Assistant send
   it when you add the player (#122). Press **Save**.
4. In Home Assistant, go to **Settings › Devices & services**: the player is listed as discovered. Add it.
5. Tap the page once (**Tap to enable sound**), so the chime and live sound may play.

**On a Home Assistant dashboard.** Tick **Also show alerts on Home Assistant dashboards in this browser** in the
settings of the web player. From then on every Home Assistant page in that browser shows the CamAlert windows on
top of the dashboard, using the dashboard's own login. This only works in the browser where you ticked it, never
for every user. The module is loaded by the integration (`/camalert_static/page/frontend.js`) and does nothing
elsewhere.

**Report a problem.** The panel (**⚙**) has **Report a problem**: a QR code to a pre-filled GitHub issue and a
download of the report without passwords or tokens ([troubleshooting](../user/troubleshooting.md)).

**More go2rtc servers** (#131) works as on the other players: `garden=http://192.168.1.20:1984` shows the cameras
of that server as `garden.<name>`; without a prefix they keep their names (`s2.<name>` when the main server has the
same name). Home Assistant forwards to each of them under the same local-network rule.

**Limits.** A background tab or a tablet with its screen off gets nothing (Fully Kiosk can wake the screen on
motion or with its own Home Assistant integration). Smart-TV browsers without WebRTC show live view as MJPEG.

## Browser extension

1. Download `camalert-browser-X.Y.Z.zip` (Chrome, Edge) or `camalert-browser-firefox-X.Y.Z.zip` (Firefox 140 or
   newer) from the [latest release](https://github.com/kevinrossnl/camalert/releases/latest).
2. Chrome or Edge: unpack the zip, open `chrome://extensions`, turn on **Developer mode**, press **Load unpacked**
   and choose the unpacked folder. Once CamAlert is in the Chrome Web Store, install it from there instead (it then
   updates by itself). Firefox: until CamAlert is on addons.mozilla.org, open `about:debugging`, **This Firefox**,
   **Load Temporary Add-on** and choose the zip (it stays until Firefox restarts).
3. Open the extension's options. Enter the address of Home Assistant and a long-lived access token. Create the token
   in your Home Assistant profile (Security), preferably for a separate user that is not an administrator. Allow the
   extension access to that address when Chrome asks.
4. Add the player in Home Assistant as above.

An alert opens a small window in the corner of the screen (alarm: in front of everything). A mosaic fills the
screen. The chime plays from the extension itself. The token stays in the browser's local extension storage; it is
never synced and never logged.

**MQTT instead of Home Assistant** (#131). Under **Connection** choose **MQTT broker over WebSocket** and enter the
broker's WebSocket address (Mosquitto: a `listener 1884` with `protocol websockets`, so `ws://192.168.1.20:1884/mqtt`
or `wss://` behind HTTPS), user and password. The extension then uses the same topics as the other players
(`camalert/<id>/show`, `mosaic`, `hide`, `dnd/set`; it publishes `state`, `dnd` and `availability`) and announces
itself through Home Assistant MQTT discovery: a device with a button per camera. Pictures come straight from go2rtc,
so the extension asks for access to the go2rtc addresses too. Without the Home Assistant connection there is no
CamAlert device in the integration (no actions, blueprints or talk-back); the password stays in the browser's local
extension storage like the token.

**Limits.** Only while the browser runs. In Firefox the extension is a Manifest V2 add-on with a background page:
Firefox stops a Manifest V3 background after a short idle time, which would close the connection that brings the
alerts.

## For developers

The shared core is plain JavaScript (`players/web/core/`, ES modules, no dependencies). Its rules, choices,
colours and texts are generated from the Python core (`python3 tools/build_web.py update`, texts with
`python3 tools/i18n/i18n.py build`). Packages: `python3 tools/build_web.py dist dist` (Chrome/Edge and Firefox); the Chrome Web Store listing, permission
justifications and screenshots are in [docs/dev/webstore/](../dev/webstore/README.md).
Tests: `node --test players/web/tests/unit/*.test.mjs` and, with Playwright,
`cd players/web && npm ci && npx playwright test` (the web page and the extension in Chromium against a fake
Home Assistant). CI area: `sh tools/ci.sh web`.

## Talking to the door

When go2rtc has a talk-back stream `<camera>_talk`, the window of that camera has a **Talk** button: the
browser's microphone goes to the camera's speaker. It needs the page over HTTPS. See
[Talking back](../integrations/talk-back.md).
