# DoorCam for Enigma2

**DoorCam** shows your IP cameras on the TV of an Enigma2 receiver (openATV, OpenPLi, VTi, ... on VU+, Dreambox, Zgemma, Octagon and others).

When someone rings the doorbell or walks up to the front door, your home automation (for example Home Assistant) asks the receiver to show that camera:

- **Photo window** – a small window in a corner of the screen with a fresh picture every 1–2 seconds; you keep watching TV.
- **Live** – the receiver switches to the live camera stream and back to your channel when the time is up.
- **Notification** – just a message on screen.

It also creates a **channel list with all your cameras**, so you can zap to them like normal channels.

DoorCam works with any camera that has an RTSP stream (UniFi Protect, Reolink, Hikvision, Dahua/Amcrest, TP-Link Tapo, Axis, ...) through **[go2rtc](https://github.com/AlexxIT/go2rtc)**, a small free camera streaming server.

> 📖 **New here? Follow the [step-by-step guide](docs/guide.md).** No programming needed.

## How it fits together

```
 cameras ──RTSP──▶ go2rtc ──RTSP / snapshots──▶ Enigma2 receiver (DoorCam) ──▶ TV
                                                   ▲
 motion / doorbell ─▶ Home Assistant ──HTTP─────────┘
```

## Features

- Settings screen on the receiver, in English, Dutch, German, French, Italian and Polish.
- Cameras are read from go2rtc automatically – choose them with the remote.
- Photo window: position (4 corners) and size (small / medium / large).
- Live mode with automatic return to the previous channel.
- One-button camera channel list ("bouquet").
- Mosaic: up to 9 cameras at once (photo mosaic, or a live mosaic channel via go2rtc).
- HTTP API for Home Assistant, Node-RED, openHAB, a doorbell script, ...
- Only reacts when the receiver is on (not in standby) and you are not already watching that camera.
- Local network only by default, optional access token.

## Install

On the receiver (via Telnet/SSH), replace the version with the [latest release](../../releases/latest):

```sh
cd /tmp
wget -O doorcam.ipk https://github.com/OWNER/enigma2-plugin-doorcam/releases/download/v1.0.0/enigma2-plugin-extensions-doorcam_1.0.0_all.ipk
opkg install /tmp/doorcam.ipk
```

Then restart the GUI and open **Menu › Plugins › DoorCam**.

## Documentation

| | |
|---|---|
| [Step-by-step guide](docs/guide.md) | From nothing to a camera pop-up on your TV |
| [go2rtc as Home Assistant app](docs/go2rtc-home-assistant.md) | Easiest if you already run Home Assistant OS |
| [go2rtc in Docker / TrueNAS / Synology](docs/go2rtc-docker.md) | Run go2rtc as its own container |
| [Camera stream addresses](docs/cameras.md) | RTSP URLs for popular camera brands |
| [Home Assistant automation](docs/home-assistant.md) | Show a camera on motion or doorbell |
| [Several cameras at once](docs/mosaic.md) | Photo mosaic or live mosaic channel |
| [HTTP API](docs/api.md) | For other systems and scripts |
| [Troubleshooting](docs/troubleshooting.md) | Black picture, slow start, no pop-up, ... |
| [Translating](docs/translating.md) | Add or improve a language |

## Why go2rtc?

Enigma2 receivers can play RTSP, but connecting directly to every camera is slow and many cameras only allow a few connections. go2rtc keeps one connection per camera, can keep your doorbell camera "warm" so it starts quickly, and makes snapshots for the photo window. It is free, small and runs almost anywhere.

## Limitations

- Hardware picture-in-picture on Enigma2 only plays TV channels, not network streams. That is why DoorCam uses a photo window instead of a real PiP.
- After switching to a camera it takes until the next key frame (usually 1–2 seconds) before the picture appears.

## License

GPL-2.0-only, see [LICENSE](LICENSE). Not affiliated with any camera brand.
