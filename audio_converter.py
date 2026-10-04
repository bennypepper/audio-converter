#!/usr/bin/env python3
"""
Audio Converter & Metadata/Artwork Engine
Supports: Opus, MP3, AAC/M4A, FLAC, ALAC, Ogg Vorbis, WAV
Features:
- Single file or recursive batch folder conversion
- Smart audio detection (prevents lossy->lossless bloat & redundant conversions)
- Multi-tier bitrate selection per codec + custom input
- Preserves all metadata tags (Title, Artist, Album, Year, Lyrics, etc.)
- Preserves embedded album art across all formats
- Multithreaded parallel encoding for maximum speed
- Gradient banner, aligned UI cards & step-by-step wizard (b = back, q = quit)
- Same-format files are copied instead of re-encoded; output is written atomically (.partial)
- Clean Ctrl+C handling, --dry-run, cover-art warnings
"""

import os
import sys
import re
import argparse
import subprocess
import base64
import shutil
import threading
import functools
from concurrent.futures import ThreadPoolExecutor, as_completed

if __name__ == '__main__':
    # Let `import audio_converter` (done by preset modules) reuse THIS module instead of loading a second copy.
    sys.modules.setdefault('audio_converter', sys.modules[__name__])

__version__ = "1.1.0"

# Enable ANSI colors & UTF-8 output on Windows
os.system('')  # Initializes Virtual Terminal processing in Windows CMD
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Terminal Styling & Colors
C_RESET   = '\033[0m'
C_BOLD    = '\033[1m'
C_DIM     = '\033[90m'
C_CYAN    = '\033[96m'
C_MAGENTA = '\033[95m'
C_GREEN   = '\033[92m'
C_YELLOW  = '\033[93m'
C_WHITE   = '\033[97m'
C_RED     = '\033[91m'


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


# Verify dependencies and auto-install if missing
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
        fatal("Required component 'mutagen' is missing from this build.",
              "Please re-download and fully extract the application.")
    print(f"{C_YELLOW}[INFO] 'mutagen' is not found. Installing via pip...{C_RESET}")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "mutagen"])
        import mutagen
        from mutagen.flac import FLAC, Picture
        from mutagen.mp3 import MP3
        from mutagen.id3 import ID3, APIC, ID3NoHeaderError
        from mutagen.mp4 import MP4, MP4Cover
        from mutagen.oggopus import OggOpus
        from mutagen.oggvorbis import OggVorbis
        print(f"{C_GREEN}[INFO] 'mutagen' successfully installed!{C_RESET}\n")
    except Exception as e:
        fatal(f"Failed to auto-install 'mutagen': {e}",
              f"Please run: {sys.executable} -m pip install mutagen")

SUPPORTED_INPUT_EXTS = {
    '.flac', '.mp3', '.m4a', '.aac', '.ogg', '.opus',
    '.wav', '.aiff', '.aif', '.wma', '.alac', '.ape', '.wv'
}

LOSSY_EXTS = {'.mp3', '.m4a', '.aac', '.ogg', '.opus', '.wma'}
LOSSLESS_EXTS = {'.flac', '.wav', '.aiff', '.aif', '.alac', '.ape', '.wv'}

CODEC_CONFIG = {
    'opus': {
        'ext': '.opus',
        'ffmpeg_args': ['-c:a', 'libopus'],
        'is_lossless': False,
        'title': 'Opus (.opus)',
        'description': 'High-efficiency modern lossy',
        'tiers': [
            ('128k', '128 kbps  (Efficient / compact storage)'),
            ('160k', '160 kbps  (High quality)'),
            ('192k', '192 kbps  (Transparent - Recommended)'),
            ('256k', '256 kbps  (Maximum fidelity)')
        ],
        'default_bitrate': '192k'
    },
    'm4a': {
        'ext': '.m4a',
        'ffmpeg_args': ['-c:a', 'aac', '-movflags', '+faststart'],
        'is_lossless': False,
        'title': 'AAC / M4A (.m4a)',
        'description': 'Apple standard & mobile playback',
        'tiers': [
            ('128k', '128 kbps  (Standard)'),
            ('192k', '192 kbps  (High quality)'),
            ('256k', '256 kbps  (Apple Music standard - Recommended)'),
            ('320k', '320 kbps  (Maximum bitrate)')
        ],
        'default_bitrate': '256k'
    },
    'mp3': {
        'ext': '.mp3',
        'ffmpeg_args': ['-c:a', 'libmp3lame', '-id3v2_version', '3'],
        'is_lossless': False,
        'title': 'MP3 (.mp3)',
        'description': 'Universal legacy compatibility',
        'tiers': [
            ('192k', '192 kbps CBR  (Standard)'),
            ('256k', '256 kbps CBR  (High quality)'),
            ('320k', '320 kbps CBR  (Maximum CBR - Recommended)'),
            ('v0',   'V0 VBR (~245k) (Dynamic LAME high efficiency)')
        ],
        'default_bitrate': '320k'
    },
    'flac': {
        'ext': '.flac',
        'ffmpeg_args': ['-c:a', 'flac', '-compression_level', '8'],
        'is_lossless': True,
        'title': 'FLAC (.flac)',
        'description': 'Bit-perfect lossless compression',
        'tiers': [],
        'default_bitrate': None
    },
    'alac': {
        'ext': '.m4a',
        'ffmpeg_args': ['-c:a', 'alac', '-movflags', '+faststart'],
        'is_lossless': True,
        'title': 'ALAC (.m4a)',
        'description': 'Apple Lossless (iOS / iTunes)',
        'tiers': [],
        'default_bitrate': None
    },
    'ogg': {
        'ext': '.ogg',
        'ffmpeg_args': ['-c:a', 'libvorbis'],
        'is_lossless': False,
        'title': 'Ogg Vorbis (.ogg)',
        'description': 'Open-source legacy lossy',
        'tiers': [
            ('128k', '128 kbps  (Standard)'),
            ('160k', '160 kbps  (High quality)'),
            ('192k', '192 kbps  (Recommended)'),
            ('256k', '256 kbps  (Maximum fidelity)')
        ],
        'default_bitrate': '192k'
    },
    'wav': {
        'ext': '.wav',
        'ffmpeg_args': ['-c:a', 'pcm_s16le'],
        'is_lossless': True,
        'title': 'WAV (.wav)',
        'description': 'Uncompressed 16-bit PCM',
        'tiers': [],
        'default_bitrate': None
    }
}

