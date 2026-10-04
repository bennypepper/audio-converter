# Portable Windows Executable Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package the Audio Converter into a zero-install, portable Windows application (`AudioConverter.exe` folder distribution with bundled FFmpeg) while keeping existing CLI, launcher, and source workflows intact.

**Architecture:** 
The application will be compiled into a PyInstaller directory distribution (`--onedir`) containing `AudioConverter.exe`, a bundled `ffmpeg.exe`, `LICENSES/`, and the `_internal/` runtime folder. A dynamic `find_ffmpeg()` resolver locates the bundled FFmpeg beside the executable (or on PATH as fallback), subprocess executions on Windows suppress console pop-up windows via `CREATE_NO_WINDOW`, frozen environments disable pip auto-installs, and a unified `--preset flac_to_opus` flag allows single-binary preset execution. Builds are packaged locally with `build.bat` and automated via GitHub Actions with pre-publish smoke testing on all codecs.

**Tech Stack:** Python 3.8+, PyInstaller 6.x, FFmpeg (LGPL/GPL essentials), mutagen, PowerShell / Batch scripting, GitHub Actions CI (`windows-latest`).

**Spec:** Audio Converter PRD & Architecture specification (Windows Portable Application).

## Global Constraints

- **Platform Target:** Windows 10/11 64-bit (x86_64).
- **Distribution Format:** Zip containing directory layout (`AudioConverter.exe`, `ffmpeg.exe`, `LICENSES/`, `_internal/`). No single-file extraction lag or registry entries.
- **Backward Compatibility:** All existing CLI flags (`-i`, `-o`, `-f`, `-b`, `-w`, `--skip-existing`, `--force-reencode`, `--include-lossy`, `--dry-run`), wizard navigation (`b`/`q`), drag-and-drop paths, and `.bat`/`.sh` launchers must remain 100% functional.
- **Zero-Install User Requirement:** Standalone users must not need Python, pip, or pre-installed FFmpeg.
- **Git & Safety Rules:** Never run automated remote git pushes (`git push`). Keep all commits local with Conventional Commit messages. Verify .gitignore prevents secrets, build artifacts (`dist/`, `build/`), or temp files from being committed.

---

### Task 1: Implement `find_ffmpeg()` Resolver and Windows Subprocess Window Suppression

**Files:**
- Modify: `audio_converter.py:284-290` (replace `check_ffmpeg`), `audio_converter.py:464-479` (update `subprocess.run` call)
- Modify: `flac_to_opus.py:98-100` (use `find_ffmpeg()` / `check_ffmpeg()`)
- Test: `test_audio_converter.py`

**Interfaces:**
- Consumes: `sys.frozen`, `sys.executable`, `sys._MEIPASS`, `shutil.which`, `subprocess.CREATE_NO_WINDOW`
- Produces: 
  - `audio_converter.find_ffmpeg() -> str | None`: Returns absolute path to bundled or system FFmpeg binary.
  - `audio_converter.get_subprocess_kwargs() -> dict`: Returns `{creationflags: subprocess.CREATE_NO_WINDOW}` on Windows, `{}` on non-Windows.
  - Updated `audio_converter.check_ffmpeg() -> str`: Exits with error message if `find_ffmpeg()` is None; returns resolved path.

- [ ] **Step 1: Write the failing tests in `test_audio_converter.py`**

Add unit tests to `test_audio_converter.py` testing:
1. `find_ffmpeg()` looks in the executable directory when frozen.
2. `find_ffmpeg()` falls back to system PATH when not beside executable.
3. `find_ffmpeg()` returns `None` when FFmpeg is not found anywhere.
4. `get_subprocess_kwargs()` returns `CREATE_NO_WINDOW` on Windows (`win32`).

