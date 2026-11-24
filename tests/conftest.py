"""pytest setup: puts the tests folder on sys.path (for `import _paths`) and marks tests by area (#27)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import _paths  # noqa: E402,F401

# folder (under tests/) or file name -> marker; run one area with e.g. `pytest -m kodi`
FOLDERS = {"core": "core", "contract": "contract", "enigma2": "enigma2", "kodi": "kodi", "homeassistant": "ha",
           "build": "build"}
FILES = {
    "ha": ("test_ha_integration", "test_blueprints"),
    "build": ("test_build", "test_private", "test_translations", "test_ci"),
}


def pytest_collection_modifyitems(config, items):
    import pytest
    for item in items:
        rel = os.path.relpath(str(item.fspath), HERE).replace(os.sep, "/")
        area = FOLDERS.get(rel.split("/")[0]) if "/" in rel else None
        if area is None:
            name = os.path.splitext(os.path.basename(rel))[0]
            area = next((a for a, files in FILES.items() if name in files), None)
        if area:
            item.add_marker(getattr(pytest.mark, area))
