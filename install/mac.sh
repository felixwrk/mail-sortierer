#!/bin/bash
# Mail-Sortierer für den Mac installieren oder aktualisieren.
# Aufruf im Terminal:  curl -fsSL https://raw.githubusercontent.com/__REPO__/main/install/mac.sh | bash
REPO="__REPO__"
set -e
echo ""
echo "=========================================="
echo "  Mail-Sortierer wird installiert"
echo "=========================================="
echo ""
if ! xcode-select -p >/dev/null 2>&1; then
  echo "Zuerst braucht dein Mac die kostenlosen Apple-Entwicklerwerkzeuge (für Python)."
  echo "Gleich öffnet sich ein Fenster: Klick dort auf \"Installieren\"."
  echo "Wenn das fertig ist, starte diese Installation einfach nochmal."
  xcode-select --install >/dev/null 2>&1 || true
  exit 1
fi
TMP="$(mktemp -d)"
echo "1/3  Neueste Version wird geladen …"
curl -fL --progress-bar "https://github.com/$REPO/releases/latest/download/Mail-Sortierer-mac.zip" -o "$TMP/app.zip"
ditto -x -k "$TMP/app.zip" "$TMP"
echo "2/3  Alte Version wird beendet …"
osascript -e 'quit app "Mail-Sortierer"' >/dev/null 2>&1 || true
pkill -f "mailsortierer.py" >/dev/null 2>&1 || true
sleep 1
echo "3/3  App wird nach \"Programme\" kopiert …"
DEST="/Applications"
[ -w "$DEST" ] || DEST="$HOME/Applications"
mkdir -p "$DEST"
rm -rf "$DEST/Mail-Sortierer.app"
ditto "$TMP/Mail-Sortierer.app" "$DEST/Mail-Sortierer.app"
xattr -dr com.apple.quarantine "$DEST/Mail-Sortierer.app" 2>/dev/null || true
rm -rf "$TMP"
echo ""
echo "Fertig! Der Mail-Sortierer liegt in: $DEST"
echo "Updates kommen ab jetzt automatisch über die App."
open "$DEST/Mail-Sortierer.app"