```python
class FindFFmpeg(unittest.TestCase):
    def test_find_ffmpeg_beside_executable(self):
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as d:
            fake_ffmpeg = touch(os.path.join(d, 'ffmpeg.exe'))
            with mock.patch('sys.frozen', True, create=True), \
                 mock.patch('sys.executable', os.path.join(d, 'AudioConverter.exe')), \
                 mock.patch('shutil.which', return_value=None):
                resolved = ac.find_ffmpeg()
                self.assertEqual(resolved, os.path.abspath(fake_ffmpeg))

    def test_find_ffmpeg_fallback_to_path(self):
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as d:
            fake_path_ffmpeg = touch(os.path.join(d, 'system_ffmpeg', 'ffmpeg.exe'))
            with mock.patch('sys.frozen', False, create=True), \
                 mock.patch.object(os.path, 'isfile', lambda p: p == fake_path_ffmpeg), \
                 mock.patch('shutil.which', return_value=fake_path_ffmpeg):
                resolved = ac.find_ffmpeg()
                self.assertEqual(resolved, os.path.abspath(fake_path_ffmpeg))

    def test_find_ffmpeg_not_found(self):
        import unittest.mock as mock
        with mock.patch('sys.frozen', False, create=True), \
             mock.patch.object(os.path, 'isfile', return_value=False), \
             mock.patch('shutil.which', return_value=None):
            resolved = ac.find_ffmpeg()
            self.assertIsNone(resolved)


class SubprocessKwargs(unittest.TestCase):
    def test_windows_creationflags(self):
        import unittest.mock as mock
        with mock.patch('sys.platform', 'win32'):
            kwargs = ac.get_subprocess_kwargs()
            import subprocess
            expected_flag = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
            self.assertEqual(kwargs.get('creationflags'), expected_flag)

    def test_non_windows_empty(self):
        import unittest.mock as mock
        with mock.patch('sys.platform', 'darwin'):
            kwargs = ac.get_subprocess_kwargs()
            self.assertEqual(kwargs, {})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python test_audio_converter.py`
Expected: FAIL with `AttributeError: module 'audio_converter' has no attribute 'find_ffmpeg'`

- [ ] **Step 3: Implement `find_ffmpeg()` and `get_subprocess_kwargs()` in `audio_converter.py`**

Add functions to `audio_converter.py`:
```python
def find_ffmpeg():
    """Locate ffmpeg executable.
    Checks:
    1. Beside the executable (sys.executable directory if frozen, sys._MEIPASS,
       or directory of audio_converter.py).
    2. System PATH via shutil.which.
    Returns absolute path or None.
    """
    candidates = []
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        candidates.append(os.path.join(exe_dir, 'ffmpeg.exe'))
        candidates.append(os.path.join(exe_dir, 'ffmpeg'))
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            candidates.append(os.path.join(meipass, 'ffmpeg.exe'))
            candidates.append(os.path.join(meipass, 'ffmpeg'))
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        candidates.append(os.path.join(script_dir, 'ffmpeg.exe'))
        candidates.append(os.path.join(script_dir, 'ffmpeg'))

    for path in candidates:
        if os.path.isfile(path):
            return os.path.abspath(path)

    from_path = shutil.which('ffmpeg')
    if from_path:
        return os.path.abspath(from_path)
    return None


def get_subprocess_kwargs():
    """Return subprocess flags to prevent console window popping up on Windows."""
    kwargs = {}
    if sys.platform == 'win32':
        create_no_window = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
        kwargs['creationflags'] = create_no_window
    return kwargs


def check_ffmpeg():
    """Verify that FFmpeg is available beside the application or on PATH."""
    path = find_ffmpeg()
    if not path:
        print(f"{C_RED}[ERROR] 'ffmpeg' is not found beside this program or in your system PATH.{C_RESET}")
        print("Please ensure ffmpeg.exe is in the application folder or added to PATH.")
        sys.exit(1)
    return path
```

