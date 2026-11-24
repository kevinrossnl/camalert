# Privacy checklist (text, images, commits)

This repository is public (mirrored to GitHub). Nothing personal may end up in it: not in files, not in images, not
in commit messages. CI (`sh tools/ci.sh privacy`) blocks the mirror when a check fails.

## What CI checks

| Check | What |
|---|---|
| `tools/check_private.py` | text files: private keys, tokens, passwords in URLs, ntfy topics, and the private denylist (CI secret `CAMALERT_DENYLIST`: own IP ranges, domains, names) |
| commit history | author, e-mail and message of every commit against the same denylist |
| `tools/check_images.py` | every PNG/JPEG/GIF/WebP: no metadata (EXIF, GPS, XMP, IPTC, ICC profiles, text chunks, comments, time stamps) (#8) |

Remove metadata from an image before you commit it (lossless, the pixels stay the same):

```sh
python3 tools/check_images.py --strip docs/images/new-screenshot.png
python3 tools/check_images.py .
```

## What only you can check: screenshots and pictures

Before you add or replace an image, open it at full size and go through this list:

- [ ] **No real camera picture.** Use drawn pictures (`tools/readme_images.py`) or solid test frames from a fake
      go2rtc (see [screenshots](screenshots.md)). No faces, people, licence plates, house numbers, street views,
      gardens or rooms.
- [ ] **No TV picture.** No programme, channel logo, EPG text or film poster. Take Enigma2 screenshots with the
      OSD only (OpenWebif `/grab?mode=osd`), Kodi screenshots with nothing playing.
- [ ] **Neutral names only:** cameras `front_door`, `garden`, `driveway`, `back_door`; players `living_room`,
      `bedroom`; labels `Person`, `Motion`. No real camera, channel, bouquet, box, Wi-Fi or user names.
- [ ] **Example addresses only:** `192.168.1.x`, `example.com`, `<token>`. No real IP addresses, host names, MAC
      addresses, serial numbers or tokens (diagnostics and settings screens show these: use a demo setup).
- [ ] **No other personal traces:** file paths with user names, e-mail addresses, notifications from other apps,
      recordings lists, the receiver's channel list or picons in the background.
- [ ] Metadata stripped (`tools/check_images.py .` = 0 problems).
- [ ] Screenshot taken at 1920x1080 with the image's default skin (Kodi: Estuary), see [screenshots](screenshots.md).

## Text and code

- Examples use `192.168.1.10`, `front_door`, `garden`, `example.com`, `<password>`.
- Commit author `CamAlert developers <noreply@camalert.invalid>`; no personal names in commit messages.
- Run `sh tools/ci.sh privacy` (with `CAMALERT_DENYLIST` set) before every push.
