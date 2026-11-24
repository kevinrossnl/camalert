# players/androidtv/ – Android TV / Fire TV app (no Kodi)

Read the root [DEVELOPMENT.md](../../DEVELOPMENT.md) first (privacy, how we work, CI). Shared logic belongs in
[core](../../core/DEVELOPMENT.md); this player re-implements it in Kotlin, so the rules come from core as **generated
data and contract tests**, never typed in twice. Issue: #64. Minimum: Android 7.1 (API 25, Fire OS 6).

## Files

| Path | What |
|---|---|
| `api/` | pure Kotlin/JVM module (no Android classes): HTTP API v1 (`Api.kt`, `HttpServer.kt`), access rules, redaction, metrics, rules, settings schema, key hints, MQTT client + discovery, Frigate trigger, `PlayerController` (show/mosaic/tour/hide rules) |
| `api/src/main/resources/camalert/core.json` | **generated** by `tools/export_contract.py`: API constants, settings schema of this player, key map, hints, labels |
| `api/src/test/resources/contract/*.json` | **generated** by `tools/export_contract.py`: HTTP + MQTT contract tables, reference answers of core functions |
| `api/src/test/kotlin/` | JVM tests: every contract row (`HttpContractTest`, also over a real socket), MQTT contract against a fake broker, core reference answers, player rules |
| `app/` | the Android app `org.camalert.tv`: foreground service (boot start), overlay windows, Media3 live view, leanback settings |
| `gradle/libs.versions.toml` | every dependency, pinned |

Never edit generated files: run `python3 tools/export_contract.py update`.

## Rules
- The contract tests (`./gradlew :api:test`) run every row of `tests/contract/api_table.py` and `mqtt_table.py`.
  A difference needs an entry in `KNOWN` (row -> issue) in the Kotlin test; KNOWN must trend to zero.
- Keep logic in `api/` (testable on the JVM). `app/` only adapts Android: overlay views, ExoPlayer, settings
  storage, service lifecycle.
- Dependencies only from Google Maven / Maven Central, pinned in `gradle/libs.versions.toml`, each justified here:
  AndroidX Media3 (`exoplayer`, `-rtsp`, `-hls`, `-ui`: live view; the platform MediaPlayer cannot do RTSP over
  TCP or fMP4 streams reliably on Fire OS 6), AndroidX Leanback Preference + Preference (on-TV settings screen),
  JUnit 4 (JVM tests). No Google Play Services. HTTP and MQTT are our own small implementations (like the
  Python players), so no networking library.
- Gradle wrapper from services.gradle.org with `distributionSha256Sum`; the wrapper jar checksum is the
  published one. Android SDK only from dl.google.com (`tools/ci.sh androidtv` checks the cmdline-tools sha256).
- Debug-signed APK only. No keystore in git (`*.jks`, `*.keystore` are ignored); release signing: see
  [docs/players/androidtv.md](../../docs/players/androidtv.md).
- Real device tests (Fire TV Stick): fake go2rtc only (`tests/fakes/go2rtc.py` via `adb reverse`), live view
  muted, nothing else installed or changed on the device; screenshots only with fake cameras and
  `tools/check_images.py --strip`.
- Build: `./gradlew :api:test :app:assembleDebug :app:lintDebug` (needs JDK 17+ and `ANDROID_HOME`); CI:
  `sh tools/ci.sh androidtv` (workstation runner only).
