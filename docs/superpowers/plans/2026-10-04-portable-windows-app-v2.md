# Portable Windows App — Implementation Plan (v2, corrected)

> **For agentic workers:** execute task-by-task, in the order and parallelism rules in "Execution order". Steps use checkbox (`- [ ]`) syntax. Locate code by **function name**, not line number (line numbers drift).
> Supersedes the earlier plan. Every change versus that plan is a fix for a concrete defect found in review; see "What changed" at the end.

**Goal:** ship `AudioConverter-vX.Y.Z-win64.zip`: a zero-install, portable Windows build (PyInstaller `--onedir`, FFmpeg bundled beside the exe) while the existing source/CLI/launcher workflows keep working unchanged.

**Architecture (unchanged in spirit):**

```text
AudioConverter/                  <- zip's single top-level folder
├─ AudioConverter.exe            <- console app (PyInstaller onedir)
├─ ffmpeg.exe                    <- pinned, checksum-verified build
├─ README.txt                    <- 3-line "how to run"
├─ LICENSES/                     <- real license texts, assembled at build time
└─ _internal/                    <- Python runtime + libs
```

`find_ffmpeg()` looks beside the exe first, then PATH. Subprocesses use `CREATE_NO_WINDOW` on Windows. The frozen app never calls pip. `--preset flac_to_opus` runs the existing FLAC→Opus workflow from the same exe. One build script (`packaging/build.py`) is used by both `build.bat` and CI, so they cannot drift.

## Decisions baked into this plan (owner: change BEFORE dispatching if you disagree)

| # | Decision | Default used here | Why |
| :-- | :-- | :-- | :-- |
| D1 | Project license | **GPL-2.0-or-later** | `mutagen` is GPL-2.0-or-later and is compiled into the exe, so the distributed binary is a GPL combined work. MIT alone is not valid for that binary. GPL-3.0-or-later is also acceptable; GPL-2.0-or-later is used because its text ships inside mutagen's own dist-info, so agents can copy it offline. Not legal advice; owner should sanity-check. |
| D2 | FFmpeg source | **Pinned release listed in `packaging/ffmpeg.lock.json`**, SHA-256 verified | A moving "latest" URL makes releases unreproducible and the license text can't match the shipped build. The provider's page states its *essentials* build is GPLv3 and includes libmp3lame, libopus and libvorbis, but **no verified URL/hash could be retrieved while writing this plan**, so the lock file ships with placeholders the owner fills in (see "Owner checklist"). |
| D3 | Preset design | `flac_to_opus.py` stays the implementation; `AudioConverter.exe --preset flac_to_opus ...` dispatches to it | Least churn; the old `flac_to_opus.py` CLI and `.bat/.sh` launchers keep working. |
| D4 | Python support | **3.9+** (CI-verified on 3.9 and 3.13) | The README currently claims 3.8+, which nobody verifies. Claim only what CI checks. |
| D5 | First release | Published as a **draft** | Unsigned exe; review before making it public. |

## Global constraints

- **Target:** Windows 10/11 x64. Distribution is a zip of the onedir folder (no single-file exe, no registry, no installer).
- **Backward compatibility (must stay 100% working):** all existing flags (`-i -o -f -b -w --skip-existing --force-reencode --include-lossy --dry-run --version`), the wizard (`b`/`q`, back navigation), drag-and-drop path argument, `convert.bat/.sh`, `flac_to_opus.py` + `flac_to_opus_192k.bat/.sh`.
- **Git:** never `git push`. Local Conventional Commits only (follow the harness's commit-attribution rules). If the working directory is not a git repo, run `git init -b main` and commit the current state as `chore: import current state` first.
- **No fabricated facts:** no guessed GitHub URLs, no invented hashes, no paraphrased license texts. Use placeholders (`<your-username>/<repo-name>`, `REPLACE_ME`) where a value is unknown.
- **Do not change** `-map_metadata` handling or any encoding arguments. (The earlier plan slipped in `-map_metadata:g 0:s:a:0`; it is intentionally absent.)

## What agents can and cannot verify

Agents run on Linux. **They cannot** run PyInstaller for Windows, `build.bat`, or the exe. Do not claim they did.

| Verifiable here (must be done) | Only verifiable on Windows/CI (document, do not claim) |
| :-- | :-- |
| Unit tests; `py_compile`; smoke tests in **source mode** with a real ffmpeg (Task 0); helper functions of `build.py`/`download_ffmpeg.py`; YAML parses; spec is valid Python | Frozen exe behaviour, bundled-ffmpeg lookup, zip contents, SmartScreen, the CI workflow itself (first real run = manual `workflow_dispatch`, which the **owner** triggers by pushing) |

### Already verified while writing this plan

The snippets for Tasks 0-4 were applied, exactly as written, to a scratch copy of the current repo and executed (Linux, Python 3.13, real FFmpeg 7.0.2 from `imageio-ffmpeg`):

- 43 unit tests pass (16 existing + the new `FindFFmpeg`, `SubprocessKwargs`, `Fatal`, `SplitPreset`, `ParserAndPreset`, `ValidateLock`, `PickMembers`, `Hashing`, `BuildHelpers`).
- All 8 smoke tests pass against the source: **all 7 codecs keep the title, artist and cover art** (and ALAC/AAC are told apart inside `.m4a`).
- The smoke test is not vacuous: deliberately disabling cover-art embedding made 6 of 7 codec checks fail (WAV has no art).
- `--preset flac_to_opus` works through `audio_converter.py` with the module alias, and `flac_to_opus.py` still works standalone.
- `packaging/AudioConverter.spec` parses; `PyInstaller 6.22.3` and `mutagen 1.48.1` exist on PyPI; mutagen's `COPYING` is present in its dist-info.

If your results differ from this, treat it as a regression to investigate, not as a reason to loosen a test.

## Execution order

```text
Task 0  ──►  Task 1  ──►  Task 2  ──┐
   └──────►  Task 3  (parallel with 1-2; disjoint files) ──┤
                                                           ├─► Task 4 ─► Task 5 ─► Task 6 ─► Task 7
```

Tasks 1 and 2 edit the same file: **sequential**. Task 3 touches only `LICENSE`, `LICENSES`-related text and `packaging/`: may run in parallel with 1-2. Task 6 (README) last before final verification.

---

## Task 0: Repo prep and a real-ffmpeg test environment

**Files:** modify `.gitignore`; create `tests/__init__.py`, `tests/helpers.py`.

- [ ] **Step 1: git** — if not a repo: `git init -b main && git add -A && git commit -m "chore: import current state"`.

- [ ] **Step 2: tooling.** A real ffmpeg is available via pip (verified: includes libopus, libmp3lame, libvorbis, aac, alac, flac, pcm_s16le):

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install mutagen imageio-ffmpeg
mkdir -p .tools/bin
ln -sf "$(python -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())')" .tools/bin/ffmpeg
export PATH="$PWD/.tools/bin:$PATH"
ffmpeg -hide_banner -encoders | grep -E "libopus|libmp3lame|libvorbis"   # all three must print
```

If pip is unreachable, say so in the final report and fall back to unit tests only; do not fake smoke results.

- [ ] **Step 2b:** append to `.gitignore`:

```gitignore
# Build output & local tooling
build/
dist/
packaging/bin/
.venv/
.venv-build/
.tools/
*.spec.bak
```

- [ ] **Step 3: `tests/helpers.py`** (shared by unit, smoke and build tests; create empty `tests/__init__.py` too):

```python
"""Shared test helpers: synthetic audio, tiny cover art, tag readers."""
import math
import os
import struct
import wave
import zlib

TITLE = "Smoke Tëst ♫"
ARTIST = "Smoke Artist"


def make_wav(path, seconds=1.0, freq=440.0, rate=44100):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    frames = bytearray()
    for i in range(int(rate * seconds)):
        v = int(32767 * 0.4 * math.sin(2 * math.pi * freq * i / rate))
        frames += struct.pack('<hh', v, v)
    with wave.open(path, 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    return path


def tiny_png():
    """A valid 1x1 red PNG (stdlib only)."""
    def chunk(tag, data):
        body = tag + data
        return struct.pack('>I', len(data)) + body + struct.pack('>I', zlib.crc32(body) & 0xFFFFFFFF)
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b'\x00\xff\x00\x00'))
            + chunk(b'IEND', b''))