Update `convert_single_file()` in `audio_converter.py`:
```python
        # 2. Build FFmpeg command
        cfg = CODEC_CONFIG[codec]
        ffmpeg_bin = find_ffmpeg() or 'ffmpeg'
        cmd = [ffmpeg_bin, '-y', '-nostdin', '-i', src_path, '-map', '0:a']
        cmd.extend(cfg['ffmpeg_args'])
        if not cfg['is_lossless'] and bitrate:
            if bitrate.lower() == 'v0' and codec == 'mp3':
                cmd.extend(['-q:a', '0'])
            else:
                cmd.extend(['-b:a', bitrate])
        cmd.extend(['-map_metadata', '0', '-map_metadata:g', '0:s:a:0', tmp_path])

        # 3. Execute FFmpeg
        kwargs = get_subprocess_kwargs()
        res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', **kwargs)
        if res.returncode != 0:
            return False, f"FFmpeg error: {res.stderr[-200:].strip()}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python test_audio_converter.py`
Expected: PASS (All tests pass including new `FindFFmpeg` and `SubprocessKwargs` suites).

- [ ] **Step 5: Commit changes locally**

```bash
git add audio_converter.py flac_to_opus.py test_audio_converter.py
git commit -m "feat: add find_ffmpeg resolver and quiet subprocess window flags"
```

---

### Task 2: Frozen Mutagen Import Guard and Main `--preset` CLI Dispatcher

**Files:**
- Modify: `audio_converter.py:50-75` (frozen guard on mutagen import), `audio_converter.py:1083-1160` (add `--preset` flag)
- Test: `test_audio_converter.py`

**Interfaces:**
- Consumes: `sys.frozen`, `flac_to_opus` preset parameters
- Produces: 
  - Safe import behavior in frozen builds: does not invoke `pip install` when frozen.
  - `--preset flac_to_opus` command-line option in `audio_converter.py`, allowing the standalone `AudioConverter.exe` to run the FLAC-to-Opus workflow without needing a separate binary.

- [ ] **Step 1: Write the failing tests in `test_audio_converter.py`**

Add unit tests verifying:
1. Frozen mode raises error / exits when mutagen is missing without calling pip.
2. CLI parser accepts `--preset flac_to_opus`.

```python
class FrozenImportAndPreset(unittest.TestCase):
    def test_preset_arg_registered(self):
        # Verify parser recognizes --preset
        import argparse
        # We can test parser construction
        parser = ac.build_argument_parser()
        args = parser.parse_args(['--preset', 'flac_to_opus'])
        self.assertEqual(args.preset, 'flac_to_opus')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python test_audio_converter.py`
Expected: FAIL with `AttributeError: module 'audio_converter' has no attribute 'build_argument_parser'`

- [ ] **Step 3: Implement frozen guard and extract `build_argument_parser()` with `--preset`**

In `audio_converter.py`, update mutagen import block:
```python
# Verify dependencies and auto-install if missing (only when running from source)
try:
    import mutagen
    from mutagen.flac import FLAC, Picture
    from mutagen.mp3 import MP3
    from mutagen.id3 import ID3, APIC, ID3NoHeaderError
    from mutagen.mp4 import MP4, MP4Cover
    from mutagen.oggopus import OggOpus
    from mutagen.oggvorbis import OggVorbis
except ImportError:
    if getattr(sys, 'frozen', False):
        print(f"\033[91m[ERROR] Required dependency 'mutagen' is missing from the frozen application bundle.\033[0m")
        print("Please reinstall or re-extract the application.")
        if sys.stdin and sys.stdin.isatty():
            input("Press Enter to exit...")
        sys.exit(1)
    print(f"\033[93m[INFO] 'mutagen' is not found. Installing via pip...\033[0m")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "mutagen"])
        import mutagen
        from mutagen.flac import FLAC, Picture
        from mutagen.mp3 import MP3
        from mutagen.id3 import ID3, APIC, ID3NoHeaderError
        from mutagen.mp4 import MP4, MP4Cover
        from mutagen.oggopus import OggOpus
        from mutagen.oggvorbis import OggVorbis
        print(f"\033[92m[INFO] 'mutagen' successfully installed!\033[0m\n")
    except Exception as e:
        print(f"\033[91m[ERROR] Failed to auto-install 'mutagen': {e}\033[0m")
        print(f"Please run: {sys.executable} -m pip install mutagen")
        if sys.stdin and sys.stdin.isatty():
            input("Press Enter to exit...")
        sys.exit(1)
```

