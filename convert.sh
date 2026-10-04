#!/usr/bin/env bash
# Launcher for macOS / Linux. Usage:
#   ./convert.sh                      interactive wizard
#   ./convert.sh ~/Music/Album        wizard with the source pre-filled
#   ./convert.sh -i ~/Music -f flac   non-interactive (any audio_converter.py flags work)
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
    echo "  Fedora:        sudo dnf install ffmpeg"
    exit 1
fi

if ! python3 -c "import mutagen" >/dev/null 2>&1; then
    echo "[INFO] Installing required dependency: mutagen..."
    python3 -m pip install --user mutagen \
        || python3 -m pip install --user --break-system-packages mutagen
fi

exec python3 audio_converter.py "$@"