def tag_flac(path):
    """Writes the reference title/artist/album and a cover picture into a FLAC file."""
    from mutagen.flac import FLAC, Picture
    f = FLAC(path)
    f['title'], f['artist'], f['album'] = [TITLE], [ARTIST], ['Smoke Album']
    pic = Picture()
    pic.type, pic.mime, pic.desc, pic.data = 3, 'image/png', 'Cover', tiny_png()
    pic.width = pic.height = 1
    pic.depth = 24
    f.clear_pictures()
    f.add_picture(pic)
    f.save()


def read_tags(path):
    """Returns (title, artist, has_cover_art) for .flac/.opus/.ogg/.mp3/.m4a."""
    ext = os.path.splitext(path)[1].lower()

    def first(values):
        return values[0] if values else None

    if ext == '.flac':
        from mutagen.flac import FLAC
        a = FLAC(path)
        return first(a.get('title')), first(a.get('artist')), bool(a.pictures)
    if ext in ('.opus', '.ogg'):
        if ext == '.opus':
            from mutagen.oggopus import OggOpus as Cls
        else:
            from mutagen.oggvorbis import OggVorbis as Cls
        a = Cls(path)
        return first(a.get('title')), first(a.get('artist')), 'metadata_block_picture' in a
    if ext == '.mp3':
        from mutagen.id3 import ID3
        t = ID3(path)
        return (str(t['TIT2']) if 'TIT2' in t else None,
                str(t['TPE1']) if 'TPE1' in t else None,
                bool(t.getall('APIC')))
    if ext == '.m4a':
        from mutagen.mp4 import MP4
        tags = MP4(path).tags or {}
        return first(tags.get('\xa9nam')), first(tags.get('\xa9ART')), bool(tags.get('covr'))
    raise ValueError(f"unsupported extension: {ext}")
```

- [ ] **Step 4: verify** `python -m unittest discover tests` still passes (existing 16 tests). Commit: `test: add shared helpers and ignore build output`.

---

## Task 1: `find_ffmpeg()`, quiet subprocesses, and visible fatal errors

**Files:** modify `audio_converter.py` (`check_ffmpeg`, `convert_single_file`, helpers above the mutagen import block); modify `tests/test_audio_converter.py`.
`flac_to_opus.py` needs **no change** here (it already calls `ac.check_ffmpeg()`).

**Interfaces produced:**
`find_ffmpeg() -> str | None` (cached) · `get_subprocess_kwargs() -> dict` · `fatal(message, hint=None, code=1)` (prints, pauses only for double-click/drag-drop launches of the frozen exe, then `sys.exit(code)`) · `check_ffmpeg()` now routes through `fatal` and returns the path.

- [ ] **Step 1: write the failing tests** (add to `tests/test_audio_converter.py`; add `import subprocess, sys` and `from unittest import mock` at the top if missing):

```python
FROZEN = dict(create=True)