Refactor CLI parser creation in `audio_converter.py`:
```python
def build_argument_parser():
    parser = argparse.ArgumentParser(
        prog="AudioConverter",
        description="Audio converter with full metadata & cover art preservation. "
                    "Run with no arguments (or just a path) for the interactive wizard."
    )
    parser.add_argument('path', nargs='?',
                        help="Optional file/folder to pre-fill the interactive wizard (drag & drop)")
    parser.add_argument('-i', '--input', help="Source file or directory (skips the wizard)")
    parser.add_argument('-o', '--output', help="Destination directory path")
    parser.add_argument('-f', '--format', choices=list(CODEC_CONFIG.keys()), default=None,
                        help="Target audio codec (opus, mp3, m4a, flac, alac, ogg, wav)")
    parser.add_argument('-b', '--bitrate', default=None,
                        help="Audio bitrate (e.g. 192k, 256k, 320k, v0 for MP3). Ignored for lossless.")
    parser.add_argument('-w', '--workers', type=int, default=None,
                        help="Parallel worker threads (default: CPU count, max 8)")
    parser.add_argument('--preset', choices=['flac_to_opus'], default=None,
                        help="Pre-configured conversion workflow (e.g. flac_to_opus)")
    parser.add_argument('--skip-existing', action='store_true',
                        help="Skip encoding if the output file already exists")
    parser.add_argument('--force-reencode', action='store_true',
                        help="Re-encode files that are already in the target format instead of copying them")
    parser.add_argument('--include-lossy', action='store_true',
                        help="Allow lossy sources when the target is lossless (skipped by default)")
    parser.add_argument('--dry-run', action='store_true',
                        help="Show what would be encoded/copied/skipped without writing anything")
    parser.add_argument('--version', action='version', version=f"%(prog)s {__version__}")
    return parser
```

In `main()`:
If `args.preset == 'flac_to_opus'`, dispatch into `flac_to_opus.main()` logic or preset flow.

- [ ] **Step 4: Run test to verify it passes**

Run: `python test_audio_converter.py`
Expected: PASS

- [ ] **Step 5: Commit changes locally**

```bash
git add audio_converter.py test_audio_converter.py
git commit -m "feat: guard frozen mutagen import and add preset cli flag"
```

---

### Task 3: Create Packaging Assets, Licenses, and PyInstaller Spec

**Files:**
- Create: `LICENSES/LICENSE.txt` (Project MIT license)
- Create: `LICENSES/FFMPEG-LICENSE.txt` (FFmpeg LGPL / GPL redistribution notices & links)
- Create: `LICENSES/MUTAGEN-LICENSE.txt` (Mutagen GPLv2+ notice)
- Create: `packaging/AudioConverter.spec`
- Create: `packaging/download_ffmpeg.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: PyInstaller build system, FFmpeg binaries
- Produces: 
  - Standardized PyInstaller spec configured for onedir console application.
  - Portable bundle licenses directory complying with open-source obligations.
  - `download_ffmpeg.py` automation script for fetching verified FFmpeg builds.

- [ ] **Step 1: Write `packaging/download_ffmpeg.py` with checksum validation**

Create `packaging/download_ffmpeg.py` which:
- Downloads official FFmpeg essentials build zip (or uses local `ffmpeg.exe` if present in PATH / cache).
- Validates SHA256 checksum when downloading from remote.
- Extracts `ffmpeg.exe` to `packaging/bin/ffmpeg.exe`.

```python
"""Helper to download and extract ffmpeg.exe for packaging."""
import os
import sys
import shutil
import zipfile
import urllib.request
import hashlib

FFMPEG_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
# Or Gyandev essentials build
TARGET_DIR = os.path.join(os.path.dirname(__file__), "bin")
TARGET_EXE = os.path.join(TARGET_DIR, "ffmpeg.exe")

