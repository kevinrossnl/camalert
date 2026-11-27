"""camalert_core.discovery: players announce themselves as _camalert._tcp.local. (#121)."""
import os
import shutil
import struct
import tempfile
import unittest

import _paths

_paths.core()
from camalert_core import discovery as d  # noqa: E402

INFO = d.service_info("00f1f52edd14", "CamAlert Kodi (Living room)", "kodi", "1.3.0", 1, 8099)
IP = "192.168.1.10"


def query(name, qtype, msg_id=0):
    return struct.pack("!HHHHHH", msg_id, 0, 1, 0, 0, 0) + d.encode_name(name) + struct.pack("!HH", qtype, 1)


class TestWhatIsAnnounced(unittest.TestCase):
    def test_txt_has_the_keys_and_never_a_token(self):
        self.assertEqual(INFO["txt"], [("id", "00f1f52edd14"), ("name", "CamAlert Kodi (Living room)"),
                                       ("platform", "kodi"), ("version", "1.3.0"), ("api_version", "1"),
                                       ("https", "0")])
        self.assertEqual(d.txt_record("x", "n", "enigma2", "1", 1, https=True)[-1], ("https", "1"))
        self.assertEqual([k for k, _ in INFO["txt"]], list(d.TXT_KEYS))

    def test_names(self):
        self.assertEqual(INFO["instance"], "CamAlert Kodi (Living room)")
        self.assertEqual(INFO["host"], "camalert-00f1f52edd14.local.")
        self.assertEqual(d.instance_name(" \n ", "ab12"), "CamAlert ab12")
        self.assertEqual(d.instance_name("a\tb\x00c", "x"), "a b c")
        long = d.instance_name("é" * 40, "x")
        self.assertLessEqual(len(long.encode("utf-8")), 63)
        self.assertEqual(long, "é" * 31)  # never half a character
        self.assertEqual(d.host_label("AB:CD/ef"), "camalert-ab-cd-ef.local.")
        self.assertEqual(d.host_label(""), "camalert-player.local.")
        self.assertIsNone(d.service_info("", "x", "kodi", "1", 1, 8099))

    def test_only_while_the_api_is_on(self):
        self.assertTrue(d.should_advertise({"enabled": True, "allow": "lan"}))
        self.assertTrue(d.should_advertise({"enabled": True, "allow": "any"}))
        self.assertFalse(d.should_advertise({"enabled": False, "allow": "lan"}))
        self.assertFalse(d.should_advertise({"enabled": True, "allow": "nobody"}))

    def test_avahi_file_is_escaped(self):
        info = d.service_info("id1", "Tom & <Jerry>", "enigma2", "1.3.0", 1, 8443, https=True)
        text = d.avahi_service(info)
        self.assertIn("<name>Tom &amp; &lt;Jerry&gt;</name>", text)
        self.assertIn("<type>_camalert._tcp</type>", text)
        self.assertIn("<port>8443</port>", text)
        self.assertIn("<txt-record>https=1</txt-record>", text)
        self.assertNotIn("token", text)


class TestMessages(unittest.TestCase):
    def test_service_query_gets_ptr_srv_txt_and_address(self):
        q = d.parse_query(query("_CamAlert._tcp.local.", d.PTR, 7))
        self.assertEqual(q[0], 7)
        self.assertEqual(q[1], [("_camalert._tcp.local.", d.PTR)])
        self.assertEqual(len(d.answers_for(q[1], INFO, IP)), 4)
        self.assertEqual(len(d.answers_for(q[1], INFO, "")), 3)  # no address known: no A record

    def test_other_questions(self):
        inst = "%s.%s" % (INFO["instance"], d.SERVICE_TYPE)
        self.assertEqual(len(d.answers_for([(d.SERVICES, d.PTR)], INFO, IP)), 1)
        self.assertEqual(len(d.answers_for([(inst.lower(), d.SRV)], INFO, IP)), 3)
        self.assertEqual(len(d.answers_for([(inst.lower(), d.TXT)], INFO, IP)), 1)
        self.assertEqual(len(d.answers_for([(INFO["host"], d.A)], INFO, IP)), 1)
        self.assertEqual(d.answers_for([("_http._tcp.local.", d.PTR), ("other.local.", d.A)], INFO, IP), [])

    def test_rubbish_and_answers_are_ignored(self):
        self.assertIsNone(d.parse_query(b""))
        self.assertIsNone(d.parse_query(b"\x00" * 12))  # no questions
        self.assertIsNone(d.parse_query(d.announcement(INFO, IP)))  # a response
        self.assertIsNone(d.parse_query(struct.pack("!HHHHHH", 0, 0, 1, 0, 0, 0) + b"\xc0\x0c"))  # pointer loop
        self.assertIsNone(d.parse_query(struct.pack("!HHHHHH", 0, 0, 1, 0, 0, 0) + b"\x05ab"))

    def test_compressed_question_names(self):
        raw = (struct.pack("!HHHHHH", 0, 0, 2, 0, 0, 0) + d.encode_name(d.SERVICE_TYPE) + struct.pack("!HH", 12, 1)
               + b"\x03xyz\xc0\x0c" + struct.pack("!HH", 1, 1))
        self.assertEqual(d.parse_query(raw)[1], [("_camalert._tcp.local.", 12), ("xyz._camalert._tcp.local.", 1)])

    def test_instance_label_may_contain_dots(self):
        info = d.service_info("id1", "Box 1.2", "enigma2", "1", 1, 8099)
        name = d.encode_name("Box 1.2." + d.SERVICE_TYPE)
        self.assertEqual(name[:8], b"\x07Box 1.2")

    def test_zeroconf_reads_the_announcement(self):
        try:
            from zeroconf import DNSIncoming
        except ImportError:
            self.skipTest("python-zeroconf not installed (it is in the Home Assistant test environment)")
        msg = DNSIncoming(d.announcement(INFO, IP))
        by_type = {}
        for rec in msg.answers():
            by_type.setdefault(rec.type, []).append(rec)
        srv, = by_type[d.SRV]
        self.assertEqual((srv.port, srv.server), (8099, INFO["host"]))
        txt, = by_type[d.TXT]
        self.assertIn(b"id=00f1f52edd14", txt.text)
        a, = by_type[d.A]
        self.assertEqual(a.address, bytes([192, 168, 1, 10]))
        self.assertTrue(all(r.ttl == 0 for r in DNSIncoming(d.announcement(INFO, IP, goodbye=True)).answers()))


