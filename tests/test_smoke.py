r"""End-to-end smoke tests.

Source mode (default; needs an ffmpeg on PATH, else the suite skips itself):
    python -m unittest tests.test_smoke -v
Built exe:
    set AUDIOCONVERTER_EXE=dist\AudioConverter\AudioConverter.exe
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
        self.assertEqual(r.returncode, 0)
        self.assertIn('Would encode 1', r.stdout)
        self.assertFalse(os.path.exists(out))

    def test_same_format_is_copied_not_reencoded(self):
        d1, d2 = os.path.join(self.tmp, 'o1'), os.path.join(self.tmp, 'o2')
        self.assertEqual(run(['-i', self.flac, '-f', 'opus', '-o', d1]).returncode, 0)
        r = run(['-i', d1, '-f', 'opus', '-o', d2])
        self.assertEqual(r.returncode, 0)
        self.assertIn('Copied (same format)', r.stdout)
        with open(os.path.join(d1, 'tone.opus'), 'rb') as a, open(os.path.join(d2, 'tone.opus'), 'rb') as b:
            self.assertEqual(a.read(), b.read())

    def test_lossy_sources_skipped_for_lossless_targets_unless_forced(self):
        mp3_dir, out = os.path.join(self.tmp, 'mp3'), os.path.join(self.tmp, 'lossless')
        self.assertEqual(run(['-i', self.wav, '-f', 'mp3', '-o', mp3_dir]).returncode, 0)
        r = run(['-i', mp3_dir, '-f', 'flac', '-o', out])
        self.assertEqual(r.returncode, 0)
        self.assertIn('Skipped 1 lossy', r.stdout)
        self.assertFalse(os.path.exists(out))
        r = run(['-i', mp3_dir, '-f', 'flac', '-o', out, '--include-lossy'])
        self.assertEqual(r.returncode, 0)
        self.assertEqual(out_files(out), ['tone.flac'])

    def test_wizard_starts_with_dropped_path_and_quits_cleanly(self):
        r = run([self.flac_dir], stdin='q\n')
        self.assertEqual(r.returncode, 0)
        self.assertIn('Cancelled', r.stdout)

    def test_flac_to_opus_preset(self):
        out = os.path.join(self.tmp, 'preset')
        r = run(['--preset', 'flac_to_opus', self.flac_dir, out, '--dry-run'])
        self.assertEqual(r.returncode, 0)
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
