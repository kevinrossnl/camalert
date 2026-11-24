# Troubleshooting

**The photo window or test shows nothing**
- Diagnostics say *go2rtc address not set* or *No valid go2rtc address*? Enter the address of your go2rtc server in
  the settings (there is no default address, #73); until then CamAlert has no cameras and contacts nothing.
- Open `http://<go2rtc>:1984/api/frame.jpeg?src=<camera>` in a browser. No picture? Then go2rtc cannot reach the camera: check the RTSP address in `go2rtc.yaml`.
- Snapshots need ffmpeg; it is included in the official go2rtc image and app.

**Black picture when zapping to a camera (Enigma2)**
- CamAlert uses `rtspt://` (RTSP over TCP) towards go2rtc. Do not use go2rtc's `stream.ts` HTTP links in channel lists: many Enigma2 receivers play them with a black picture.
- Check that port 8554 of go2rtc is reachable from the player (firewall between networks: allow TCP 8554).

**It takes 2–5 seconds before the camera appears**
- The player waits for the next key frame. Set the camera's I-frame interval (GOP) to 1–2 s, use the sub stream, and add the camera to `preload` in go2rtc.

**Home Assistant triggers, but nothing appears**
- Is the player in standby? CamAlert ignores requests in standby.
- Are you already watching that camera? Then the request is ignored too.
- Call `http://<player>:8099/camalert/status` from the Home Assistant machine. `forbidden` means the caller is not in your local network or the token is wrong.

**The motion sensor never turns on**
- Motion detection must be enabled in the camera / NVR (for UniFi Protect: `switch.<camera>_detections_motion`).

**Why not real picture-in-picture?**
- The PiP decoder of Enigma2 receivers only plays TV channels, not network streams. The photo window works on every player.

**Logs**
- Set *Log level* to *verbose*; read the end of `camalert.log` in Diagnostics, via `/camalert/log`, or with *Download
  diagnostics* in Home Assistant. Every request is logged with its source, decision and reason; the event list shows the
  same for the last 20 requests.

**The camera channel list does not change (Enigma2)**
- CamAlert only rewrites the list when the cameras or names changed, at most every 30 minutes. Press **yellow** in the settings to update it now.
- If go2rtc is unreachable, the existing list is kept on purpose.

**Kodi**
- See [Kodi › troubleshooting](../players/kodi.md#troubleshooting).
