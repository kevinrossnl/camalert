"""camalert_core.access: address allowlist, token, rate limit."""
import unittest

import _paths

_paths.core()
from camalert_core import access  # noqa: E402


class TestAccess(unittest.TestCase):
    def test_access(self):
        self.assertTrue(access.client_allowed("192.168.1.5"))
        self.assertTrue(access.client_allowed("::ffff:10.0.0.2"))
        self.assertTrue(access.client_allowed("127.0.0.1"))
        self.assertFalse(access.client_allowed("8.8.8.8"))
        self.assertTrue(access.client_allowed("8.8.8.8", "any"))
        self.assertFalse(access.client_allowed("garbage"))
        self.assertTrue(access.token_ok("", None))
        self.assertTrue(access.token_ok("s3cret", "s3cret"))
        self.assertFalse(access.token_ok("s3cret", "nope"))
        self.assertFalse(access.token_ok("s3cret", None))

    def test_lan_ranges(self):
        """#52: an explicit list of local ranges, CGNAT/Tailscale included, documentation ranges excluded."""
        lan = ("10.1.2.3", "172.16.0.1", "172.31.255.254", "192.168.1.5", "100.64.0.1", "100.101.102.103",
               "100.127.255.254", "127.0.0.1", "169.254.10.1", "::1", "fe80::1", "fe80::1%eth0", "fd00::1",
               "fd7a:115c:a1e0::1", "fc00::1", "::ffff:192.168.1.5", "::ffff:100.64.1.1", "[fd00::2]")
        outside = ("8.8.8.8", "192.0.2.1", "198.51.100.7", "203.0.113.9", "198.18.0.1", "2001:db8::1",
                   "100.63.255.255", "100.128.0.0", "172.32.0.1", "0.0.0.0", "255.255.255.255", "240.0.0.1",
                   "224.0.0.1", "2001:4860:4860::8888", "::ffff:8.8.8.8", "::ffff:203.0.113.9", "", None, "x")
        for ip in lan:
            self.assertTrue(access.lan_address(ip), ip)
            self.assertTrue(access.client_allowed(ip), ip)
        for ip in outside:
            self.assertFalse(access.lan_address(ip), ip)
            self.assertFalse(access.client_allowed(ip, "lan"), ip)
            self.assertTrue(access.client_allowed(ip, "any"), ip)

    def test_local_names(self):
        for h in ("homeassistant", "ha.local", "ha.lan", "ha.home", "ha.home.arpa", "ha.internal", "HA.LOCAL."):
            self.assertTrue(access.local_name(h), h)
        for h in ("", "example.com", "ha.local.example.com", None):
            self.assertFalse(access.local_name(h), h)

    def test_url_target(self):
        """#53: a host name is allowed when it resolves to LAN addresses only (resolved, never trusted)."""
        names = {"ha.split.example": ["192.168.1.20"], "ha.ts.example": ["100.101.102.103", "fd7a:115c:a1e0::5"],
                 "ha.public.example": ["203.0.113.10"], "ha.mixed.example": ["192.168.1.20", "8.8.8.8"]}
        asked = []

        def resolver(host):
            asked.append(host)
            return names.get(host, [])

        ok = ("http://192.168.1.20:8123/api/webhook/x", "https://[fd00::1]/x", "http://100.64.1.2/x",
              "http://homeassistant/x", "http://ha.local/x", "http://ha.home.arpa/x", "https://ha.split.example/x",
              "http://ha.ts.example:8123/x")
        for url in ok:
            self.assertIsNone(access.url_target(url, "192.168.1.5", resolver), url)
        self.assertNotIn("ha.local", asked)  # local names are never resolved
        self.assertIsNone(access.url_target("http://8.8.8.8/x", "8.8.8.8", resolver))  # the caller itself
        refused = {"ftp://192.168.1.20/x": "http", "http://:80/x": "invalid", "http://[zz/x": "invalid",
                   "http://8.8.8.8/x": "local network", "http://203.0.113.9/x": "local network",
                   "http://[2001:db8::1]/x": "local network", "https://ha.public.example/x": "local network",
                   "https://ha.mixed.example/x": "local network", "https://nothing.example/x": "does not resolve",
                   None: "http"}
        for url, why in refused.items():
            self.assertIn(why, access.url_target(url, "192.168.1.5", resolver) or "", url)

    def test_resolve(self):
        self.assertIn("127.0.0.1", access.resolve("127.0.0.1"))
        self.assertEqual(access.resolve("nothing.invalid"), [])
        self.assertEqual(access.resolve("\udcff" + "x" * 300), [])

    def test_rate_limit_and_exposure(self):
        r = access.RateLimiter(3, 10)
        self.assertEqual([r.allow("a", t) for t in (0, 1, 2, 3)], [True, True, True, False])
        self.assertTrue(r.allow("b", 3))
        self.assertTrue(r.allow("a", 11))
        self.assertTrue(access.exposed_without_token("any", "", "1.2.3.4"))
        self.assertFalse(access.exposed_without_token("any", "secret", "1.2.3.4"))
        self.assertFalse(access.exposed_without_token("any", "", "192.168.1.5"))
        self.assertFalse(access.exposed_without_token("lan", "", "1.2.3.4"))


if __name__ == "__main__":
    unittest.main()
