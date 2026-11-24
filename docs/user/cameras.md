# Camera stream addresses

Replace `<user>`, `<password>` and the IP address with your own. Prefer the **sub stream** (lower resolution): it starts faster on the player. Test every address in VLC first.

| Brand | Main stream | Sub stream |
|---|---|---|
| **UniFi Protect** | In Protect: camera › Settings › Advanced › RTSP, enable *Medium* (or *Low*). You get `rtsps://<nvr-ip>:7441/<key>?enableSrtp`. Use: `rtsp://<nvr-ip>:7447/<key>` | same, with the Low key |
| **Reolink** | `rtsp://<user>:<password>@<ip>:554/h264Preview_01_main` | `rtsp://<user>:<password>@<ip>:554/h264Preview_01_sub` |
| **Hikvision / Annke** | `rtsp://<user>:<password>@<ip>:554/Streaming/Channels/101` | `rtsp://<user>:<password>@<ip>:554/Streaming/Channels/102` |
| **Dahua / Amcrest / Lorex** | `rtsp://<user>:<password>@<ip>:554/cam/realmonitor?channel=1&subtype=0` | `...&subtype=1` |
| **TP-Link Tapo / VIGI** | `rtsp://<camera-account>:<password>@<ip>:554/stream1` | `rtsp://<camera-account>:<password>@<ip>:554/stream2` |
| **Axis** | `rtsp://<user>:<password>@<ip>/axis-media/media.amp` | add `?resolution=640x360` |
| **Foscam** | `rtsp://<user>:<password>@<ip>:88/videoMain` | `rtsp://<user>:<password>@<ip>:88/videoSub` |
| **EZVIZ** | `rtsp://admin:<verification code>@<ip>:554/h264/ch1/main/av_stream` | `.../ch1/sub/av_stream` |
| **ONVIF camera (unknown brand)** | go2rtc can find it: `onvif://<user>:<password>@<ip>` | |

Ring, Nest, Arlo, Blink, Eufy (cloud cameras) usually have no RTSP. go2rtc supports some of them, see the [go2rtc sources list](https://github.com/AlexxIT/go2rtc#source-list).

## Codec

Use **H.264** where possible. Most Enigma2 receivers also play H.265 (HEVC), but older ones do not.

## Faster start

The picture appears at the next *key frame* (I-frame). Many cameras send one every 2–4 seconds. If your camera lets you set the *I-frame interval* / *GOP*, set it to about 1–2 seconds (for example GOP 25 at 25 fps).
