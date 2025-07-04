#!/bin/sh
#
# Lädt PDFs von https://www.europa.eda.admin.ch/de/vernehmlassung-paket-schweiz-eu
# herunter und benennt sie richtig!
#
# Voraussetzung:
# - Playright muss installiert sein:
#   - pip install playwright
#   - python -m playwright install
#
# Nutzung:
#   ./bin/download.sh
#

cd "$(dirname "$0")/.."

python download/download.py
