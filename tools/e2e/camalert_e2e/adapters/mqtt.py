"""MQTT for the mqtt scenario (#77): publishes one CamAlert command to the broker the players listen to.

Uses the core's own MQTT codec (QoS 0, no extra package). The broker and its login come from the profile file
(`mqtt:` with *_env names for the login, never literal secrets).
"""
import os
import socket
import sys

from .. import transport

_CORE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))), "core")
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)
from camalert_core.mqtt import codec  # noqa: E402


class Mqtt(object):
    def __init__(self, host, port=1883, user="", password="", prefix="camalert", connect=socket.create_connection,
                 timeout=10):
        self.host, self.port, self.user, self.password, self.prefix = host, int(port), user, password, prefix
        self.connect, self.timeout = connect, timeout

    def publish(self, topic, payload):
        """Connects, waits for CONNACK, publishes once (QoS 0) and disconnects."""
        s = self.connect((self.host, self.port), self.timeout)
        try:
            s.settimeout(self.timeout)
            s.sendall(codec.mqtt_connect("camalert-e2e-%d" % os.getpid(), self.user or None, self.password or None))
            buf = b""
            while True:
                chunk = s.recv(64)
                if not chunk:
                    raise transport.TransportError("MQTT broker closed the connection")
                buf += chunk
                packets, buf = codec.mqtt_split(buf)
                if packets:
                    kind, _flags, body = packets[0]
                    if kind != 2 or len(body) < 2 or body[1] != 0:
                        raise transport.TransportError("MQTT broker refused the login (CONNACK %r)" % body[-1:])
                    break
            s.sendall(codec.mqtt_publish(topic, payload))
            s.sendall(codec.MQTT_DISCONNECT)
        finally:
            s.close()

    def show(self, node, **command):
        """The same command Home Assistant's MQTT buttons send: <prefix>/<node>/show with a JSON payload."""
        import json
        self.publish("%s/%s/show" % (self.prefix, node), json.dumps(command))
