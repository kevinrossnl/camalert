"""pytest setup: puts the tests folder on sys.path (for `import _paths`) and marks tests by area (#27)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import _paths  # noqa: E402,F401

# file name -> marker; run one area with e.g. `pytest -m kodi`
AREAS = {
    "core": ("test_logic", "test_devices", "test_robustness", "test_logging_and_more", "test_imports", "test_lint"),
    "contract": ("test_http_contract", "test_mqtt_contract"),
    "enigma2": ("test_enigma2_images", "test_init_settings", "test_enigma2_server", "test_enigma2_mqtt"),
    "kodi": ("test_kodi", "test_kodi_versions"),
    "ha": ("test_ha_integration", "test_blueprints"),
    "build": ("test_build", "test_golden", "test_private", "test_translations"),
}


def pytest_collection_modifyitems(config, items):
    import pytest
    for item in items:
        name = os.path.splitext(os.path.basename(str(item.fspath)))[0]
        for area, files in AREAS.items():
            if name in files:
                item.add_marker(getattr(pytest.mark, area))
