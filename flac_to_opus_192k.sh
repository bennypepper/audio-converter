#!/usr/bin/env bash
# FLAC -> Opus launcher for macOS / Linux. Usage:
#   ./flac_to_opus_192k.sh                 interactive wizard
#   ./flac_to_opus_192k.sh ~/Music/Hi-Res  one-shot 192k conversion
set -e
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
    echo "[ERROR] python3 not found. Please install Python 3.8 or newer."
    exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "[ERROR] ffmpeg not found on PATH."
    echo "  macOS:         brew install ffmpeg"
    echo "  Debian/Ubuntu: sudo apt install ffmpeg"
    exit 1
fi

if ! python3 -c "import mutagen" >/dev/null 2>&1; then
    echo "[INFO] Installing required dependency: mutagen..."
    python3 -m pip install --user mutagen \
        || python3 -m pip install --user --break-system-packages mutagen
fi

exec python3 flac_to_opus.py "$@"
