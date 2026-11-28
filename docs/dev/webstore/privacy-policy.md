# CamAlert browser extension: privacy policy

CamAlert is an open-source player for Home Assistant (GPL v2, <https://github.com/kevinrossnl/camalert>). This
policy covers the CamAlert extension for Chrome, Edge and Firefox.

**What the extension stores.** The address of your own Home Assistant and its access token, or with MQTT the address,
user and password of your own MQTT broker; the player's settings (name, go2rtc addresses, window position and size,
language). Everything is kept in the browser's local extension storage on your computer. It is never synced to
other devices and never logged.

**What the extension sends, and where.** It connects only to the addresses you enter: your Home Assistant (its
WebSocket API and its CamAlert picture view), and with MQTT your broker and your go2rtc servers. The token or
password is only sent to the server it belongs to. Camera pictures go from your go2rtc (through your Home Assistant)
to the extension's window and nowhere else.

**What the extension does not do.** No account, no analytics, no tracking, no advertising, no data for the
developers or for anyone else. Nothing is sold or shared. The extension reads no web pages.

**Removing your data.** Remove the extension (or clear its settings in its options) and everything it stored is
gone. Revoke the access token in your Home Assistant profile.

Questions: <https://github.com/kevinrossnl/camalert/issues>.
