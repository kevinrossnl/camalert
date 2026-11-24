# docs/ (and README.md) – documentation

Read the root [DEVELOPMENT.md](../DEVELOPMENT.md) first (privacy, how we work). Structure, words, generated parts and the
docs tests are described in [dev/docs.md](dev/docs.md); in short:

- `index.md` lists every page; `user/` for all users, `players/` for one player, `integrations/` for other systems,
  `dev/` for contributors. One fact on one page, other pages link to it. New pages go into `index.md`.
- English; glossary terms verbatim ([user/glossary.md](user/glossary.md)); **player** when Kodi is included,
  "receiver" only for Enigma2; **Kodi 19 or newer**.
- Never edit between `<!-- BEGIN generated -->` markers: `python3 tools/docs.py update` (key table, glossary,
  settings come from core).
- Images: drawn illustrations (`tools/readme_images.py`) or OSD-only screenshots with demo cameras
  ([dev/screenshots.md](dev/screenshots.md)); the privacy checklist ([dev/privacy.md](dev/privacy.md)) and
  `python3 tools/check_images.py --strip` before every image commit.
- Examples: `192.168.1.10`, `front_door`, `garden`, `<password>`, `<player>`.
- `python3 -m pytest tests/test_docs.py` (links, anchors, generated blocks, words) before a push.
