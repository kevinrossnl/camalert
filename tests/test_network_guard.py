"""The test run is network-free (#73): the guard of tests/netguard.py blocks everything but loopback."""
import socket
import unittest
import urllib.request

import netguard
from fakes.go2rtc import FakeGo2rtc

LAN = "192.0.2.10"  # TEST-NET-1 (RFC 5737): never a real host


class TestNetworkGuard(unittest.TestCase):
    def test_installed_for_the_whole_run(self):
        self.assertTrue(netguard.installed())

    def test_tcp_to_the_lan_is_blocked(self):
        with netguard.expect_blocked() as seen:
            with socket.socket() as s:
                with self.assertRaises(netguard.NetworkBlocked) as cm:
                    s.connect((LAN, 1984))
                self.assertIn("not a loopback address", str(cm.exception))
                self.assertIsInstance(cm.exception, OSError)  # code under test sees a normal network error
                with self.assertRaises(OSError):
                    s.connect_ex((LAN, 1984))
        self.assertEqual(seen, [(LAN, 1984), (LAN, 1984)])

    def test_urlopen_and_host_names_are_blocked(self):
        with netguard.expect_blocked() as seen:
            with self.assertRaises(OSError):
                urllib.request.urlopen("http://%s:1984/api/streams" % LAN, timeout=2)
            with socket.socket() as s:
                with self.assertRaises(netguard.NetworkBlocked):
                    s.connect(("go2rtc.example.invalid", 1984))
        self.assertIn(("go2rtc.example.invalid", 1984), seen)
        self.assertEqual(len(seen), 2)

    def test_dns_of_real_names_is_blocked(self):
        with netguard.expect_blocked() as seen:
            for fn in (lambda h: socket.getaddrinfo(h, 80), socket.gethostbyname, socket.gethostbyname_ex):
                with self.assertRaises(netguard.NameBlocked) as cm:
                    fn("go2rtc.lan")
                self.assertIsInstance(cm.exception, socket.gaierror)  # code under test sees "name not known"
        self.assertEqual(seen, [("dns", "go2rtc.lan")] * 3)

    def test_reserved_names_fail_without_dns_and_without_failing_the_test(self):
        with netguard.expect_blocked() as seen:
            for host in ("nothing.invalid", "cam.test", b"x.localhost."):
                with self.assertRaises(socket.gaierror):
                    socket.getaddrinfo(host, 80)
            with self.assertRaises(UnicodeError):  # refused by Python itself, no lookup
                socket.getaddrinfo("\udcff" + "x" * 300, 80)
        self.assertEqual(seen, [])

    def test_addresses_and_localhost_resolve(self):
        self.assertEqual(socket.getaddrinfo("192.0.2.10", 80, socket.AF_INET)[0][4], ("192.0.2.10", 80))
        self.assertTrue(socket.getaddrinfo("localhost", 80))
        self.assertEqual(socket.gethostbyname("127.0.0.1"), "127.0.0.1")
        self.assertTrue(socket.getaddrinfo(None, 80))

    def test_udp_to_the_lan_is_blocked(self):
        with netguard.expect_blocked() as seen:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                with self.assertRaises(netguard.NetworkBlocked):
                    s.sendto(b"<14>syslog", (LAN, 514))
                with self.assertRaises(netguard.NetworkBlocked):
                    s.sendto(b"<14>syslog", 0, (LAN, 514))
        self.assertEqual(seen, [(LAN, 514), (LAN, 514)])

    def test_loopback_fakes_keep_working(self):
        fake = FakeGo2rtc().start()
        self.addCleanup(fake.server_close)
        self.addCleanup(fake.shutdown)
        with urllib.request.urlopen(fake.url + "/api/streams", timeout=5) as r:
            self.assertIn(b"front_door", r.read())
        port = fake.server_address[1]
        with socket.create_connection(("localhost", port), 2):
            pass
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.sendto(b"x", ("127.0.0.1", 9))

    def test_is_local(self):
        for a in (("127.0.0.1", 1), ("127.8.9.1", 1), ("::1", 1, 0, 0), ("localhost", 1), "/tmp/sock", b"\0abstract"):
            self.assertTrue(netguard.is_local(a), a)
        for a in (("192.168.1.10", 1984), ("10.0.0.1", 1), ("8.8.8.8", 53), ("fe80::1%eth0", 1, 0, 2),
                  ("example.invalid", 80), (b"192.0.2.1", 1)):
            self.assertFalse(netguard.is_local(a), a)


if __name__ == "__main__":
    unittest.main()