class FindFFmpeg(unittest.TestCase):
    def setUp(self):
        ac.find_ffmpeg.cache_clear()

    def tearDown(self):
        ac.find_ffmpeg.cache_clear()

    def test_prefers_bundled_beside_frozen_exe_over_path(self):
        with tempfile.TemporaryDirectory() as d:
            bundled = touch(os.path.join(d, 'ffmpeg.exe'))
            with mock.patch.object(sys, 'frozen', True, **FROZEN), \
                 mock.patch.object(sys, 'executable', os.path.join(d, 'AudioConverter.exe')), \
                 mock.patch('shutil.which', return_value='/usr/bin/ffmpeg'):
                self.assertEqual(ac.find_ffmpeg(), os.path.abspath(bundled))

    def test_falls_back_to_path(self):
        with tempfile.TemporaryDirectory() as d:
            on_path = touch(os.path.join(d, 'bin', 'ffmpeg'))
            with mock.patch.object(sys, 'frozen', True, **FROZEN), \
                 mock.patch.object(sys, 'executable', os.path.join(d, 'AudioConverter.exe')), \
                 mock.patch('shutil.which', return_value=on_path):
                self.assertEqual(ac.find_ffmpeg(), os.path.abspath(on_path))

    def test_returns_none_when_missing(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(sys, 'frozen', True, **FROZEN), \
                 mock.patch.object(sys, 'executable', os.path.join(d, 'AudioConverter.exe')), \
                 mock.patch('shutil.which', return_value=None):
                self.assertIsNone(ac.find_ffmpeg())


class SubprocessKwargs(unittest.TestCase):
    def test_windows_hides_console(self):
        with mock.patch.object(sys, 'platform', 'win32'):
            flag = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
            self.assertEqual(ac.get_subprocess_kwargs(), {'creationflags': flag})

    def test_other_platforms_add_nothing(self):
        with mock.patch.object(sys, 'platform', 'linux'):
            self.assertEqual(ac.get_subprocess_kwargs(), {})


class Fatal(unittest.TestCase):
    def _run(self, frozen, tty, argv):
        class FakeStdin:
            def isatty(self_inner):
                return tty
        with mock.patch.object(sys, 'frozen', frozen, **FROZEN), \
             mock.patch.object(sys, 'stdin', FakeStdin()), \
             mock.patch.object(sys, 'argv', argv), \
             mock.patch('builtins.input') as fake_input, \
             mock.patch('builtins.print'):
            with self.assertRaises(SystemExit) as cm:
                ac.fatal("boom")
        return cm.exception.code, fake_input.called

    def test_pauses_for_drag_and_drop_launch_of_frozen_exe(self):
        self.assertEqual(self._run(True, True, ['AudioConverter.exe', 'C:\\Music']), (1, True))

    def test_pauses_for_plain_double_click(self):
        self.assertEqual(self._run(True, True, ['AudioConverter.exe']), (1, True))

    def test_never_pauses_when_flags_are_used(self):
        self.assertEqual(self._run(True, True, ['AudioConverter.exe', '-i', 'x']), (1, False))

    def test_never_pauses_from_source_or_pipes(self):
        self.assertEqual(self._run(False, True, ['audio_converter.py']), (1, False))
        self.assertEqual(self._run(True, False, ['AudioConverter.exe']), (1, False))
```

- [ ] **Step 2:** run `python -m unittest tests.test_audio_converter` → expect `AttributeError` for the new names.

- [ ] **Step 3: implement.** Add `import functools` to the imports. Directly after the `C_*` colour constants and **above** the mutagen import block add:

```python
def _launched_interactively():
    """True for a double-click / drag-and-drop launch of the frozen exe (real console, no flags)."""
    return (getattr(sys, 'frozen', False)
            and bool(sys.stdin) and sys.stdin.isatty()
            and not any(a.startswith('-') for a in sys.argv[1:]))


def fatal(message, hint=None, code=1):
    """Print an error and exit. A double-clicked exe waits for Enter so the message can be read."""
    print(f"{C_RED}[ERROR] {message}{C_RESET}")
    if hint:
        print(hint)
    if _launched_interactively():
        try:
            input(f"\n{C_DIM}Press Enter to exit...{C_RESET}")
        except (EOFError, KeyboardInterrupt):
            pass
    sys.exit(code)
```

Replace `check_ffmpeg` and add the resolver next to it:

```python
def _ffmpeg_search_dirs():
    if getattr(sys, 'frozen', False):
        dirs = [os.path.dirname(sys.executable)]
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            dirs.append(meipass)
        return dirs
    return [os.path.dirname(os.path.abspath(__file__))]


@functools.lru_cache(maxsize=1)
def find_ffmpeg():
    """Absolute path to ffmpeg: beside the app first (bundled copy wins), then PATH. None if not found."""
    for base in _ffmpeg_search_dirs():
        for name in ('ffmpeg.exe', 'ffmpeg'):
            candidate = os.path.join(base, name)
            if os.path.isfile(candidate):
                return os.path.abspath(candidate)
    on_path = shutil.which('ffmpeg')
    return os.path.abspath(on_path) if on_path else None


def get_subprocess_kwargs():
    """Extra subprocess.run kwargs: keep Windows from flashing a console window per ffmpeg call."""
    if sys.platform == 'win32':
        return {'creationflags': getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)}
    return {}


def check_ffmpeg():
    """Exit with a readable message when FFmpeg is missing; otherwise return its path."""
    path = find_ffmpeg()
    if not path:
        fatal("'ffmpeg' was not found next to this program or on your PATH.",
              "Put ffmpeg.exe in the same folder as this program (extract the whole zip first),\n"
              "or install FFmpeg and add it to PATH.")
    return path
```

In `convert_single_file`, change **only** these two things (leave every encoding argument and `-map_metadata` exactly as is):

```python
        ffmpeg_bin = find_ffmpeg() or 'ffmpeg'
        cmd = [ffmpeg_bin, '-y', '-nostdin', '-i', src_path, '-map', '0:a']
        ...
        res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace',
                             **get_subprocess_kwargs())
