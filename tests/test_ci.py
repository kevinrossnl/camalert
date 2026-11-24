"""CI runner choice (#54): tools/ci_pick_runner.py and the structure of .forgejo/workflows/tests.yml."""
import io
import json
import os
import re
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

import _paths

_paths.tools()
import ci_pick_runner as pick  # noqa: E402

try:
    import yaml
except ImportError:  # optional, like the blueprint tests
    yaml = None

WORKFLOW = os.path.join(_paths.ROOT, ".forgejo", "workflows", "tests.yml")
CI_SH = os.path.join(_paths.TOOLS, "ci.sh")
AREAS = ["lint", "core", "unit", "build", "privacy"]
PREF = ["werkstation", "skills-werkstation"]


def runner(name, labels, status):
    return {"name": name, "labels": labels, "status": status}


NAS = runner("nas", ["truenas", "staging-truenas"], "idle")


class Choose(unittest.TestCase):
    def test_idle_workstation_wins(self):
        r = [NAS, runner("ws", ["skills-werkstation"], "idle")]
        self.assertEqual(pick.choose(r, PREF)[:2], ("skills-werkstation", "parallel"))

    def test_first_preferred_label_wins(self):
        r = [runner("a", ["skills-werkstation"], "idle"), runner("b", ["werkstation", "playwright"], "idle")]
        self.assertEqual(pick.choose(r, PREF)[0], "werkstation")

    def test_idle_beats_busy_and_busy_beats_fallback(self):
        r = [runner("b", ["werkstation"], "active"), runner("a", ["skills-werkstation"], "idle")]
        self.assertEqual(pick.choose(r, PREF)[0], "skills-werkstation")
        r = [NAS, runner("b", ["werkstation"], "active")]
        self.assertEqual(pick.choose(r, PREF)[:2], ("werkstation", "parallel"))

    def test_offline_workstation_falls_back_sequential(self):
        r = [NAS, runner("ws", ["skills-werkstation"], "offline")]
        label, mode, reason = pick.choose(r, PREF)
        self.assertEqual((label, mode), ("truenas", "sequential"))
        self.assertIn("ws=offline", reason)
        self.assertEqual(pick.choose([], PREF)[:2], ("truenas", "sequential"))

    def test_unknown_status_falls_back(self):
        self.assertEqual(pick.choose(None, PREF)[:2], ("truenas", "sequential"))

    def test_force(self):
        online = [runner("ws", ["skills-werkstation"], "idle")]
        self.assertEqual(pick.choose(online, PREF, force="truenas")[:2], ("truenas", "sequential"))
        self.assertEqual(pick.choose(online, PREF, force=" TrueNAS ")[0], "truenas")
        self.assertEqual(pick.choose([runner("ws", ["skills-werkstation"], "active")], PREF, force="werkstation")[:2],
                         ("skills-werkstation", "parallel"))
        # without a runner list: the last preferred label (the one this repository can always use)
        self.assertEqual(pick.choose(None, PREF, force="werkstation")[0], "skills-werkstation")
        self.assertEqual(pick.choose(online, PREF, force="bogus")[:2], ("truenas", "sequential"))
        self.assertEqual(pick.choose(online, PREF, force="")[0], "skills-werkstation")


