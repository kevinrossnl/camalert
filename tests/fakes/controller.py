"""A controller that records every call, for the HTTP and MQTT contract tests (same interface on both players)."""


class RecordingController(object):
    """Stands in for display.Controller (Enigma2) and controller.Controller (Kodi)."""

    def __init__(self, ptz=("garden",), results=None):
        self.calls = []
        self.ptz = set(ptz)
        self.results = dict({"show": "show", "mosaic": "show", "tour": "show"}, **(results or {}))
        self.events = [{"time": 1, "camera": "garden", "label": "", "source": "api", "priority": "normal",
                        "action": "show", "reason": "", "snapshot": "/tmp/x.jpg", "frigate_id": None}]
        self.last_caller = None
        self.names, self.names_at = [], 0.0      # Kodi
        self._names, self._names_at = [], 0.0    # Enigma2
        self.dnd = False
        self.fail = None  # name of a method that raises

    def _call(self, name, *args):
        self.calls.append((name,) + args)
        if self.fail == name:
            raise ValueError("boom")

    def show(self, stream=None, seconds=None, mode=None, priority=None, source="api", label=None, event_id=None):
        self._call("show", stream, seconds, mode, priority, source, label)
        return self.results["show"]

    def hide(self, resume=True):
        self._call("hide")

    def mosaic(self, streams=None, seconds=0):
        self._call("mosaic", streams, seconds)
        return self.results["mosaic"]

    def tour(self, streams=None, interval=None):
        self._call("tour", streams, interval)
        return self.results["tour"]

    def has_ptz(self, name):
        return bool(name) and name in self.ptz

    def ptz_move(self, action, name=None):
        self._call("ptz", action, name)
        return True

    def set_dnd(self, on):
        self._call("dnd", bool(on))
        self.dnd = bool(on)

    def status(self):
        return {"window": None, "live": None, "paused": False, "dnd": self.dnd}

    def camera_on_screen(self):
        return None, False
