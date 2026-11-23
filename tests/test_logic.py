import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "CamAlert"))
import logic as L  # noqa: E402


class TestLogic(unittest.TestCase):
    def test_slug_and_names(self):
        self.assertEqual(L.slug("Zürich Süd Straße"), "zuerich_sued_strasse")
        self.assertEqual(L.display_name("front_door"), "Front door")

    def test_normalize_server(self):
        self.assertEqual(L.normalize_server("192.168.1.10"), "http://192.168.1.10:1984")
        self.assertEqual(L.normalize_server("http://cam.local:1984/"), "http://cam.local:1984")
        self.assertEqual(L.normalize_server("https://go2rtc.example"), "https://go2rtc.example:443")
        self.assertIsNone(L.normalize_server(""))
        self.assertIsNone(L.normalize_server("ftp://x"))

    def test_streams_from_json(self):
        self.assertEqual(L.streams_from_json('{"garden": {}, "front_door": {}, "bad name": {}}'), ["front_door", "garden"])
        self.assertEqual(L.streams_from_json("not json"), [])
        self.assertEqual(L.streams_from_json("[]"), [])

    def test_urls_and_refs(self):
        srv = "http://192.168.1.10:1984"
        url = L.rtsp_url(srv, "front_door")
        self.assertEqual(url, "rtspt://192.168.1.10:8554/front_door")
        self.assertEqual(L.snapshot_url(srv, "front_door", 320), srv + "/api/frame.jpeg?src=front_door&width=320")
        ref = L.service_ref(url, "Front door", 3)
        self.assertTrue(ref.startswith("4097:0:1:DC03:"))
        self.assertNotIn("rtspt://", ref)
        self.assertEqual(L.stream_from_ref(ref), "front_door")
        self.assertIsNone(L.stream_from_ref("1:0:19:EF10:421:1:C00000:0:0:0:"))

    def test_direct_mode(self):
        cred = "admin:" + "pw@"
        text = """# comment
Front door | rtsp://CRED192.168.1.20:554/stream2 | http://CRED192.168.1.20/cgi-bin/snap.cgi
Garden|rtsp://192.168.1.21/live
broken line
Garden | rtsp://192.168.1.22/dup
""".replace("CRED", cred)
        cams = L.parse_camera_file(text)
        self.assertEqual([c["name"] for c in cams], ["front_door", "garden"])
        self.assertIsNone(cams[1]["snapshot"])
        ref = L.service_ref(L.tcp_url(cams[0]["rtsp"]), "Front door")
        self.assertEqual(L.stream_from_ref(ref, cams), "front_door")
        self.assertIsNone(L.stream_from_ref(L.service_ref("rtspt://x/y", "X"), cams))
        b = L.bouquet_text("Cams", None, None, cameras=cams)
        self.assertIn("rtspt%3a//192.168.1.21/live:Garden", b)
        self.assertEqual(L.split_credentials("http://admin:" + "p%40ss@cam:8080/snap.jpg?x=1"),
                         ("http://cam:8080/snap.jpg?x=1", "admin", "p@ss"))
        self.assertEqual(L.split_credentials("http://cam/snap.jpg"), ("http://cam/snap.jpg", None, None))

    def test_bouquet(self):
        b = L.bouquet_text("Cameras", "http://192.168.1.10:1984", ["front_door", "garden"])
        self.assertTrue(b.startswith("#NAME Cameras\n"))
        self.assertEqual(b.count("#SERVICE 4097"), 2)
        self.assertIn("#DESCRIPTION Garden", b)
        tv = "#NAME User - bouquets (TV)\n"
        once = L.add_to_bouquets(tv)
        self.assertIn(L.BOUQUET_FILE, once)
        self.assertEqual(L.add_to_bouquets(once), once)

    def test_clamp_and_mode(self):
        self.assertEqual(L.clamp_seconds("2"), 5)
        self.assertEqual(L.clamp_seconds("999"), 300)
        self.assertEqual(L.clamp_seconds("x", 30), 30)
        self.assertEqual(L.pick_mode("live"), "live")
        self.assertEqual(L.pick_mode("evil", "photo"), "photo")

    def test_decide(self):
        self.assertEqual(L.decide(True, None, None, "a"), "ignore")
        self.assertEqual(L.decide(False, None, None, ""), "ignore")
        self.assertEqual(L.decide(False, "a", None, "a"), "ignore")
        self.assertEqual(L.decide(False, None, "a", "a"), "extend")
        self.assertEqual(L.decide(False, None, "b", "a"), "show")

    def test_should_pause(self):
        self.assertTrue(L.should_pause(True, "photo", False))
        self.assertTrue(L.should_pause(True, "notify", False))
        self.assertFalse(L.should_pause(True, "live", False))
        self.assertFalse(L.should_pause(True, "photo", True))
        self.assertFalse(L.should_pause(False, "photo", False))

    def test_time_window(self):
        self.assertTrue(L.in_time_window((12, 0), (7, 0), (23, 0)))
        self.assertFalse(L.in_time_window((23, 0), (7, 0), (23, 0)))
        self.assertFalse(L.in_time_window((6, 59), (7, 0), (23, 0)))
        self.assertTrue(L.in_time_window((1, 0), (22, 0), (6, 0)))
        self.assertFalse(L.in_time_window((12, 0), (22, 0), (6, 0)))
        self.assertTrue(L.in_time_window((3, 3), (8, 0), (8, 0)))

    def test_lowered_volume(self):
        self.assertEqual(L.lowered_volume(60, 50), 30)
        self.assertEqual(L.lowered_volume(60, 100), 60)
        self.assertEqual(L.lowered_volume(60, 0), 0)
        self.assertEqual(L.lowered_volume(60, 150), 60)

    def test_parse_cams_and_grid(self):
        self.assertEqual(L.parse_cams("front_door, garden garden;x"), ["front_door", "garden"])
        self.assertEqual(len(L.parse_cams(",".join("c%d" % i for i in range(12)))), 9)
        tiles = L.grid(4, 1920, 1080)
        self.assertEqual(len(tiles), 4)
        for x, y, w, h in tiles:
            self.assertTrue(0 <= x and x + w <= 1920 and 0 <= y and y + h <= 1080)
            self.assertLessEqual(abs(w * 9 // 16 - h), 1)
        self.assertEqual(len(L.grid(5, 1280, 720)), 5)
        self.assertEqual(L.grid(1, 1920, 1080)[0][2] > 1800, True)

    def test_mqtt_packets(self):
        c = L.mqtt_connect("dc1", "user", "pw", "camalert/x/availability")
        self.assertEqual(c[0], 0x10)
        self.assertIn(b"MQTT\x04", c)
        self.assertEqual(c[c.index(b"MQTT") + 5], 0x02 | 0x04 | 0x20 | 0x80 | 0x40)
        p = L.mqtt_publish("a/b", "x" * 200, retain=True)
        self.assertEqual(p[0], 0x31)
        self.assertEqual(p[1:3], bytes([0xCD, 0x01]))  # 205 = 0xCD 0x01 (variable length)
        pk, rest = L.mqtt_split(p + b"\x20\x02\x00" )
        self.assertEqual(len(pk), 1)
        self.assertEqual(rest, b"\x20\x02\x00")
        pk, rest = L.mqtt_split(rest + b"\x00")
        self.assertEqual((pk[0][0], rest), (2, b""))
        topic, payload = L.mqtt_parse_publish(0, L.mqtt_publish("camalert/x/show", "garden")[2:])
        self.assertEqual((topic, payload), ("camalert/x/show", b"garden"))
        self.assertEqual(L.mqtt_subscribe(1, ["a/#"]), b"\x82\x08\x00\x01\x00\x03a/#\x00")

    def test_mqtt_command(self):
        self.assertEqual(L.mqtt_command(b"garden"), {"cam": "garden"})
        self.assertEqual(L.mqtt_command(b'{"cam": "garden", "sec": 20, "x": 1}'), {"cam": "garden", "sec": 20})
        self.assertEqual(L.mqtt_command(b""), {})
        self.assertEqual(L.mqtt_command(b"{bad"), {})

    def test_discovery(self):
        msgs = dict(L.discovery("abc123", "CamAlert kitchen", [("front_door", "Front door")]))
        import json
        btn = json.loads(msgs["homeassistant/button/camalert_abc123/show_front_door/config"])
        self.assertEqual(btn["command_topic"], "camalert/abc123/show")
        self.assertEqual(btn["payload_press"], "front_door")
        self.assertEqual(btn["device"]["identifiers"], ["camalert_abc123"])
        self.assertIn("homeassistant/sensor/camalert_abc123/on_screen/config", msgs)

    def test_priority_rules(self):
        self.assertEqual(L.pick_priority("alarm"), "alarm")
        self.assertEqual(L.pick_priority("x"), "normal")
        self.assertTrue(L.blocked_by_rules("normal", True, False, False, False))
        self.assertTrue(L.blocked_by_rules("normal", False, True, True, True))
        self.assertFalse(L.blocked_by_rules("normal", True, True, True, False))
        self.assertFalse(L.blocked_by_rules("high", True, False, True, True))
        self.assertFalse(L.blocked_by_rules("alarm", True, False, True, True))

    def test_known_camera(self):
        self.assertTrue(L.known_camera("a", []))
        self.assertTrue(L.known_camera("a", ["a", "b"]))
        self.assertFalse(L.known_camera("x", ["a", "b"]))
        self.assertFalse(L.known_camera("", ["a"]))

    def test_key_action(self):
        self.assertEqual(L.key_action(352), "live")
        self.assertEqual(L.key_action(105), "prev")
        self.assertEqual(L.key_action(106), "next")
        self.assertEqual(L.key_action(174), "close")
        self.assertEqual(L.key_action(115), "pass")
        self.assertEqual(L.key_action(3), "close_pass")  # number 2
        self.assertEqual(L.key_action(402), "close_pass")  # channel up

    def test_clock_tuple(self):
        self.assertEqual(L.clock_tuple([7, 30]), (7, 30))
        self.assertEqual(L.clock_tuple("03:05"), (3, 5))
        self.assertEqual(L.clock_tuple(23 * 3600 + 60), (23, 1))
        self.assertEqual(L.clock_tuple(None), (0, 0))

    def test_valid_port(self):
        self.assertEqual(L.valid_port("8554", 1), 8554)
        self.assertEqual(L.valid_port(0, 8099), 8099)
        self.assertEqual(L.valid_port("x", 1883), 1883)
        self.assertEqual(L.valid_port(70000, 1883), 1883)

    def test_neighbour(self):
        self.assertEqual(L.neighbour(["a", "b", "c"], "c", 1), "a")
        self.assertEqual(L.neighbour(["a", "b", "c"], "a", -1), "c")
        self.assertEqual(L.neighbour(["a", "b"], "x", 1), "a")
        self.assertIsNone(L.neighbour([], "a", 1))

    def test_geometry(self):
        self.assertEqual(L.window_geometry("top_right", "medium", 1920, 1080), (1240, 40, 640, 360, 40))
        x, y, w, h, t = L.window_geometry("bottom_left", "small", 1280, 720)
        self.assertEqual((x, w), (26, 320))
        self.assertEqual(y + h + t, 720 - 26)

    def test_access(self):
        self.assertTrue(L.client_allowed("192.168.1.5"))
        self.assertTrue(L.client_allowed("::ffff:10.0.0.2"))
        self.assertTrue(L.client_allowed("127.0.0.1"))
        self.assertFalse(L.client_allowed("8.8.8.8"))
        self.assertTrue(L.client_allowed("8.8.8.8", "any"))
        self.assertFalse(L.client_allowed("garbage"))
        self.assertTrue(L.token_ok("", None))
        self.assertTrue(L.token_ok("s3cret", "s3cret"))
        self.assertFalse(L.token_ok("s3cret", "nope"))
        self.assertFalse(L.token_ok("s3cret", None))


if __name__ == "__main__":
    unittest.main()
