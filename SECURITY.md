# Security policy

## Supported versions

Security fixes are made for the **latest release** of CamAlert (Enigma2 plugin, Kodi add-on, Home Assistant
integration). Please update before you report a problem.

| Version | Supported |
|---|---|
| 1.x (latest release) | yes |
| older | no |

## Reporting a vulnerability

Please report vulnerabilities **privately**, never in a public issue, discussion or forum:

1. Go to the [Security tab](https://github.com/kevinrossnl/camalert/security) of the repository.
2. Choose **Report a vulnerability** (GitHub private vulnerability reporting). Only the maintainers can see it.
3. Describe the problem, the affected player and version, and the steps to reproduce it. Remove your own
   passwords, tokens, IP addresses and camera names from logs.

CamAlert is maintained by volunteers. We aim to confirm a report within 7 days and to agree a disclosure date with
you; a fix is published as a new release with a GitHub Security Advisory that credits you, unless you prefer not
to be named.

## Scope

In scope: the HTTP API and its access rules (local network only by default, optional access token), MQTT and Home
Assistant discovery, the Home Assistant integration and blueprints, the handling of camera passwords (devices
file, logs, diagnostics) and the packages and update feeds built by this repository.

Out of scope: go2rtc, Home Assistant, Kodi, Enigma2 images and the cameras themselves (report those to their own
projects), and setups where the CamAlert API is deliberately opened to the internet without an access token.

How CamAlert protects the API is described under [Security](docs/integrations/api.md#security) in the HTTP API page.