```

- [ ] **Step 4:** `python -m unittest discover tests` → all pass (16 old + new).
- [ ] **Step 5: commit** `feat: bundled-ffmpeg lookup, hidden console windows, visible fatal errors`.

---

## Task 2: Frozen import guard, `--preset`, safe module aliasing, crash handler

**Files:** modify `audio_converter.py`, `flac_to_opus.py`, `tests/test_audio_converter.py`.

**Why the design differs from the earlier plan:** calling `flac_to_opus.main()` from an exe that runs `audio_converter.py` as `__main__` makes `flac_to_opus`'s `import audio_converter` load a **second copy** of the module, and `flac_to_opus`'s argparse would reject `--preset`. Fixes: alias the running module, and strip `--preset` before handing arguments over.

- [ ] **Step 1: failing tests** (add to `tests/test_audio_converter.py`):

```python
class SplitPreset(unittest.TestCase):
    def test_no_preset_leaves_args_alone(self):
        self.assertEqual(ac.split_preset(['-i', 'x']), (None, ['-i', 'x']))

    def test_space_form(self):
        self.assertEqual(ac.split_preset(['--preset', 'flac_to_opus', 'src', '--dry-run']),
                         ('flac_to_opus', ['src', '--dry-run']))

    def test_equals_form_anywhere(self):
        self.assertEqual(ac.split_preset(['src', '--preset=flac_to_opus']), ('flac_to_opus', ['src']))

    def test_dangling_flag_is_left_for_argparse_to_reject(self):
        self.assertEqual(ac.split_preset(['--preset']), (None, ['--preset']))


class ParserAndPreset(unittest.TestCase):
    def test_parser_lists_preset(self):
        args = ac.build_argument_parser().parse_args(['--preset', 'flac_to_opus'])
        self.assertEqual(args.preset, 'flac_to_opus')

    def test_unknown_preset_is_rejected_with_exit_2(self):
        import contextlib
        import io
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            ac.main(['--preset', 'nope'])
        self.assertEqual(cm.exception.code, 2)

    def test_preset_names_match_parser_choices(self):
        parser = ac.build_argument_parser()
        choices = next(a.choices for a in parser._actions if a.dest == 'preset')
        self.assertEqual(sorted(choices), sorted(ac.PRESET_NAMES))
```

- [ ] **Step 2:** run → `AttributeError: ... split_preset`.

- [ ] **Step 3: implement in `audio_converter.py`.**

(a) Module aliasing, directly after the imports:

```python
if __name__ == '__main__':
    # Let `import audio_converter` (done by preset modules) reuse THIS module instead of loading a second copy.
    sys.modules.setdefault('audio_converter', sys.modules[__name__])
```

(b) Mutagen guard. In the existing `except ImportError:` block add as the **first** statement:

```python
    if getattr(sys, 'frozen', False):
        fatal("Required component 'mutagen' is missing from this build.",
              "Please re-download and fully extract the application.")
```

Keep the rest of the pip auto-install for source runs; replace its `input("Press Enter to exit...")`+`sys.exit(1)` with `fatal(...)` calls too, and use `C_*` constants instead of raw escape codes.

(c) Preset plumbing, above `main`:

```python
PRESET_NAMES = ('flac_to_opus',)


def split_preset(argv):
    """Pulls `--preset NAME` / `--preset=NAME` out of argv. Returns (name_or_None, remaining_args)."""
    name, rest, i = None, [], 0
    while i < len(argv):
        arg = argv[i]
        if arg == '--preset' and i + 1 < len(argv):
            name, i = argv[i + 1], i + 2
        elif arg.startswith('--preset='):
            name, i = arg.split('=', 1)[1], i + 1
        else:
            rest.append(arg)
            i += 1
    return name, rest
```

(d) Extract the parser from `main()` into `build_argument_parser()` (identical options; change `prog` to `"AudioConverter"` only when frozen: `prog="AudioConverter" if getattr(sys, 'frozen', False) else "audio_converter.py"`) and add:

```python
    parser.add_argument('--preset', choices=PRESET_NAMES, default=None,
                        help="Run a pre-configured workflow, e.g. --preset flac_to_opus SOURCE [DEST] "
                             "(takes its own options; see --preset flac_to_opus --help)")
```

(e) `main(argv=None)`: `argv = list(sys.argv[1:] if argv is None else argv)`. At the top:

```python
    parser = build_argument_parser()
    preset, rest = split_preset(argv)
    if preset is not None:
        if preset not in PRESET_NAMES:
            parser.error(f"unknown preset '{preset}' (choose from: {', '.join(PRESET_NAMES)})")
        import flac_to_opus  # imported lazily; the alias at the top of this file prevents a double load
        return flac_to_opus.main(rest, prog=f"{parser.prog} --preset {preset}")
    args = parser.parse_args(argv)
```

(f) Crash handler + entry point; replace the file's final block:

```python
def cli_entry():
    """Console entry point. A crash shows its traceback (and waits, for double-click launches)."""
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{C_YELLOW}[!] Cancelled.{C_RESET}")
        sys.exit(130)
    except SystemExit:
        raise
    except Exception:
        import traceback
        traceback.print_exc()
        fatal("Unexpected error. Please report it with the details above.")


if __name__ == '__main__':
    cli_entry()
