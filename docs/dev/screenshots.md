# Screenshots

Screenshots in the docs show **only CamAlert's own screens**, never a camera picture or a TV programme
(checklist: [privacy](privacy.md)). Illustrations with a drawn TV picture (`docs/images/hero.jpg`, `mosaic.jpg`,
`tour.jpg`, `flow.png`, the demo GIF `demo.gif`) are made by `tools/readme_images.py`.

| File | What |
|---|---|
| `images/enigma2/settings-1.png`, `settings-2.png` | settings screen (General/Display, Display/Rules/Triggers) |
| `images/enigma2/photo-window.png` | photo window with a label (*Person · Front door*) and the key hint |
| `images/enigma2/notification.png` | notification mode: small window with label and priority |
| `images/enigma2/multi-camera-window.png` | multi-camera window with one camera *not reachable* |
| `images/enigma2/mosaic.png` | mosaic, one tile *Camera not reachable* |
| `images/enigma2/tour.png` | tour with its key hint |
| `images/enigma2/event-list.png` | event list, an ignored request with its reason |
| `images/enigma2/diagnostics.png` | diagnostics |
| `images/enigma2/key-help.png` | HELP key in the tour |
| `images/kodi/photo-window.png`, `multi-camera-window.png` | Kodi photo window (label, key hint) and multi-camera window, cropped to the window |
| `images/kodi/mosaic.png`, `tour.png` | Kodi mosaic (one tile *Camera not reachable*) and tour with their key hints |
| `images/kodi/settings.png`, `event-list.png`, `diagnostics.png` | Kodi settings, event list (an ignored request) and diagnostics, cropped to the dialog |
| `images/kodi/menu.png` | Kodi choice list when CamAlert is opened from *Program add-ons* (#106), cropped to the dialog |
| `images/kodi/camera-list.png` | Kodi video add-on: the camera list with a demo camera selected (#107), full screen |

The Enigma2 screenshots were taken on openATV 8.0.1 with its default skin (MetrixHD, 1280x720 OSD); the Kodi
screenshots on Kodi 21 (LibreELEC) with Estuary at 1920x1080, cropped and scaled to 2/3.

## How to take them (Enigma2)

1. **Neutral first, never mute** (root DEVELOPMENT.md): do not touch volume or mute. Silence comes from the demo
   settings (chime off) and `test=1`. Write down the channel (OpenWebif `/api/getcurrent`) and copy
   `/etc/enigma2/settings`, the CamAlert channel list and `camalert.log`.
2. **Demo setup.** Start the fake go2rtc on the receiver (`python3 tests/fakes/go2rtc.py --unreachable driveway`:
   cameras `front_door`, `garden`, `driveway`, `back_door`, solid-colour frames, `driveway` fails). Stop Enigma2
   (`init 4`), replace the `config.plugins.camalert.*` lines by a demo set (go2rtc `http://127.0.0.1:1984`, default
   camera `front_door`, automatic channel list and update check off, own event folder, **an access token** so that
   no real automation can open a real camera while you work), set the menu language to English
   (`config.misc.locale=en_GB`, `config.misc.language=en`), move `camalert.log` aside and start Enigma2 (`init 3`).
3. **Fill the event list from the receiver itself** (`127.0.0.1`, so no real address appears in diagnostics), with
   the token in the `X-CamAlert-Token` header: a few `show` requests with labels and priorities, one with do not
   disturb on (ignored), the multi-camera window, the mosaic and the tour.
4. **Grab the OSD only:** `http://<receiver>/grab?format=png&mode=osd` (no video layer, so no TV picture). The OSD
   is transparent where the TV would be: flatten it on a neutral dark grey (`#282c34`). Navigate with
   `/api/remotecontrol?command=<key code>`.
5. **Restore everything:** `init 4`, put back the settings file and `camalert.log`, stop the fake go2rtc, `init 3`,
   then restore the channel. Check that the CamAlert channel list did not change.
6. Look at every picture at full size (privacy checklist), crop away other plugins or vendor pictures, then
   `python3 tools/check_images.py --strip <files>` and `python3 tools/check_images.py .`.

## How to take them (Kodi)

1. **Neutral first, never mute** (root DEVELOPMENT.md), nothing playing (JSON-RPC `Player.GetActivePlayers` is empty).
   Copy the add-on folder and its data folder (`settings.xml`, `camalert.log`, `events/`). LibreELEC has no `diff`
   or `cmp`: compare the restore later with `md5sum`.
2. **Demo setup.** Start the fake go2rtc on the player (`python3 tests/fakes/go2rtc.py --unreachable driveway`),
   stop Kodi, put a demo `settings.xml` in the data folder (go2rtc `http://127.0.0.1:1984`, default camera
   `front_door`, camera names, **an access token**) and start Kodi.
3. **Neutral background:** the home screen shows posters of your library, so open the System screen
   (`GUI.ActivateWindow` `settings`) before every screenshot and crop to CamAlert's own window.
4. Open the screens through the API on `127.0.0.1` (with the token) and `Addons.ExecuteAddon` (`events`,
   `diagnostics`, no parameter = settings); take each picture with `Input.ExecuteAction` `screenshot` (Kodi's
   screenshot folder). Fill the event list first as for Enigma2. Since 1.1.0 `Addons.ExecuteAddon` without a
   parameter opens the **video add-on** (camera list, #107); the choice list of the script (#106) opens with
   `kodi-send --action="RunScript(service.camalert)"` over ssh. Right after a Kodi start the library scan shows a
   title of your own library in the top right corner: wait for it or crop it away.
5. **Restore everything:** stop Kodi, put back both folders, stop the fake go2rtc, start Kodi. Stop the fake
   go2rtc by its pid, not with `pkill -f go2rtc.py` inside an ssh command: that pattern also matches the ssh
   shell itself and kills the rest of the restore. Use one JSON-RPC connection at a time: many short connections
   in a row crashed Kodi 21 once.
6. Review, crop, `python3 tools/check_images.py --strip <files>` as for Enigma2.