class _Api(BaseHTTPRequestHandler):
    body = b"[]"
    code = 200
    seen = []

    def do_GET(self):  # noqa: N802
        _Api.seen.append((self.path, self.headers.get("Authorization")))
        self.send_response(_Api.code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(_Api.body)

    def log_message(self, *args):
        pass


class Fetch(unittest.TestCase):
    def setUp(self):
        self.srv = HTTPServer(("127.0.0.1", 0), _Api)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = "http://127.0.0.1:%d" % self.srv.server_address[1]
        _Api.seen = []

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def run_main(self, **env):
        out, err = io.StringIO(), io.StringIO()
        base = {"GITHUB_SERVER_URL": self.url}
        base.update(env)
        import contextlib
        with contextlib.redirect_stderr(err):
            pick.main(base, out)
        return dict(line.split("=", 1) for line in out.getvalue().split()), err.getvalue()

    def test_online_runner_via_api(self):
        _Api.code, _Api.body = 200, json.dumps([runner("ws", ["skills-werkstation"], "idle")]).encode()
        res, err = self.run_main(RUNNER_STATUS_TOKEN="secret-value")
        self.assertEqual(res, {"runner": "skills-werkstation", "mode": "parallel"})
        self.assertEqual(_Api.seen, [("/api/v1/user/actions/runners?limit=50", "token secret-value")])
        self.assertNotIn("secret-value", err)

    def test_api_errors_fall_back(self):
        for code, body in ((403, b'{"message":"scope"}'), (200, b'{"not":"a list"}'), (200, b"garbage")):
            _Api.code, _Api.body = code, body
            res, err = self.run_main(RUNNER_STATUS_TOKEN="secret-value")
            self.assertEqual(res, {"runner": "truenas", "mode": "sequential"}, (code, body))
            self.assertNotIn("secret-value", err)

    def test_no_token_no_request(self):
        res, _ = self.run_main()
        self.assertEqual(res["runner"], "truenas")
        self.assertEqual(_Api.seen, [])

    def test_force_truenas_asks_nothing(self):
        res, err = self.run_main(RUNNER_STATUS_TOKEN="x", FORCE_RUNNER="truenas")
        self.assertEqual(res, {"runner": "truenas", "mode": "sequential"})
        self.assertEqual(_Api.seen, [])
        self.assertIn("forced", err)

    def test_labels_from_env(self):
        _Api.code, _Api.body = 200, json.dumps([runner("x", ["big"], "idle")]).encode()
        res, _ = self.run_main(RUNNER_STATUS_TOKEN="x", WORKSTATION_LABELS="big other", FALLBACK_LABEL="small")
        self.assertEqual(res["runner"], "big")


@unittest.skipIf(yaml is None, "pyyaml not installed")
class Workflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(WORKFLOW) as f:
            cls.wf = yaml.safe_load(f)
        cls.jobs = cls.wf["jobs"]

    def test_pick_runner_is_light_and_on_the_nas(self):
        job = self.jobs["pick-runner"]
        self.assertEqual(job["runs-on"], "truenas")
        self.assertLessEqual(job["timeout-minutes"], 2)
        self.assertEqual(set(job["outputs"]), {"runner", "mode"})
        text = json.dumps(job["steps"])
        self.assertNotIn("apt-get", text)
        self.assertIn("tools/ci_pick_runner.py", text)

    def test_heavy_jobs_use_the_picked_runner(self):
        for name in AREAS + ["sequential"]:
            job = self.jobs[name]
            self.assertEqual(job["runs-on"], "${{ needs.pick-runner.outputs.runner }}", name)
            self.assertEqual(job["needs"], "pick-runner", name)
            want = "sequential" if name == "sequential" else "parallel"
            self.assertEqual(job["if"], "needs.pick-runner.outputs.mode == '%s'" % want, name)

    def test_every_area_runs_in_both_modes(self):
        seq = json.dumps(self.jobs["sequential"]["steps"])
        for area in AREAS:
            self.assertIn("tools/ci.sh %s" % area, json.dumps(self.jobs[area]["steps"]), area)
            self.assertIn("tools/ci.sh %s" % area, seq, area)
        with open(CI_SH) as f:
            sh = f.read()
        for area in AREAS + ["tools"]:
            self.assertRegex(sh, r"(?m)^  %s\)$" % area)

    def test_gate_needs_everything_and_stays_light(self):
        gate = self.jobs["gate"]
        self.assertEqual(gate["if"], "always()")
        self.assertEqual(set(gate["needs"]), set(self.jobs) - {"gate"})
        self.assertEqual(gate["runs-on"], "truenas")
        env = gate["steps"][0]["env"]
        for area in AREAS:
            self.assertIn("needs.%s.result" % area, env["PARALLEL"])
        self.assertIn("needs.sequential.result", env["SEQUENTIAL"])

    def test_force_runner_input(self):
        on = self.wf.get("on", self.wf.get(True))
        opts = on["workflow_dispatch"]["inputs"]["force_runner"]
        self.assertEqual(opts["options"], ["auto", "werkstation", "truenas"])
        self.assertEqual(opts["default"], "auto")

    def test_secrets_only_where_needed(self):
        with open(WORKFLOW) as f:
            text = f.read()
        self.assertEqual(sorted(set(re.findall(r"secrets\.(\w+)", text))), ["CAMALERT_DENYLIST", "RUNNER_STATUS_TOKEN"])
        self.assertEqual(json.dumps(self.jobs["pick-runner"]).count("secrets.RUNNER_STATUS_TOKEN"), 1)
        for name, job in self.jobs.items():
            if name != "pick-runner":
                self.assertNotIn("RUNNER_STATUS_TOKEN", json.dumps(job), name)


if __name__ == "__main__":
    unittest.main()
