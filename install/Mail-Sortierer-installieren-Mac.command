#!/bin/bash
# Doppelklick (beim ersten Mal: Rechtsklick -> Öffnen) installiert den Mail-Sortierer.
curl -fsSL "https://raw.githubusercontent.com/__REPO__/main/install/mac.sh" | bash
echo ""
read -r -p "Enter drücken zum Schließen …"
