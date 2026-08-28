#!/usr/bin/env bash
# Wrap the Linux PyInstaller folder bundle into a Debian package.
#
#   uv run --extra package pyinstaller packaging/argos_linux.spec --noconfirm
#   packaging/make_deb.sh
#
# Produces dist/argos_<version>_<architecture>.deb. This is an unsigned,
# self-contained desktop bundle for Debian/Ubuntu-family systems; ASTAP and its
# star databases remain an observer-installed dependency.

set -euo pipefail
cd "$(dirname "$0")/.."

BUNDLE="dist/Argos"
[ -d "$BUNDLE" ] || { echo "error: $BUNDLE not found — run PyInstaller first" >&2; exit 1; }
command -v dpkg-deb >/dev/null || {
    echo "error: dpkg-deb is required to build a .deb package" >&2
    exit 1
}

VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' argos/__init__.py)"
[ -n "$VERSION" ] || { echo "error: could not read Argos version" >&2; exit 1; }
ARCH="$(dpkg --print-architecture)"
PACKAGE="dist/argos_${VERSION}_${ARCH}.deb"
STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT

install -d "$STAGING/DEBIAN" "$STAGING/usr/lib/argos" "$STAGING/usr/bin"
install -d "$STAGING/usr/share/applications" "$STAGING/usr/share/doc/argos"
install -d "$STAGING/usr/share/icons/hicolor/512x512/apps"
cp -a "$BUNDLE/." "$STAGING/usr/lib/argos/"
ln -s ../lib/argos/Argos "$STAGING/usr/bin/argos"
install -m 644 packaging/argos.desktop "$STAGING/usr/share/applications/argos.desktop"
install -m 644 argos/ui/assets/logo.png "$STAGING/usr/share/icons/hicolor/512x512/apps/argos.png"
install -m 644 LICENSE "$STAGING/usr/share/doc/argos/copyright"

cat > "$STAGING/DEBIAN/control" <<EOF
Package: argos
Version: ${VERSION}
Section: science
Priority: optional
Architecture: ${ARCH}
Maintainer: Jules Perret
Depends: libdbus-1-3, libegl1, libfontconfig1, libgl1, libxkbcommon0
Description: Scientific acquisition and differential photometry for Seestar telescopes
 Argos controls ASCOM Alpaca equipment, writes science FITS and produces
 live differential-photometry measurements. ASTAP remains an external solver.
EOF

dpkg-deb --root-owner-group --build "$STAGING" "$PACKAGE"
echo "Done: $PACKAGE"
