# Monitoring

- **Prometheus**: `GET /camalert/metrics` on every player (requests by result, errors, camera not reachable, last
  event, uptime, on screen, do not disturb), with the label `platform="enigma2"` or `platform="kodi"`. Like `log`
  and `events` it only answers callers in the local network unless a token is set ([API](api.md#security)).
- **Grafana**: `grafana/camalert-dashboard.json` is a ready-made dashboard for players and Kodis.
- **Logs**: *Remote syslog* (`host:port`, UDP, RFC 5424, facility local0) sends `camalert.log` to Loki / Grafana
  Alloy or rsyslog as well ([logging](../user/features.md#logging)).
- **Rate limit**: the API answers at most 30 requests per 10 seconds per caller (then HTTP 429) and logs a warning
  when it is called from outside the local network without a token.
