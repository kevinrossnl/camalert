"""Writes the golden listings after an INTENDED package change; review the diff before committing (#28):

    python3 -m tests.build.update_golden
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: E402

_paths.tools()
from build.listing import build_all  # noqa: E402

GOLDEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden")


def main():
    with tempfile.TemporaryDirectory() as d:
        for name, text in build_all(d).items():
            with open(os.path.join(GOLDEN, name), "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            print("wrote", os.path.join("tests", "build", "golden", name))


if __name__ == "__main__":
    main()
