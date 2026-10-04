#!/usr/bin/env python3
"""Build the portable Windows release. Used by build.bat AND by CI so the two cannot drift.

  python packaging/build.py                    # dev build -> dist/AudioConverter-v<ver>-dev-win64.zip
  python packaging/build.py --tag v1.2.0       # release build; tag must equal v<__version__>
  python packaging/build.py --ffmpeg-local C:\\tools\\ffmpeg.exe   # unverified dev build (never with --tag)
"""
import argparse
import hashlib
import importlib.metadata as metadata
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DIST = os.path.join(ROOT, 'dist')
APP_DIR = os.path.join(DIST, 'AudioConverter')
BIN = os.path.join(HERE, 'bin')


def read_version():
    with open(os.path.join(ROOT, 'audio_converter.py'), encoding='utf-8') as fh:
        text = fh.read()
    return re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.M).group(1)


def check_tag(tag, version):
    if tag and tag != f"v{version}":
        raise SystemExit(f"[ERROR] Tag '{tag}' does not match __version__ (expected 'v{version}'). "
                         "Bump __version__ or fix the tag.")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for block in iter(lambda: fh.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def make_zip(src_dir, zip_path):
    """Zip src_dir with ONE top-level folder and forward-slash entry names (works with every unzip tool)."""
    top = os.path.basename(os.path.normpath(src_dir))
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for folder, _, files in os.walk(src_dir):
            for name in sorted(files):
                full = os.path.join(folder, name)
                arcname = top + '/' + os.path.relpath(full, src_dir).replace(os.sep, '/')
                zf.write(full, arcname)


def find_dist_license(package, filename='COPYING'):
    dist = metadata.distribution(package)
    for f in dist.files or []:
        if f.name == filename:
            return str(dist.locate_file(f))
    raise SystemExit(f"[ERROR] {filename} not found in the installed '{package}' distribution.")


def assemble(app_dir):
    """Copy ffmpeg + real license texts + notices into the PyInstaller output folder."""
    lic = os.path.join(app_dir, 'LICENSES')
    os.makedirs(lic, exist_ok=True)
    shutil.copy2(os.path.join(BIN, 'ffmpeg.exe'), os.path.join(app_dir, 'ffmpeg.exe'))
    pairs = [
        (os.path.join(ROOT, 'LICENSE'), 'Audio-Converter-LICENSE.txt'),
        (find_dist_license('mutagen'), 'Mutagen-COPYING.txt'),
        (os.path.join(BIN, 'ffmpeg-LICENSE.txt'), 'FFmpeg-LICENSE.txt'),
        (os.path.join(BIN, 'ffmpeg.version.txt'), 'FFmpeg-SOURCE.txt'),
        (os.path.join(HERE, 'THIRD-PARTY-NOTICES.txt'), 'THIRD-PARTY-NOTICES.txt'),
    ]
    for src, name in pairs:
        shutil.copy2(src, os.path.join(lic, name))
    shutil.copy2(os.path.join(HERE, 'README-portable.txt'), os.path.join(app_dir, 'README.txt'))


def smoke_test(app_dir):
    """Run the smoke suite against a RELOCATED copy (path with a space) to prove it is portable."""
    with tempfile.TemporaryDirectory(prefix="Audio Converter Test ") as tmp:
        moved = os.path.join(tmp, 'AudioConverter')
        shutil.copytree(app_dir, moved)
        env = dict(os.environ, AUDIOCONVERTER_EXE=os.path.join(moved, 'AudioConverter.exe'))
        rc = subprocess.run([sys.executable, '-m', 'unittest', 'tests.test_smoke', '-v'], cwd=ROOT, env=env).returncode
    if rc != 0:
        raise SystemExit("[ERROR] Smoke tests failed against the built exe. Not packaging.")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--tag', help="release tag, e.g. v1.2.0 (must match __version__)")
    ap.add_argument('--ffmpeg-local', metavar='PATH', help="use an unverified local ffmpeg.exe (dev only)")
    ap.add_argument('--skip-smoke', action='store_true')
    args = ap.parse_args(argv)

    if sys.platform != 'win32':
        raise SystemExit("[ERROR] The Windows release must be built on Windows (use CI or build.bat).")
    version = read_version()
    check_tag(args.tag, version)
    if args.ffmpeg_local and args.tag:
        raise SystemExit("[ERROR] --ffmpeg-local builds cannot be released (--tag).")
    label = args.tag or f"v{version}-dev"

    stage = [sys.executable, os.path.join(HERE, 'download_ffmpeg.py')]
    stage += ['--local', args.ffmpeg_local] if args.ffmpeg_local else []
    if subprocess.run(stage).returncode != 0:
        raise SystemExit("[ERROR] Could not stage ffmpeg.")

    for folder in (APP_DIR, os.path.join(ROOT, 'build')):
        shutil.rmtree(folder, ignore_errors=True)
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--distpath', DIST,
                    '--workpath', os.path.join(ROOT, 'build'), os.path.join(HERE, 'AudioConverter.spec')],
                   check=True)
    assemble(APP_DIR)
    if not args.skip_smoke:
        smoke_test(APP_DIR)

    zip_path = os.path.join(DIST, f"AudioConverter-{label}-win64.zip")
    make_zip(APP_DIR, zip_path)
    digest = sha256_file(zip_path)
    with open(zip_path + '.sha256', 'w', encoding='utf-8') as fh:
        fh.write(f"{digest}  {os.path.basename(zip_path)}\n")
    print(f"\n[OK] {zip_path}\n     sha256 {digest}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
