"""The fake cameras: the fake go2rtc of the tests (tests/fakes/go2rtc.py, solid colours) and the fake PTZ camera
(tools/e2e/fake_ptz.py). Both run on the receiver itself, on 127.0.0.1, only for the time of a run."""
import importlib.util
import os
import sys

E2E = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(E2E))
GO2RTC = os.path.join(ROOT, "tests", "fakes", "go2rtc.py")
PTZ = os.path.join(E2E, "fake_ptz.py")
CORE = os.path.join(ROOT, "core")


def _go2rtc():
    spec = importlib.util.spec_from_file_location("camalert_e2e_fake_go2rtc", GO2RTC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CAMERAS = dict(_go2rtc().CAMERAS)          # name -> (r, g, b)
NAMES = sorted(CAMERAS, key=lambda n: ("front_door", "garden", "driveway", "back_door").index(n)
               if n in ("front_door", "garden", "driveway", "back_door") else 9)
PTZ_CAMERA = NAMES[0]


def go2rtc_source():
    with open(GO2RTC, encoding="utf-8") as f:
        return f.read()


def ptz_source():
    with open(PTZ, encoding="utf-8") as f:
        return f.read()


def devices_line(port):
    """The devices file during a run: only the fake PTZ camera (Foscam CGI) on the receiver itself."""
    return "# CamAlert e2e run: fake camera, the real file is restored afterwards\n%s|foscam|127.0.0.1:%d|e2e|e2e\n" % (
        PTZ_CAMERA, port)


def schema_defaults(platform="enigma2"):
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    from camalert_core import schema
    return schema.defaults(platform)
