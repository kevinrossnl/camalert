"""Property-based tests for the pure core parsers (#34), with hypothesis.

CI profile: derandomized, at most 200 examples per test (fast and repeatable); HYPOTHESIS_PROFILE=nightly runs
more. A failing example found here becomes an ordinary unit test next to the module it breaks.
Skipped when hypothesis is not installed (it no longer supports Python 3.8; the core itself still runs there).
"""
import os
import unittest

import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import HealthCheck, given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

import _paths  # noqa: E402

_paths.core()
from camalert_core import rules, urls  # noqa: E402
from camalert_core.mqtt import codec  # noqa: E402
from camalert_core.obs.log import redact  # noqa: E402
from camalert_core.triggers import frigate  # noqa: E402

settings.register_profile("ci", max_examples=200, derandomize=True, deadline=None,
                          suppress_health_check=[HealthCheck.too_slow])
settings.register_profile("nightly", max_examples=5000, deadline=None, suppress_health_check=[HealthCheck.too_slow])
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "ci"))

topics = st.text(st.characters(blacklist_categories=("Cs",)), min_size=1, max_size=80)
secrets = st.text(st.sampled_from("abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!$%*+-_~"),
                  min_size=6, max_size=24)
names = st.from_regex(r"[A-Za-z0-9_.-]{1,24}", fullmatch=True)


class TestMqttCodec(unittest.TestCase):
    @given(st.integers(min_value=0, max_value=268435455))
    def test_remaining_length_round_trip(self, n):
        enc = codec._mqtt_len(n)
        self.assertLessEqual(len(enc), 4)
        packets, rest = codec.mqtt_split(b"\x30" + enc + b"\x00" * min(n, 0))
        if n == 0:
            self.assertEqual(packets, [(3, 0, b"")])
        else:  # body missing: nothing is complete yet, everything is kept
            self.assertEqual((packets, rest), ([], b"\x30" + enc))

    @given(topics, st.binary(max_size=2000), st.booleans())
    def test_publish_round_trip(self, topic, payload, retain):
        packet = codec.mqtt_publish(topic, payload, retain)
        packets, rest = codec.mqtt_split(packet + packet)
        self.assertEqual(rest, b"")
        self.assertEqual(len(packets), 2)
        kind, flags, body = packets[0]
        self.assertEqual((kind, flags & 1), (3, int(retain)))
        self.assertEqual(codec.mqtt_parse_publish(flags, body), (topic, payload))

    @given(st.binary(max_size=300), st.integers(min_value=1, max_value=299))
    def test_split_keeps_every_byte_in_order(self, data, cut):
        """Fed in two pieces, the splitter returns the same packets as in one go and loses nothing."""
        whole, rest = codec.mqtt_split(data)
        first, carry = codec.mqtt_split(data[:cut])
        second, rest2 = codec.mqtt_split(carry + data[cut:])
        self.assertEqual(first + second, whole)
        self.assertEqual(rest2, rest)

    @given(st.integers(min_value=0, max_value=15), st.binary(max_size=200))
    def test_parse_publish_never_crashes(self, flags, body):
        topic, payload = codec.mqtt_parse_publish(flags, body)
        self.assertIsInstance(topic, str)
        self.assertIsInstance(payload, bytes)


class TestRedact(unittest.TestCase):
    @given(secrets, st.sampled_from(["token", "password", "pwd", "pass", "api_key", "access_token", "key"]),
           st.sampled_from(["http", "https", "rtsp"]))
    def test_query_secrets_never_leak(self, secret, key, scheme):
        url = "%s://192.0.2.10:1984/api/x?src=cam1&%s=%s&width=640" % (scheme, key, secret)
        self.assertNotIn(secret, redact(url))
        self.assertNotIn(secret, redact("request failed: " + url + " (timed out)"))

    @given(names, secrets, st.sampled_from(["http", "https", "rtsp", "rtsps"]))
    def test_userinfo_never_leaks(self, user, secret, scheme):
        out = redact("%s://%s:%s@192.0.2.10:554/stream1" % (scheme, user, secret))
        self.assertNotIn(secret, out)
        self.assertIn("192.0.2.10:554/stream1", out)

    @given(secrets)
    def test_headers_and_json_never_leak(self, secret):
        for text in ("Authorization: Bearer %s" % secret, '{"token": "%s", "x": 1}' % secret,
                     "<wsse:Password Type=\"PasswordDigest\">%s</wsse:Password>" % secret, "password=%s" % secret):
            self.assertNotIn(secret, redact(text))

    @given(st.text(max_size=200))
    def test_redact_is_idempotent(self, text):
        once = redact(text)
        self.assertEqual(redact(once), once)


