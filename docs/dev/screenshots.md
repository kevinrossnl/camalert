# Screenshots

Screenshots in the docs show **only CamAlert's own screens**, never a camera picture or a TV programme
(checklist: [privacy](privacy.md)). Illustrations with a drawn TV picture (`docs/images/hero.jpg`, `mosaic.jpg`,
`tour.jpg`, `flow.png`) are made by `tools/readme_images.py`.

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

The Enigma2 screenshots were taken on openATV 8.0.1 with its default skin (MetrixHD, 1280x720 OSD).

## How to take them (Enigma2)

1. **Make the receiver quiet and neutral first.** Write down the channel, the volume and the mute state
   (OpenWebif `/api/getcurrent`, `/api/vol`), set the volume to 0 (`/api/vol?set=set0`; `set=mute` *toggles*, so
   check `ismute` before you use it). Copy `/etc/enigma2/settings`, the CamAlert channel list and `camalert.log`.
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
   then restore volume, mute and channel. Check that the CamAlert channel list did not change.
6. Look at every picture at full size (privacy checklist), crop away other plugins or vendor pictures, then
   `python3 tools/check_images.py --strip <files>` and `python3 tools/check_images.py .`.

Kodi: the same with Estuary and nothing playing; the fake go2rtc runs on any computer in the network.
