#!/usr/bin/env bash
set -euo pipefail

APP_ID="org.evans.FileExplorer"
MANIFEST="org.evans.FileExplorer.yml"
BUILD_DIR=".flatpak-build"
REPO_DIR=".flatpak-repo"
BUNDLE="${APP_ID}.flatpak"

FLATPAK_SCOPE=""
if flatpak --user remotes | awk '{print $1}' | grep -qx "flathub"; then
  FLATPAK_SCOPE="--user"
elif flatpak remotes | awk '{print $1}' | grep -qx "flathub"; then
  FLATPAK_SCOPE=""
else
  flatpak --user remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
  FLATPAK_SCOPE="--user"
fi

flatpak-builder --force-clean $FLATPAK_SCOPE --install-deps-from=flathub "$BUILD_DIR" "$MANIFEST"
flatpak-builder --repo="$REPO_DIR" --force-clean "$BUILD_DIR" "$MANIFEST"
flatpak build-bundle "$REPO_DIR" "$BUNDLE" "$APP_ID"
flatpak install -y $FLATPAK_SCOPE "$REPO_DIR" "$APP_ID"

printf '\nBuilt bundle: %s\n' "$BUNDLE"
printf 'Run with: flatpak run %s\n' "$APP_ID"
