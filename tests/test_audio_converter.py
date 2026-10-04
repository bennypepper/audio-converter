"""Unit tests for the pure helpers (no FFmpeg needed).  Run:  python -m unittest discover tests"""
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import audio_converter as ac  # noqa: E402


def touch(path, data=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as fh:
        fh.write(data)
    return path


class ParseBitrate(unittest.TestCase):
    def test_plain_number_gets_k_suffix(self):
        self.assertEqual(ac.parse_bitrate('192', 'opus'), '192k')

    def test_k_suffix_and_case(self):
        self.assertEqual(ac.parse_bitrate(' 224K ', 'm4a'), '224k')

    def test_v0_only_for_mp3(self):
        self.assertEqual(ac.parse_bitrate('v0', 'mp3'), 'v0')
        self.assertIsNone(ac.parse_bitrate('v0', 'opus'))

    def test_rejects_garbage(self):
        for bad in ('', 'abc', '5', '12345k', '-192k'):
            self.assertIsNone(ac.parse_bitrate(bad, 'opus'), bad)


class Shorten(unittest.TestCase):
    def test_short_text_untouched(self):
        self.assertEqual(ac.shorten('abc', 10), 'abc')

    def test_long_text_is_trimmed_to_limit(self):
        out = ac.shorten('x' * 200, 52)
        self.assertEqual(len(out), 52)
        self.assertIn('...', out)


class CollectFiles(unittest.TestCase):
    def test_recursive_collection_filters_by_extension(self):
        with tempfile.TemporaryDirectory() as d:
            touch(os.path.join(d, 'a.flac'))
            touch(os.path.join(d, 'sub', 'b.MP3'))
            touch(os.path.join(d, 'cover.jpg'))
            rels = sorted(rel for _, rel in ac.collect_files(d))
            self.assertEqual(rels, sorted(['a.flac', os.path.join('sub', 'b.MP3')]))

    def test_single_unsupported_file_returns_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(ac.collect_files(touch(os.path.join(d, 'notes.txt'))), [])


class DefaultDestination(unittest.TestCase):
    def test_folder_gets_codec_suffix(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(ac.default_destination({'input_path': d, 'codec': 'opus'}), d + '_opus')

    def test_single_file_goes_to_converted_folder_next_to_it(self):
        with tempfile.TemporaryDirectory() as d:
            f = touch(os.path.join(d, 'song.flac'))
            self.assertEqual(ac.default_destination({'input_path': f, 'codec': 'mp3'}),
                             os.path.join(d, 'converted_mp3'))


class AlreadyInTarget(unittest.TestCase):
    def test_same_extension_is_detected(self):
        self.assertTrue(ac.already_in_target('x.opus', 'opus'))
        self.assertTrue(ac.already_in_target('x.MP3', 'mp3'))
        self.assertTrue(ac.already_in_target('x.flac', 'flac'))

    def test_different_extension_is_not(self):
        self.assertFalse(ac.already_in_target('x.flac', 'opus'))

    def test_wav_is_always_normalized(self):
        self.assertFalse(ac.already_in_target('x.wav', 'wav'))


class DecideAction(unittest.TestCase):
    def test_actions(self):
        with tempfile.TemporaryDirectory() as d:
            flac = touch(os.path.join(d, 'a.flac'))
            opus_src = touch(os.path.join(d, 'in', 'b.opus'))
            dst_opus = os.path.join(d, 'out', 'b.opus')

            self.assertEqual(ac.decide_action(flac, os.path.join(d, 'out', 'a.opus'), 'opus'), 'encode')
            self.assertEqual(ac.decide_action(opus_src, dst_opus, 'opus'), 'copy')
            self.assertEqual(ac.decide_action(opus_src, dst_opus, 'opus', force_reencode=True), 'encode')
            self.assertEqual(ac.decide_action(opus_src, opus_src, 'opus'), 'skip-self')

            touch(dst_opus)
            self.assertEqual(ac.decide_action(opus_src, dst_opus, 'opus', skip_existing=True), 'skip-exists')

    def test_empty_existing_output_is_not_treated_as_done(self):
        with tempfile.TemporaryDirectory() as d:
            src = touch(os.path.join(d, 'a.flac'))
            dst = touch(os.path.join(d, 'out', 'a.opus'), data=b"")
            self.assertEqual(ac.decide_action(src, dst, 'opus', skip_existing=True), 'encode')


class CopyThrough(unittest.TestCase):
    def test_same_format_file_is_copied_without_ffmpeg(self):
        with tempfile.TemporaryDirectory() as d:
            src = touch(os.path.join(d, 'in', 'a.opus'), data=b"opus-bytes")
            dst = os.path.join(d, 'out', 'a.opus')
            ok, msg = ac.convert_single_file(src, dst, 'opus', '192k')
            self.assertTrue(ok)
            self.assertTrue(msg.startswith('Copied'))
            with open(dst, 'rb') as fh:
                self.assertEqual(fh.read(), b"opus-bytes")
            self.assertEqual(os.listdir(os.path.dirname(dst)), ['a.opus'])  # no .partial left behind


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


if __name__ == '__main__':
    unittest.main()
