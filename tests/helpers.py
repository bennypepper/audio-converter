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
