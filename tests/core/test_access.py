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
