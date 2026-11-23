# Troubleshooting

**The photo window or test shows nothing**
- Open `http://<go2rtc>:1984/api/frame.jpeg?src=<camera>` in a browser. No picture? Then go2rtc cannot reach the camera: check the RTSP address in `go2rtc.yaml`.
- Snapshots need ffmpeg; it is included in the official go2rtc image and app.

**Black picture when zapping to a camera**
- CamAlert uses `rtspt://` (RTSP over TCP) towards go2rtc. Do not use go2rtc's `stream.ts` HTTP links in channel lists: many receivers play them with a black picture.
- Check that port 8554 of go2rtc is reachable from the receiver (firewall between networks: allow TCP 8554).

**It takes 2–5 seconds before the camera appears**
- The receiver waits for the next key frame. Set the camera's I-frame interval (GOP) to 1–2 s, use the sub stream, and add the camera to `preload` in go2rtc.

**Home Assistant triggers, but nothing appears**
- Is the receiver in standby? CamAlert ignores requests in standby.
- Are you already watching that camera? Then the request is ignored too.
- Call `http://<receiver>:8099/camalert/status` from the Home Assistant machine. `forbidden` means the caller is not in your local network or the token is wrong.

**The motion sensor never turns on**
- Motion detection must be enabled in the camera / NVR (for UniFi Protect: `switch.<camera>_detections_motion`).

**Why not real picture-in-picture?**
- The PiP decoder of Enigma2 receivers only plays TV channels, not network streams. The photo window works on every receiver.

**Logs**
- Enable the debug log in the receiver's settings and look for lines with `[CamAlert]`.

**The camera list does not change**
- CamAlert only rewrites the list when the cameras or names changed, at most every 30 minutes. Press **yellow** in the settings to update it now.
- If go2rtc is unreachable, the existing list is kept on purpose.
