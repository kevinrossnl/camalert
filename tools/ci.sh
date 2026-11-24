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
#             the Android SDK comes from dl.google.com (cmdline-tools checked against ANDROID_CMDLINE_SHA256).
#             Workstation runner only: with ANDROIDTV_SKIP set (NAS fallback) it prints why and does nothing.
set -eu
area="${1:?usage: tools/ci.sh tools|lint|core|unit|build|privacy|ha|androidtv}"
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
    if [ ! -x "$sdk/cmdline-tools/latest/bin/sdkmanager" ]; then
      zip="commandlinetools-linux-${ANDROID_CMDLINE_BUILD:-16111833}_latest.zip"
      curl -fsSL -o "/tmp/$zip" "https://dl.google.com/android/repository/$zip"
      echo "${ANDROID_CMDLINE_SHA256:-0877a1d048fe4a24efe2eff536ca4223f7adeb58648bb81909d33c446918cfa8}  /tmp/$zip" | sha256sum -c -
      mkdir -p "$sdk/cmdline-tools"
      rm -rf "$sdk/cmdline-tools/latest" "$sdk/cmdline-tools/cmdline-tools"
      unzip -q "/tmp/$zip" -d "$sdk/cmdline-tools" && mv "$sdk/cmdline-tools/cmdline-tools" "$sdk/cmdline-tools/latest"
    fi
    export ANDROID_HOME="$sdk"
    # sdkmanager checks every package against the checksums of Google's repository index
    yes | "$sdk/cmdline-tools/latest/bin/sdkmanager" --licenses > /dev/null 2>&1 || true
    "$sdk/cmdline-tools/latest/bin/sdkmanager" "platforms;android-37.0" "build-tools;37.0.0" > /dev/null
    cd players/androidtv
    ./gradlew --no-daemon --console=plain :api:test :app:assembleDebug :app:lintDebug
    cd ../..
    python3 tools/apk_listing.py check players/androidtv/app/build/outputs/apk/debug/app-debug.apk
    ;;
  *)
    echo "unknown area: $area" >&2
    exit 2
    ;;
esac