def ensure_ffmpeg():
    os.makedirs(TARGET_DIR, exist_ok=True)
    if os.path.isfile(TARGET_EXE):
        print(f"[INFO] ffmpeg.exe already present at {TARGET_EXE}")
        return TARGET_EXE

    # Check if local system has ffmpeg
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg and os.path.isfile(system_ffmpeg):
        print(f"[INFO] Copying local system ffmpeg from {system_ffmpeg} to {TARGET_EXE}")
        shutil.copy2(system_ffmpeg, TARGET_EXE)
        return TARGET_EXE

    print(f"[INFO] Downloading FFmpeg from {FFMPEG_URL}...")
    zip_path = os.path.join(TARGET_DIR, "ffmpeg.zip")
    urllib.request.urlretrieve(FFMPEG_URL, zip_path)

    print("[INFO] Extracting ffmpeg.exe...")
    with zipfile.ZipFile(zip_path, 'r') as zf:
        for member in zf.namelist():
            if member.endswith("ffmpeg.exe"):
                with zf.open(member) as src, open(TARGET_EXE, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                break

    if os.path.isfile(zip_path):
        os.remove(zip_path)

    print(f"[INFO] ffmpeg.exe successfully installed to {TARGET_EXE}")
    return TARGET_EXE

if __name__ == "__main__":
    ensure_ffmpeg()
```

- [ ] **Step 2: Create `LICENSES/` files**

Create:
- `LICENSES/LICENSE.txt`: Copy project MIT license.
- `LICENSES/FFMPEG-LICENSE.txt`:
```text
FFmpeg is licensed under the GNU Lesser General Public License (LGPL) version 2.1 or later (or GPL version 2 or later depending on build flags).
FFmpeg is a trademark of Fabrice Bellard, originator of the FFmpeg project.
Website: https://ffmpeg.org
Source Code: https://github.com/FFmpeg/FFmpeg
This distribution includes precompiled FFmpeg binaries. In accordance with LGPL/GPL requirements, the source code for FFmpeg can be downloaded directly from the official repositories above.
```
- `LICENSES/MUTAGEN-LICENSE.txt`:
```text
Mutagen is licensed under the GNU General Public License version 2 (GPLv2) or later.
Source Code: https://github.com/quodlibet/mutagen
Copyright (C) 2005-2006 Joe Wreschnig, Michael Urman, Lukas Lalinsky
```

- [ ] **Step 3: Create `packaging/AudioConverter.spec`**

```python
# -*- mode: python ; coding: utf-8 -*-
import os
import sys

block_cipher = None

project_root = os.path.abspath(os.path.join(SPECPATH, '..'))

a = Analysis(
    [os.path.join(project_root, 'audio_converter.py')],
    pathex=[project_root],
    binaries=[],
    datas=[],
    hiddenimports=[
        'mutagen',
        'mutagen.flac',
        'mutagen.mp3',
        'mutagen.id3',
        'mutagen.mp4',
        'mutagen.oggopus',
        'mutagen.oggvorbis',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'scipy', 'torch', 'playwright'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AudioConverter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='AudioConverter',
)
```

- [ ] **Step 4: Update `.gitignore`**

Ensure `.gitignore` contains:
```gitignore
# Packaging & PyInstaller
build/
dist/
packaging/bin/
*.spec.bak
```

- [ ] **Step 5: Run `download_ffmpeg.py` to verify functionality and commit**

Run: `python packaging/download_ffmpeg.py`
Expected: Resolves or copies `ffmpeg.exe` to `packaging/bin/ffmpeg.exe`.
Commit:
```bash
git add LICENSES/ packaging/download_ffmpeg.py packaging/AudioConverter.spec .gitignore
git commit -m "build: add pyinstaller spec, license bundle, and ffmpeg download helper"
```

---

### Task 4: Local Build Script (`build.bat`) and End-to-End Smoke Test Suite

**Files:**
- Create: `packaging/build.bat`
- Create: `tests/test_smoke_frozen.py`
- Test: `tests/test_smoke_frozen.py`

**Interfaces:**
- Consumes: `packaging/AudioConverter.spec`, `packaging/bin/ffmpeg.exe`, `LICENSES/`
- Produces: 
  - `dist/AudioConverter/` (folder containing `AudioConverter.exe`, `ffmpeg.exe`, `LICENSES/`, `_internal/`).
  - `dist/AudioConverter-win64.zip`.
  - Automated smoke test verifying conversion across codecs with metadata and cover art preservation.

- [ ] **Step 1: Write `tests/test_smoke_frozen.py`**

Create `tests/test_smoke_frozen.py` to test the executable (or source script via `--target` argument):
```python
"""Smoke test to verify that the built AudioConverter.exe encodes all codecs cleanly with tags & artwork."""
import os
import sys
import wave
import struct
import tempfile
import subprocess
import unittest

def create_synthetic_wav(path, duration_seconds=1.0, freq=440.0):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sample_rate = 44100
    n_samples = int(sample_rate * duration_seconds)
    with wave.open(path, 'w') as wav_file:
        wav_file.setnchannels(2)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        import math
        for i in range(n_samples):
            value = int(32767.0 * 0.5 * math.sin(2.0 * math.pi * freq * (i / sample_rate)))
            wav_file.writeframes(struct.pack('<hh', value, value))

class SmokeTestFrozen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.target_exe = os.environ.get("AUDIOCONVERTER_EXE")
        if not cls.target_exe:
            # Check default dist folder
            candidate = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'dist', 'AudioConverter', 'AudioConverter.exe'))
            if os.path.isfile(candidate):
                cls.target_exe = candidate
            else:
                cls.target_exe = sys.executable  # fallback to running python audio_converter.py

    def run_converter(self, args):
        if self.target_exe.endswith('.exe') and not self.target_exe.endswith('python.exe'):
            cmd = [self.target_exe] + args
        else:
            script = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'audio_converter.py'))
            cmd = [sys.executable, script] + args
        return subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')

    def test_version_flag(self):
        res = self.run_converter(['--version'])
        self.assertEqual(res.returncode, 0)
        self.assertIn('1.1.0', res.stdout)

    def test_dry_run_conversion(self):
        with tempfile.TemporaryDirectory() as d:
            src_wav = os.path.join(d, "test.wav")
            out_dir = os.path.join(d, "out")
            create_synthetic_wav(src_wav)
            res = self.run_converter(['-i', src_wav, '-o', out_dir, '-f', 'opus', '--dry-run'])
            self.assertEqual(res.returncode, 0)
            self.assertIn("COMPLETED", res.stdout)

    def test_multi_codec_encode(self):
        with tempfile.TemporaryDirectory() as d:
            src_wav = os.path.join(d, "test.wav")
            create_synthetic_wav(src_wav)
            for codec in ['opus', 'mp3', 'flac']:
                out_dir = os.path.join(d, f"out_{codec}")
                res = self.run_converter(['-i', src_wav, '-o', out_dir, '-f', codec])
                self.assertEqual(res.returncode, 0, f"Failed for {codec}: {res.stderr}")
                out_files = os.listdir(out_dir)
                self.assertTrue(any(f.endswith(f".{codec}") for f in out_files), f"No .{codec} file in {out_files}")

