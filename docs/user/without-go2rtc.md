# Using CamAlert without go2rtc

go2rtc is recommended (faster start, fewer connections to your cameras, snapshots for every camera). If you cannot run it, CamAlert can talk to the cameras directly.

## Set up

1. In CamAlert set **Cameras via** to **Directly from the cameras**.
2. Create the camera file on the player – Enigma2: `/etc/enigma2/camalert_cameras.conf` (for example with *FileCommander*, FTP/WinSCP, or a network share); Kodi: `cameras.conf` in the add-on data folder (or the file set in *Camera file (direct mode)*, see [Kodi](../players/kodi.md#where-things-are)); Android TV: *Settings › General › Cameras without go2rtc › Camera list* (see [Android TV](../players/androidtv.md#settings)). One camera per line:

   ```
   # name        | live stream (RTSP)                                         | snapshot (optional)
   Front door    | rtsp://admin:<password>@192.168.1.20:554/h264Preview_01_sub | http://192.168.1.20/cgi-bin/api.cgi?cmd=Snap&channel=0&user=admin&password=<password>
   Garden        | rtsp://admin:<password>@192.168.1.21:554/Streaming/Channels/102 | http://admin:<password>@192.168.1.21/ISAPI/Streaming/channels/102/picture
   Driveway      | rtsp://192.168.1.22:554/stream2
   ```

   - The **name** is what you see on screen; in requests you use it in lowercase with `_` (`Front door` → `front_door`).
   - Lines starting with `#` are ignored.
3. Open the CamAlert settings: choose the **Default camera** (OK) and test it (Enigma2: **yellow** creates the channel list, **blue** tests).

## Snapshot addresses

The photo window and the mosaic need a snapshot (JPEG) address. Without one, CamAlert switches to the live stream instead.

| Brand | Snapshot address |
|---|---|
| Reolink | `http://<ip>/cgi-bin/api.cgi?cmd=Snap&channel=0&user=<user>&password=<password>` |
| Hikvision / Annke | `http://<user>:<password>@<ip>/ISAPI/Streaming/channels/102/picture` |
| Dahua / Amcrest | `http://<user>:<password>@<ip>/cgi-bin/snapshot.cgi?channel=1` |
| Axis | `http://<user>:<password>@<ip>/axis-cgi/jpg/image.cgi?resolution=640x360` |
| Foscam | `http://<ip>:88/cgi-bin/CGIProxy.fcgi?cmd=snapPicture2&usr=<user>&pwd=<password>` |
| UniFi Protect, Tapo, EZVIZ | no simple snapshot address → use go2rtc, or live mode |

`user:password@` in the address works for both basic and digest authentication.

## Security

The camera file contains camera passwords. Give the cameras their own user with view-only rights, and do not share the file. Settings backups of the player may include it.

## Differences with go2rtc

- Every player connects to the cameras itself; some cameras allow only 2–4 connections.
- Starting is slower: nothing is kept "warm".
- The live mosaic channel needs go2rtc; the photo mosaic works if your cameras have snapshot addresses.
