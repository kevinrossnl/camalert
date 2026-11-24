"""The HTTP API contract (#4): one table, run against the Enigma2 and the Kodi API handler.

Each row: request (path, args, caller address, tokens, settings, method), expected status code, expected JSON
(subset: every key given must match), expected controller calls (None = not checked) and an optional check.
Known differences between a player and the contract live in KNOWN in test_http_contract.py, each tied to an
issue; a fixed difference makes its KNOWN entry stale, which fails the test.
"""

# A public address. Not an RFC 5737 one: Python counts 192.0.2.0/24, 198.51.100.0/24 and 203.0.113.0/24 as
# private (ipaddress.is_private), so client_allowed() lets them in like the LAN.
WAN = "8.8.8.8"
LAN = "192.168.1.5"
HA_UA = "HomeAssistant/2026.11 aiohttp/3.10"
CAMERAS = ["front_door", "garden"]


def row(name, path, args=None, code=200, json=None, calls=None, ip=LAN, header=None, user_agent="", settings=None,
        method="GET", check=None, ctl=None, cameras=None):
    return {"name": name, "path": path, "args": args or {}, "code": code, "json": json, "calls": calls, "ip": ip,
            "header": header, "user_agent": user_agent, "settings": settings or {}, "method": method,
            "check": check, "ctl": ctl or {}, "cameras": cameras}


def no_snapshot_paths(body):
    ev = body["events"]
    return ev and ev[0]["camera"] == "garden" and all("snapshot" not in e for e in ev)


def log_lines(body):
    return isinstance(body.get("lines"), list)


def prometheus(body):
    return isinstance(body, str) and "camalert_uptime_seconds" in body and "camalert_requests_total" in body


STATUS_KEYS = ("result", "version", "id", "name", "window", "live", "paused", "dnd", "platform")


def status_keys(body):
    return all(k in body for k in STATUS_KEYS) and body["result"] is True


