#!/usr/bin/env python3
"""Stage the pinned FFmpeg into packaging/bin/ (ffmpeg.exe + its license + a version note).

  python packaging/download_ffmpeg.py                  # download the build in ffmpeg.lock.json, verify SHA-256
  python packaging/download_ffmpeg.py --hash FILE.zip  # print a file's SHA-256 (to fill in the lock file)
  python packaging/download_ffmpeg.py --local PATH     # developer builds only: use a local ffmpeg.exe, no verification
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
LOCK = os.path.join(HERE, 'ffmpeg.lock.json')
BIN = os.path.join(HERE, 'bin')
REQUIRED_KEYS = ('version', 'url', 'sha256', 'license', 'source_url')


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for block in iter(lambda: fh.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def validate_lock(lock):
    """Raises ValueError unless every field is filled in and the hash looks like a SHA-256."""
    for key in REQUIRED_KEYS:
        value = str(lock.get(key, '')).strip()
        if not value or value == 'REPLACE_ME':
            raise ValueError(f"packaging/ffmpeg.lock.json: '{key}' is not filled in (see the Owner checklist).")
    if not re.fullmatch(r'[0-9a-fA-F]{64}', lock['sha256']):
        raise ValueError("packaging/ffmpeg.lock.json: 'sha256' must be 64 hex characters.")
    if not lock['url'].lower().startswith('https://'):
        raise ValueError("packaging/ffmpeg.lock.json: 'url' must be https.")


def pick_members(names):
    """From a zip's member names choose (ffmpeg.exe, license file). Raises if either is missing."""
    exe = next((n for n in names if re.search(r'(^|/)bin/ffmpeg\.exe$', n, re.I)), None)
    lic = next((n for n in names if re.fullmatch(r'[^/]+/LICENSE(\.txt)?', n, re.I)), None)
    if not exe:
        raise ValueError("ffmpeg.exe (bin/ffmpeg.exe) not found in the archive.")
    if not lic:
        raise ValueError("No top-level LICENSE file in the archive; the license text must ship with ffmpeg.exe.")
    return exe, lic


def download(url, dest, retries=3, timeout=60):
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp, open(dest, 'wb') as out:
                shutil.copyfileobj(resp, out)
            return
        except Exception as exc:  # network errors vary widely
            if attempt == retries:
                raise
            print(f"[WARN] download failed ({exc}); retrying {attempt}/{retries - 1}...")
            time.sleep(2 * attempt)


def stage_from_zip(zip_path, lock):
    os.makedirs(BIN, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        exe, lic = pick_members(zf.namelist())
        for member, target in ((exe, 'ffmpeg.exe'), (lic, 'ffmpeg-LICENSE.txt')):
            with zf.open(member) as src, open(os.path.join(BIN, target), 'wb') as dst:
                shutil.copyfileobj(src, dst)
    with open(os.path.join(BIN, 'ffmpeg.version.txt'), 'w', encoding='utf-8') as fh:
        fh.write("FFmpeg build bundled with Audio Converter\n"
                 f"Version: {lock['version']}\nDownloaded from: {lock['url']}\n"
                 f"SHA-256 of archive: {lock['sha256']}\nLicense: {lock['license']}\n"
                 f"Corresponding source code: {lock['source_url']}\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--hash', metavar='FILE', help="print the SHA-256 of FILE and exit")
    ap.add_argument('--local', metavar='FFMPEG_EXE', help="developer builds only; skips verification")
    args = ap.parse_args(argv)

    if args.hash:
        print(sha256_file(args.hash))
        return 0
    if args.local:
        os.makedirs(BIN, exist_ok=True)
        shutil.copy2(args.local, os.path.join(BIN, 'ffmpeg.exe'))
        with open(os.path.join(BIN, 'ffmpeg-LICENSE.txt'), 'w', encoding='utf-8') as fh:
            fh.write("LOCAL DEVELOPER BUILD - this FFmpeg was not verified. Do not publish.\n")
        with open(os.path.join(BIN, 'ffmpeg.version.txt'), 'w', encoding='utf-8') as fh:
            fh.write("LOCAL DEVELOPER BUILD - not for release.\n")
        print("[WARN] Using an unverified local ffmpeg.exe. This build must not be released.")
        return 0

    with open(LOCK, encoding='utf-8') as fh:
        lock = json.load(fh)
    try:
        validate_lock(lock)
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        return 1

    os.makedirs(BIN, exist_ok=True)
    zip_path = os.path.join(BIN, 'ffmpeg-download.zip')
    print(f"[INFO] Downloading FFmpeg {lock['version']} ...")
    download(lock['url'], zip_path)
    actual = sha256_file(zip_path)
    if actual.lower() != lock['sha256'].lower():
        os.remove(zip_path)
        print(f"[ERROR] SHA-256 mismatch!\n  expected {lock['sha256']}\n  actual   {actual}")
        return 1
    stage_from_zip(zip_path, lock)
    os.remove(zip_path)
    print(f"[INFO] Staged verified ffmpeg.exe in {BIN}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
