# Watching several cameras at once

Enigma2 cannot play several network streams at the same time (picture-in-picture only plays TV channels). DoorCam offers two ways to see all cameras at once.

## Option 1 – Photo mosaic in DoorCam (no extra load on your server)

**Menu › Plugins › DoorCam mosaic** (also in the blue *Extensions* menu) shows up to 9 cameras in a grid. Every tile shows a fresh picture about every 1–2 seconds. Press **EXIT** to close.

- Choose the cameras in the settings: **Mosaic cameras** › OK (empty = all cameras, up to 9).
- From Home Assistant or a script: `/doorcam/mosaic?cam=front_door,garden,drive&sec=60` (or `/doorcam/show` with more than one `cam`).

## Option 2 – Live mosaic channel (smooth video, uses server CPU)

go2rtc can combine several cameras into one live video with ffmpeg. It then appears as a normal channel in the camera list. Add to the `streams:` section of `go2rtc.yaml` (one line):

```yaml
  mosaic: "exec:ffmpeg -hide_banner -loglevel error -rtsp_transport tcp -i rtsp://127.0.0.1:8554/front_door -rtsp_transport tcp -i rtsp://127.0.0.1:8554/garden -rtsp_transport tcp -i rtsp://127.0.0.1:8554/drive -rtsp_transport tcp -i rtsp://127.0.0.1:8554/backyard -filter_complex [0:v]fps=10,scale=960:540,setsar=1[v0];[1:v]fps=10,scale=960:540,setsar=1[v1];[2:v]fps=10,scale=960:540,setsar=1[v2];[3:v]fps=10,scale=960:540,setsar=1[v3];[v0][v1][v2][v3]xstack=inputs=4:layout=0_0|w0_0|0_h0|w0_h0[out] -map [out] -c:v libx264 -preset superfast -tune zerolatency -g 10 -pix_fmt yuv420p -an -rtsp_transport tcp -f rtsp {output}"
```

Replace the four camera names with your own (the names of your other streams). Restart go2rtc, then press **yellow** (*Camera list*) in DoorCam: the mosaic appears as a channel.

- The server decodes 4 streams and encodes 1 new one: roughly 1–2 CPU cores on a typical NAS, **only while someone watches** the mosaic.
- With a graphics card or Intel Quick Sync you can use hardware encoding; see the [go2rtc ffmpeg documentation](https://github.com/AlexxIT/go2rtc#source-ffmpeg).
- The first picture takes a few seconds (ffmpeg has to connect to all cameras).