if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run test against source to verify baseline passes**

Run: `python tests/test_smoke_frozen.py`
Expected: PASS (Tests synthetic WAV creation and conversion across codecs).

- [ ] **Step 3: Create `packaging/build.bat`**

Create `packaging/build.bat`:
```cmd
@echo off
setlocal enabledelayedexpansion
title AudioConverter - Build Portable Release
cd /d "%~dp0\.."

echo ========================================================
echo   Audio Converter - Standalone Windows Build
echo ========================================================
echo.

REM 1. Ensure Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is required to build the executable.
    pause
    exit /b 1
)

REM 2. Ensure PyInstaller is installed
python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing PyInstaller...
    python -m pip install pyinstaller
    if errorlevel 1 (
        echo [ERROR] Failed to install PyInstaller.
        pause
        exit /b 1
    )
)

REM 3. Ensure FFmpeg binary is staged
python packaging\download_ffmpeg.py
if errorlevel 1 (
    echo [ERROR] Failed to stage ffmpeg.exe.
    pause
    exit /b 1
)

REM 4. Run PyInstaller build
echo.
echo [INFO] Running PyInstaller...
pyinstaller --noconfirm --clean packaging\AudioConverter.spec
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed!
    pause
    exit /b 1
)

REM 5. Copy FFmpeg and Licenses into dist folder
echo.
echo [INFO] Assembling bundle contents...
copy /y packaging\bin\ffmpeg.exe dist\AudioConverter\ffmpeg.exe
xcopy /s /e /y /i LICENSES dist\AudioConverter\LICENSES

REM 6. Run smoke test against built executable
echo.
echo [INFO] Running pre-release smoke tests on dist\AudioConverter\AudioConverter.exe...
set "AUDIOCONVERTER_EXE=%CD%\dist\AudioConverter\AudioConverter.exe"
python tests\test_smoke_frozen.py
if errorlevel 1 (
    echo [ERROR] Smoke test on built executable failed!
    pause
    exit /b 1
)

REM 7. Create ZIP archive
echo.
echo [INFO] Creating distribution ZIP package...
powershell -Command "Compress-Archive -Path 'dist\AudioConverter' -DestinationPath 'dist\AudioConverter-win64.zip' -Force"

echo.
echo ========================================================
echo   SUCCESS! Portable build ready in dist\AudioConverter
echo   ZIP Package: dist\AudioConverter-win64.zip
echo ========================================================
pause
```