BOX_WIDTH = 76
ANSI_REGEX = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')


def box_line(content, color=C_CYAN):
    """Formats a line inside a box with dynamic space padding to ensure borders align."""
    vis_len = len(ANSI_REGEX.sub('', content))
    padding = max(0, BOX_WIDTH - vis_len - 4)
    return f"{color}│{C_RESET}  {content}{' ' * padding}{color}│{C_RESET}"


def box_top(title="", color=C_CYAN):
    if title:
        t_str = f" [ {title} ] "
        total_dashes = BOX_WIDTH - len(t_str) - 2
        left_dashes = max(2, total_dashes // 2)
        right_dashes = max(2, total_dashes - left_dashes)
        return f"{color}╭{'─' * left_dashes}{C_BOLD}{t_str}{C_RESET}{color}{'─' * right_dashes}╮{C_RESET}"
    return f"{color}╭{'─' * (BOX_WIDTH - 2)}╮{C_RESET}"


def box_bot(color=C_CYAN):
    return f"{color}╰{'─' * (BOX_WIDTH - 2)}╯{C_RESET}"


def box_div(color=C_CYAN):
    return f"{color}├{'─' * (BOX_WIDTH - 2)}┤{C_RESET}"


GRADIENT = [51, 50, 44, 38, 33, 63, 99, 135, 171, 207, 201]

_GLYPHS = {
    'A': [" █████╗ ", "██╔══██╗", "███████║", "██╔══██║", "██║  ██║", "╚═╝  ╚═╝"],
    'U': ["██╗   ██╗", "██║   ██║", "██║   ██║", "██║   ██║", "╚██████╔╝", " ╚═════╝ "],
    'D': ["██████╗ ", "██╔══██╗", "██║  ██║", "██║  ██║", "██████╔╝", "╚═════╝ "],
    'I': ["██╗", "██║", "██║", "██║", "██║", "╚═╝"],
    'O': [" ██████╗ ", "██╔═══██╗", "██║   ██║", "██║   ██║", "╚██████╔╝", " ╚═════╝ "],
    'C': [" ██████╗", "██╔════╝", "██║     ", "██║     ", "╚██████╗", " ╚═════╝"],
    'N': ["███╗   ██╗", "████╗  ██║", "██╔██╗ ██║", "██║╚██╗██║", "██║ ╚████║", "╚═╝  ╚═══╝"],
    'V': ["██╗   ██╗", "██║   ██║", "██║   ██║", "╚██╗ ██╔╝", " ╚████╔╝ ", "  ╚═══╝  "],
    'E': ["███████╗", "██╔════╝", "█████╗  ", "██╔══╝  ", "███████╗", "╚══════╝"],
    'R': ["██████╗ ", "██╔══██╗", "██████╔╝", "██╔══██╗", "██║  ██║", "╚═╝  ╚═╝"],
    'T': ["████████╗", "╚══██╔══╝", "   ██║   ", "   ██║   ", "   ██║   ", "   ╚═╝   "],
    'F': ["███████╗", "██╔════╝", "█████╗  ", "██╔══╝  ", "██║     ", "╚═╝     "],
    'L': ["██╗     ", "██║     ", "██║     ", "██║     ", "███████╗", "╚══════╝"],
    'P': ["██████╗ ", "██╔══██╗", "██████╔╝", "██╔═══╝ ", "██║     ", "╚═╝     "],
    'S': ["███████╗", "██╔════╝", "███████╗", "╚════██║", "███████║", "╚══════╝"],
    '>': [" ██╗    ", " ╚██╗   ", "  ╚██╗  ", "  ██╔╝  ", " ██╔╝   ", " ╚═╝    "],
}


def _render_word(word):
    """Builds the 6 rows of block-letter art for a word from the glyph table."""
    rows = []
    for r in range(6):
        row = ''
        for ch in word:
            glyph = _GLYPHS[ch]
            width = max(len(line) for line in glyph)
            row += glyph[r].ljust(width)
        rows.append(row)
    return rows


def fg256(n):
    return f"\033[38;5;{n}m"


def gradient_text(text, colors=None, bold=True):
    """Colors each character of `text` along a left-to-right 256-color gradient."""
    colors = colors or GRADIENT
    span = max(1, len(text) - 1)
    out = []
    for i, ch in enumerate(text):
        if ch == ' ':
            out.append(ch)
        else:
            out.append(fg256(colors[int(i / span * (len(colors) - 1))]) + ch)
    return (C_BOLD if bold else '') + ''.join(out) + C_RESET


def print_banner(words=("AUDIO", "CONVERTER"),
                 tagline="♫  Audio Transcoder & Metadata Engine  ♫",
                 features="Opus · AAC · MP3 · FLAC · ALAC · Vorbis · WAV   ✦   tags & album art preserved"):
    """Prints a block-letter logo (one stacked line per word) with a cyan -> magenta gradient."""
    blocks = [_render_word(w) for w in words]
    width = max(len(row) for block in blocks for row in block)
    rows = [row.center(width) for block in blocks for row in block]
    total_rows = len(rows)

    print()
    for r_i, row in enumerate(rows):
        out = []
        for c_i, ch in enumerate(row):
            if ch == ' ':
                out.append(' ')
                continue
            t = (c_i / width) * 0.65 + (r_i / total_rows) * 0.35
            color = fg256(GRADIENT[min(len(GRADIENT) - 1, int(t * len(GRADIENT)))])
            if ch == '█':
                out.append(f"\033[1m{color}{ch}\033[22m")
            else:
                out.append(f"\033[2m{color}{ch}\033[22m")  # shadow strokes, dimmed
        print('  ' + ''.join(out) + C_RESET)

    rule = 10
    pad = max(0, (width - (len(tagline) + 4 + 2 * rule)) // 2) + 2
    print()
    print(' ' * pad + f"{C_DIM}{'━' * rule}{C_RESET}  {gradient_text(tagline)}  {C_DIM}{'━' * rule}{C_RESET}")
    pad2 = max(0, (width - len(features)) // 2) + 2
    print(' ' * pad2 + f"{C_DIM}{features}{C_RESET}")
    print()


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


def clean_path(path_str):
    """Strip surrounding quotes and whitespace from drag-and-dropped paths."""
    if not path_str:
        return ""
    p = path_str.strip()
    if (p.startswith('"') and p.endswith('"')) or (p.startswith("'") and p.endswith("'")):
        p = p[1:-1].strip()
    return os.path.expanduser(p)


def extract_artwork(file_path):
    """Extract embedded album art (bytes, mime_type) from an audio file."""
    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext == '.flac':
            audio = FLAC(file_path)
            if audio.pictures:
                pic = audio.pictures[0]
                return pic.data, pic.mime
        elif ext == '.mp3':
            audio = MP3(file_path)
            if audio.tags:
                for tag in audio.tags.values():
                    if isinstance(tag, APIC):
                        return tag.data, tag.mime
        elif ext in ('.m4a', '.mp4'):
            audio = MP4(file_path)
            if 'covr' in audio and audio['covr']:
                covr = audio['covr'][0]
                mime = 'image/png' if getattr(covr, 'imageformat', None) == MP4Cover.FORMAT_PNG else 'image/jpeg'
                return bytes(covr), mime
        elif ext == '.opus':
            audio = OggOpus(file_path)
            if 'metadata_block_picture' in audio:
                b64 = audio['metadata_block_picture'][0]
                pic = Picture(base64.b64decode(b64))
                return pic.data, pic.mime
        elif ext == '.ogg':
            audio = OggVorbis(file_path)
            if 'metadata_block_picture' in audio:
                b64 = audio['metadata_block_picture'][0]
                pic = Picture(base64.b64decode(b64))
                return pic.data, pic.mime
    except Exception:
        pass
    return None, None


def embed_artwork(file_path, pic_data, mime_type='image/jpeg'):
    """Embed album art into the destination audio file."""
    if not pic_data:
        return False
    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext == '.opus':
            pic = Picture()
            pic.data = pic_data
            pic.type = 3  # Front Cover
            pic.mime = mime_type
            pic.desc = 'Cover'
            audio = OggOpus(file_path)
            audio['metadata_block_picture'] = [base64.b64encode(pic.write()).decode('ascii')]
            audio.save()
        elif ext == '.mp3':
            try:
                tags = ID3(file_path)
            except ID3NoHeaderError:
                tags = ID3()
            tags.delall('APIC')
            tags.add(APIC(
                encoding=3,
                mime=mime_type,
                type=3,
                desc='Cover',
                data=pic_data
            ))
            tags.save(file_path, v2_version=3)
        elif ext in ('.m4a', '.mp4'):
            audio = MP4(file_path)
            fmt = MP4Cover.FORMAT_PNG if mime_type == 'image/png' else MP4Cover.FORMAT_JPEG
            audio['covr'] = [MP4Cover(pic_data, imageformat=fmt)]
            audio.save()
        elif ext == '.flac':
            audio = FLAC(file_path)
            pic = Picture()
            pic.data = pic_data
            pic.type = 3
            pic.mime = mime_type
            pic.desc = 'Cover'
            audio.clear_pictures()
            audio.add_picture(pic)
            audio.save()
        elif ext == '.ogg':
            pic = Picture()
            pic.data = pic_data
            pic.type = 3
            pic.mime = mime_type
            pic.desc = 'Cover'
            audio = OggVorbis(file_path)
            audio['metadata_block_picture'] = [base64.b64encode(pic.write()).decode('ascii')]
            audio.save()
        else:
            return False
    except Exception:
        return False
    return True


def m4a_codec(path):
    """Returns the codec inside an .m4a container ('alac', 'mp4a.40.2', ...)."""
    try:
        return (MP4(path).info.codec or '').lower()
    except Exception:
        return ''


def already_in_target(src_path, codec):
    """True when the source already is the exact target codec/container, so re-encoding would only hurt."""
    cfg = CODEC_CONFIG[codec]
    if cfg['ext'] == '.wav':
        return False  # always re-encode so the output is normalized to 16-bit PCM
    if os.path.splitext(src_path)[1].lower() != cfg['ext']:
        return False
    if cfg['ext'] == '.m4a':  # AAC and ALAC share the .m4a extension
        src_codec = m4a_codec(src_path)
        return src_codec == 'alac' if codec == 'alac' else src_codec.startswith('mp4a')
    return True


def decide_action(src_path, dst_path, codec, skip_existing=False, force_reencode=False):
    """Returns 'skip-self', 'skip-exists', 'copy' or 'encode' for one file."""
    if os.path.abspath(src_path) == os.path.abspath(dst_path):
        return 'skip-self'
    if skip_existing and os.path.exists(dst_path) and os.path.getsize(dst_path) > 0:
        return 'skip-exists'
    if not force_reencode and already_in_target(src_path, codec):
        return 'copy'
    return 'encode'


def _remove_quietly(path):
    try:
        os.remove(path)
    except OSError:
        pass


def convert_single_file(src_path, dst_path, codec, bitrate=None, skip_existing=False, force_reencode=False):
    """Encodes (or copies) one file, preserving metadata and cover art.

    Output goes to a temporary '.partial' file and is renamed into place only once complete, so an
    interrupted run never leaves a half-written file that 'skip existing' would mistake for a finished one.
    """
    action = decide_action(src_path, dst_path, codec, skip_existing, force_reencode)
    if action == 'skip-self':
        return True, "Skipped (output would overwrite the source)"
    if action == 'skip-exists':
        return True, "Skipped (already exists)"

    os.makedirs(os.path.dirname(dst_path) or '.', exist_ok=True)
    root, ext = os.path.splitext(dst_path)
    tmp_path = f"{root}.partial{ext}"

    try:
        if action == 'copy':
            shutil.copy2(src_path, tmp_path)
            os.replace(tmp_path, dst_path)
            return True, "Copied (already in target format)"

        # 1. Extract cover art prior to conversion
        pic_data, mime_type = extract_artwork(src_path)

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
        res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace',
                             **get_subprocess_kwargs())
        if res.returncode != 0:
            return False, f"FFmpeg error: {res.stderr[-200:].strip()}"

        # 4. Embed artwork, then move the finished file into place
        note = ""
        if pic_data and not embed_artwork(tmp_path, pic_data, mime_type):
            note = " (cover art could not be embedded)"
        os.replace(tmp_path, dst_path)
        return True, "Success" + note
    finally:
        _remove_quietly(tmp_path)


def collect_files(input_path, recursive=True):
    """Collect audio files from a file path or directory."""
    files_to_process = []
    if os.path.isfile(input_path):
        ext = os.path.splitext(input_path)[1].lower()
        if ext in SUPPORTED_INPUT_EXTS:
            files_to_process.append((input_path, os.path.basename(input_path)))
    elif os.path.isdir(input_path):
        if recursive:
            for root, _, files in os.walk(input_path):
                for f in files:
                    if os.path.splitext(f)[1].lower() in SUPPORTED_INPUT_EXTS:
                        full_path = os.path.join(root, f)
                        rel_path = os.path.relpath(full_path, input_path)
                        files_to_process.append((full_path, rel_path))
        else:
            for f in os.listdir(input_path):
                full_path = os.path.join(input_path, f)
                if os.path.isfile(full_path) and os.path.splitext(f)[1].lower() in SUPPORTED_INPUT_EXTS:
                    files_to_process.append((full_path, f))
    return files_to_process


STEP_NEXT = 'next'
STEP_BACK = 'back'
GO_BACK = object()  # sentinel returned by ask() when the user types b / back

STEP_LABELS = ["Source", "Codec", "Quality", "Output", "Confirm"]


def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')


def nav_line(allow_back=True):
    back = f"{C_YELLOW}b{C_RESET} {C_DIM}back{C_RESET}    " if allow_back else ""
    return f"{back}{C_YELLOW}q{C_RESET} {C_DIM}quit{C_RESET}"


def breadcrumb(current, labels=None):
    parts = []
    for i, label in enumerate(labels or STEP_LABELS):
        if i < current:
            parts.append(f"{C_GREEN}✔ {label}{C_RESET}")
        elif i == current:
            parts.append(f"{C_CYAN}{C_BOLD}● {label}{C_RESET}")
        else:
            parts.append(f"{C_DIM}○ {label}{C_RESET}")
    return "  " + f" {C_DIM}──{C_RESET} ".join(parts)


def selection_summary(st):
    """One dim line recapping the choices made so far."""
    bits = []
    if st.get('input_path'):
        stripped = st['input_path'].rstrip('\\/')
        name = os.path.basename(stripped) or st['input_path']
        if len(name) > 32:
            name = name[:29] + '...'
        bits.append(f"{name} ({len(st['all_files'])} tracks)")
    if st.get('codec'):
        cfg = CODEC_CONFIG[st['codec']]
        label = cfg['title']
        if st.get('bitrate') and not cfg['is_lossless']:
            label += f" @ {st['bitrate']}"
        bits.append(label)
    if not bits:
        return ""
    return "  " + C_DIM + "  │  ".join(bits) + C_RESET


def render_header(st, crumb, full_banner=False, labels=None, banner=None,
                  title="AUDIO CONVERTER", subtitle="Transcoder & Metadata Engine"):
    if full_banner:
        (banner or print_banner)()
    else:
        clear_screen()
        print()
        print("  " + gradient_text(f"♫  {title}") + f"  {C_DIM}· {subtitle}{C_RESET}")
        print()
    print(breadcrumb(crumb, labels))
    summary = selection_summary(st)
    if summary:
        print(summary)
    print()


def ask(label, allow_back=True):
    """Prompt helper: 'q' quits, 'b' returns GO_BACK (when allowed)."""
    raw = input(f"\n{C_YELLOW}▶ {label} {C_RESET}").strip()
    low = raw.lower()
    if low in ('q', 'quit', 'exit'):
        print(f"\n{C_YELLOW}[!] Cancelled.{C_RESET}")
        sys.exit(0)
    if allow_back and low in ('b', 'back'):
        return GO_BACK
    return raw


def shorten(text, limit=52):
    """Middle-ellipsis for long paths so they fit inside the boxes."""
    if len(text) <= limit:
        return text
    keep = limit - 3
    return text[:keep // 3] + '...' + text[-(keep - keep // 3):]


def print_invalid(msg):
    print(f"  {C_RED}[!] {msg}{C_RESET}")


def lossy_files(files):
    return [it for it in files if os.path.splitext(it[0])[1].lower() in LOSSY_EXTS]


def effective_files(st):
    """The queue after applying the optional 'skip lossy files' choice."""
    files = st['all_files']
    if CODEC_CONFIG[st['codec']]['is_lossless'] and st.get('skip_lossy', True):
        files = [it for it in files if os.path.splitext(it[0])[1].lower() not in LOSSY_EXTS]
    return files


def default_destination(st):
    path, codec = st['input_path'], st['codec']
    if os.path.isdir(path):
        stripped = path.rstrip('\\/')
        base = stripped if len(stripped) > 2 else path
        return f"{base}_{codec}"
    parent = os.path.dirname(path) or "."
    return os.path.join(parent, f"converted_{codec}")


def parse_bitrate(val, codec):
    v = val.strip().lower()
    if v == 'v0' and codec == 'mp3':
        return 'v0'
    if v.isdigit():
        v += 'k'
    if re.fullmatch(r'\d{2,3}k', v):
        return v
    return None


# ───────────────────────────── wizard steps ─────────────────────────────

def step_source(st):
    print(box_top("SELECT AUDIO SOURCE"))
    print(box_line("Drag & drop an audio file or music folder into this window."))
    if st.get('input_path'):
        print(box_line(f"{C_DIM}Press Enter to keep the current source.{C_RESET}"))
    print(box_div())
    print(box_line(nav_line(allow_back=False)))
    print(box_bot())

    while True:
        raw = ask("Source path:", allow_back=False)
        if not raw and st.get('input_path'):
            return STEP_NEXT
        path = clean_path(raw)
        if not path or not os.path.exists(path):
            print_invalid("Invalid path or file does not exist. Please try again.")
            continue
        files = collect_files(path, recursive=True)
        if not files:
            print_invalid("No supported audio files found at that path.")
            continue
        st['input_path'] = path
        st['all_files'] = files
        return STEP_NEXT


def step_codec(st):
    keys = list(CODEC_CONFIG.keys())
    current = st.get('codec') or 'opus'

    print(box_top("CHOOSE TARGET CODEC"))
    for idx, k in enumerate(keys, 1):
        cfg = CODEC_CONFIG[k]
        badge = f"{C_MAGENTA}[Lossless]{C_RESET}" if cfg['is_lossless'] else f"{C_CYAN}[Lossy]{C_RESET}"
        mark = f" {C_GREEN}◀{C_RESET}" if k == current else ""
        print(box_line(
            f"{C_YELLOW}[{idx}]{C_RESET} {C_WHITE}{C_BOLD}{cfg['title']:<18}{C_RESET} "
            f"{badge}  {C_DIM}{cfg['description']}{C_RESET}{mark}"
        ))
    print(box_div())
    print(box_line(nav_line()))
    print(box_bot())

    while True:
        choice = ask(f"Select codec [1-{len(keys)}] (Enter = {keys.index(current) + 1}):")
        if choice is GO_BACK:
            return STEP_BACK
        if not choice:
            new = current
        elif choice.isdigit() and 1 <= int(choice) <= len(keys):
            new = keys[int(choice) - 1]
        else:
            print_invalid(f"Invalid choice. Enter 1 to {len(keys)}.")
            continue
        if new != st.get('codec'):
            st['bitrate'] = None  # tiers differ per codec
        st['codec'] = new
        return STEP_NEXT


def guard_applies(st):
    return CODEC_CONFIG[st['codec']]['is_lossless'] and bool(lossy_files(st['all_files']))


def step_guard(st):
    lossy = lossy_files(st['all_files'])
    all_lossy = len(lossy) == len(st['all_files'])
    y = C_YELLOW

    print(box_top("LOSSY AUDIO DETECTED", color=y))
    print(box_line(f"Found {len(lossy)} lossy track(s) (MP3/AAC/Opus/etc.) in your selection.", color=y))
    print(box_line("Converting lossy audio to a lossless format inflates file size", color=y))
    print(box_line("without restoring discarded frequencies (no quality gain).", color=y))
    print(box_div(color=y))
    print(box_line(f"{C_YELLOW}[1]{C_RESET} {C_GREEN}Skip lossy files, convert lossless masters only (Recommended){C_RESET}", color=y))
    print(box_line(f"{C_YELLOW}[2]{C_RESET} {C_WHITE}Convert all files anyway (force transcode){C_RESET}", color=y))
    print(box_div(color=y))
    print(box_line(nav_line(), color=y))
    print(box_bot(color=y))

    while True:
        choice = ask("Select option [1-2] (Enter = 1):")
        if choice is GO_BACK:
            return STEP_BACK
        if choice in ('', '1'):
            if all_lossy:
                print_invalid("Every track is lossy, nothing would be left. Pick 2, or type b to change codec.")
                continue
            st['skip_lossy'] = True
            return STEP_NEXT
        if choice == '2':
            st['skip_lossy'] = False
            return STEP_NEXT
        print_invalid("Invalid choice. Enter 1 or 2.")


def bitrate_applies(st):
    return not CODEC_CONFIG[st['codec']]['is_lossless']


def step_bitrate(st):
    codec = st['codec']
    cfg = CODEC_CONFIG[codec]
    tiers = cfg['tiers']
    current = st.get('bitrate') or cfg['default_bitrate']

    print(box_top(f"SELECT BITRATE FOR {cfg['title'].upper()}"))
    for idx, (b_val, b_desc) in enumerate(tiers, 1):
        mark = f" {C_GREEN}◀{C_RESET}" if b_val == current else ""
        print(box_line(f"{C_YELLOW}[{idx}]{C_RESET} {C_WHITE}{C_BOLD}{b_desc}{C_RESET}{mark}"))
    print(box_line(f"{C_YELLOW}[{len(tiers) + 1}]{C_RESET} {C_WHITE}Custom (enter your own kbps value){C_RESET}"))
    print(box_div())
    print(box_line(nav_line()))
    print(box_bot())

    while True:
        raw = ask(f"Choose quality [1-{len(tiers) + 1}] (Enter = {current}):")
        if raw is GO_BACK:
            return STEP_BACK
        if not raw:
            st['bitrate'] = current
            return STEP_NEXT
        if raw.isdigit():
            num = int(raw)
            if 1 <= num <= len(tiers):
                st['bitrate'] = tiers[num - 1][0]
                return STEP_NEXT
            if num == len(tiers) + 1:
                while True:
                    cv = ask("Custom bitrate (e.g. 96k, 224k) (b = back to list):")
                    if cv is GO_BACK:
                        break
                    parsed = parse_bitrate(cv, codec)
                    if parsed:
                        st['bitrate'] = parsed
                        return STEP_NEXT
                    print_invalid("Enter a value like 96k or 224 (kbps).")
                continue
        print_invalid(f"Invalid choice. Enter 1 to {len(tiers) + 1}.")


def step_dest(st):
    default_dst = default_destination(st)
    custom = st.get('dst_custom')
    current = custom or default_dst

    print(box_top("DESTINATION FOLDER"))
    print(box_line(f"{'Selected' if custom else 'Default'}: {C_WHITE}{shorten(current)}{C_RESET}"))
    print(box_line("Press Enter to keep it, or drag & drop a different folder."))
    print(box_div())
    print(box_line(nav_line()))
    print(box_bot())

    raw = ask("Destination path:")
    if raw is GO_BACK:
        return STEP_BACK
    if raw:
        st['dst_custom'] = clean_path(raw)
    st['dst'] = st.get('dst_custom') or default_dst
    return STEP_NEXT


def step_skip(st):
    current = st.get('skip_existing', True)
    print(box_top("OPTIONS"))
    print(box_line("Skip files that already exist in the destination folder?"))
    print(box_line(f"{C_DIM}Handy for resuming an interrupted batch without re-encoding.{C_RESET}"))
    print(box_div())
    print(box_line(nav_line()))
    print(box_bot())

    hint = "Y/n" if current else "y/N"
    while True:
        raw = ask(f"Skip already converted files? [{hint}]:")
        if raw is GO_BACK:
            return STEP_BACK
        low = raw.lower()
        if not low:
            st['skip_existing'] = current
            return STEP_NEXT
        if low in ('y', 'yes'):
            st['skip_existing'] = True
            return STEP_NEXT
        if low in ('n', 'no'):
            st['skip_existing'] = False
            return STEP_NEXT
        print_invalid("Please answer y or n.")


def step_confirm(st):
    cfg = CODEC_CONFIG[st['codec']]
    files = effective_files(st)
    rate_str = f" @ {st['bitrate']}" if (st.get('bitrate') and not cfg['is_lossless']) else " (Lossless Bit-Perfect)" if cfg['is_lossless'] else ""
    skipped_lossy = len(st['all_files']) - len(files)

    print(box_top("JOB SUMMARY"))
    print(box_line(f"{C_BOLD}Source:{C_RESET}        {C_WHITE}{shorten(st['input_path'])}{C_RESET}"))
    print(box_line(f"{C_BOLD}Queue:{C_RESET}         {C_YELLOW}{len(files)} file(s){C_RESET}"))
    if skipped_lossy:
        print(box_line(f"{C_BOLD}Filtered:{C_RESET}      {C_DIM}{skipped_lossy} lossy file(s) left out{C_RESET}"))
    print(box_line(f"{C_BOLD}Target:{C_RESET}        {C_GREEN}{cfg['title']}{rate_str}{C_RESET}"))
    print(box_line(f"{C_BOLD}Destination:{C_RESET}   {C_WHITE}{shorten(st['dst'])}{C_RESET}"))
    print(box_line(f"{C_BOLD}Skip existing:{C_RESET} {C_WHITE}{'Yes' if st['skip_existing'] else 'No'}{C_RESET}"))
    if same_applies(st):
        print(box_line(f"{C_BOLD}Same-format:{C_RESET}   {C_WHITE}{'Re-encode' if st.get('force_reencode') else 'Copy as-is'}{C_RESET}"))
    print(box_line(f"{C_BOLD}Tags & Art:{C_RESET}    {C_MAGENTA}Preserve all metadata & embedded album covers{C_RESET}"))
    print(box_div())
    print(box_line(f"{C_YELLOW}Enter{C_RESET} {C_DIM}start{C_RESET}    {nav_line()}    {C_YELLOW}n{C_RESET} {C_DIM}cancel{C_RESET}"))
    print(box_bot())

    while True:
        raw = ask(f"{C_GREEN}{C_BOLD}Start conversion?{C_RESET}{C_YELLOW} [Y/n]:")
        if raw is GO_BACK:
            return STEP_BACK
        low = raw.lower()
        if low in ('', 'y', 'yes'):
            return STEP_NEXT
        if low in ('n', 'no'):
            print(f"\n{C_YELLOW}[!] Aborted.{C_RESET}")
            sys.exit(0)
        print_invalid("Press Enter to start, b to go back, or n to cancel.")


def same_format_count(st):
    return sum(1 for src, _ in effective_files(st) if already_in_target(src, st['codec']))


def same_applies(st):
    return same_format_count(st) > 0


def step_same(st):
    cfg = CODEC_CONFIG[st['codec']]
    n = same_format_count(st)
    rate = f" @ {st['bitrate']}" if (st.get('bitrate') and not cfg['is_lossless']) else ""
    why = ("Re-encoding lossy audio a second time only lowers its quality."
           if not cfg['is_lossless'] else "Re-encoding lossless files again gains nothing.")
    forced = bool(st.get('force_reencode'))
    mark1 = "" if forced else f" {C_GREEN}◀{C_RESET}"
    mark2 = f" {C_GREEN}◀{C_RESET}" if forced else ""

    print(box_top("FILES ALREADY IN TARGET FORMAT"))
    print(box_line(f"{n} file(s) are already {cfg['title']}."))
    print(box_line(why))
    print(box_div())
    print(box_line(f"{C_YELLOW}[1]{C_RESET} {C_GREEN}Copy them as-is (Recommended){C_RESET}{mark1}"))
    print(box_line(f"{C_YELLOW}[2]{C_RESET} {C_WHITE}Re-encode them anyway{rate}{C_RESET}{mark2}"))
    print(box_div())
    print(box_line(nav_line()))
    print(box_bot())

    while True:
        choice = ask(f"Select option [1-2] (Enter = {2 if forced else 1}):")
        if choice is GO_BACK:
            return STEP_BACK
        if choice == '':
            return STEP_NEXT
        if choice == '1':
            st['force_reencode'] = False
            return STEP_NEXT
        if choice == '2':
            st['force_reencode'] = True
            return STEP_NEXT
        print_invalid("Invalid choice. Enter 1 or 2.")


# (name, function, breadcrumb index, applies-predicate)
WIZARD_STEPS = [
    ('source',  step_source,  0, None),
    ('codec',   step_codec,   1, None),
    ('guard',   step_guard,   1, guard_applies),
    ('bitrate', step_bitrate, 2, bitrate_applies),
    ('same',    step_same,    2, same_applies),
    ('dest',    step_dest,    3, None),
    ('skip',    step_skip,    3, None),
    ('confirm', step_confirm, 4, None),
]


def run_wizard(steps, st, labels, banner, title, subtitle, start=0):
    """Generic step runner: each step returns 'next' or 'back'; inapplicable steps are skipped."""
    clear_screen()
    i, direction, first = start, 1, True
    while i < len(steps):
        name, fn, crumb, applies = steps[i]
        if applies and not applies(st):
            i = max(0, i + direction)  # silently pass over steps that don't apply
            continue
        render_header(st, crumb, full_banner=first, labels=labels, banner=banner, title=title, subtitle=subtitle)
        first = False
        if fn(st) == STEP_BACK:
            direction = -1
            i = max(0, i - 1)
        else:
            direction = 1
            i += 1
    return st


def interactive_mode(initial_path=None):
    """Step-based wizard. Type 'b' at any prompt to go back, 'q' to quit.

    `initial_path` (e.g. a file dropped onto convert.bat) pre-fills the source and starts at the codec step.
    """
    st = {'skip_existing': True, 'force_reencode': False}
    start = 0
    if initial_path:
        path = clean_path(initial_path)
        files = collect_files(path, recursive=True) if os.path.exists(path) else []
        if files:
            st['input_path'], st['all_files'] = path, files
            start = 1
    run_wizard(WIZARD_STEPS, st, None, None, "AUDIO CONVERTER", "Transcoder & Metadata Engine", start)

    cfg = CODEC_CONFIG[st['codec']]
    bitrate = None if cfg['is_lossless'] else st['bitrate']
    return (st['input_path'], st['dst'], st['codec'], bitrate,
            st['skip_existing'], st['force_reencode'], effective_files(st))


def default_workers():
    return max(1, min(8, os.cpu_count() or 4))


def run_batch(file_list, dst_dir, codec, bitrate, skip_existing, force_reencode, workers, dry_run=False):
    """Converts the queue in parallel and prints the result card. Returns True when nothing failed."""
    out_ext = CODEC_CONFIG[codec]['ext']

    def out_path(rel_name):
        return os.path.join(dst_dir, os.path.splitext(rel_name)[0] + out_ext)

    # ── Dry run: show what would happen, write nothing ──
    if dry_run:
        tags = {
            'encode':      f"{C_GREEN}→ [ENCODE]{C_RESET}",
            'copy':        f"{C_CYAN}⧉ [COPY]  {C_RESET}",
            'skip-exists': f"{C_YELLOW}↷ [SKIP]  {C_RESET}",
            'skip-self':   f"{C_YELLOW}↷ [SKIP]  {C_RESET}",
        }
        tally = {}
        print(f"\n{C_CYAN}──▶ Dry run: {len(file_list)} track(s) checked, nothing will be written.{C_RESET}\n")
        for src_file, rel_name in file_list:
            action = decide_action(src_file, out_path(rel_name), codec, skip_existing, force_reencode)
            tally[action] = tally.get(action, 0) + 1
            print(f"  {tags[action]}  {C_WHITE}{rel_name}{C_RESET}")
        skips = tally.get('skip-exists', 0) + tally.get('skip-self', 0)
        print(f"\n  {C_BOLD}Would encode {tally.get('encode', 0)}, copy {tally.get('copy', 0)}, skip {skips}.{C_RESET}")
        return True

    total = len(file_list)
    print(f"\n{C_CYAN}──▶ Processing {total} tracks using {workers} parallel threads...{C_RESET}\n")

    stats = {'done': 0, 'copied': 0, 'skipped': 0, 'failed': 0, 'cancelled': 0, 'art': 0}
    stop = threading.Event()

    def process_item(item):
        src_file, rel_name = item
        if stop.is_set():
            return rel_name, False, "Cancelled"
        try:
            ok, msg = convert_single_file(src_file, out_path(rel_name), codec, bitrate, skip_existing, force_reencode)
        except Exception as exc:  # never let one bad file kill the batch
            ok, msg = False, f"Error: {exc}"
        return rel_name, ok, msg

    def record(ok, msg):
        """Updates the tallies; returns (status, note), or None for items that never started."""
        if not ok:
            if msg.startswith("Cancelled"):
                stats['cancelled'] += 1
                return None
            stats['failed'] += 1
            return (f"{C_RED}✖ [FAIL]{C_RESET}",
                    f"           {C_DIM}{shorten(msg.replace(chr(10), ' '), 100)}{C_RESET}")
        if msg.startswith("Skipped"):
            stats['skipped'] += 1
            return f"{C_YELLOW}↷ [SKIP]{C_RESET}", ""
        if msg.startswith("Copied"):
            stats['copied'] += 1
            return f"{C_CYAN}⧉ [COPY]{C_RESET}", ""
        stats['done'] += 1
        if "cover art" in msg:
            stats['art'] += 1
            return (f"{C_GREEN}✔ [DONE]{C_RESET}",
                    f"           {C_DIM}⚠ cover art could not be embedded{C_RESET}")
        return f"{C_GREEN}✔ [DONE]{C_RESET}", ""

    def show(prefix, rel_name, result):
        if result is None:
            return
        status, note = result
        print(f"  {prefix} {status}  {C_WHITE}{rel_name}{C_RESET}")
        if note:
            print(note)

    executor = ThreadPoolExecutor(max_workers=workers)
    futures = []
    counted = set()
    completed = 0
    interrupted = False
    try:
        futures = [executor.submit(process_item, item) for item in file_list]
        for future in as_completed(futures):
            counted.add(future)
            completed += 1
            rel_name, ok, msg = future.result()
            pct = int((completed / total) * 100)
            show(f"{C_BOLD}[{completed:02d}/{total:02d} {pct:3d}%]{C_RESET}", rel_name, record(ok, msg))
    except KeyboardInterrupt:
        interrupted = True
        stop.set()
        for f in futures:
            f.cancel()
        print(f"\n{C_YELLOW}[!] Interrupted - stopping after the files already in progress...{C_RESET}")
    finally:
        try:
            executor.shutdown(wait=True)
        except KeyboardInterrupt:
            executor.shutdown(wait=False)

    if interrupted:
        # Files that were already running finish after the interrupt - count them too.
        for f in futures:
            if f not in counted and f.done() and not f.cancelled():
                rel_name, ok, msg = f.result()
                show(f"{C_BOLD}[finished]{C_RESET}", rel_name, record(ok, msg))
        stats['cancelled'] = total - (stats['done'] + stats['copied'] + stats['skipped'] + stats['failed'])

    color = C_YELLOW if interrupted else C_GREEN
    print(f"\n" + box_top("INTERRUPTED" if interrupted else "COMPLETED", color=color))
    print(box_line(f"{C_BOLD}Converted:{C_RESET}               {C_GREEN}{stats['done']} track(s){C_RESET}", color=color))
    if stats['copied']:
        print(box_line(f"{C_BOLD}Copied (same format):{C_RESET}    {C_CYAN}{stats['copied']} track(s){C_RESET}", color=color))
    if stats['skipped']:
        print(box_line(f"{C_BOLD}Skipped:{C_RESET}                 {C_YELLOW}{stats['skipped']} track(s){C_RESET}", color=color))
    if stats['failed']:
        print(box_line(f"{C_BOLD}Failed:{C_RESET}                  {C_RED}{stats['failed']} track(s){C_RESET}", color=color))
    if stats['cancelled']:
        print(box_line(f"{C_BOLD}Not processed:{C_RESET}           {C_YELLOW}{stats['cancelled']} track(s){C_RESET}", color=color))
    if stats['art']:
        print(box_line(f"{C_BOLD}Cover art not embedded:{C_RESET}  {C_YELLOW}{stats['art']} track(s){C_RESET}", color=color))
    print(box_line(f"{C_BOLD}Saved In:{C_RESET}                {C_WHITE}{shorten(dst_dir, 44)}{C_RESET}", color=color))
    print(box_bot(color=color))

    return stats['failed'] == 0 and not interrupted


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


def build_argument_parser():
    parser = argparse.ArgumentParser(
        prog="AudioConverter" if getattr(sys, 'frozen', False) else "audio_converter.py",
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
    parser.add_argument('--skip-existing', action='store_true',
                        help="Skip encoding if the output file already exists")
    parser.add_argument('--force-reencode', action='store_true',
                        help="Re-encode files that are already in the target format instead of copying them")
    parser.add_argument('--include-lossy', action='store_true',
                        help="Allow lossy sources when the target is lossless (skipped by default)")
    parser.add_argument('--preset', choices=PRESET_NAMES, default=None,
                        help="Run a pre-configured workflow, e.g. --preset flac_to_opus SOURCE [DEST] "
                             "(takes its own options; see --preset flac_to_opus --help)")
    parser.add_argument('--dry-run', action='store_true',
                        help="Show what would be encoded/copied/skipped without writing anything")
    parser.add_argument('--version', action='version', version=f"%(prog)s {__version__}")
    return parser


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_argument_parser()
    preset, rest = split_preset(argv)
    if preset is not None:
        if preset not in PRESET_NAMES:
            parser.error(f"unknown preset '{preset}' (choose from: {', '.join(PRESET_NAMES)})")
        import flac_to_opus  # imported lazily; the alias at the top of this file prevents a double load
        return flac_to_opus.main(rest, prog=f"{parser.prog} --preset {preset}")
    args = parser.parse_args(argv)
    if args.workers is not None and args.workers < 1:
        parser.error("--workers must be at least 1")
    check_ffmpeg()
    workers = args.workers or default_workers()

    if not args.input:
        # ── Interactive wizard ──
        (input_path, dst_dir, codec, bitrate, skip_existing,
         force_reencode, file_list) = interactive_mode(args.path)
        interactive = True
    else:
        # ── Non-interactive (flags) ──
        interactive = False
        print_banner()
        input_path = clean_path(args.input)
        if not os.path.exists(input_path):
            print(f"{C_RED}[ERROR] Input path does not exist: {input_path}{C_RESET}")
            sys.exit(1)

        codec = (args.format or 'opus').lower()
        cfg = CODEC_CONFIG[codec]
        if cfg['is_lossless']:
            if args.bitrate:
                print(f"{C_YELLOW}[!] {cfg['title']} is lossless - ignoring --bitrate.{C_RESET}")
            bitrate = None
        elif args.bitrate:
            bitrate = parse_bitrate(args.bitrate, codec)
            if not bitrate:
                print(f"{C_RED}[ERROR] Invalid bitrate '{args.bitrate}' for {cfg['title']} "
                      f"(use e.g. 192k{', or v0' if codec == 'mp3' else ''}).{C_RESET}")
                sys.exit(2)
        else:
            bitrate = cfg['default_bitrate']

        dst_dir = clean_path(args.output) if args.output else default_destination(
            {'input_path': input_path, 'codec': codec})
        skip_existing = args.skip_existing
        force_reencode = args.force_reencode
        file_list = collect_files(input_path, recursive=True)

        if cfg['is_lossless'] and not args.include_lossy:
            lossy_paths = {item[0] for item in lossy_files(file_list)}
            if lossy_paths:
                file_list = [item for item in file_list if item[0] not in lossy_paths]
                print(f"{C_YELLOW}[!] Skipped {len(lossy_paths)} lossy source file(s) - converting lossy audio to "
                      f"{cfg['title']} gains no quality. Use --include-lossy to convert them anyway.{C_RESET}")

    if not file_list:
        print(f"{C_YELLOW}[!] No supported audio files to convert.{C_RESET}")
        if interactive:
            input(f"\n{C_DIM}Press Enter to exit...{C_RESET}")
        sys.exit(0)

    ok = run_batch(file_list, dst_dir, codec, bitrate, skip_existing, force_reencode, workers, dry_run=args.dry_run)

    if interactive:
        input(f"\n{C_DIM}Press Enter to exit...{C_RESET}")
    else:
        sys.exit(0 if ok else 1)


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
