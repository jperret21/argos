#!/usr/bin/env bash
# Wrap dist/Argos.app into a distributable .dmg.
#
#   uv run --extra package pyinstaller packaging/argos.spec --noconfirm
#   packaging/make_dmg.sh
#
# Produces dist/Argos-<version>-macOS-<arch>.dmg.
#
# Uses hdiutil rather than a third-party tool: it ships with macOS, so the
# release workflow needs nothing installed beyond Python.
#
# The image is UNSIGNED. Gatekeeper will refuse the first launch — the README
# documents the right-click → Open path. Signing needs an Apple Developer
# account, which the project does not have.

set -euo pipefail
cd "$(dirname "$0")/.."

APP="dist/Argos.app"
[ -d "$APP" ] || { echo "error: $APP not found — run PyInstaller first" >&2; exit 1; }

VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' argos/__init__.py)"
[ -n "$VERSION" ] || { echo "error: could not read __version__ from argos/__init__.py" >&2; exit 1; }

ARCH="$(uname -m)"
DMG="dist/Argos-${VERSION}-macOS-${ARCH}.dmg"
STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT

echo "Staging Argos ${VERSION} (${ARCH})…"
cp -R "$APP" "$STAGING/"
# The drag-to-install target every macOS user expects.
ln -s /Applications "$STAGING/Applications"
cp LICENSE "$STAGING/LICENSE.txt"

# First-launch instructions ride along in the image: an unsigned build fails
# in a way that looks like a corrupt download ("Argos is damaged"), and a user
# who cannot see why will just delete it.
cat > "$STAGING/READ ME FIRST.txt" <<'EOF'
Argos — first launch on macOS
=============================

Argos is not signed with an Apple Developer certificate, so macOS blocks it
the first time. This is about the absence of a paid certificate, not about
the software being unsafe.

To open it:

  1. Drag Argos into your Applications folder.
  2. Right-click (or Control-click) Argos, and choose "Open".
  3. Confirm "Open" in the dialog that appears.

You only need to do this once. Afterwards it launches normally.

If macOS says Argos "is damaged and can't be opened", run this in Terminal:

  xattr -dr com.apple.quarantine /Applications/Argos.app

Plate solving needs ASTAP installed separately — Argos does not bundle it.
See https://www.hnsky.org/astap.htm

Argos is free software under the GNU GPL v3. See LICENSE.txt.
EOF

rm -f "$DMG"
echo "Building ${DMG}…"
hdiutil create \
    -volname "Argos ${VERSION}" \
    -srcfolder "$STAGING" \
    -ov -format UDZO \
    "$DMG" >/dev/null

echo "Done: ${DMG} ($(du -h "$DMG" | cut -f1))"
