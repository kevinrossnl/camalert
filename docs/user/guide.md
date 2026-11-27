# Step-by-step guide

![How CamAlert fits together](../images/flow.png)

This guide takes you from zero to a camera picture on your TV when someone is at the door. It takes about 30 minutes. You need:

- A **player**: an Enigma2 receiver with Python 3 (openATV 7 or newer, OpenPLi 9 or newer, ...) or Kodi 19 or newer
  (LibreELEC, CoreELEC, OSMC, Windows, Linux, Android).
- One or more IP cameras with RTSP (see [cameras.md](cameras.md)).
- A computer, NAS or Home Assistant system that is always on, for **go2rtc**.
- Optional: Home Assistant (or another system) that knows when there is motion or someone rings.

## Step 1 – Find the RTSP address of your camera

Every camera has an address like `rtsp://user:password@192.168.1.20:554/stream1`. Look up your brand in [cameras.md](cameras.md).

Tip: use the **sub stream** / low resolution (for example 640×360 or 1280×720). It starts faster and the box needs less power.

Test it on a computer with [VLC](https://www.videolan.org/): *Media › Open Network Stream* and paste the address. If you see the picture, it is correct.

## Step 2 – Install go2rtc

(Don't want an extra server? Skip to [using CamAlert without go2rtc](without-go2rtc.md).)

Choose one:

- **A. You run Home Assistant OS** → [install the go2rtc app](go2rtc-home-assistant.md) (easiest).
- **B. You have a NAS or a server with Docker** → [run the go2rtc container](go2rtc-docker.md).

In both cases you end up with a file `go2rtc.yaml` that lists your cameras, for example:

```yaml
streams:
  front_door: rtsp://admin:<password>@192.168.1.20:554/stream2
  garden: rtsp://admin:<password>@192.168.1.21:554/stream2

preload:
  front_door: "video&audio"   # keeps the door camera ready, so it starts faster
```

Use simple names: lowercase letters, digits and `_` only. They become the camera names on the TV ("front_door" shows as "Front door").

Open `http://<go2rtc-address>:1984` in your browser: you should see your cameras there and can click them to watch.

## Step 3 – Install CamAlert on the player

- Enigma2 receiver: [install the plugin](../players/enigma2.md#install), then restart the GUI.
- Kodi: [install the CamAlert repository and add-on](../players/kodi.md#install).

## Step 4 – Set up CamAlert

### The wizard (first start)

The first time you open CamAlert on a new player (Enigma2: **Menu › Plugins › CamAlert**; Kodi: **Add-ons ›
Program add-ons › CamAlert**; Android TV: the CamAlert app) and no go2rtc address is set yet, a short wizard opens:

1. **go2rtc**: CamAlert looks for go2rtc in your network for up to about 10 seconds: at `homeassistant.local:1984`,
   at your Home Assistant if the player already knows it, and at every address of your own network on port 1984.
   Choose the go2rtc it found, *Enter the address yourself*, or (Enigma2 and Kodi) *Without go2rtc (camera file)*.
2. **Default camera**: choose a camera; it appears on screen as a preview. Answer *Is this the right camera?*.
3. **Test**: if you like, a test notification appears. A test never plays the doorbell chime.
4. **Ready**: the wizard shows the name and address of the player. In Home Assistant, go to **Settings › Devices &
   services › Add integration › CamAlert** and enter that address.

Leaving the wizard (EXIT/BACK) at any point is fine: it does not open by itself again and you continue in the
settings. Start it again from the settings menu with **Start the wizard again** (Enigma2: MENU in the settings;
Kodi: the CamAlert menu; Android TV: the first settings screen). A player that already has a go2rtc address never
sees the wizard.

### The settings

Open **Menu › Plugins › CamAlert** (Kodi: **Add-ons › My add-ons › Services › CamAlert › Configure**; the settings
have the same names, Enigma2-only steps are marked):

![CamAlert settings: general and display](../images/enigma2/settings-1.png)


1. **go2rtc address**: `http://<go2rtc-address>:1984` (for example `http://192.168.1.10:1984`). A new install has no
   address: until you enter one CamAlert contacts nothing, and the settings and diagnostics say *go2rtc address not set*.
2. **Default camera**: select the line and press **OK**; choose your door camera from the list.
3. **Display mode**: *Photo window* (you keep watching TV), *Live view* or *Notification*.
4. **Duration**: how long the camera stays on screen.
   - Photo window / notification: **Pause TV meanwhile** pauses the channel (timeshift) and continues where you left off. This needs a hard disk or USB stick that is set up for timeshift.
5. Enigma2: press **yellow** to create the channel list with all cameras. CamAlert keeps that list up to date by itself (every 30 minutes, setting *Update camera list automatically*): new cameras in go2rtc appear, removed ones disappear. Choose with *Camera list position* whether the list is at the top or bottom of your channel lists.
   - **Camera names**: press OK to give a camera its own name (for example `front_door` → "Front door (street)"). The name is used everywhere: channel list, photo window, mosaic, tour and Home Assistant.
6. Press **blue** to test (Kodi: *Test: show the default camera* under General): the default camera appears.
7. Press **green** to save (Kodi: OK).

On Enigma2 you can now also zap to your cameras via the new channel list (press OK on a channel, then the bouquet list), open **CamAlert mosaic** (all cameras at once) or **CamAlert tour** (one after the other) from the plugin menu or the blue button.

![The photo window on top of a TV programme (illustration)](../images/hero.jpg)

When the photo window is on screen you can use the remote: **OK** switches to the live picture, **◀ ▶** shows another camera, **EXIT** closes it (any other key also closes it, so you can just keep zapping).

### Copy the settings to another player (export and import)

Set up one player, then copy its settings to the others:

- **Enigma2**: in the settings press **MENU › Export settings**. CamAlert writes `camalert-settings.json` to a USB
  stick or the hard disk when there is one, otherwise to `/home/root`. On the other Enigma2 box put the file in one of
  those places and choose **MENU › Import settings**.
- **Kodi**: open the add-on (**Add-ons › Program add-ons › CamAlert**) and choose **Export settings** or **Import
  settings**; you pick the folder or file yourself, so a USB stick or a network share works.

The export leaves the passwords and the access token out, unless you choose *With passwords and access token*
(then keep the file to yourself). A setting the file does not hold keeps its value, so importing an export without
passwords keeps the passwords of the player. Settings another kind of player does not have are skipped, and a file
of an older CamAlert is updated on import; a file of a newer CamAlert is refused.

Before every import CamAlert saves the current settings, and **Undo the last import** brings them back (also after
an update of CamAlert that changed the settings). The last 5 copies stay on the player: Enigma2
`/etc/enigma2/camalert-backups/`, Kodi `addon_data/service.camalert/backups/`.

The Android TV app has no export or import yet.

## Step 5 – Show the camera automatically

- **Home Assistant**: install the CamAlert integration and use a ready-made blueprint, see [Home Assistant](../integrations/home-assistant.md). No YAML needed.
- **Anything else** (Node-RED, openHAB, a script): `POST http://<player-ip>:8099/camalert/show` with `cam=front_door` – see [HTTP API](../integrations/api.md).

Done! Something not working? See [troubleshooting.md](troubleshooting.md).