class TestUrls(unittest.TestCase):
    @given(names, st.integers(min_value=100, max_value=4000))
    def test_snapshot_url_quotes_the_name(self, name, width):
        url = urls.snapshot_url("http://192.0.2.10:1984", name, width)
        self.assertRegex(url, r"^http://192\.0\.2\.10:1984/api/frame\.jpeg\?src=[A-Za-z0-9_.%-]+&width=\d+$")

    @given(st.text(max_size=40))
    def test_unicode_and_spaces_never_break_the_query(self, name):
        url = urls.snapshot_url("http://192.0.2.10:1984", name or "x")
        query = url.split("?", 1)[1]
        self.assertNotIn(" ", query)
        self.assertEqual(query.count("&"), 1)

    @given(st.text(max_size=60))
    def test_normalize_server_is_a_fixed_point(self, text):
        n = urls.normalize_server(text)
        if n is not None:
            self.assertRegex(n, r"^https?://")
            self.assertEqual(urls.normalize_server(n), n)

    @given(st.ip_addresses(v=6).map(str), st.integers(min_value=1, max_value=65535))
    def test_ipv6_servers(self, host, port):
        n = urls.normalize_server("http://[%s]:%d" % (host, port))
        self.assertTrue(n.startswith("http://[") and n.endswith("]:%d" % port), n)
        rtsp = urls.rtsp_url(n, "cam1")
        self.assertIn("[", rtsp)

    @given(st.one_of(st.integers(), st.text(max_size=10), st.none(), st.floats(allow_nan=True)))
    def test_valid_port(self, value):
        p = urls.valid_port(value, 1984)
        self.assertTrue(1 <= p <= 65535)

    @given(st.one_of(st.integers(), st.text(max_size=10), st.none(), st.floats(allow_nan=True)))
    def test_clamp_seconds(self, value):
        s = rules.clamp_seconds(value)
        self.assertTrue(s == 30 or rules.MIN_SECONDS <= s <= rules.MAX_SECONDS)

    @given(st.dictionaries(st.text(max_size=12), st.recursive(
        st.none() | st.booleans() | st.integers() | st.text(max_size=20),
        lambda c: st.lists(c, max_size=3) | st.dictionaries(st.text(max_size=8), c, max_size=3), max_leaves=8),
        max_size=6))
    def test_derived_streams_never_crash(self, data):
        self.assertIsInstance(urls.derived_streams(data), set)


class TestFrigate(unittest.TestCase):
    EXAMPLE = ('{"type": "new", "after": {"id": "1700000000.1-abc", "camera": "front_door", "label": "person", '
               '"top_score": 0.81, "has_snapshot": true}}')

    @given(st.binary(max_size=300))
    def test_random_payloads_have_a_defined_fallback(self, payload):
        """Anything on the Frigate topic gives an event or None: never an exception."""
        out = frigate.frigate_event(payload)
        self.assertTrue(out is None or isinstance(out, dict))

    @given(st.integers(min_value=0, max_value=len(EXAMPLE) - 1), st.characters())
    def test_mutated_fixture(self, pos, ch):
        text = self.EXAMPLE[:pos] + ch + self.EXAMPLE[pos + 1:]
        out = frigate.frigate_event(text.encode("utf-8", "surrogatepass"))
        self.assertTrue(out is None or isinstance(out, dict))

    @given(st.text(max_size=30), st.text(max_size=30), st.text(max_size=60))
    def test_stream_mapping_never_crashes(self, camera, labels, camera_map):
        event = {"camera": camera, "label": "person", "id": "1"}
        out = frigate.frigate_stream(event, labels, camera_map)
        self.assertTrue(out is None or isinstance(out, str))


if __name__ == "__main__":
    unittest.main()
