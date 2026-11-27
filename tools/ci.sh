#!/bin/sh
# The CI steps per area (#26, #54), used by .forgejo/workflows/tests.yml in both modes: one job per area on the
# workstation runner (parallel) and one job running every area in turn on the NAS fallback (sequential).
# Also works locally:  sh tools/ci.sh lint   (tools needs root + apt; the other areas only python3 + pytest).
#
#   tools     install the Debian packages in $PACKAGES
#   lint | core | unit | build | privacy   one area each (privacy needs CAMALERT_DENYLIST)
#   ha        Home Assistant runtime tests (#33) for HA_VERSION=latest|min (tests/homeassistant/requirements-*.txt):
#             a uv venv with the pinned pytest-homeassistant-custom-component; HA_PY=<python> uses an existing one
#   androidtv Android TV player (#64): JVM contract tests, debug APK, Android lint, golden APK listing. Needs JDK 17+;
#             the Android Gradle plugin downloads the SDK packages from dl.google.com (license accepted here).
#             Workstation runner only: with ANDROIDTV_SKIP set (NAS fallback) it prints why and does nothing.
#   pymatrix  compatibility matrix (#21): core, Enigma2, Kodi and contract tests on every Python the players run on
#             (PY_VERSIONS, default 3.8 .. 3.13), each in its own uv venv; the property tests (#34) need hypothesis,
#             which is installed from Python 3.9 on. Workstation runner only: PYMATRIX_SKIP set = skipped (NAS).
set -eu
area="${1:?usage: tools/ci.sh tools|lint|core|unit|build|privacy|ha|androidtv|pymatrix}"
case "$area" in
  tools)
    echo "apt: ${PACKAGES:?PACKAGES not set}"
    # shellcheck disable=SC2086
    { apt-get update -qq && apt-get install -y -qq --no-install-recommends $PACKAGES; } > /dev/null
    ;;
  lint)
    python3 -m pytest -m "lint" --junitxml=junit-lint.xml
    ;;
  core)
    # branch coverage of the core by tests/core alone must stay >= 90 %
    python3 -m coverage run --source=core/camalert_core -m pytest tests/core --junitxml=junit-core.xml
    python3 -m coverage report --fail-under=90
    ;;
  unit)
    python3 -m coverage run -m pytest --junitxml=junit-unit.xml
    python3 -m coverage report
    python3 -m coverage xml
    ;;
  build)
    python3 -m pytest -m build --junitxml=junit-build.xml
    python3 tools/build_ipk.py dist
    python3 tools/build_kodi.py dist
    ;;
  privacy)
    # blocks the GitHub mirror if anything personal slipped in (files and the whole commit history)
    test -n "${CAMALERT_DENYLIST:-}" || { echo "secret CAMALERT_DENYLIST missing"; exit 1; }
    python3 tools/check_private.py .
    python3 tools/check_images.py .   # no EXIF/text/ICC metadata in images (#8)
    git log --format='%an %ae%n%B' | python3 -c '
import os,re,sys
deny=[w.strip().lower() for w in re.split(r"[\n,]",os.environ["CAMALERT_DENYLIST"]) if len(w.strip())>=3]
t=sys.stdin.read().lower(); bad=[i+1 for i,w in enumerate(deny) if w in t]
print("commit history: %d problems" % len(bad)); sys.exit(1 if bad else 0)'
    ;;
  ha)
    v="${HA_VERSION:-latest}"
    py="${HA_PY:-}"
    if [ -z "$py" ]; then
      if ! command -v uv > /dev/null; then
        curl -LsSf "https://github.com/astral-sh/uv/releases/download/${UV_VERSION:-0.13.8}/uv-x86_64-unknown-linux-gnu.tar.gz" \
          | tar xz -C /usr/local/bin --strip-components=1
      fi
      # exact versions: homeassistant 2026.10 needs Python >= 3.14.2 (an older uv would pick 3.14.0)
      pyver=3.14.10; [ "$v" = min ] && pyver=3.13.18
      uv venv -q --clear -p "$pyver" ".venv-ha-$v"
      VIRTUAL_ENV=".venv-ha-$v" uv pip install -q -r "tests/homeassistant/requirements-$v.txt"
      py=".venv-ha-$v/bin/python"
    fi
    "$py" -m pytest tests/homeassistant -o asyncio_mode=auto --junitxml="junit-ha-$v.xml" \
      --cov=custom_components/camalert --cov-branch --cov-report=term-missing --cov-fail-under=90
    ;;
  androidtv)
    if [ -n "${ANDROIDTV_SKIP:-}" ]; then
      echo "androidtv SKIPPED: $ANDROIDTV_SKIP (the Android build runs only on the workstation runner, #64)"
      exit 0
    fi
    sdk="${ANDROID_HOME:-$PWD/.android-sdk}"
    # Accept the Android SDK license (https://developer.android.com/studio/terms), as `sdkmanager --licenses` would;
    # the Android Gradle plugin then installs the platform, build-tools and platform-tools it needs from
    # dl.google.com itself (checksums from Google's index). No cmdline-tools: since 23.0 its sdkmanager hands over
    # to a self-downloading "Android CLI" that failed in CI (#64).
    mkdir -p "$sdk/licenses"
    printf '\n24333f8a63b6825ea9c5514f83c2829b004d1fee' > "$sdk/licenses/android-sdk-license"
    export ANDROID_HOME="$sdk"
    cd players/androidtv
    ./gradlew --no-daemon --console=plain :api:test :app:assembleDebug :app:lintDebug
    cd ../..
    python3 tools/apk_listing.py check players/androidtv/app/build/outputs/apk/debug/app-debug.apk
    ;;
  pymatrix)
    if [ -n "${PYMATRIX_SKIP:-}" ]; then
      echo "pymatrix SKIPPED: $PYMATRIX_SKIP (the Python matrix runs only on the workstation runner, #21)"
      exit 0
    fi
    if ! command -v uv > /dev/null; then
      curl -LsSf "https://github.com/astral-sh/uv/releases/download/${UV_VERSION:-0.13.8}/uv-x86_64-unknown-linux-gnu.tar.gz" \
        | tar xz -C /usr/local/bin --strip-components=1
    fi
    failed=""
    for v in ${PY_VERSIONS:-3.8 3.9 3.10 3.11 3.12 3.13}; do
      echo "=== Python $v"
      uv venv -q --clear -p "$v" ".venv-py$v"
      extra="hypothesis"; [ "$v" = 3.8 ] && extra=""
      # shellcheck disable=SC2086
      VIRTUAL_ENV=".venv-py$v" uv pip install -q pytest pyyaml pillow $extra
      ".venv-py$v/bin/python" -m pytest -q tests/core tests/enigma2 tests/kodi tests/contract \
        --junitxml="junit-py$v.xml" || failed="$failed $v"
    done
    test -z "$failed" || { echo "pymatrix failed on Python$failed"; exit 1; }
    ;;
  *)
    echo "unknown area: $area" >&2
    exit 2
    ;;
esac
