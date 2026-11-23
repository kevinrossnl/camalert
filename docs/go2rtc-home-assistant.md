# go2rtc as a Home Assistant app

If you run **Home Assistant OS** (or Supervised), you can install go2rtc as an app (formerly called add-on). This is the easiest way.

> Home Assistant also has go2rtc built in (since 2024.11), but that one only listens inside Home Assistant itself. Your receiver cannot reach it, so you need the separate app below.

1. In Home Assistant go to **Settings › Apps › App store** (older versions: *Add-on store*).
2. Open the menu **⋮ › Repositories** and add `https://github.com/AlexxIT/hassio-addons`.
3. Search for **go2rtc**, open it and press **Install**. Turn on **Start on boot** and **Watchdog**, then **Start**.
4. The app reads its configuration from `/config/go2rtc.yaml` (the same folder as `configuration.yaml`). Create it, for example with the *File editor* app:

   ```yaml
   streams:
     front_door: rtsp://admin:<password>@192.168.1.20:554/stream2
     garden: rtsp://admin:<password>@192.168.1.21:554/stream2

   preload:
     front_door: "video&audio"
   ```

5. Restart the go2rtc app.
6. Open `http://<home-assistant-ip>:1984` in your browser. You should see your cameras.

In DoorCam use `http://<home-assistant-ip>:1984` as **go2rtc address** and `8554` as **RTSP port**.

### Notes

- The app uses port 1984 (web/API) and 8554 (RTSP). If another app already uses one of them, change the port in the app's *Network* settings and in DoorCam.
- go2rtc's web page has **no password**. Anyone in your network can see the cameras. Keep it inside your home network, never forward these ports to the internet.
- Prefer not to put camera passwords in the file? go2rtc can use Home Assistant cameras directly, see the [go2rtc documentation](https://github.com/AlexxIT/go2rtc#source-hass).