```

(g) `flac_to_opus.py`: change `def main():` to `def main(argv=None, prog="flac_to_opus.py"):`, pass `prog=prog` to its `ArgumentParser`, call `parser.parse_args(argv)`, and make its `if __name__` block call `main()`. Everything else unchanged (`SOURCE [DEST] -b -w --overwrite --dry-run --version` must still work).

- [ ] **Step 4:** `python -m unittest discover tests` → pass. Also confirm manually: `python audio_converter.py --help` lists `--preset`; `python flac_to_opus.py --version` works.
- [ ] **Step 5: commit** `feat: frozen import guard, --preset dispatch, crash handler`.

---

## Task 3: License decision, packaging assets, pinned FFmpeg

**Files:** modify `LICENSE`; create `packaging/AudioConverter.spec`, `packaging/download_ffmpeg.py`, `packaging/ffmpeg.lock.json`, `packaging/THIRD-PARTY-NOTICES.txt`, `packaging/README-portable.txt`, `packaging/release-notes.md`, `requirements-build.txt`.

- [ ] **Step 1: license (D1).** Replace root `LICENSE` with: a 6-line project notice (`Audio Converter — Copyright (C) 2026 [Your Name]` … "either version 2 of the License, or (at your option) any later version") followed by the **verbatim GPL-2.0 text copied from mutagen's installed license file**:

```bash
python - <<'EOF'
import importlib.metadata as md
d = md.distribution("mutagen")
f = next(p for p in d.files if p.name == "COPYING")
print(d.locate_file(f))
EOF
```

Check the copied file begins with `GNU GENERAL PUBLIC LICENSE` / `Version 2, June 1991`. Leave `[Your Name]` as a placeholder.

- [ ] **Step 2: `requirements-build.txt`** (versions verified to exist):

```text
-r requirements.txt
pyinstaller==6.22.3
mutagen==1.48.1
```

- [ ] **Step 3: `packaging/ffmpeg.lock.json`** (placeholders on purpose; D2):

```json
{
  "version": "REPLACE_ME",
  "url": "REPLACE_ME",
  "sha256": "REPLACE_ME",
  "license": "REPLACE_ME",
  "source_url": "REPLACE_ME"
}
```

- [ ] **Step 4: `packaging/download_ffmpeg.py`**

```python
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
```

- [ ] **Step 5: `packaging/AudioConverter.spec`.** Generate the skeleton with the pinned PyInstaller (`pyi-makespec --onedir --console --name AudioConverter audio_converter.py`; PyInstaller 6.x specs have **no** `cipher`/`block_cipher`/`a.zipfiles`), then make it:

```python
# -*- mode: python ; coding: utf-8 -*-
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))

a = Analysis(
    [os.path.join(ROOT, 'audio_converter.py')],
    pathex=[ROOT],
    binaries=[],
    datas=[],
    hiddenimports=['flac_to_opus'],   # imported lazily by the --preset dispatcher
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AudioConverter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX-packed exes trigger far more antivirus false positives
    console=True,       # this is a terminal app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='AudioConverter',
)
```

Verify here: `python -c "import ast,sys; ast.parse(open('packaging/AudioConverter.spec').read())"`.

- [ ] **Step 6: static text files.**
  - `packaging/README-portable.txt` (goes in the zip root): (1) extract the **whole** folder — do not run from inside the zip; (2) double-click `AudioConverter.exe` or drag a file/folder onto it; keep `AudioConverter.exe`, `ffmpeg.exe` and `_internal` together; (3) Windows may show a SmartScreen warning because the app is unsigned: **More info → Run anyway**; licenses are in `LICENSES\`.
  - `packaging/THIRD-PARTY-NOTICES.txt`: list Python (PSF License 2.0), mutagen (GPL-2.0-or-later, https://github.com/quodlibet/mutagen), PyInstaller bootloader (GPL-2.0-or-later with the bootloader exception, https://pyinstaller.org), FFmpeg (license and source link: see `FFmpeg-SOURCE.txt`; FFmpeg is a separate program launched as a subprocess). State that the full texts for mutagen and FFmpeg are in this folder.
  - `packaging/release-notes.md`: unsigned-exe/SmartScreen note, how to verify the `.sha256`, "extract before running", one line on the GPL licensing.

- [ ] **Step 7: tests** — create `tests/test_build_helpers.py`:

```python
import importlib.util
import os
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, 'packaging', f'{name}.py'))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod          # needed by zipfile/dataclass-style lookups; harmless here
    spec.loader.exec_module(mod)
    return mod


dl = load('download_ffmpeg')
GOOD = {'version': '1', 'url': 'https://example.invalid/f.zip', 'sha256': 'a' * 64,
        'license': 'GPL-3.0-or-later', 'source_url': 'https://example.invalid/src'}


class ValidateLock(unittest.TestCase):
    def test_placeholders_rejected(self):
        with self.assertRaises(ValueError):
            dl.validate_lock({k: 'REPLACE_ME' for k in GOOD})

    def test_bad_hash_and_http_rejected(self):
        with self.assertRaises(ValueError):
            dl.validate_lock({**GOOD, 'sha256': 'xyz'})
        with self.assertRaises(ValueError):
            dl.validate_lock({**GOOD, 'url': 'http://example.invalid/f.zip'})

    def test_good_lock_passes(self):
        dl.validate_lock(GOOD)

    def test_committed_lock_has_all_keys(self):
        import json
        with open(os.path.join(ROOT, 'packaging', 'ffmpeg.lock.json'), encoding='utf-8') as fh:
            self.assertEqual(set(json.load(fh)), set(dl.REQUIRED_KEYS))


class PickMembers(unittest.TestCase):
    def test_finds_exe_and_license(self):
        names = ['ffmpeg-7/LICENSE', 'ffmpeg-7/bin/ffmpeg.exe', 'ffmpeg-7/bin/ffprobe.exe']
        self.assertEqual(dl.pick_members(names), ('ffmpeg-7/bin/ffmpeg.exe', 'ffmpeg-7/LICENSE'))

    def test_missing_license_is_an_error(self):
        with self.assertRaises(ValueError):
            dl.pick_members(['ffmpeg-7/bin/ffmpeg.exe'])


