"""The HTTP API contract (#4): one table, run against the Enigma2 and the Kodi API handler.

Each row: request (path, args, caller address, tokens, settings, method), expected status code, expected JSON
(subset: every key given must match), expected controller calls (None = not checked) and an optional check.
Known differences between a player and the contract live in KNOWN in test_http_contract.py, each tied to an
issue; a fixed difference makes its KNOWN entry stale, which fails the test.
"""

# A public address. Since #52 the RFC 5737 documentation ranges are outside the local network too (DOC below).
WAN = "8.8.8.8"
DOC = "203.0.113.9"
TAILSCALE = "100.101.102.103"
LAN = "192.168.1.5"
HA_UA = "HomeAssistant/2026.11 aiohttp/3.10"
CAMERAS = ["front_door", "garden"]


def row(name, path, args=None, code=200, json=None, calls=None, ip=LAN, header=None, user_agent="", settings=None,
        method="POST", check=None, ctl=None, cameras=None, body=None, headers=None):
    """method: POST for actions (the parameters go into a form body), GET for reads. body: raw JSON body.
    headers: response headers that must be there ({name: value}, value None = must be absent)."""
    return {"name": name, "path": path, "args": args or {}, "code": code, "json": json, "calls": calls, "ip": ip,
            "header": header, "user_agent": user_agent, "settings": settings or {}, "method": method,
            "check": check, "ctl": ctl or {}, "cameras": cameras, "body": body, "headers": headers or {}}


def get(name, path, args=None, **kw):
    return row(name, path, args, method="GET", **kw)


def no_snapshot_paths(body):
    ev = body["events"]
    return ev and ev[0]["camera"] == "garden" and all("snapshot" not in e for e in ev)


def no_spoken_key(body):
    return isinstance(body, dict) and "spoken" not in body  # #89: only with say / say_url


def log_lines(body):
    return isinstance(body.get("lines"), list)


def prometheus(body):
    return isinstance(body, str) and "camalert_uptime_seconds" in body and "camalert_requests_total" in body


STATUS_KEYS = ("result", "version", "id", "name", "window", "live", "paused", "dnd", "platform", "api_version",
               "capabilities", "min_ha_version", "mqtt", "screen", "position", "size",
               "configured", "button_signing")
SCREENS = ("none", "photo", "strip", "notification", "live", "mosaic", "tour")  # status "screen" (#63)


def status_keys(body):
    return all(k in body for k in STATUS_KEYS) and body["result"] is True and body["api_version"] == 1 and \
        {"post", "header_token", "show", "ptz", "screen", "settings", "setup", "test"} <= set(body["capabilities"]) and \
        body["screen"] in SCREENS


