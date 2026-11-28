# Talking back to the door

CamAlert shows the doorbell camera on the TV, but none of the TV players has a microphone: Enigma2 and Kodi have no
audio capture, and a Fire TV's voice remote only talks to Alexa. So there are two ways to answer (#98):

| Way | Needs | Where |
| --- | --- | --- |
| **Quick replies**: a colour key speaks a prepared text | a speaker on the camera (or any media player) | every TV player, see [Home Assistant](home-assistant.md#quick-replies-from-the-tv) |
| **Talk**: your own voice, live | a device with a microphone: phone, tablet or PC | the [web player](../players/web.md) |

This page is about **Talk**.

## How it works

go2rtc cannot talk to UniFi Protect on its own: Protect's stream has no audio back-channel. CamAlert uses go2rtc's
`exec` back-channel instead:

1. The web player opens a WebRTC connection with your microphone to the go2rtc stream `<camera>_talk` (through
   Home Assistant, like the live view).
2. go2rtc pipes your audio (PCMA, 8 kHz) into FFmpeg.
3. FFmpeg encodes it the way the camera expects (AAC, mono, 22050 Hz for UniFi Protect) and sends it as UDP straight
   to the camera's talk-back port (Protect: port 7004).

When go2rtc has a stream `<camera>_talk`, the web player shows a **Talk** button in the title bar of that camera's
window. Press it to talk, press **Stop talking** to stop; talking stops by itself after one minute and when the
window closes. The `_talk` stream is never shown as a camera on any player.

Tested with a UniFi Protect AI Turret (Protect 7.3): the camera played the audio about half a second after it was
sent, straight from the go2rtc host to the camera, without the Protect console in between.

## Setting it up

1. **Find the camera's address and talk-back settings.** For UniFi Protect, read them (read only) with

   ```sh
   python3 tools/talkback.py protect https://<console> <user> --password-file <file>
   ```

   It lists the cameras that have a speaker, with their address, format, port and sample rate.

2. **Add the talk stream to go2rtc.yaml**, under `streams:`. Generate the line with

   ```sh
   python3 tools/talkback.py stream front_door 192.168.1.14
   ```

   which gives

   ```yaml
     front_door_talk: "exec:ffmpeg -hide_banner -loglevel error -fflags nobuffer -f alaw -ar 8000 -ac 1 -i - -c:a aac -b:a 32k -ar 22050 -ac 1 -f adts udp://192.168.1.14:7004#backchannel=1#audio=alaw/8000"
   ```

   The name must be the camera's go2rtc name plus `_talk`. Restart go2rtc.

3. **Firewall**: the go2rtc host must reach the camera on UDP port 7004. When the cameras are in their own VLAN,
   allow UDP from the go2rtc host to the camera's port 7004.

4. **HTTPS**: browsers only give a page the microphone over HTTPS (or on `localhost`). Open Home Assistant over
   HTTPS (Nabu Casa, your own certificate or a reverse proxy) for the web player. Over plain HTTP the button says
   *Talking needs the page over HTTPS*.

## Good to know

- Echo: use a headset or keep the phone away from the door's speaker sound; the browser's echo cancellation helps.
- Delay: about half a second one way.
- Other cameras: any camera that takes audio over UDP, RTSP back-channel or one of go2rtc's two-way sources works
  the same way; only the `exec` line differs. Cameras with an RTSP back-channel can use their RTSP source with
  `#backchannel=1` directly.
- Nothing in CamAlert changes the camera or Protect: the speaker volume is the one set in Protect.
