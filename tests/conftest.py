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
    "build": ("test_build", "test_private", "test_images", "test_translations", "test_i18n", "test_ci", "test_docs", "test_community"),
    "contract": ("test_fake_go2rtc", "test_network_guard"),
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



# --- Network guard (#73): no test reaches the network; see tests/netguard.py ----------------------------------------
import pytest  # noqa: E402

import netguard  # noqa: E402

netguard.install()


@pytest.fixture(autouse=True)
def network_guard(request):
    """Fails the test when it (or a thread it started) tried to reach a non-loopback address, also when the code
    under test swallowed the NetworkBlocked error."""
    netguard.CURRENT["test"] = request.node.nodeid
    yield
    netguard.CURRENT["test"] = None
    mine = netguard.blocked(request.node.nodeid)
    if mine:
        pytest.fail("network access blocked during this test (#73): %s; tests use fakes on 127.0.0.1 (tests/fakes)"
                    % ", ".join(mine), pytrace=False)


def pytest_sessionfinish(session, exitstatus):
    lines = netguard.summary()
    if lines:
        sys.stderr.write("\nNETWORK GUARD (#73): blocked outbound sockets:\n  %s\n" % "\n  ".join(lines))
        if session.exitstatus == 0:
            session.exitstatus = 1