TABLE = [
    # --- access: address allowlist, tokens, enabled, methods -------------------------------------------------
    row("lan_without_token", "/camalert/hide", json={"result": True, "action": "hide"}, calls=[("hide",)]),
    row("wan_refused", "/camalert/hide", ip=WAN, code=403, json={"result": False, "error": "forbidden"}, calls=[]),
    row("documentation_range_refused", "/camalert/hide", ip=DOC, code=403, calls=[]),
    row("tailscale_allowed", "/camalert/hide", ip=TAILSCALE, calls=[("hide",)]),
    row("wan_allowed_with_any", "/camalert/hide", ip=WAN, settings={"allow": "any"}, calls=[("hide",)]),
    row("token_missing", "/camalert/hide", settings={"token": "secret"}, code=403, json={"error": "forbidden"},
        calls=[]),
    row("token_wrong_header", "/camalert/hide", header="bad", settings={"token": "secret"}, code=403, calls=[]),
    row("token_header", "/camalert/hide", header="secret", settings={"token": "secret"}, calls=[("hide",)]),
    get("token_query_deprecated", "/camalert/status", {"token": "secret"}, settings={"token": "secret"},
        json={"result": True}),
    row("disabled", "/camalert/hide", settings={"enabled": False}, json={"result": False, "error": "disabled"},
        calls=[]),
    row("unknown_action", "/camalert/nonsense", code=404, json={"result": False, "error": "unknown action"}),
    row("method_not_allowed", "/camalert/hide", method="PUT", code=405, calls=[]),
    row("internal_error", "/camalert/hide", code=500, json={"result": False, "error": "internal error"},
        ctl={"fail": "hide"}),
    # --- show --------------------------------------------------------------------------------------------------
    row("show_all_parameters", "/camalert/show", {"cam": "garden", "sec": "20", "mode": "live", "priority": "alarm"},
        json={"result": True, "action": "show", "cam": "garden"},
        calls=[("show", "garden", 20, "live", "alarm", "api", None)], headers={"Deprecation": None}),
    row("show_default_camera", "/camalert/show", json={"result": True, "action": "show", "cam": "front_door"},
        calls=[("show", None, None, None, None, "api", None)]),
    row("show_from_home_assistant", "/camalert/show", {"cam": "garden", "label": "Person"}, user_agent=HA_UA,
        calls=[("show", "garden", None, None, None, "ha", "Person")]),
    row("show_seconds_clamped", "/camalert/show", {"cam": "garden", "sec": "999"},
        calls=[("show", "garden", 300, None, None, "api", None)]),
    row("show_until_hide", "/camalert/show", {"cam": "garden", "sec": "0"},  # #81: until hide, at most HOLD_SECONDS
        calls=[("show", "garden", 600, None, None, "api", None)]),
    row("show_until_hide_json", "/camalert/show", body=b'{"cam": "garden", "sec": 0}',
        calls=[("show", "garden", 600, None, None, "api", None)]),
    row("show_several_cameras", "/camalert/show", {"cam": "garden, front_door", "mode": "strip"},
        calls=[("show", "garden,front_door", None, "strip", None, "api", None)]),
    row("show_alias", "/camalert/camalert", json={"result": True, "action": "show"}),
    row("show_ignored", "/camalert/show", {"cam": "garden"}, json={"result": False, "action": "ignore"},
        ctl={"results": {"show": "ignore"}}),
    row("show_invalid_camera_name", "/camalert/show", {"cam": "../etc/passwd"}, code=400,
        json={"result": False, "error": "invalid camera name"}, calls=[]),
    row("show_camera_url_refused", "/camalert/show", {"cam": "http://203.0.113.9/x.jpg"}, code=400, calls=[]),
    row("show_invalid_mode", "/camalert/show", {"cam": "garden", "mode": "fullscreen"}, code=400, calls=[]),
    # #89 spoken announcement: say_url only into the local network (no DNS: IP addresses and local names), checked
    # before anything is shown; never spoken for a test, or below the `speak` setting (default high)
    row("show_say_url_internet_refused", "/camalert/show", {"cam": "garden", "say_url": "http://8.8.8.8/x.wav"},
        code=400, json={"result": False}, calls=[]),
    row("show_say_url_dns_name_refused", "/camalert/show", {"cam": "garden", "say_url": "https://tts.example.com/x.wav"},
        code=400, json={"result": False}, calls=[]),
    row("show_say_url_not_http_refused", "/camalert/show", {"cam": "garden", "say_url": "file:///etc/passwd"},
        code=400, calls=[]),
    row("show_say_test_not_spoken", "/camalert/show",
        {"cam": "garden", "priority": "high", "say": "Someone is at the door",
         "say_url": "http://192.168.1.20:8123/api/tts_proxy/abc.wav", "test": "1"},
        json={"result": True, "action": "show", "spoken": False}),
    row("show_say_normal_priority_not_spoken", "/camalert/show",
        {"cam": "garden", "say": "Motion", "say_url": "http://192.168.1.20:8123/api/tts_proxy/abc.wav"},
        json={"result": True, "action": "show", "spoken": False}),
    row("show_say_off_not_spoken", "/camalert/show",
        {"cam": "garden", "priority": "high", "say": "Someone is at the door"}, settings={"speak": "off"},
        json={"result": True, "action": "show", "spoken": False}),
    row("show_without_say_has_no_spoken_key", "/camalert/show", {"cam": "garden"},
        check=no_spoken_key),
    row("show_invalid_priority", "/camalert/show", {"cam": "garden", "priority": "urgent"}, code=400, calls=[]),
    row("show_json_body", "/camalert/show", body=b'{"cam": "garden", "sec": 20, "priority": "high"}',
        calls=[("show", "garden", 20, None, "high", "api", None)]),
    row("show_broken_json_body", "/camalert/show", body=b'{"cam": ', code=400, calls=[]),
    # --- test flag (#62): source "test" = no chime, event tagged; the flag itself is not passed on ----------------
    row("show_test_flag", "/camalert/show", {"cam": "garden", "test": "1"}, json={"result": True, "action": "show"},
        calls=[("show", "garden", None, None, None, "test", None)]),
    row("show_test_flag_from_home_assistant", "/camalert/show", {"cam": "garden", "test": "true"}, user_agent=HA_UA,
        calls=[("show", "garden", None, None, None, "test", None)]),
    row("show_test_flag_off", "/camalert/show", {"cam": "garden", "test": "0"},
        calls=[("show", "garden", None, None, None, "api", None)]),
    row("show_test_flag_invalid", "/camalert/show", {"cam": "garden", "test": "x"}, code=400,
        json={"result": False, "error": "test must be 1 or 0"}, calls=[]),
    row("mosaic_test_flag", "/camalert/mosaic", {"test": "1"}, calls=[("mosaic", None, 60)]),
    get("show_get_deprecated", "/camalert/show", {"cam": "garden"}, json={"result": True},
        calls=[("show", "garden", None, None, None, "api", None)], headers={"Deprecation": "true"}),
    # --- mosaic, tour ------------------------------------------------------------------------------------------
    row("mosaic", "/camalert/mosaic", {"cam": "a,b"}, json={"result": True, "action": "show"},
        calls=[("mosaic", "a,b", 60)]),
    row("mosaic_seconds", "/camalert/mosaic", {"sec": "20"}, calls=[("mosaic", None, 20)]),
    row("mosaic_invalid_camera", "/camalert/mosaic", {"cam": "a,b/c"}, code=400, calls=[]),
    row("tour_interval_clamped", "/camalert/tour", {"interval": "99"}, calls=[("tour", None, 60)]),
    row("tour_interval_invalid", "/camalert/tour", {"interval": "abc"}, calls=[("tour", None, None)]),
    row("tour_failed", "/camalert/tour", json={"result": False, "action": "error"}, ctl={"results": {"tour": "error"}}),
    # --- do not disturb ----------------------------------------------------------------------------------------
    row("dnd_on", "/camalert/dnd", {"on": "1"}, json={"result": True, "dnd": True}, calls=[("dnd", True)]),
    row("dnd_off", "/camalert/dnd", {"on": "0"}, json={"result": True, "dnd": False}, calls=[("dnd", False)]),
    get("dnd_state", "/camalert/dnd", settings={"dnd": True}, json={"result": True, "dnd": True}, calls=[],
        headers={"Deprecation": None}),
    row("dnd_invalid_value", "/camalert/dnd", {"on": "maybe"}, code=400, calls=[]),
    # --- window position and size (#84) ------------------------------------------------------------------------
    get("settings_read", "/camalert/settings", settings={"position": "bottom_left", "size": "large"},
        json={"result": True, "position": "bottom_left", "size": "large"}, calls=[], headers={"Deprecation": None}),
    row("settings_set_position", "/camalert/settings", {"position": "top_left"},
        json={"result": True, "position": "top_left", "size": "medium"}, calls=[]),
    row("settings_set_both", "/camalert/settings", {"position": "bottom_right", "size": "small"},
        json={"result": True, "position": "bottom_right", "size": "small"}),
    row("settings_json_body", "/camalert/settings", body=b'{"size": "large"}',
        json={"result": True, "position": "top_right", "size": "large"}),
    row("settings_invalid_position", "/camalert/settings", {"position": "middle"}, code=400, json={"result": False}),
    row("settings_invalid_size", "/camalert/settings", {"size": "huge"}, code=400, json={"result": False}),
    get("settings_get_with_value_deprecated", "/camalert/settings", {"size": "small"},
        json={"result": True, "size": "small"}, headers={"Deprecation": "true"}),
    # --- Home Assistant sets the player up (#122): never set up = any address, else only the local network ------
    row("setup_new_player", "/camalert/setup", {"server": "http://192.168.1.10:1984", "camera": "garden"},
        json={"result": True, "configured": True, "server": "http://192.168.1.10:1984", "camera": "garden"}, calls=[]),
    row("setup_bare_address_keeps_camera", "/camalert/setup", {"server": "192.168.1.10:1984"},
        json={"result": True, "server": "http://192.168.1.10:1984", "camera": "front_door"}),
    row("setup_new_player_any_address", "/camalert/setup", {"server": "https://ha.public.example:1984"},
        json={"result": True, "server": "https://ha.public.example:1984"}),
    row("setup_configured_lan", "/camalert/setup", {"server": "http://192.168.1.20:1984"},
        settings={"server": "http://192.168.1.10:1984"}, json={"result": True, "server": "http://192.168.1.20:1984"}),
    row("setup_configured_local_name", "/camalert/setup", {"server": "http://homeassistant.local:1984"},
        settings={"server": "http://192.168.1.10:1984"}, json={"result": True}),
    row("setup_configured_internet_refused", "/camalert/setup", {"server": "http://" + WAN + ":1984"},
        settings={"server": "http://192.168.1.10:1984"}, code=409,
        json={"result": False, "error": "already set up"}),
    row("setup_configured_public_name_refused", "/camalert/setup", {"server": "https://ha.public.example:1984"},
        settings={"server": "http://192.168.1.10:1984"}, code=409, json={"error": "already set up"}),
    row("setup_direct_mode_counts_as_set_up", "/camalert/setup", {"server": "http://" + WAN + ":1984"},
        settings={"source": "direct"}, code=409, json={"error": "already set up"}),
    row("setup_invalid_server", "/camalert/setup", {"server": "ftp://192.168.1.10/x"}, code=400,
        json={"result": False, "error": "invalid server"}),
    row("setup_missing_server", "/camalert/setup", code=400, json={"error": "invalid server"}),
    row("setup_invalid_camera", "/camalert/setup", {"server": "http://192.168.1.10:1984", "camera": "a,b"},
        code=400, json={"result": False}),
    row("setup_needs_the_token", "/camalert/setup", {"server": "http://192.168.1.10:1984"},
        settings={"token": "secret"}, code=403),
    row("setup_from_wan_refused", "/camalert/setup", {"server": "http://192.168.1.10:1984"}, ip=WAN, code=403),
    # --- Home Assistant installs a newer release (#126): fixed source, newer only, allow_update on by default ----
    row("update_newer", "/camalert/update", {"version": "99.0.0"}, json={"result": True, "version": "99.0.0"},
        calls=[("update", "99.0.0")]),
    row("update_v_prefix", "/camalert/update", {"version": "v99.0.1"}, json={"result": True, "version": "99.0.1"},
        calls=[("update", "99.0.1")]),
    row("update_not_newer", "/camalert/update", {"version": "0.0.0"}, code=400,
        json={"result": False, "error": "not newer than the installed version"}, calls=[]),
    row("update_invalid_version", "/camalert/update", {"version": "99.0"}, code=400,
        json={"result": False, "error": "invalid version"}, calls=[]),
    row("update_path_in_version", "/camalert/update", {"version": "../99.0.0"}, code=400,
        json={"error": "invalid version"}, calls=[]),
    row("update_missing_version", "/camalert/update", code=400, json={"error": "invalid version"}, calls=[]),
    row("update_off", "/camalert/update", {"version": "99.0.0"}, settings={"allow_update": False}, code=403,
        json={"result": False, "error": "updates from Home Assistant are off"}, calls=[]),
    row("update_needs_the_token", "/camalert/update", {"version": "99.0.0"}, settings={"token": "secret"},
        code=403, calls=[]),
    row("update_from_wan_refused", "/camalert/update", {"version": "99.0.0"}, ip=WAN, code=403, calls=[]),
    # --- camera control, webhook -------------------------------------------------------------------------------
    row("ptz", "/camalert/ptz", {"cam": "garden", "move": "left"}, json={"result": True, "cam": "garden", "move": "left"},
        calls=[("ptz", "left", "garden")]),
    row("ptz_camera_without_ptz", "/camalert/ptz", {"cam": "front_door", "move": "left"}, code=400,
        json={"result": False}, calls=[]),
    row("ptz_unknown_move", "/camalert/ptz", {"cam": "garden", "move": "jump"}, code=400, calls=[]),
    row("webhook_not_http", "/camalert/webhook", {"url": "ftp://192.168.1.20/x"}, code=400, json={"result": False}),
    row("webhook_set", "/camalert/webhook", {"url": "http://192.168.1.20:8123/api/webhook/abc"},
        json={"result": True, "webhook": True, "signed": False}),
    row("webhook_set_signed", "/camalert/webhook", {"url": "http://192.168.1.20:8123/api/webhook/abc",
                                                     "secret": "ab" * 32},
        json={"result": True, "webhook": True, "signed": True}),  # #82: colour keys signed with this secret
    row("webhook_invalid_secret", "/camalert/webhook", {"url": "http://192.168.1.20:8123/api/webhook/abc",
                                                         "secret": "not hex"}, code=400, json={"result": False}),
    row("webhook_removed_drops_secret", "/camalert/webhook", {"url": "", "secret": "ab" * 32},
        settings={"ha_webhook": "http://192.168.1.20:8123/api/webhook/abc", "ha_webhook_secret": "cd" * 32},
        json={"result": True, "webhook": False, "signed": False}),
    row("webhook_local_name", "/camalert/webhook", {"url": "http://homeassistant.local:8123/api/webhook/abc"},
        json={"result": True, "webhook": True}),
    row("webhook_internet_refused", "/camalert/webhook", {"url": "http://" + WAN + "/api/webhook/abc"}, code=400,
        json={"result": False}),
    row("webhook_internet_name_refused", "/camalert/webhook", {"url": "https://ha.public.example/hook"}, code=400),
    row("webhook_name_partly_public_refused", "/camalert/webhook", {"url": "https://ha.mixed.example/hook"}, code=400),
    row("webhook_unresolvable_name_refused", "/camalert/webhook", {"url": "https://nothing.example/hook"}, code=400),
    row("webhook_split_dns_name", "/camalert/webhook", {"url": "https://ha.split-dns.example:8123/api/webhook/abc"},
        json={"result": True, "webhook": True}),
    row("webhook_documentation_ip_refused", "/camalert/webhook", {"url": "http://" + DOC + "/hook"}, code=400),
    row("webhook_removed", "/camalert/webhook", {"url": ""}, json={"result": True, "webhook": False}),
    # --- read-only ---------------------------------------------------------------------------------------------
    get("status", "/camalert/status", check=status_keys),
    get("cameras", "/camalert/cameras", cameras=CAMERAS,
        json={"result": True, "cameras": [{"name": "front_door", "title": "Front door", "snapshot": True},
                                          {"name": "garden", "title": "Garden", "snapshot": True}]}),
    get("events_without_snapshot_paths", "/camalert/events", json={"result": True}, check=no_snapshot_paths),
    get("log", "/camalert/log", {"lines": "5"}, json={"result": True}, check=log_lines),
    get("metrics", "/camalert/metrics", check=prometheus),
    get("log_from_wan_needs_token", "/camalert/log", ip=WAN, settings={"allow": "any"}, code=403),
    get("events_from_wan_needs_token", "/camalert/events", ip=WAN, settings={"allow": "any"}, code=403),
    get("metrics_from_wan_needs_token", "/camalert/metrics", ip=WAN, settings={"allow": "any"}, code=403),
    get("log_from_wan_with_token", "/camalert/log", ip=WAN, header="secret",
        settings={"allow": "any", "token": "secret"}, json={"result": True}),
]

ROUTES = sorted({r["path"].rsplit("/", 1)[-1] for r in TABLE})
