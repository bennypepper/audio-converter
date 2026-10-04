"""Unit tests for the pure helpers (no FFmpeg needed).  Run:  python -m unittest discover tests"""
import os
import sys
import tempfile
import unittest

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


if __name__ == '__main__':
    unittest.main()
