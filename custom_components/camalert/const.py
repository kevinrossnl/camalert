"""Constants for the CamAlert integration."""
DOMAIN = "camalert"
CONF_HTTPS = "https"
CONF_VERIFY_SSL = "verify_ssl"
CONF_TOKEN = "token"
DEFAULT_PORT = 8099
MODES = ["photo", "live", "notify", "strip"]
PTZ_MOVES = ["up", "down", "left", "right", "zoom_in", "zoom_out", "home", "stop"]
BUTTONS = ["red", "green", "yellow", "blue"]
EVENT_BUTTON = "camalert_button"
SIGNAL_BUTTON = "camalert_button_%s"
SCAN_INTERVAL_SECONDS = 10
CAMERA_REFRESH_SECONDS = 300
PRIORITIES = ["normal", "high", "alarm"]
