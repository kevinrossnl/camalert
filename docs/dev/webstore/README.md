# Chrome Web Store listing

Everything the Chrome Web Store (and Microsoft Edge Add-ons, which asks the same) wants for the browser extension
(#131), ready to copy into the developer dashboard. The upload itself is done by the maintainer; nothing here is
uploaded automatically.

| File | What |
|---|---|
| `screenshot-1-doorbell.png` … `screenshot-4-mqtt.png` | screenshots, 1280x800 |
| `promo-440x280.png` | small promo tile |
| `marquee-1400x560.png` | marquee promo tile (optional) |
| [privacy-policy.md](privacy-policy.md) | the privacy policy the listing links to |

The screenshots show the real extension in Chromium against the fake Home Assistant of the tests, with the drawn
demo cameras of `tools/readme_images.py` (never a real camera picture). Make them again after a visible change:
`python3 tools/webstore_images.py`, then `python3 tools/check_images.py --strip docs/dev/webstore/*.png`
(see [screenshots](../screenshots.md) and the [privacy checklist](../privacy.md)).

The package to upload is `camalert-browser-X.Y.Z.zip` from the release (not the `-firefox-` one). Its name and short
description come from `players/web/extension/_locales/` (English is the default; Dutch, German, French, Italian and
Polish too), so the dashboard offers those six listing languages.

## Store listing

- **Category:** Tools
- **Language:** English (then add the other five under *Store listing › language*)
- **Homepage URL:** `https://github.com/kevinrossnl/camalert`
- **Support URL:** `https://github.com/kevinrossnl/camalert/issues`

### Description (English)

```text
CamAlert shows your IP cameras on your screen when it matters: someone rings the doorbell, Frigate sees a person,
an alarm goes off. A small window with the camera picture appears in a corner of the screen, with the doorbell
chime; a mosaic shows every camera at once.

CamAlert is a player for Home Assistant. The extension makes your desktop browser one more CamAlert player next to
the Enigma2, Kodi and Android TV players: Home Assistant adds it as a device, and your automations, the CamAlert
actions and the blueprints work as for any other player.

- Photo window, multi-camera window, notification and mosaic, with priorities (alarm comes first)
- Live view with WebRTC from go2rtc, MJPEG when WebRTC does not start
- Several go2rtc servers, and Do not disturb from Home Assistant
- Or without Home Assistant's connection: MQTT over WebSocket, with Home Assistant MQTT discovery
- Six languages: English, Dutch, German, French, Italian, Polish

What you need: Home Assistant with the CamAlert integration (HACS) and go2rtc. The extension talks only to your own
Home Assistant, go2rtc and MQTT broker. Its access token stays in the browser's local extension storage: never
synced, never sent anywhere else. No account, no tracking, no ads. Open source (GPL v2).
```

### Description (Dutch)

```text
CamAlert toont je IP-camera's op je scherm als het ertoe doet: iemand belt aan, Frigate ziet een persoon, een
alarm gaat af. Een klein venster met het camerabeeld verschijnt in een hoek van het scherm, met de deurbel; een
mozaïek toont alle camera's tegelijk.

CamAlert is een speler voor Home Assistant. De extensie maakt van je desktopbrowser nog een CamAlert-speler naast
de Enigma2-, Kodi- en Android TV-spelers: Home Assistant voegt hem toe als apparaat, en je automatiseringen, de
CamAlert-acties en de blueprints werken zoals bij elke andere speler.

- Fotovenster, venster met meerdere camera's, melding en mozaïek, met prioriteiten (alarm gaat voor)
- Live beeld met WebRTC van go2rtc, MJPEG als WebRTC niet start
- Meer go2rtc-servers, en Niet storen vanuit Home Assistant
- Of zonder de verbinding met Home Assistant: MQTT via WebSocket, met MQTT-discovery van Home Assistant
- Zes talen: Engels, Nederlands, Duits, Frans, Italiaans, Pools

Wat je nodig hebt: Home Assistant met de CamAlert-integratie (HACS) en go2rtc. De extensie praat alleen met je
eigen Home Assistant, go2rtc en MQTT-broker. Het toegangstoken blijft in de lokale extensie-opslag van de browser:
nooit gesynchroniseerd, nooit ergens anders heen gestuurd. Geen account, geen tracking, geen advertenties. Open
source (GPL v2).
```

### Description (German)

```text
CamAlert zeigt deine IP-Kameras auf deinem Bildschirm, wenn es darauf ankommt: Jemand klingelt, Frigate erkennt
eine Person, ein Alarm geht los. Ein kleines Fenster mit dem Kamerabild erscheint in einer Ecke des Bildschirms,
mit dem Türgong; ein Mosaik zeigt alle Kameras auf einmal.

CamAlert ist ein Player für Home Assistant. Die Erweiterung macht deinen Desktop-Browser zu einem weiteren
CamAlert-Player neben den Playern für Enigma2, Kodi und Android TV: Home Assistant fügt ihn als Gerät hinzu, und
deine Automatisierungen, die CamAlert-Aktionen und die Blueprints funktionieren wie bei jedem anderen Player.

- Fotofenster, Fenster mit mehreren Kameras, Benachrichtigung und Mosaik, mit Prioritäten (Alarm geht vor)
- Livebild mit WebRTC von go2rtc, MJPEG, wenn WebRTC nicht startet
- Mehrere go2rtc-Server, und Nicht stören aus Home Assistant
- Oder ohne die Verbindung zu Home Assistant: MQTT über WebSocket, mit MQTT-Discovery von Home Assistant
- Sechs Sprachen: Englisch, Niederländisch, Deutsch, Französisch, Italienisch, Polnisch

Was du brauchst: Home Assistant mit der CamAlert-Integration (HACS) und go2rtc. Die Erweiterung spricht nur mit
deinem eigenen Home Assistant, go2rtc und MQTT-Broker. Das Zugriffstoken bleibt im lokalen Erweiterungsspeicher des
Browsers: nie synchronisiert, nie anderswohin gesendet. Kein Konto, kein Tracking, keine Werbung. Open Source
(GPL v2).
```

### Description (French)

```text
CamAlert affiche vos caméras IP sur votre écran au bon moment : quelqu'un sonne, Frigate détecte une personne,
une alarme se déclenche. Une petite fenêtre avec l'image de la caméra apparaît dans un coin de l'écran, avec le
carillon ; une mosaïque montre toutes les caméras à la fois.

CamAlert est un lecteur pour Home Assistant. L'extension fait de votre navigateur de bureau un lecteur CamAlert de
plus, à côté des lecteurs Enigma2, Kodi et Android TV : Home Assistant l'ajoute comme appareil, et vos
automatisations, les actions CamAlert et les blueprints fonctionnent comme pour tout autre lecteur.

- Fenêtre photo, fenêtre multi-caméras, notification et mosaïque, avec des priorités (l'alarme passe en premier)
- Vue en direct en WebRTC depuis go2rtc, en MJPEG si WebRTC ne démarre pas
- Plusieurs serveurs go2rtc, et Ne pas déranger depuis Home Assistant
- Ou sans la connexion à Home Assistant : MQTT via WebSocket, avec la découverte MQTT de Home Assistant
- Six langues : anglais, néerlandais, allemand, français, italien, polonais

Ce qu'il vous faut : Home Assistant avec l'intégration CamAlert (HACS) et go2rtc. L'extension ne communique
qu'avec votre propre Home Assistant, go2rtc et broker MQTT. Le jeton d'accès reste dans le stockage local de
l'extension : jamais synchronisé, jamais envoyé ailleurs. Pas de compte, pas de pistage, pas de publicité. Open
source (GPL v2).
```

### Description (Italian)

```text
CamAlert mostra le telecamere IP sullo schermo quando serve: qualcuno suona il campanello, Frigate rileva una
persona, scatta un allarme. Una piccola finestra con l'immagine della telecamera compare in un angolo dello
schermo, con il suono del campanello; un mosaico mostra tutte le telecamere insieme.

CamAlert è un lettore per Home Assistant. L'estensione rende il browser desktop un altro lettore CamAlert accanto
ai lettori Enigma2, Kodi e Android TV: Home Assistant lo aggiunge come dispositivo, e le automazioni, le azioni
CamAlert e i blueprint funzionano come per qualsiasi altro lettore.

- Finestra foto, finestra con più telecamere, notifica e mosaico, con priorità (l'allarme viene prima)
- Visione dal vivo con WebRTC da go2rtc, MJPEG se WebRTC non parte
- Più server go2rtc, e Non disturbare da Home Assistant
- Oppure senza la connessione a Home Assistant: MQTT tramite WebSocket, con il rilevamento MQTT di Home Assistant
- Sei lingue: inglese, olandese, tedesco, francese, italiano, polacco

Cosa serve: Home Assistant con l'integrazione CamAlert (HACS) e go2rtc. L'estensione comunica solo con il proprio
Home Assistant, go2rtc e broker MQTT. Il token di accesso resta nella memoria locale dell'estensione: mai
sincronizzato, mai inviato altrove. Nessun account, nessun tracciamento, nessuna pubblicità. Open source (GPL v2).
```

### Description (Polish)

```text
CamAlert pokazuje obraz z kamer IP na ekranie, gdy to ważne: ktoś dzwoni do drzwi, Frigate wykrywa osobę, włącza
się alarm. W rogu ekranu pojawia się małe okno z obrazem z kamery, z dźwiękiem dzwonka; mozaika pokazuje wszystkie
kamery naraz.

CamAlert to odtwarzacz dla Home Assistant. Rozszerzenie zmienia przeglądarkę na komputerze w kolejny odtwarzacz
CamAlert obok odtwarzaczy Enigma2, Kodi i Android TV: Home Assistant dodaje go jako urządzenie, a automatyzacje,
akcje CamAlert i blueprinty działają jak dla każdego innego odtwarzacza.

- Okno ze zdjęciem, okno z kilkoma kamerami, powiadomienie i mozaika, z priorytetami (alarm ma pierwszeństwo)
- Podgląd na żywo przez WebRTC z go2rtc, MJPEG, gdy WebRTC nie startuje
- Kilka serwerów go2rtc oraz Nie przeszkadzać z Home Assistant
- Albo bez połączenia z Home Assistant: MQTT przez WebSocket, z wykrywaniem MQTT w Home Assistant
- Sześć języków: angielski, niderlandzki, niemiecki, francuski, włoski, polski

Co jest potrzebne: Home Assistant z integracją CamAlert (HACS) i go2rtc. Rozszerzenie łączy się tylko z własnym
Home Assistant, go2rtc i brokerem MQTT. Token dostępu zostaje w lokalnej pamięci rozszerzenia: nigdy nie jest
synchronizowany ani wysyłany gdzie indziej. Bez konta, bez śledzenia, bez reklam. Open source (GPL v2).
```

## Privacy practices

**Single purpose:**

```text
Shows the user's own security camera pictures in a small browser window when their Home Assistant (or MQTT
broker) asks for it, for example when someone rings the doorbell.
```

**Permission justifications:**

| Permission | Justification to paste |
|---|---|
| `storage` | Keeps the player's settings (name, go2rtc address, window position and size, language) and the address and access token of the user's own Home Assistant (or MQTT broker) in chrome.storage.local, on this computer only. |
| `alarms` | A check every 30 seconds that reconnects to the user's Home Assistant when the service worker was stopped, so alerts keep arriving. |
| `offscreen` | Plays the doorbell chime of an alert (AUDIO_PLAYBACK): a service worker cannot play sound. |
| Host permissions (optional, `http://*/*` and `https://*/*`) | Asked at run time for exactly the addresses the user enters: their own Home Assistant (WebSocket API and camera pictures), and with MQTT their broker and go2rtc servers. These are local addresses that differ per home, so they cannot be listed in advance. No other site is accessed and no page content is read. |

**Remote code:** *No, I am not using remote code.* (All JavaScript is in the package; the extension only exchanges
data with the user's own servers.)

**Data usage** — tick:

- *Authentication information*: the access token of the user's own Home Assistant (or the MQTT password). It is
  stored on the user's computer and only sent to the server it belongs to.

and leave every other type unticked. Tick all three certifications (not sold to third parties, not used for
anything unrelated to the single purpose, not used for creditworthiness or lending).

**Privacy policy URL:** `https://github.com/kevinrossnl/camalert/blob/main/docs/dev/webstore/privacy-policy.md`

## Test instructions for the review

```text
CamAlert needs the user's own Home Assistant with the CamAlert integration and go2rtc; there is no public demo
server. To see it work: in Home Assistant create a long-lived access token (Profile > Security), enter the address
and the token in the extension's options and add the discovered player under Settings > Devices & services; the
action camalert.show then opens the alert window. The source and the end-to-end tests (players/web/tests/e2e) are at
https://github.com/kevinrossnl/camalert.
```

## Steps in the developer dashboard

1. Download `camalert-browser-X.Y.Z.zip` from the latest GitHub release (the one without `firefox`).
2. Open the [Chrome Web Store developer dashboard](https://chrome.google.com/webstore/devconsole), signed in with
   the CamAlert Google account, and press **New item**. Choose the zip and press **Upload**.
3. **Package** tab: check that version X.Y.Z and the name CamAlert are shown.
4. **Store listing** tab: paste the English description, choose the category **Tools** and the language
   **English**, upload the icon (`players/web/extension/icon.png`, 128x128), the four screenshots, the small promo
   tile `promo-440x280.png` and optionally the marquee `marquee-1400x560.png`, and fill in the homepage and support
   URL. Press **Save draft**. Then pick each other language at the top of the tab and paste its description.
5. **Privacy** tab: paste the single purpose and the four permission justifications, answer *No* to remote code,
   tick *Authentication information* and the three certifications, enter the privacy policy URL. **Save draft**.
6. **Distribution** tab: *Free*, visibility **Public** (or **Unlisted** for a first test), all regions. **Save
   draft**.
7. **Test instructions** tab: paste the text above. **Save draft**.
8. Press **Submit for review** (top right) and confirm. The review takes a few days; the result comes by e-mail.

A new version later: **Package › Upload new package** with the zip of the new release, then **Submit for review**.
Edge Add-ons (Partner Center) takes the same zip, texts and images.
