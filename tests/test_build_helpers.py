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


if __name__ == '__main__':
    unittest.main()

