#!/usr/bin/env bash
# The Android build, run by .github/workflows/android.yml once Java, Python and Gradle are set up.  The game's
# code and data are this repository's own: app/build.gradle copies them into the project before it builds.
set -euo pipefail
cd "$(dirname "$0")/.."                              # android/

mkdir -p out
if [ -n "${SIGNING_KEY:-}" ]; then
  # the release: signed with the project's permanent key, so each one installs over the last
  printf '%s' "$SIGNING_KEY" | tr -d ' \r\n\t' | base64 -d > /tmp/audiodefence.p12
  export AD_KEYSTORE=/tmp/audiodefence.p12
  trap 'rm -f /tmp/audiodefence.p12' EXIT
  gradle --no-daemon --stacktrace assembleRelease
  cp app/build/outputs/apk/release/app-release.apk out/AudioDefence.apk
  echo "Built android/out/AudioDefence.apk, the release, signed with the permanent key."
else
  echo "::warning::There is no SIGNING_KEY secret in this repository, so this is only a TEST build (app-debug-TEST.apk). It cannot install over a release, and a release cannot install over it."
  gradle --no-daemon --stacktrace assembleDebug
  cp app/build/outputs/apk/debug/app-debug.apk out/app-debug-TEST.apk
fi
du -sh app/src/main/assets/game
