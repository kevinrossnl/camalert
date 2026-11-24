"""run.py, the fake PTZ camera, the ssh Box commands and the Home Assistant scenario of the e2e runner (#35)."""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
import urllib.request

from e2e_fakes import Clock, Receiver

import _paths

_paths.e2e()
import run as run_cli  # noqa: E402  (tools/e2e/run.py)
from camalert_e2e import profiles, scenarios as sc  # noqa: E402
from camalert_e2e.adapters import enigma2  # noqa: E402
from camalert_e2e.adapters.ha import HomeAssistant  # noqa: E402
from camalert_e2e.errors import Skip  # noqa: E402
from camalert_e2e.runner import Runner  # noqa: E402

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("e2e_fake_ptz", os.path.join(_paths.E2E, "fake_ptz.py"))
fake_ptz = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fake_ptz)


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.rx = Receiver(Clock())

    def tearDown(self):
        self.rx.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def main(self, *args, profile=None):
        path = os.path.join(self.tmp, "devices.json")
        with open(path, "w") as f:
            json.dump(profile or {"devices": {"boven": self.rx.profile(cameras="real", ssh="")}}, f)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = run_cli.main(["--profiles", path, "--reports", self.tmp] + list(args))
        return code, out.getvalue()

    def test_dry_run_and_errors(self):
        code, out = self.main("--device", "boven", "--dry-run", "--nobody-watching", "boven")
        self.assertEqual(code, 0, out)
        self.assertIn("boven: dry-run", out)
        self.assertEqual((self.rx.saveconfig_calls, self.rx.ctl.calls), ([], []))
        self.assertEqual(len(os.listdir(self.tmp)), 2)  # devices.json + one run folder
        k = Receiver(Clock())
        try:
            two = {"devices": {"boven": self.rx.profile(cameras="real", ssh=""),
                               "beneden": k.profile(cameras="real", ssh="")}}
            code, out = self.main("--device", "boven,beneden", "--dry-run", "--nobody-watching", "boven,beneden",
                                  profile=two)
            self.assertEqual(code, 0, out)
            run = out.split("report: ")[1].split(" ")[0]
            with open(os.path.join(run, "report.json")) as f:
                self.assertEqual([d["device"] for d in json.load(f)["devices"]], ["boven", "beneden"])
        finally:
            k.close()
        self.assertEqual(self.main()[0], 2)
        self.assertEqual(self.main("--device", "nope")[0], 2)
        self.assertEqual(self.main("--device", "boven", "--scenario", "dance")[0], 2)
        self.assertEqual(self.main("--device", "boven", profile={"devices": {}})[0], 2)

    def test_skipped_run_and_restore_last(self):
        code, out = self.main("--device", "boven", "--scenario", "show")
        self.assertEqual(code, 0)
        self.assertIn("nobody watching", out)
        code, out = self.main("--restore", "last")
        self.assertEqual((code, out.strip()), (0, "no earlier run to restore"))


class TestFakePtz(unittest.TestCase):
    def test_records_commands(self):
        tmp = tempfile.mkdtemp()
        calls = os.path.join(tmp, "calls.txt")
        srv = fake_ptz.FakePtz(calls_file=calls).start()
        try:
            base = "http://127.0.0.1:%d/cgi-bin/CGIProxy.fcgi?usr=e2e&pwd=e2e&cmd=" % srv.server_address[1]
            self.assertIn(b"<result>0</result>", urllib.request.urlopen(base + "ptzMoveLeft").read())
            self.assertIn(b"motionDetectAlarm", urllib.request.urlopen(base + "getDevState").read())
            with self.assertRaises(Exception):
                urllib.request.urlopen("http://127.0.0.1:%d/other" % srv.server_address[1])
            self.assertEqual(open(calls).read().split(), ["ptzMoveLeft", "getDevState"])
        finally:
            srv.shutdown()
            srv.server_close()
            shutil.rmtree(tmp)


