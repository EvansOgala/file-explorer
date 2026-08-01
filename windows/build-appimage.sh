#!/usr/bin/env bash
set -euo pipefail

APP_ID="org.evans.FileExplorer"
APP_NAME="FileExplorer"
ENTRY="main.py"
DESKTOP_FILE="$APP_ID.desktop"
ICON_FILE="$APP_ID.svg"
META_FILE="$APP_ID.metainfo.xml"
APPDIR="AppDir"
DIST_DIR="dist"
BUILD_DIR="build"
OUT_APPIMAGE="${APP_ID}-$(uname -m).AppImage"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_TOOL="$SCRIPT_DIR/tools/appimagetool.AppImage"
ALT_LOCAL_TOOL="$SCRIPT_DIR/tools/appimagetool-x86_64.AppImage"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Missing required command: python3"
  exit 1
fi

if ! python3 -c 'import PyInstaller' >/dev/null 2>&1; then
  echo "PyInstaller is not installed."
  echo "Install with: python3 -m pip install --user pyinstaller"
  exit 1
fi

APPIMAGETOOL_BIN=""
if command -v appimagetool >/dev/null 2>&1; then
  APPIMAGETOOL_BIN="$(command -v appimagetool)"
elif [ -f "$LOCAL_TOOL" ]; then
  chmod +x "$LOCAL_TOOL"
  APPIMAGETOOL_BIN="$LOCAL_TOOL"
elif [ -f "$ALT_LOCAL_TOOL" ]; then
  chmod +x "$ALT_LOCAL_TOOL"
  APPIMAGETOOL_BIN="$ALT_LOCAL_TOOL"
else
  echo "appimagetool was not found."
  echo "Install it system-wide, or place it at:"
  echo "  $LOCAL_TOOL"
  echo "or:"
  echo "  $ALT_LOCAL_TOOL"
  exit 1
fi

cd "$SCRIPT_DIR"
rm -rf "$APPDIR" "$DIST_DIR" "$BUILD_DIR" "${APP_NAME}.spec" "${APP_ID}.spec"

python3 -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --onedir \
  --name "$APP_NAME" \
  --hidden-import=gi \
  --hidden-import=gi.overrides.Gtk \
  --hidden-import=gi.repository.Gtk \
  --hidden-import=gi.repository.Gio \
  --hidden-import=gi.repository.GLib \
  "$ENTRY"

mkdir -p "$APPDIR/usr/bin"
cp -a "$DIST_DIR/$APP_NAME/." "$APPDIR/usr/bin/"

cat > "$APPDIR/usr/bin/$APP_ID" <<EOLAUNCH
#!/usr/bin/env sh
set -eu
HERE="\$(dirname "\$(readlink -f "\$0")")"
exec "\$HERE/$APP_NAME" "\$@"
EOLAUNCH
chmod +x "$APPDIR/usr/bin/$APP_ID"

cat > "$APPDIR/AppRun" <<'EOFRUN'
#!/usr/bin/env sh
set -eu
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/org.evans.FileExplorer" "$@"
EOFRUN
chmod +x "$APPDIR/AppRun"

cp "$DESKTOP_FILE" "$APPDIR/$APP_ID.desktop"

ICON_EXT="${ICON_FILE##*.}"
case "$ICON_EXT" in
  svg)
    cp "$ICON_FILE" "$APPDIR/$APP_ID.svg"
    ICON_DIR="scalable"
    ;;
  png)
    cp "$ICON_FILE" "$APPDIR/$APP_ID.png"
    ICON_DIR="256x256"
    ;;
  *)
    echo "Unsupported icon file format: $ICON_FILE"
    exit 1
    ;;
esac

mkdir -p "$APPDIR/usr/share/icons/hicolor/$ICON_DIR/apps"
cp "$ICON_FILE" "$APPDIR/usr/share/icons/hicolor/$ICON_DIR/apps/$APP_ID.$ICON_EXT"
mkdir -p "$APPDIR/usr/share/applications"
cp "$APPDIR/$APP_ID.desktop" "$APPDIR/usr/share/applications/$APP_ID.desktop"

if [ -f "$META_FILE" ]; then
  mkdir -p "$APPDIR/usr/share/metainfo"
  cp "$META_FILE" "$APPDIR/usr/share/metainfo/$APP_ID.metainfo.xml"
  cp "$META_FILE" "$APPDIR/usr/share/metainfo/$APP_ID.appdata.xml"
fi

if [[ "$APPIMAGETOOL_BIN" == *.AppImage ]]; then
  "$APPIMAGETOOL_BIN" --appimage-extract-and-run "$APPDIR" "$OUT_APPIMAGE"
else
  "$APPIMAGETOOL_BIN" "$APPDIR" "$OUT_APPIMAGE"
fi

echo "Built: $OUT_APPIMAGE"
