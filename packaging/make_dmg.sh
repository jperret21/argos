#!/usr/bin/env bash
# Wrap a macOS .app into a distributable .dmg: the app, an Applications link,
# LICENSE.txt and READ ME FIRST.txt (the Gatekeeper steps).
#
#   packaging/make_dmg.sh [path/to/App.app] [output folder]
#
# The desktop app (W8, Tauri): the bundle `npx tauri build --bundles app`
# leaves in <target>/release/bundle/macos/ARGOS.app (.github/workflows/
# release.yml). With no argument, the Qt app of packaging/argos.spec,
# dist/Argos.app. Produces <output folder, default dist>/
# <app name>-<version>-macOS-<arch>.dmg, the version read from
# argos/__init__.py (the one source); the app's own version must match.
#
# Uses hdiutil rather than a third-party tool: it ships with macOS, so the
# release workflow needs nothing installed beyond Python.
#
# The image is not notarised (the app is signed ad hoc at most). Gatekeeper
# will refuse the first launch — READ ME FIRST.txt documents the right-click
# → Open path. Notarising needs an Apple Developer account, which the project
# does not have.

set -euo pipefail
cd "$(dirname "$0")/.."

APP="${1:-dist/Argos.app}"
OUT="${2:-dist}"
[ -d "$APP" ] || { echo "error: $APP not found — build the app first" >&2; exit 1; }
NAME="$(basename "$APP" .app)"

VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' argos/__init__.py)"
[ -n "$VERSION" ] || { echo "error: could not read __version__ from argos/__init__.py" >&2; exit 1; }
APP_VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$APP/Contents/Info.plist")"
[ "$APP_VERSION" = "$VERSION" ] || {
    echo "error: $APP is version $APP_VERSION, argos/__init__.py says $VERSION" >&2
    exit 1
}

ARCH="$(uname -m)"
mkdir -p "$OUT"
DMG="$OUT/${NAME}-${VERSION}-macOS-${ARCH}.dmg"
STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT

echo "Staging ${NAME} ${VERSION} (${ARCH})…"
# -R keeps the symlinks of the app's frozen server (ditto would too).
cp -R "$APP" "$STAGING/"
# The drag-to-install target every macOS user expects.
ln -s /Applications "$STAGING/Applications"
cp LICENSE "$STAGING/LICENSE.txt"

# First-launch instructions ride along in the image: an unsigned build fails
# in a way that looks like a corrupt download ("Argos is damaged"), and a user
# who cannot see why will just delete it.
cat > "$STAGING/READ ME FIRST.txt" <<EOF
${NAME} — first launch on macOS
$(printf '%*s' "$(( ${#NAME} + 24 ))" '' | tr ' ' '=')

${NAME} is not signed with an Apple Developer certificate, so macOS blocks it
the first time. This is about the absence of a paid certificate, not about
the software being unsafe.

To open it:

  1. Drag ${NAME} into your Applications folder.
  2. Open ${NAME} once; macOS refuses it. Click "Done".
  3. macOS 15 (Sequoia) or later: open System Settings > Privacy & Security,
     scroll to "${NAME} was blocked to protect your Mac", click "Open Anyway"
     and confirm with "Open Anyway" (your password may be asked).
     macOS 11 to 14: right-click (or Control-click) ${NAME} in Applications,
     choose "Open", then "Open" again in the dialog.

You only need to do this once. Afterwards it launches normally. The very
first launch can take longer while macOS checks the application.

If macOS says ${NAME} "is damaged and can't be opened", run this in Terminal:

  xattr -dr com.apple.quarantine "/Applications/${NAME}.app"

Plate solving needs ASTAP installed separately — ${NAME} does not bundle it.
See https://www.hnsky.org/astap.htm

${NAME} is free software under the GNU GPL v3 or later. See LICENSE.txt.
EOF

rm -f "$DMG"
echo "Building ${DMG}…"
hdiutil create \
    -volname "${NAME} ${VERSION}" \
    -srcfolder "$STAGING" \
    -ov -format UDZO \
    "$DMG" >/dev/null

echo "Done: ${DMG} ($(du -h "$DMG" | cut -f1))"