class Shell(object):
    def __init__(self, answers):
        self.answers, self.cmds = list(answers), []

    def run(self, cmd, stdin=None, check=True):
        self.cmds.append((cmd, stdin))
        return self.answers.pop(0) if self.answers else ""


class TestBox(unittest.TestCase):
    def test_commands(self):
        sh = Shell(["", "4242\n", "stopped", '{"front_door": {}}', "existed\n", "", "", "ok\n", "a\nb\n"])
        box = enigma2.Box(sh)
        box.upload("go2rtc.py", "code")
        self.assertEqual(box.start("go2rtc.py", "--port 1"), 4242)
        box.stop(4242)
        self.assertIn("front_door", box.fetch("http://127.0.0.1:1/api/streams"))
        self.assertEqual(box.swap_devices(), "existed")
        box.write_devices("x|foscam|127.0.0.1:2|e2e|e2e\n")
        self.assertTrue(box.restore_devices("existed"))
        self.assertEqual(box.read_ptz_calls(), "a\nb\n")
        box.cleanup()
        self.assertEqual(sh.cmds[-1][0], "rm -rf %s" % enigma2.BOX_DIR)
        self.assertTrue(all(enigma2.DEVICES_FILE not in (stdin or "") for _, stdin in sh.cmds))
        self.assertIn("cp -p %s %s" % (enigma2.DEVICES_FILE, enigma2.DEVICES_BACKUP), sh.cmds[4][0])
        with self.assertRaises(Skip):
            enigma2.Box(Shell(["backup-exists\n"])).swap_devices()
        self.assertFalse(enigma2.Box(Shell(["", "left\n"])).restore_devices("absent"))


class TestHomeAssistantScenario(unittest.TestCase):
    def test_service_calls_reach_the_player(self):
        clock = Clock()
        rx = Receiver(clock)
        try:
            calls = []
            dev = enigma2.Enigma2(profiles.device("boven", rx.profile(cameras="real", ssh="", ha_device_id="dev1")),
                                  {}, sleep=clock.sleep)

            def http(url, method="GET", data=None, headers=None, timeout=10):
                body = json.loads(data) if data else None
                calls.append((url, body, headers["Authorization"]))
                if url.endswith("/show"):
                    rx.ctl.show(body["camera"], priority=body["priority"])
                elif url.endswith("/hide"):
                    rx.ctl.hide()
                return 200, []
            ha = HomeAssistant("http://192.168.1.5:8123/", "tok", http)
            ctx = sc.Context(dev, {}, ["porch"], None, {}, ha=ha, sleep=clock.sleep, clock=clock)
            r = sc.run("ha", ctx)
            self.assertEqual(r.status, "passed", r.checks)
            self.assertEqual(calls[0][:2], ("http://192.168.1.5:8123/api/services/camalert/show",
                                            {"device_id": "dev1", "camera": "porch", "priority": "normal",
                                             "seconds": 15}))
            self.assertEqual(calls[0][2], "Bearer tok")
            ctx.ha = None
            self.assertEqual(sc.run("ha", ctx).status, "skipped")
            bad = HomeAssistant("http://h", "t", lambda *a, **k: (401, {}))
            with self.assertRaises(Exception):
                bad.service("camalert", "hide", {})
            with self.assertRaises(Exception):
                bad.state("media_player.tv")
            self.assertEqual(HomeAssistant("http://h", "t", lambda *a, **k: (200, {"state": "off"})).state("m"), "off")
        finally:
            rx.close()

    def test_make_ha_needs_url_and_token(self):
        from camalert_e2e.runner import make_ha
        self.assertIsNone(make_ha({"url": "http://h", "token_env": "HA_T"}, {}))
        self.assertIsNotNone(make_ha({"url": "http://h", "token_env": "HA_T"}, {"HA_T": "x"}))
        self.assertIsInstance(Runner({}, {}, {}, tempfile.gettempdir(), environ={}).ha, type(None))


if __name__ == "__main__":
    unittest.main()
