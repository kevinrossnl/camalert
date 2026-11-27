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

The same holds for go2rtc's snapshots (`frame.jpeg`): go2rtc waits for the next key frame, so the first picture of
the photo window can take 2–5 seconds. CamAlert asks for the first picture with `cache=10s` (go2rtc 1.9.14 or newer)
and shows *Loading picture...* meanwhile; UniFi Protect cameras get their pictures from Protect
([devices](devices.md#pictures-from-unifi-protect)).

### Keep cameras ready

For one or two important cameras (the front door, say) the picture can be there at once, also when nothing asked
for that camera in the last seconds: let go2rtc turn the camera into a small MJPEG stream and let the player keep
that stream open **while it is on**.

1. In go2rtc add a stream for the camera, **without** putting it in `preload`:

   ```yaml
   streams:
     front_door_jpeg: ffmpeg:front_door#video=mjpeg#hardware#width=640#raw=-r 2
   ```

   `#hardware` uses the GPU of the go2rtc host when it has one (Intel Quick Sync, VAAPI); leave it out otherwise.
2. In CamAlert set *Display › Keep cameras ready* to `front_door=front_door_jpeg` (camera name = go2rtc stream;
   several with `|`; just `front_door` uses the camera's own stream, which must then be MJPEG).
3. While the player is on, it keeps `stream.mjpeg` of that stream open and keeps only the last picture; the photo
   window, the multi-camera window and the tour show it at once (it is used when it is at most 5 seconds old,
   otherwise the next source: UniFi Protect, then go2rtc's `frame.jpeg`). In standby, with the screen off or with
   CamAlert off the player closes the stream. When no player watches it any more, go2rtc stops ffmpeg by itself:
   that is why the stream must **not** be in `preload`. Waking a player from standby takes seconds anyway, so
   the stream is not kept open in standby.

The diagnostics show per camera *Ready: front_door (last picture 1 s ago)* or *not connected*.

**What it costs** (estimate, measure on your own host): while at least one player is on, go2rtc runs one ffmpeg per
ready camera, however many players watch it. Decoding the camera stream is the largest part: with hardware
acceleration it takes almost no CPU, in software roughly 10–20 % of one core for a 1080p stream (less with a
substream); making 2 JPEGs per second at 640 px wide is negligible. No extra traffic from the camera when go2rtc
already pulls it (for example for `preload` of the camera itself); each player that is on receives about 50–100 KB/s.
Measure it with `docker stats` (or your NAS's monitoring) before and after.

**Alternative without the player setting** (not tested with go2rtc 1.9.15): go2rtc's API can add and remove a
`preload` while it runs (`PUT` / `DELETE` on the preload endpoint in go2rtc's OpenAPI, since 1.9.14), so a Home
Assistant automation could preload `front_door_jpeg` when a CamAlert player is on and remove it when all are off.
That only keeps go2rtc warm: the player still asks `frame.jpeg`, which then answers within about half a second. The player
setting above does both in one place and needs no automation.