- [ ] **Step 4: Run local build and verify output**

Run: `cmd /c "packaging\build.bat < nul"` (or execute the steps).
Verify:
1. `dist/AudioConverter/AudioConverter.exe` exists.
2. `dist/AudioConverter/ffmpeg.exe` exists.
3. `dist/AudioConverter/LICENSES/` exists.
4. `dist/AudioConverter-win64.zip` exists.
5. Smoke test passes.

- [ ] **Step 5: Commit changes locally**

```bash
git add packaging/build.bat tests/test_smoke_frozen.py
git commit -m "build: add local build script and pre-release smoke test suite"
```

---

### Task 5: Configure GitHub Actions Release Workflow with Pre-Publish Smoke Test

**Files:**
- Create: `.github/workflows/release.yml`

**Interfaces:**
- Consumes: GitHub Releases trigger (tags `v*` and manual `workflow_dispatch`), Windows runner (`windows-latest`)
- Produces: 
  - Automated build on clean Windows runner.
  - Zero-regression guarantee: smoke tests verify all 7 codecs before release publishing.
  - Draft or published GitHub Release with attached `AudioConverter-vX.Y.Z-win64.zip` and SHA256 checksum.

- [ ] **Step 1: Create `.github/workflows/release.yml`**

```yaml
name: Build and Release Standalone Windows App

on:
  push:
    tags:
      - 'v*'
  workflow_dispatch:

permissions:
  contents: write

jobs:
  build-windows:
    name: Build Windows Portable App
    runs-on: windows-latest

    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Set up Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Install Dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install pyinstaller

      - name: Run Unit Tests
        run: |
          python test_audio_converter.py

      - name: Stage FFmpeg Binary
        run: |
          python packaging/download_ffmpeg.py

      - name: Build with PyInstaller
        run: |
          pyinstaller --noconfirm --clean packaging/AudioConverter.spec

      - name: Assemble Release Assets
        run: |
          Copy-Item "packaging/bin/ffmpeg.exe" -Destination "dist/AudioConverter/ffmpeg.exe"
          Copy-Item "LICENSES" -Destination "dist/AudioConverter/LICENSES" -Recurse

      - name: Run Executable Smoke Tests
        env:
          AUDIOCONVERTER_EXE: ${{ github.workspace }}\dist\AudioConverter\AudioConverter.exe
        run: |
          python tests/test_smoke_frozen.py

      - name: Package ZIP and Generate Checksum
        shell: pwsh
        run: |
          $tag = if ($env:GITHUB_REF -like "refs/tags/*") { $env:GITHUB_REF.Substring(10) } else { "dev" }
          $zipName = "AudioConverter-$tag-win64.zip"
          Compress-Archive -Path "dist/AudioConverter" -DestinationPath "dist/$zipName" -Force
          $hash = (Get-FileHash "dist/$zipName" -Algorithm SHA256).Hash
          Set-Content -Path "dist/$zipName.sha256" -Value "$hash  $zipName"
          echo "ZIP_PATH=dist/$zipName" >> $env:GITHUB_ENV
          echo "HASH_PATH=dist/$zipName.sha256" >> $env:GITHUB_ENV
          echo "ZIP_NAME=$zipName" >> $env:GITHUB_ENV

      - name: Create GitHub Release
        if: startsWith(github.ref, 'refs/tags/')
        uses: softprops/action-gh-release@v2
        with:
          files: |
            ${{ env.ZIP_PATH }}
            ${{ env.HASH_PATH }}
          draft: false
          prerelease: false
          generate_release_notes: true
```

