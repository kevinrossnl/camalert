# Loxone, KNX, ioBroker, openHAB and Homey

CamAlert needs no Home Assistant: every system that can send an HTTP request or an MQTT message can show a camera on
the TV (#96). This page has a ready example per system. All examples use

- the player at `192.168.1.20` (CamAlert API port 8099; see [HTTP API](api.md));
- the camera `front_door` (its go2rtc name);
- a `POST` with a JSON body, priority `high` for the doorbell, so *Do not disturb* and the time rules do not hide it
  (see [priorities](home-assistant.md));
- the access token, when you set one in CamAlert, in the header `X-CamAlert-Token`.

The request in full:

```http
POST http://192.168.1.20:8099/camalert/show
Content-Type: application/json
X-CamAlert-Token: <your token, only when one is set>

{"cam": "front_door", "priority": "high", "label": "Doorbell"}
```

To show it on several players, send the request to each player. Over MQTT one message per player goes to
`camalert/<player id>/show` with the same JSON (see [MQTT](mqtt.md)); the player id is in `/camalert/status`.

## Loxone

The Miniserver sends HTTP requests with a **Virtual Output** (Loxone Config › Virtual Outputs):

1. Add a Virtual Output with the **Address** `http://192.168.1.20:8099`.
2. Below it add a **Virtual Output Command**:
   - **Command for ON**: `/camalert/show`
   - **HTTP Extensions for ON**: `Content-Type: application/json` (add `X-CamAlert-Token: ...` on a new line when
     you set a token)
   - **HTTP POST Command for ON**: `{"cam": "front_door", "priority": "high", "label": "Doorbell"}`
   - **HTTP Method for ON**: `POST`
3. Connect the doorbell input (for example the Intercom block's bell output, or a digital input) to the command.

A second command with `/camalert/hide` and an empty body closes the window again. The field names are the ones of
Loxone Config; the HTTP monitor (Loxone Config › Diagnostics › HTTP Monitor) shows what the Miniserver sends. A
forum example of a POST is listed under [sources](#sources).

## KNX

KNX itself has no HTTP: the doorbell is a group address on the bus. Two ways:

- **Through Home Assistant** (recommended when you have it): add the doorbell group address as a KNX
  `binary_sensor` (KNX panel or YAML with `state_address`), then use the CamAlert doorbell blueprint with that
  sensor (see [Home Assistant](home-assistant.md)). For a raw telegram the KNX integration also offers the
  `knx.telegram` trigger.
- **Through a KNX logic server** that can send HTTP requests (for example a LogicMachine, Gira X1 / HomeServer or
  Enertex EibPC): on a telegram of the doorbell group address, send the `POST` above. How to send an HTTP request
  differs per device; see its manual.

## ioBroker

In the **JavaScript** adapter (version 7.9.0 or newer has `httpPost`), a script on the doorbell state:

```js
on({ id: 'knx.0.doorbell', val: true }, () => {   // your doorbell state
    httpPost('http://192.168.1.20:8099/camalert/show',
        { cam: 'front_door', priority: 'high', label: 'Doorbell' },
        { timeout: 5000, headers: { 'Content-Type': 'application/json' /*, 'X-CamAlert-Token': '...' */ } },
        (error, response) => {
            if (error) console.error('CamAlert: ' + error);
        });
});
```

With the **MQTT** adapter connected to the same broker as the players, write the JSON to
`camalert/<player id>/show` instead.

## openHAB

A rule in the rules DSL on the doorbell item:

```java
rule "Doorbell on the TV"
when
    Item Doorbell changed to ON
then
    sendHttpPostRequest("http://192.168.1.20:8099/camalert/show", "application/json",
        '{"cam": "front_door", "priority": "high", "label": "Doorbell"}',
        newHashMap(/* "X-CamAlert-Token" -> "..." */), 5000)
end
```

`sendHttpPostRequest(url, contentType, content, headers, timeout)` is one of openHAB's HTTP actions; in JavaScript
rules it is `actions.HTTP.sendHttpPostRequest(...)` with the same parameters. With the MQTT binding, publish the JSON
to `camalert/<player id>/show` instead.

## Homey

On a **Homey Pro (2023)** use the built-in **Logic** card *Make a HTTP POST request* (in an Advanced Flow headers go on
separate lines) in a flow that starts on the doorbell:

- URL `http://192.168.1.20:8099/camalert/show`
- header `Content-Type: application/json` (and `X-CamAlert-Token: ...` when you set a token)
- body `{"cam": "front_door", "priority": "high", "label": "Doorbell"}`

On an older Homey the app *HTTP request flow cards* has a **POST JSON** card for the same request (the app is only
available for Homeys from 2019 and earlier).

## Checking it

Send the request once by hand with `test=1` added to the JSON (`"test": "1"`): the window appears without the
doorbell chime and the event is tagged *test* in the player's event list. An answer `{"result": true, ...}` means the
player accepted it; `403` means a token is missing or wrong, or the caller is outside the allowed network.

## Sources

- Loxone: [Virtual Output with an HTTP POST command, LoxForum thread with screenshots](https://www.loxforum.com/forum/german/software-konfiguration-programm-und-visualisierung/480027-virtual-output-configuration-assistance-to-configuration-with-http-post-command)
- Home Assistant: [KNX integration](https://www.home-assistant.io/integrations/knx/)
- ioBroker: [JavaScript adapter, `httpPost`](https://github.com/ioBroker/ioBroker.javascript/blob/master/docs/en/javascript.md)
- openHAB: [HTTP actions](https://www.openhab.org/javadoc/latest/org/openhab/core/model/script/actions/http)
- Homey: [built-in Logic HTTP card, Homey community](https://community.homey.app/t/any-http-request-flow-cards-that-work-with-a-homey-pro-2023/81872),
  [HTTP request flow cards app](https://homey.app/en-gl/app/com.internet/)
