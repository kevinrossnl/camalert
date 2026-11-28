# players/web/ – web player and browser extension (#92, #127)

Read the root [DEVELOPMENT.md](../../DEVELOPMENT.md) first (privacy, how we work, CI). User documentation:
[docs/players/web.md](../../docs/players/web.md).

## Rules
- **One shared core** (`core/`, plain ES modules, **no dependencies**, relative imports only): the web page
  (`page/`), the Home Assistant dashboard module (`page/frontend.js`) and the extension (`extension/`) only differ in
  the settings backend, the view and the link to Home Assistant. `tests/test_web.py` checks the imports.
- Rules, choices, colours and layout come from the Python core as **generated data** (`core/generated.js`,
  `python3 tools/build_web.py update`), never typed in twice. Texts come from the master catalogue: English in
  `i18n/strings.json`, then `python3 tools/i18n/i18n.py update` (translate) and `build` (writes `core/i18n.js`).
- The API (`core/api.js`) answers like `core/camalert_core/api.py`: same actions, parameters, errors and answers.
  A browser player has no PTZ, tour, webhook or update (`build_web.CAPABILITIES`).
- Home Assistant serves the web player from `custom_components/camalert/www/`: a **copy** written by
  `python3 tools/build_web.py update` (never edit it by hand; `check` fails when it is stale).
- Never store a token in the player settings (`core/store.js`); the page signs in with Home Assistant's login, the
  extension keeps its token in `chrome.storage.local` only. Never log or show a token.
- The extension stays Manifest V3 with minimal permissions: `storage`, `alarms`, `offscreen`, and only *optional*
  host permissions for the Home Assistant address.

## Files

| Path | What |
|---|---|
| `core/api.js` | the CamAlert API of a browser player (validation and answers) |
| `core/controller.js` | what is on screen and for how long (no DOM) |
| `core/pictures.js` | camera names (helpers #117, composites #125), titles, picture sources |
| `core/player.js` | one player: store + controller + view + link; go2rtc through Home Assistant |
| `core/store.js` | settings with the schema's defaults (localStorage / chrome.storage.local) |
| `core/transport.js` | `HaSocket` (own WebSocket) and `FrontendLink` (inside the HA frontend) |
| `core/ui.js` | the screen: windows, mosaic, notification, chime (shadow DOM) |
| `core/generated.js`, `core/i18n.js` | generated (see above) |
| `page/` | `player.html` + `page.js` (web player), `auth.js` (HA login), `frontend.js` (dashboard module) |
| `extension/` | Manifest V3: `background.js` (service worker), `alert.*` (alert window), `options.*`, `popup.*`, `offscreen.*` |
| `tests/unit/` | `node --test` (every CI runner) |
| `tests/e2e/`, `tests/fake/` | Playwright against a fake Home Assistant (workstation runner) |