TABLE = [
    # --- access: address allowlist, tokens, enabled -----------------------------------------------------------
    row("lan_without_token", "/camalert/hide", json={"result": True, "action": "hide"}, calls=[("hide",)]),
    row("wan_refused", "/camalert/hide", ip=WAN, code=403, json={"result": False, "error": "forbidden"}, calls=[]),
    row("wan_allowed_with_any", "/camalert/hide", ip=WAN, settings={"allow": "any"}, calls=[("hide",)]),
    row("token_missing", "/camalert/hide", settings={"token": "secret"}, code=403, json={"error": "forbidden"},
        calls=[]),
    row("token_wrong_header", "/camalert/hide", header="bad", settings={"token": "secret"}, code=403, calls=[]),
    row("token_header", "/camalert/hide", header="secret", settings={"token": "secret"}, calls=[("hide",)]),
    row("token_query", "/camalert/hide", {"token": "secret"}, settings={"token": "secret"}, calls=[("hide",)]),
    row("disabled", "/camalert/hide", settings={"enabled": False}, json={"result": False, "error": "disabled"},
        calls=[]),
    row("unknown_action", "/camalert/nonsense", code=404, json={"result": False, "error": "unknown action"}),
    row("internal_error", "/camalert/hide", code=500, json={"result": False, "error": "internal error"},
        ctl={"fail": "hide"}),
    # --- show --------------------------------------------------------------------------------------------------
    row("show_all_parameters", "/camalert/show", {"cam": "garden", "sec": "20", "mode": "live", "priority": "alarm"},
        json={"result": True, "action": "show", "cam": "garden"},
        calls=[("show", "garden", 20, "live", "alarm", "api", None)]),
    row("show_default_camera", "/camalert/show", json={"result": True, "action": "show", "cam": "front_door"},
        calls=[("show", None, None, None, None, "api", None)]),
    row("show_from_home_assistant", "/camalert/show", {"cam": "garden", "label": "Person"}, user_agent=HA_UA,
        calls=[("show", "garden", None, None, None, "ha", "Person")]),
    row("show_seconds_clamped", "/camalert/show", {"cam": "garden", "sec": "999"},
        calls=[("show", "garden", 300, None, None, "api", None)]),
    row("show_alias", "/camalert/camalert", json={"result": True, "action": "show"}),
    row("show_ignored", "/camalert/show", {"cam": "garden"}, json={"result": False, "action": "ignore"},
        ctl={"results": {"show": "ignore"}}),
    row("show_invalid_camera_name", "/camalert/show", {"cam": "../etc/passwd"}, code=400, calls=[]),
    row("show_post", "/camalert/show", {"cam": "garden"}, method="POST", json={"result": True, "action": "show"},
        calls=[("show", "garden", None, None, None, "api", None)]),
    # --- mosaic, tour ------------------------------------------------------------------------------------------
    row("mosaic", "/camalert/mosaic", {"cam": "a,b"}, json={"result": True, "action": "show"},
        calls=[("mosaic", "a,b", 60)]),
    row("mosaic_seconds", "/camalert/mosaic", {"sec": "20"}, calls=[("mosaic", None, 20)]),
    row("tour_interval_clamped", "/camalert/tour", {"interval": "99"}, calls=[("tour", None, 60)]),
    row("tour_interval_invalid", "/camalert/tour", {"interval": "abc"}, calls=[("tour", None, None)]),
    row("tour_failed", "/camalert/tour", json={"result": False, "action": "error"}, ctl={"results": {"tour": "error"}}),
    # --- do not disturb ----------------------------------------------------------------------------------------
    row("dnd_on", "/camalert/dnd", {"on": "1"}, json={"result": True}, calls=[("dnd", True)]),
    row("dnd_off", "/camalert/dnd", {"on": "0"}, json={"result": True}, calls=[("dnd", False)]),
    row("dnd_state", "/camalert/dnd", settings={"dnd": True}, json={"result": True, "dnd": True}, calls=[]),
    row("dnd_invalid_value", "/camalert/dnd", {"on": "maybe"}, calls=[]),
    # --- camera control, webhook -------------------------------------------------------------------------------
    row("ptz", "/camalert/ptz", {"cam": "garden", "move": "left"}, json={"result": True, "cam": "garden", "move": "left"},
        calls=[("ptz", "left", "garden")]),
    row("ptz_camera_without_ptz", "/camalert/ptz", {"cam": "front_door", "move": "left"}, code=400,
        json={"result": False}, calls=[]),
    row("ptz_unknown_move", "/camalert/ptz", {"cam": "garden", "move": "jump"}, code=400, calls=[]),
    row("webhook_not_http", "/camalert/webhook", {"url": "ftp://192.168.1.20/x"}, code=400, json={"result": False}),
    row("webhook_set", "/camalert/webhook", {"url": "http://192.168.1.20:8123/api/webhook/abc"},
        json={"result": True, "webhook": True}),
    row("webhook_removed", "/camalert/webhook", {"url": ""}, json={"result": True, "webhook": False}),
    # --- read-only ---------------------------------------------------------------------------------------------
    row("status", "/camalert/status", check=status_keys),
    row("cameras", "/camalert/cameras", cameras=CAMERAS,
        json={"result": True, "cameras": [{"name": "front_door", "title": "Front door", "snapshot": True},
                                          {"name": "garden", "title": "Garden", "snapshot": True}]}),
    row("events_without_snapshot_paths", "/camalert/events", json={"result": True}, check=no_snapshot_paths),
    row("log", "/camalert/log", {"lines": "5"}, json={"result": True}, check=log_lines),
    row("metrics", "/camalert/metrics", check=prometheus),
    row("log_from_wan_needs_token", "/camalert/log", ip=WAN, settings={"allow": "any"}, code=403),
]

ROUTES = sorted({r["path"].rsplit("/", 1)[-1] for r in TABLE})
