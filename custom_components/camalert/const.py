"""Constants for the CamAlert integration."""
DOMAIN = "camalert"
CONF_HTTPS = "https"
CONF_VERIFY_SSL = "verify_ssl"
CONF_TOKEN = "token"
DEFAULT_PORT = 8099
DEFAULT_VERIFY_SSL = True  # check certificates, like the players do (UI review #2); off for CamAlert's own
MODES = ["photo", "live", "notify", "strip"]
NOTHING = "none"  # sensor state when no camera is on screen (translated)
PTZ_MOVES = ["up", "down", "left", "right", "zoom_in", "zoom_out", "home", "stop"]
BUTTONS = ["red", "green", "yellow", "blue"]
EVENT_BUTTON = "camalert_button"
SIGNAL_BUTTON = "camalert_button_%s"
SCAN_INTERVAL_SECONDS = 10
CAMERA_REFRESH_SECONDS = 300
PRIORITIES = ["normal", "high", "alarm"]
# Window position and size of a player (#84), the choices of its settings (tests check them against the core).
WINDOW_SETTINGS = {
    "position": ["top_right", "top_left", "bottom_right", "bottom_left"],
    "size": ["small", "medium", "large"],
}