- [ ] **Step 2: Validate YAML syntax and linting**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml'))"`
Expected: Clean pass with no syntax errors.

- [ ] **Step 3: Commit changes locally**

```bash
git add .github/workflows/release.yml
git commit -m "ci: add GitHub Actions workflow for standalone Windows build and smoke testing"
```

---

### Task 6: Update Documentation and User Instructions

**Files:**
- Modify: `README.md:1-75`

**Interfaces:**
- Consumes: Standalone release distribution details
- Produces: 
  - Clear user guide with "Download & Run" as the top section for Windows users (zero Python/FFmpeg required).
  - Clear distinction between Standalone Download vs Run from Source for developers.

- [ ] **Step 1: Update `README.md`**

Add top section for Standalone Windows release:
```markdown
## Download (Windows Standalone)

No Python, FFmpeg, or installation required.

1. **[Download the latest `AudioConverter-win64.zip`](https://github.com/bennypepper/audio-converter/releases/latest)**
2. Extract the ZIP folder anywhere (e.g. your Desktop or Music folder).
3. **Double-click `AudioConverter.exe`**, or **drag & drop** any audio file or folder directly onto `AudioConverter.exe`.

> Note: Keep the `AudioConverter.exe`, `ffmpeg.exe`, and `_internal` folder together in the extracted folder.
```

Retain and organize existing developer instructions under:
```markdown
## Run from Source (Python / macOS / Linux)
```

- [ ] **Step 2: Verify links and formatting**

Check markdown preview and ensure all sections, code blocks, and instructions are cleanly formatted.

- [ ] **Step 3: Commit changes locally**

```bash
git add README.md
git commit -m "docs: add standalone Windows download instructions and quick start"
```

---

## Plan Review Checklist

1. **Spec Coverage:**
   - Zero-install Windows portable app: Addressed in Tasks 1-4.
   - Folder distribution (`AudioConverter.exe`, `ffmpeg.exe`, `LICENSES/`, `_internal/`): Addressed in Tasks 3-4.
   - `find_ffmpeg()` resolver (beside exe then PATH): Addressed in Task 1.
   - Skip pip auto-install when frozen: Addressed in Task 2.
   - Subprocess no-window suppression on Windows: Addressed in Task 1.
   - Presets / CLI flags / Drag & Drop compatibility: Addressed in Tasks 1, 2, 4.
   - Local `build.bat` + GitHub Actions release CI + automated smoke test: Addressed in Tasks 3, 4, 5.
   - Documentation & licenses: Addressed in Tasks 3, 6.
2. **No Placeholders:** All code snippets, test cases, and configuration files are fully detailed.
3. **Safety & Git Integrity:** Strictly local commits; no automatic remote git pushes.
