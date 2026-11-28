"""#89: spoken announcement rules, the same on every player (camalert_core.speech, Speech.kt)."""
import io
import unittest

import _paths

_paths.core()
from camalert_core import api, speech  # noqa: E402

WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 24


class TestSpeech(unittest.TestCase):
    def test_setting(self):
        self.assertEqual(speech.SPEAK_CHOICES, ("off", "high", "all"))
        self.assertTrue(speech.speak_wanted("high", "high"))
        self.assertTrue(speech.speak_wanted("high", "alarm"))
        self.assertFalse(speech.speak_wanted("high", "normal"))
        self.assertTrue(speech.speak_wanted("all", "normal"))
        self.assertFalse(speech.speak_wanted("off", "alarm"))

    def test_request(self):
        self.assertEqual(speech.speech_request({}), (None, None))
        self.assertEqual(speech.speech_request({"say": "  Someone \\n at   the door "}), (None, "Someone \\n at the door"))
        self.assertEqual(len(speech.speech_request({"say": "x" * 999})[1]), speech.MAX_TEXT)
        url = "http://192.168.1.20:8123/api/tts_proxy/abc.wav"
        self.assertEqual(speech.speech_request({"say_url": url, "say": "Hi"}), (url, "Hi"))
        self.assertEqual(speech.speech_request({"say_url": "http://homeassistant.local:8123/a.wav"})[0],
                         "http://homeassistant.local:8123/a.wav")
        self.assertEqual(speech.speech_request({"say_url": "http://8.8.8.8/a.wav"}, "8.8.8.8")[0], "http://8.8.8.8/a.wav")
        for bad in ("http://8.8.8.8/a.wav", "https://tts.example.com/a.wav", "file:///etc/passwd", "ftp://192.168.1.2/a",
                    "http://192.168.1.2/" + "a" * 3000):
            with self.assertRaises(speech.SpeechError, msg=bad):
                speech.speech_request({"say_url": bad})

    def test_should_speak(self):
        url = "http://192.168.1.20/a.wav"
        self.assertTrue(speech.should_speak("high", "high", "ha", "show", url, None))
        self.assertTrue(speech.should_speak("high", "alarm", "api", "wake", None, "Alarm"))
        self.assertFalse(speech.should_speak("high", "high", "test", "show", url, None))  # #62
        self.assertFalse(speech.should_speak("high", "high", "menu", "show", url, None))  # #13
        self.assertFalse(speech.should_speak("high", "high", "ha", "ignore", url, None))  # Do not disturb, hours
        self.assertFalse(speech.should_speak("high", "high", "ha", "show", None, None))
        self.assertFalse(speech.should_speak("off", "alarm", "ha", "show", url, None))

    def test_wav(self):
        self.assertTrue(speech.is_wav(WAV))
        self.assertFalse(speech.is_wav(b"ID3\x04" + b"\x00" * 20))  # mp3
        self.assertFalse(speech.is_wav(b"RIFF"))

        class R(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        self.assertEqual(speech.fetch_wav("http://x", opener=lambda u, timeout: R(WAV)), WAV)
        with self.assertRaises(speech.SpeechError):
            speech.fetch_wav("http://x", opener=lambda u, timeout: R(b"ID3" + b"\x00" * 40))
        with self.assertRaises(speech.SpeechError):
            speech.fetch_wav("http://x", opener=lambda u, timeout: R(WAV + b"\x00" * speech.MAX_AUDIO))

    def test_api_calls_the_player_only_when_wanted(self):
        said = []

        class Ctl(object):
            last_caller = None

            def show(self, *a, **kw):
                return "show"

        class B(api.Backend):
            platform, version = "test", "9.9.9"

            def settings(self):
                return {"enabled": True, "allow": "lan", "token": "", "duration": 30, "camera": "front_door",
                        "dnd": False, "speak": "high"}

            def controller(self):
                return ctl

            def node(self):
                return "n", "N"

            def log(self, *a, **kw):
                pass

            def speak(self, url, text, priority):
                said.append((url, text, priority))
                return True
        ctl = Ctl()
        url = "http://192.168.1.20:8123/api/tts_proxy/abc.wav"
        req = api.Request("POST", "/camalert/show", {"cam": "garden", "priority": "high", "say": "Hi", "say_url": url},
                          ip="192.168.1.5")
        api.LIMIT.seen.clear()
        r = api.handle(B(), req)
        self.assertEqual((r.code, r.body["spoken"]), (200, True))
        self.assertEqual(said, [(url, "Hi", "high")])
        r = api.handle(B(), api.Request("POST", "/camalert/show", {"cam": "garden", "say": "Hi"}, ip="192.168.1.5"))
        self.assertFalse(r.body["spoken"])  # priority normal, setting high
        self.assertEqual(len(said), 1)
        self.assertIn("speak", api.CAPABILITIES)


if __name__ == "__main__":
    unittest.main()
