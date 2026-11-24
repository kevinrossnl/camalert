# Glossary

The words CamAlert uses on screen, in Home Assistant and in these docs, with their translations. They come from the
master catalogue (`core/i18n/glossary.json`) and are used verbatim in every language
([translating](../dev/translating.md)).

<!-- BEGIN generated: glossary (tools/docs.py) -->
| Term | Meaning | nl | de | fr | it | pl |
|---|---|---|---|---|---|---|
| **Photo window** | A small window in a corner of the screen with a fresh camera picture every 1-2 seconds; the TV or film keeps playing. | Fotovenster | Fotofenster | Fenêtre photo | Finestra foto | Okno ze zdjęciem |
| **Multi-camera window** | 2 to 4 cameras together in one photo window (mode `strip`). | Venster met meerdere camera's | Fenster mit mehreren Kameras | Fenêtre multi-caméras | Finestra con più telecamere | Okno z kilkoma kamerami |
| **Live view** | The camera stream full screen; afterwards the player returns to what was playing. | Live beeld | Live-Ansicht | Direct | Visione live | Podgląd na żywo |
| **Notification** | A small message with one picture of the camera. | Melding | Benachrichtigung | Notification | Notifica | Powiadomienie |
| **Mosaic** | Up to 9 cameras at once, full screen. | Mozaïek | Mosaik | Mosaïque | Mosaico | Mozaika |
| **Tour** | One camera after the other, full screen. | Rondgang | Rundgang | Ronde | Giro | Obchód |
| **Paused** | The tour stays on the current camera (OK). | Gepauzeerd | Angehalten | En pause | In pausa | Wstrzymano |
| **Display mode** | How a camera is shown: photo window, live view or notification. | Weergavemodus | Anzeigemodus | Mode d'affichage | Modalità di visualizzazione | Tryb wyświetlania |
| **Duration** | How long a camera stays on screen (seconds). | Duur | Dauer | Durée | Durata | Czas |
| **Do not disturb** | Blocks normal requests (and high ones if set); alarm always comes through. | Niet storen | Nicht stören | Ne pas déranger | Non disturbare | Nie przeszkadzać |
| **Cooldown** | Minimum time before the same camera is shown again. | Wachttijd | Wartezeit | Délai | Attesa | Odstęp |
| **Normal** | Priority of a request that follows every rule (motion). | Normaal | Normal | Normale | Normale | Normalny |
| **High** | Priority that always comes through, except in standby (doorbell). | Hoog | Hoch | Haute | Alta | Wysoki |
| **Alarm** | Priority that always comes through and can wake the player. | Alarm | Alarm | Alarme | Allarme | Alarm |
| **Doorbell chime** | A short ding-dong played with high or alarm requests. | Deurbelgeluid | Türklingelton | Son de sonnette | Suono del campanello | Dźwięk dzwonka |
| **Camera control (PTZ)** | Pan, tilt and zoom a camera with the remote (ONVIF or Foscam). | Camerabediening (PTZ) | Kamerasteuerung (PTZ) | Contrôle de la caméra (PTZ) | Controllo telecamera (PTZ) | Sterowanie kamerą (PTZ) |
| **Colour keys** | RED, GREEN, YELLOW and BLUE: sent to Home Assistant while a camera is on screen. | Kleurtoetsen | Farbtasten | Touches de couleur | Tasti colorati | Kolorowe przyciski |
| **Camera names** | The names shown for the cameras; by default made from the go2rtc names. | Cameranamen | Kameranamen | Noms des caméras | Nomi delle telecamere | Nazwy kamer |
| **Event list** | The last 20 requests with what CamAlert did and why. | Gebeurtenissen | Ereignisliste | Liste des événements | Elenco eventi | Lista zdarzeń |
| **Diagnostics** | Checks of go2rtc, every camera, the API, MQTT and the log, on the TV. | Diagnose | Diagnose | Diagnostic | Diagnostica | Diagnostyka |
| **Camera not reachable** | Shown in a tile when a camera did not deliver a picture twice in a row. | Camera niet bereikbaar | Kamera nicht erreichbar | Caméra injoignable | Telecamera non raggiungibile | Kamera nieosiągalna |
| **Player** | An Enigma2 receiver or a Kodi device with CamAlert. | Speler | Wiedergabegerät | Lecteur | Lettore | Odtwarzacz |

Do not use (the docs test and the translation check refuse them):

- ~~pop-up(s)~~ → *photo window*
- ~~corner window~~ → *multi-camera window*
- ~~camera title(s)~~ → *camera names*
- ~~quiet mode~~ → *do not disturb (level)*
- ~~doorbell sound~~ → *doorbell chime*
- ~~several cameras in one window~~ → *multi-camera window*
- ~~Frigate detections~~ → *Frigate events*
- *receiver* when Kodi is meant too → *player* ("Enigma2 receiver" is fine)

Tone of the translations: nl *je*, de *du*, fr *vous*, it *impersonal*, pl *impersonal*.
<!-- END generated: glossary -->
