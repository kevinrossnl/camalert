"""Enigma2-only helpers: service references, channel lists, remote keys, picons, chime, update source."""
import os
import wave
import unittest

import _paths

_paths.core()
from camalert_core import cameras  # noqa: E402
from camalert_core import urls  # noqa: E402

keys = picons = services = None


def setUpModule():
    """The Enigma2 package needs the fake Enigma2 modules to import."""
    global keys, picons, services
    import importlib
    from enigma2.harness import e2fake
    e2fake.install("openatv")
    keys = importlib.import_module("CamAlert.keys")
    picons = importlib.import_module("CamAlert.picons")
    services = importlib.import_module("CamAlert.services")


def tearDownModule():
    from enigma2.harness import e2fake
    e2fake.uninstall()


class TestServices(unittest.TestCase):
    def test_urls_and_refs(self):
        srv = "http://192.168.1.10:1984"
        url = urls.rtsp_url(srv, "front_door")
        self.assertEqual(url, "rtspt://192.168.1.10:8554/front_door")
        self.assertEqual(urls.snapshot_url(srv, "front_door", 320), srv + "/api/frame.jpeg?src=front_door&width=320")
        ref = services.service_ref(url, "Front door", 3)
        self.assertTrue(ref.startswith("4097:0:1:DC03:"))
        self.assertNotIn("rtspt://", ref)
        self.assertEqual(services.stream_from_ref(ref), "front_door")
        self.assertIsNone(services.stream_from_ref("1:0:19:EF10:421:1:C00000:0:0:0:"))

    def test_direct_mode(self):
        cred = "admin:" + "pw@"
        text = """# comment
Front door | rtsp://CRED192.168.1.20:554/stream2 | http://CRED192.168.1.20/cgi-bin/snap.cgi
Garden|rtsp://192.168.1.21/live
broken line
Garden | rtsp://192.168.1.22/dup
""".replace("CRED", cred)
        cams = cameras.parse_camera_file(text)
        ref = services.service_ref(urls.tcp_url(cams[0]["rtsp"]), "Front door")
        self.assertEqual(services.stream_from_ref(ref, cams), "front_door")
        self.assertIsNone(services.stream_from_ref(services.service_ref("rtspt://x/y", "X"), cams))
        b = services.bouquet_text("Cams", None, None, cameras=cams)
        self.assertIn("rtspt%3a//192.168.1.21/live:Garden", b)

    def test_bouquet(self):
        b = services.bouquet_text("Cameras", "http://192.168.1.10:1984", ["front_door", "garden"])
        self.assertTrue(b.startswith("#NAME Cameras\n"))
        self.assertEqual(b.count("#SERVICE 4097"), 2)
        self.assertIn("#DESCRIPTION Garden", b)
        tv = "#NAME User - bouquets (TV)\n"
        once = services.add_to_bouquets(tv)
        self.assertIn(services.BOUQUET_FILE, once)
        self.assertEqual(services.add_to_bouquets(once), once)

    def test_key_action(self):
        self.assertEqual(keys.key_action(352), "live")
        self.assertEqual(keys.key_action(105), "prev")
        self.assertEqual(keys.key_action(106), "next")
        self.assertEqual(keys.key_action(174), "close")
        self.assertEqual(keys.key_action(115), "pass")
        self.assertEqual(keys.key_action(3), "close_pass")  # number 2
        self.assertEqual(keys.key_action(402), "close_pass")  # channel up

    def test_titles(self):
        t = {"front_door": "Front door", "garden": "Back garden"}
        b = services.bouquet_text("Cams", "http://192.168.1.10:1984", ["front_door", "side_gate"], titles=t)
        self.assertIn(":Front door\n", b)
        self.assertIn("#DESCRIPTION Side gate", b)

    def test_place_in_bouquets(self):
        tv = '#NAME User - bouquets (TV)\n#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "userbouquet.fav.tv" ORDER BY bouquet\n'
        bottom = services.place_in_bouquets(tv)
        self.assertTrue(bottom.rstrip().endswith('"userbouquet.camalert.tv" ORDER BY bouquet'))
        top = services.place_in_bouquets(bottom, position="top")
        lines = top.splitlines()
        self.assertTrue(lines[0].startswith("#NAME"))
        self.assertIn("camalert", lines[1])
        self.assertIn("userbouquet.fav.tv", lines[2])
        self.assertEqual(top.count("camalert"), 1)
        self.assertEqual(services.place_in_bouquets(top, position="top"), top)  # unchanged when already right

    def test_place_keep(self):
        tv = "#NAME User - bouquets (TV)\n#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET \"a.tv\" ORDER BY bouquet\n"
        first = services.place_in_bouquets(tv, "cam.tv", "keep")
        self.assertTrue(first.rstrip().endswith('"cam.tv" ORDER BY bouquet'))
        moved = first.replace('#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "a.tv"', "X").replace(
            "#NAME User - bouquets (TV)\n", "#NAME User - bouquets (TV)\n" + first.splitlines()[-1] + "\n", 1)
        moved = "\n".join(l for i, l in enumerate(moved.splitlines()) if not (i == len(moved.splitlines()) - 1 and "cam.tv" in l)) + "\n"
        self.assertEqual(services.place_in_bouquets(moved, "cam.tv", "keep"), moved)
        self.assertNotEqual(services.place_in_bouquets(moved, "cam.tv", "bottom"), moved)

    def test_media_refs(self):
        self.assertTrue(services.is_media_ref("1:0:0:0:0:0:0:0:0:0:/media/hdd/movie/x.ts"))
        self.assertTrue(services.is_media_ref("4097:0:0:0:0:0:0:0:0:0:/media/autofs/Opnames/a b.mkv:a b"))
        self.assertFalse(services.is_media_ref("1:0:19:EF10:421:1:C00000:0:0:0:"))
        self.assertFalse(services.is_media_ref("4097:0:1:DC01:0:0:0:0:0:0:rtspt%3a//x/y:Y"))

    def test_update_source(self):
        self.assertEqual(services.github_repo("Package: x\nHomepage: https://github.com/someone/camalert\n"), "someone/camalert")
        self.assertIsNone(services.github_repo("Homepage: https://example.com/x"))

    def test_picons_and_chime(self):
        self.assertEqual(picons.picon_name("Grüner Weg"), "grunerweg.png")
        self.assertEqual(picons.picon_name("Tom & Jerry+*"), "tomandjerryplusstar.png")
        self.assertIsNone(picons.picon_name("!!"))
        cmd = services.chime_command("/x/chime.wav")
        self.assertEqual(cmd[0], "gst-launch-1.0")
        self.assertIn("location=/x/chime.wav", cmd)
        self.assertEqual(cmd[-1], "alsasink")
        import wave
        w = wave.open(os.path.join(_paths.ENIGMA2, "chime.wav"))
        self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate()), (1, 2, 22050))
        self.assertLess(w.getnframes() / 22050.0, 2.0)

    def test_ptz_keys(self):
        self.assertEqual(keys.ptz_key(keys.KEY_UP), "up")
        self.assertEqual(keys.ptz_key(keys.KEY_CHANNELUP), "zoom_in")
        self.assertEqual(keys.ptz_key(keys.KEY_OK), "home")
        self.assertEqual(keys.ptz_key(keys.KEY_EXIT), "leave")
        self.assertEqual(keys.ptz_key(115), "pass")
        self.assertIsNone(keys.ptz_key(keys.KEY_YELLOW))  # #42: YELLOW is not always a leave key
        self.assertEqual(keys.button_for(keys.KEY_YELLOW, "yellow", has_ptz=True), "ptz")
        self.assertEqual(keys.button_for(398, "blue", has_ptz=True), "red")
        self.assertIsNone(keys.button_for(352))

    def test_actionmaps_come_from_the_key_map(self):
        ctx, acts = keys.action_map_args("tour", {"hold": 1, "close": 2, "prev": 3, "next": 4, "live": 5})
        self.assertEqual(ctx, ["ColorActions", "DirectionActions", "OkCancelActions"])
        self.assertEqual(acts, {"ok": 1, "cancel": 2, "left": 3, "right": 4, "green": 5})
        self.assertEqual(keys.action_map_args("mosaic", {"close": 9}), (["OkCancelActions"], {"ok": 9, "cancel": 9}))


if __name__ == "__main__":
    unittest.main()