class Hashing(unittest.TestCase):
    def test_sha256_of_known_content(self):
        with tempfile.NamedTemporaryFile(delete=False) as fh:
            fh.write(b'abc')
        try:
            self.assertEqual(dl.sha256_file(fh.name),
                             'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
        finally:
            os.remove(fh.name)


if __name__ == '__main__':
    unittest.main()
```

(Task 4 appends `build.py` helper tests to this file.)

- [ ] **Step 8: verify** `python -m unittest tests.test_build_helpers`; `python packaging/download_ffmpeg.py` must print the "not filled in" error and exit 1 (this is the correct behaviour until the owner pins a build). Commit: `build: pinned-ffmpeg staging, spec, GPL license and notices`.

---

## Task 4: One build script, local wrapper, and the real smoke tests

**Files:** create `packaging/build.py`, `packaging/build.bat`, `tests/test_smoke.py`; append to `tests/test_build_helpers.py`.

- [ ] **Step 1: `tests/test_smoke.py`.** Runs against the **source** by default, or a built exe when `AUDIOCONVERTER_EXE` is set. It must verify the product promise: **all 7 codecs, tags, cover art**.

```python
"""End-to-end smoke tests.

Source mode (default; needs an ffmpeg on PATH, else the suite skips itself):
    python -m unittest tests.test_smoke -v
Built exe:
    set AUDIOCONVERTER_EXE=dist\\AudioConverter\\AudioConverter.exe
    python -m unittest tests.test_smoke -v
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
import helpers  # noqa: E402

EXE = os.environ.get('AUDIOCONVERTER_EXE')


def source_version():
    with open(os.path.join(ROOT, 'audio_converter.py'), encoding='utf-8') as fh:
        text = fh.read()
    return re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.M).group(1)


def command(args):
    base = [EXE] if EXE else [sys.executable, os.path.join(ROOT, 'audio_converter.py')]
    return base + list(args)


def clean_env():
    env = dict(os.environ)
    if EXE and sys.platform == 'win32':
        # Prove the BUNDLED ffmpeg is used: hide anything installed on the machine.
        root = os.environ.get('SystemRoot', r'C:\Windows')
        env['PATH'] = os.pathsep.join([os.path.join(root, 'System32'), root])
    return env


def run(args, stdin=None, env=None, timeout=300):
    return subprocess.run(command(args), input=stdin, capture_output=True, text=True,
                          encoding='utf-8', errors='replace', env=env or clean_env(), timeout=timeout)


def out_files(folder):
    return sorted(os.listdir(folder)) if os.path.isdir(folder) else []


def setUpModule():
    if EXE:
        assert os.path.isfile(EXE), f"AUDIOCONVERTER_EXE does not exist: {EXE}"
    else:
        import audio_converter as ac
        if not ac.find_ffmpeg():
            raise unittest.SkipTest("no ffmpeg available for source-mode smoke tests")


# codec flag, expected extension, extra args.  flac->flac would be a plain copy, so force a real encode.
CASES = [('opus', '.opus', []), ('m4a', '.m4a', []), ('mp3', '.mp3', []), ('ogg', '.ogg', []),
         ('alac', '.m4a', []), ('flac', '.flac', ['--force-reencode']), ('wav', '.wav', [])]


class Smoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="Audio Smoke ")   # space in the path on purpose
        cls.tmp = cls._tmp.name
        cls.wav = helpers.make_wav(os.path.join(cls.tmp, 'wav', 'tone.wav'))
        cls.flac_dir = os.path.join(cls.tmp, 'flac')
        r = run(['-i', cls.wav, '-f', 'flac', '-o', cls.flac_dir])
        assert r.returncode == 0, r.stdout + r.stderr
        cls.flac = os.path.join(cls.flac_dir, 'tone.flac')
        helpers.tag_flac(cls.flac)     # reference tags + cover art that every codec must preserve

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_version_matches_source(self):
        r = run(['--version'])
        self.assertEqual(r.returncode, 0)
        self.assertIn(source_version(), r.stdout)

    def test_every_codec_keeps_tags_and_cover_art(self):
        for codec, ext, extra in CASES:
            with self.subTest(codec=codec):
                out = os.path.join(self.tmp, f'out_{codec}')
                r = run(['-i', self.flac, '-f', codec, '-o', out] + extra)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                files = out_files(out)
                self.assertEqual(files, ['tone' + ext], files)
                path = os.path.join(out, files[0])
                if codec == 'wav':
                    with wave.open(path) as w:
                        self.assertEqual((w.getnchannels(), w.getsampwidth()), (2, 2))
                    continue
                title, artist, has_art = helpers.read_tags(path)
                self.assertEqual((title, artist), (helpers.TITLE, helpers.ARTIST))
                self.assertTrue(has_art, f"cover art missing in {codec} output")
                if ext == '.m4a':
                    from mutagen.mp4 import MP4
                    kind = MP4(path).info.codec
                    self.assertTrue(kind == 'alac' if codec == 'alac' else kind.startswith('mp4a'), kind)

    def test_dry_run_writes_nothing(self):
        out = os.path.join(self.tmp, 'dry')
        r = run(['-i', self.flac, '-f', 'opus', '-o', out, '--dry-run'])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('Would encode 1', r.stdout)
        self.assertFalse(os.path.exists(out))

    def test_same_format_is_copied_not_reencoded(self):
        d1, d2 = os.path.join(self.tmp, 'o1'), os.path.join(self.tmp, 'o2')
        self.assertEqual(run(['-i', self.flac, '-f', 'opus', '-o', d1]).returncode, 0)
        r = run(['-i', d1, '-f', 'opus', '-o', d2])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('Copied (same format)', r.stdout)
        with open(os.path.join(d1, 'tone.opus'), 'rb') as a, open(os.path.join(d2, 'tone.opus'), 'rb') as b:
            self.assertEqual(a.read(), b.read())

    def test_lossy_sources_skipped_for_lossless_targets_unless_forced(self):
        mp3_dir, out = os.path.join(self.tmp, 'mp3'), os.path.join(self.tmp, 'lossless')
        self.assertEqual(run(['-i', self.wav, '-f', 'mp3', '-o', mp3_dir]).returncode, 0)
        r = run(['-i', mp3_dir, '-f', 'flac', '-o', out])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('Skipped 1 lossy', r.stdout)
        self.assertFalse(os.path.exists(out))
        r = run(['-i', mp3_dir, '-f', 'flac', '-o', out, '--include-lossy'])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(out_files(out), ['tone.flac'])

    def test_wizard_starts_with_dropped_path_and_quits_cleanly(self):
        r = run([self.flac_dir], stdin='q\n')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('Cancelled', r.stdout)

    def test_flac_to_opus_preset(self):
        out = os.path.join(self.tmp, 'preset')
        r = run(['--preset', 'flac_to_opus', self.flac_dir, out, '--dry-run'])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('Would encode 1', r.stdout)

    @unittest.skipIf(EXE, "bundled ffmpeg is always present next to the exe")
    def test_missing_ffmpeg_gives_clear_error(self):
        empty = tempfile.mkdtemp()
        env = dict(os.environ, PATH=empty)
        r = run(['-i', self.flac, '-f', 'opus', '-o', os.path.join(self.tmp, 'nf')], env=env)
        self.assertEqual(r.returncode, 1)
        self.assertIn('ffmpeg', r.stdout.lower())


if __name__ == '__main__':
    unittest.main()
```

Run it here (`python -m unittest tests.test_smoke -v`, with the Task 0 PATH). **Every test must pass on real ffmpeg.** If a test exposes a genuine product bug (e.g. cover art missing for a codec), report it as a finding; do not weaken the assertion.

- [ ] **Step 2: `packaging/build.py`.**

```python
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
```

- [ ] **Step 3: append tests** to `tests/test_build_helpers.py` (import with `bt = load('build')` — note `build` is also a folder name in the repo root; keep the helper's `spec_from_file_location` form, never `import build`):

```python
bt = load('build')


class BuildHelpers(unittest.TestCase):
    def test_tag_must_match_version(self):
        bt.check_tag('v1.1.0', '1.1.0')
        bt.check_tag(None, '1.1.0')
        with self.assertRaises(SystemExit):
            bt.check_tag('v9.9.9', '1.1.0')

    def test_zip_has_single_top_folder_and_forward_slashes(self):
        import zipfile
        with tempfile.TemporaryDirectory() as d:
            app = os.path.join(d, 'AudioConverter')
            os.makedirs(os.path.join(app, '_internal'))
            for rel in ('AudioConverter.exe', os.path.join('_internal', 'x.dll')):
                open(os.path.join(app, rel), 'wb').close()
            z = os.path.join(d, 'out.zip')
            bt.make_zip(app, z)
            names = zipfile.ZipFile(z).namelist()
            self.assertTrue(all(n.startswith('AudioConverter/') for n in names), names)
            self.assertTrue(all('\\' not in n for n in names), names)
            self.assertIn('AudioConverter/_internal/x.dll', names)

    def test_version_is_readable(self):
        self.assertRegex(bt.read_version(), r'^\d+\.\d+\.\d+')

    def test_mutagen_license_is_found(self):
        self.assertTrue(os.path.isfile(bt.find_dist_license('mutagen')))
```

- [ ] **Step 4: `packaging/build.bat`** (thin wrapper; CRLF is enforced by `.gitattributes`):

```bat
@echo off
setlocal
cd /d "%~dp0\.."
if not exist .venv-build ( python -m venv .venv-build || goto :fail )
call .venv-build\Scripts\activate.bat || goto :fail
python -m pip install --upgrade pip >nul
python -m pip install -r requirements-build.txt || goto :fail
python packaging\build.py %* || goto :fail
echo.
echo Done. The zip is in the dist folder.
exit /b 0
:fail
echo.
echo [ERROR] Build failed - see the messages above.
exit /b 1
```

- [ ] **Step 5: verify here:** `python -m unittest discover tests -v` (smoke runs in source mode with the pip ffmpeg); `python packaging/build.py --help`; `python packaging/build.py` must refuse on Linux with the "must be built on Windows" message. Commit: `build: single build script, local wrapper, full-codec smoke tests`.

---

## Task 5: GitHub Actions

**Files:** create `.github/workflows/release.yml`.

- [ ] **Step 1:**

```yaml
name: Build & release (Windows portable)

on:
  push:
    branches: [main]
    tags: ['v*']
  pull_request:
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  unit:
    name: Unit tests (${{ matrix.os }}, Python ${{ matrix.python }})
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest]
        python: ['3.9', '3.13']
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
      - run: python -m pip install -r requirements.txt
      - run: python -m unittest tests.test_audio_converter tests.test_build_helpers -v

  windows-build:
    name: Build, smoke-test and package
    needs: unit
    runs-on: windows-latest
    permissions:
      contents: write          # only used to create the draft release
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: pip
          cache-dependency-path: requirements-build.txt
      - run: python -m pip install -r requirements-build.txt
      - name: Build (tag builds are release builds)
        shell: pwsh
        run: |
          if ($env:GITHUB_REF -like 'refs/tags/v*') { python packaging/build.py --tag $env:GITHUB_REF_NAME }
          else { python packaging/build.py }
      - uses: actions/upload-artifact@v4
        with:
          name: AudioConverter-win64
          path: |
            dist/AudioConverter-*.zip
            dist/AudioConverter-*.zip.sha256
      - name: Publish DRAFT release
        if: startsWith(github.ref, 'refs/tags/v')
        uses: softprops/action-gh-release@v2
        with:
          draft: true
          generate_release_notes: true
          body_path: packaging/release-notes.md
          files: |
            dist/AudioConverter-*.zip
            dist/AudioConverter-*.zip.sha256
```

`build.py` already runs the smoke suite (relocated folder, path with a space, PATH hidden) and fails the job before anything is zipped or published.

- [ ] **Step 2: verify here:** `python -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml'))"` (install `pyyaml` in the venv if needed). Note in the final report that the first real run happens only after the owner pushes and starts it with **Actions → Run workflow**.
- [ ] **Step 3: commit** `ci: windows build with pre-publish smoke tests and draft release`.

---

## Task 6: Documentation

**Files:** modify `README.md`; create `docs/RELEASING.md`.

- [ ] **Step 1: README.** Add this as the **first** section after the title/intro (no guessed URLs):

```markdown
## Download (Windows, no installation)

1. Open the [latest release](https://github.com/<your-username>/<repo-name>/releases/latest) and download `AudioConverter-vX.Y.Z-win64.zip`.
2. **Extract the whole zip** (right-click → *Extract All*). Do not run it from inside the zip.
3. Double-click `AudioConverter.exe`, or drag an audio file or folder onto it.

No Python or FFmpeg needed. Keep `AudioConverter.exe`, `ffmpeg.exe` and the `_internal` folder together.
The app is unsigned, so Windows SmartScreen may warn: click **More info → Run anyway**.
Optional: compare the zip's SHA-256 with the `.sha256` file on the release page
(`Get-FileHash .\AudioConverter-vX.Y.Z-win64.zip`).
```

Then: rename the existing install/usage material to **"Run from source (Python, macOS, Linux)"**; change the Python requirement to **3.9+**; document `--preset flac_to_opus` (`AudioConverter.exe --preset flac_to_opus SOURCE [DEST]`) next to the existing FLAC→Opus section; add the SmartScreen entry to Troubleshooting; update **Project Structure** (`packaging/`, `tests/`, `docs/`, `.github/`); add a **"Building the Windows release"** section (`packaging\build.bat`, needs the owner-filled `packaging/ffmpeg.lock.json`; see `docs/RELEASING.md`); replace the License section with **GPL-2.0-or-later** plus a one-paragraph reason (bundles mutagen, GPL; FFmpeg is a separate program, license text in `LICENSES/`).

- [ ] **Step 2: `docs/RELEASING.md`** — numbered steps: bump `__version__` → commit → fill/refresh `packaging/ffmpeg.lock.json` if FFmpeg changes (`python packaging/download_ffmpeg.py --hash FILE.zip`) → `git tag vX.Y.Z` → push the tag → wait for CI → review the **draft** release → download the zip on a clean Windows machine (Windows Sandbox is ideal) and run it → publish.
- [ ] **Step 3:** run a link/placeholder check: `grep -rnE "bennypepper|Benny|C:\\\\Users" .` must find nothing; `<your-username>/<repo-name>` placeholders are expected. Commit: `docs: standalone download, preset, licensing and release process`.

---

## Task 7: Final verification and report

- [ ] `python -m py_compile audio_converter.py flac_to_opus.py packaging/*.py tests/*.py`
- [ ] `python -m unittest discover tests -v` with the Task 0 PATH → everything passes, including smoke tests with real ffmpeg.
- [ ] `git status` clean; `git ls-files | grep -E "^(dist|build)/|packaging/bin/"` prints nothing; no `.venv`, `.tools` committed.
- [ ] Back-compat spot checks: `python audio_converter.py --help`; `python flac_to_opus.py --help`; `python audio_converter.py --preset flac_to_opus <dir> <dst> --dry-run`.
- [ ] **Final report must state plainly:** what was verified here (list), what was *not* (frozen exe, bundled-ffmpeg lookup, CI), any real product bugs the smoke tests exposed, and the Owner checklist below.

---

## Owner checklist (agents cannot do these)

1. **Pin FFmpeg (D2):** choose a *versioned* FFmpeg Windows build whose license you accept, download the zip, run `python packaging/download_ffmpeg.py --hash <zip>`, and fill all five fields of `packaging/ffmpeg.lock.json` (URL must be a permanent versioned link; `source_url` = that release's corresponding source). Until this is done, release builds stop with a clear error by design.
2. Confirm the license decision (D1) and put your name in `LICENSE`.
3. Replace `<your-username>/<repo-name>` in the README.
4. Push, then run **Actions → Build & release → Run workflow** once. Expect the first Windows run to surface small portability fixes (tests were developed on Linux); fix forward.
5. Download the resulting artifact and test it on a clean Windows machine/VM (Windows Sandbox): double-click, drag-and-drop a folder, convert a real album, confirm tags and cover art.
6. Only then tag `v1.1.0` (must equal `__version__`), review the draft release, publish.

## What changed versus the earlier plan

| Defect in earlier plan | Fix here |
| :-- | :-- |
| Tests at repo root / `python test_audio_converter.py` | `tests/` + `python -m unittest ...`; CI uses module names |
| Dry-run test asserted `COMPLETED` (never printed) | Asserts `Would encode 1` and that nothing was written |
| Smoke test: 3/7 codecs, no tag/art checks, hard-coded `1.1.0` | All 7 codecs, tags + art read back, version read from source |
| Stray `-map_metadata:g 0:s:a:0` | Removed; encoding args untouched |
| FFmpeg: moving "latest" URL, unimplemented checksum, silent PATH fallback | Lock file + enforced SHA-256, explicit `--local` opt-in, never for releases |
| MIT license vs bundled GPL mutagen; paraphrased license texts | GPL-2.0-or-later (D1); real texts assembled at build time |
| Guessed GitHub URL; zip name mismatch | Placeholders; one naming scheme from `build.py` |
| `--preset` → double module load + argparse clash | Module alias + `--preset` stripped before dispatch |
| Double-click failures closed the window instantly | `fatal()` pauses for drag/double-click launches; crash handler |
| Spec from a pre-6.0 template; UPX | Regenerated for 6.22.3; `upx=False` |
| `build.bat` and CI duplicated steps | Single `build.py` |
| Verification steps agents could not run | Explicit verifiable-here vs CI split; real ffmpeg via pip |
| Unpinned toolchain, public release by default, Py 3.8 claim | Pinned versions, draft release, 3.9+ verified in CI; relocated-folder + PATH-isolated smoke test |