class FakeSock(object):
    def __init__(self):
        self.sent, self.closed = [], False

    def sendto(self, data, addr):
        self.sent.append((data, addr))

    def recvfrom(self, n):
        import socket
        raise socket.timeout()

    def close(self):
        self.closed = True


class TestResponder(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.sock = FakeSock()
        self.r = d.Responder(ip=lambda: IP, sock_factory=lambda: self.sock, clock=lambda: self.now)

    def tearDown(self):
        self.r.stop()

    def test_announces_answers_and_says_goodbye(self):
        self.assertTrue(self.r.start(INFO))
        self.assertEqual(self.sock.sent[0][1], (d.MDNS_ADDR, d.MDNS_PORT))
        self.r.start(INFO)  # same info: no second announcement
        self.assertEqual(len(self.sock.sent), 1)
        reply = self.r.handle(query(d.SERVICE_TYPE, d.PTR), ("192.168.1.20", 5353))
        self.assertEqual(reply[1], (d.MDNS_ADDR, d.MDNS_PORT))
        self.assertIsNone(self.r.handle(query(d.SERVICE_TYPE, d.PTR), ("192.168.1.20", 5353)))  # once a second
        self.now += 1.5
        self.assertIsNotNone(self.r.handle(query(d.SERVICE_TYPE, d.PTR), ("192.168.1.20", 5353)))
        legacy = self.r.handle(query(d.SERVICE_TYPE, d.PTR, 42), ("192.168.1.20", 40000))
        self.assertEqual(legacy[1], ("192.168.1.20", 40000))
        self.assertEqual(struct.unpack("!HHH", legacy[0][:6]), (42, 0x8400, 1))  # its id and question back
        self.assertIsNone(self.r.handle(query("_http._tcp.local.", d.PTR), ("192.168.1.20", 5353)))
        self.r.stop()
        self.assertTrue(self.sock.closed)
        self.assertFalse(self.r.running)
        self.assertIsNone(self.r.handle(query(d.SERVICE_TYPE, d.PTR), ("192.168.1.20", 5353)))

    def test_socket_problem_is_logged_not_raised(self):
        logs = []

        def broken():
            raise OSError("address in use")
        r = d.Responder(log=lambda m, level="normal": logs.append(m), sock_factory=broken)
        self.assertFalse(r.start(INFO))
        self.assertIn("address in use", logs[0])


class FakeResponder(object):
    def __init__(self, ok=True):
        self.ok, self.info = ok, None

    def start(self, info):
        self.info = info if self.ok else None
        return self.ok

    def stop(self):
        self.info = None


class TestAdvertiser(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.avahi = True
        self.resp = FakeResponder()
        self.adv = d.Advertiser(avahi_dir=self.dir, running=lambda: self.avahi, responder=self.resp,
                                enabled=lambda: True)

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_avahi_when_it_runs(self):
        self.assertEqual(self.adv.update(INFO), "avahi")
        with open(self.adv.path, encoding="utf-8") as f:
            self.assertIn("<port>8099</port>", f.read())
        mtime = os.stat(self.adv.path).st_mtime_ns
        self.adv.update(INFO)  # unchanged: the file is not rewritten (avahi would reload)
        self.assertEqual(os.stat(self.adv.path).st_mtime_ns, mtime)
        self.assertIsNone(self.resp.info)
        self.adv.update(None)  # API off
        self.assertFalse(os.path.exists(self.adv.path))

    def test_responder_without_avahi_and_switching(self):
        self.avahi = False
        self.assertEqual(self.adv.update(INFO), "responder")
        self.assertEqual(self.resp.info, INFO)
        self.assertFalse(os.path.exists(self.adv.path))
        self.avahi = True
        self.assertEqual(self.adv.update(INFO), "avahi")
        self.assertIsNone(self.resp.info)
        self.avahi = False
        self.assertEqual(self.adv.update(INFO), "responder")
        self.assertFalse(os.path.exists(self.adv.path))  # no stale file next to the responder
        self.adv.stop()
        self.assertIsNone(self.resp.info)

    def test_read_only_or_missing_folder_uses_the_responder(self):
        adv = d.Advertiser(avahi_dir=os.path.join(self.dir, "missing"), running=lambda: True, responder=self.resp,
                           enabled=lambda: True)
        self.assertEqual(adv.update(INFO), "responder")
        adv = d.Advertiser(avahi_dir="", running=lambda: True, responder=FakeResponder(ok=False), enabled=lambda: True)
        self.assertIsNone(adv.update(INFO))  # nothing possible: logged, never raised

    def test_the_test_suite_never_announces(self):
        self.assertTrue(os.environ.get("CAMALERT_NO_ANNOUNCE"))  # set in tests/conftest.py
        adv = d.Advertiser(avahi_dir=self.dir, running=lambda: True, responder=self.resp)
        self.assertIsNone(adv.update(INFO))
        self.assertIsNone(self.resp.info)
        self.assertEqual(os.listdir(self.dir), [])


if __name__ == "__main__":
    unittest.main()
