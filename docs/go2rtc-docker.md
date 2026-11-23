# go2rtc in Docker, TrueNAS or Synology

Run go2rtc as a container on any always-on machine.

## Docker Compose

Create a folder, for example `/opt/go2rtc`, with a file `go2rtc.yaml` (see the [guide](guide.md#step-2--install-go2rtc)) and a `compose.yaml`:

```yaml
services:
  go2rtc:
    image: alexxit/go2rtc:1.9.15        # pin a version, update on purpose
    restart: unless-stopped
    ports:
      - "1984:1984"   # web page + API (snapshots for the photo window)
      - "8554:8554"   # RTSP (live view on the receiver)
    volumes:
      - /opt/go2rtc:/config:ro
```

Start it with `docker compose up -d` and open `http://<server-ip>:1984`.

Do **not** add a `command:` line: the image already starts go2rtc with `/config/go2rtc.yaml`.

In `go2rtc.yaml`, make RTSP listen on all addresses (this is the default, but check it if you copied an example):

```yaml
rtsp:
  listen: ":8554"
```

## TrueNAS SCALE (Apps)

1. **Datasets** › your pool › *Add Dataset*: name `go2rtc`, **Dataset Preset: Apps**. Create the folder `config` in it and put `go2rtc.yaml` there.
2. **Apps › Discover Apps › ⋮ › Install via YAML**, name `go2rtc`, and paste:

   ```yaml
   services:
     go2rtc:
       image: alexxit/go2rtc:1.9.15
       ports:
         - "1984:1984"
         - "8554:8554"
       restart: unless-stopped
       user: "568:568"
       volumes:
         - /mnt/<pool>/go2rtc/config:/config:ro
   ```

3. Save. The app should show *Running*. If it stops immediately, check that the dataset preset is *Apps* (so user 568 may read the folder).

## Synology (Container Manager)

Create a project with the Docker Compose file above (use a folder in `/volume1/docker/go2rtc`).

## CPU and network

go2rtc only passes the camera stream through; it hardly uses CPU. A camera only streams while someone watches it (or when it is in `preload`). Snapshots for the photo window use a little CPU (ffmpeg) while the window is open.
