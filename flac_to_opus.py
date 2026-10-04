#!/usr/bin/env python3
"""
FLAC -> Opus preset transcoder (defaults to 192 kbps)

A thin, opinionated front-end for audio_converter.py: pick a FLAC folder or file, choose an Opus
quality tier, and convert while keeping every tag and the embedded album cover.

Usage:
  python flac_to_opus.py                      # interactive wizard
  python flac_to_opus.py SOURCE [DEST]        # one-shot, 192k, skips files that already exist
  python flac_to_opus.py SOURCE -b 160k --dry-run
"""

import os
import sys
import argparse

import audio_converter as ac

PRESET_CODEC = 'opus'
DEFAULT_BITRATE = '192k'
STEP_LABELS = ["Source", "Quality", "Output", "Confirm"]


def print_banner():
    ac.print_banner(
        ("FLAC>OPUS",),
        tagline="♫  FLAC to Opus Transcoder  ♫",
        features="Hi-res masters, small files   ✦   tags & album art preserved",
    )


def collect_flac_files(path):
    return [item for item in ac.collect_files(path, recursive=True) if item[0].lower().endswith('.flac')]


def step_source(st):
    print(ac.box_top("SELECT FLAC SOURCE"))
    print(ac.box_line("Drag & drop a FLAC file or a folder of FLACs into this window."))
    if st.get('input_path'):
        print(ac.box_line(f"{ac.C_DIM}Press Enter to keep the current source.{ac.C_RESET}"))
    print(ac.box_div())
    print(ac.box_line(ac.nav_line(allow_back=False)))
    print(ac.box_bot())

    while True:
        raw = ac.ask("Source path:", allow_back=False)
        if not raw and st.get('input_path'):
            return ac.STEP_NEXT
        path = ac.clean_path(raw)
        if not path or not os.path.exists(path):
            ac.print_invalid("Invalid path or file does not exist. Please try again.")
            continue
        files = collect_flac_files(path)
        if not files:
            ac.print_invalid("No FLAC files found at that path.")
            continue
        st['input_path'] = path
        st['all_files'] = files
        return ac.STEP_NEXT


WIZARD_STEPS = [
    ('source',  step_source,     0, None),
    ('bitrate', ac.step_bitrate, 1, None),
    ('dest',    ac.step_dest,    2, None),
    ('skip',    ac.step_skip,    2, None),
    ('confirm', ac.step_confirm, 3, None),
]


def interactive_mode():
    st = {'codec': PRESET_CODEC, 'bitrate': DEFAULT_BITRATE, 'skip_existing': True, 'force_reencode': False}
    ac.run_wizard(WIZARD_STEPS, st, STEP_LABELS, print_banner, "FLAC → OPUS", "Preset Transcoder")
    return st['input_path'], st['dst'], st['bitrate'], st['skip_existing'], st['all_files']


def main():
    parser = argparse.ArgumentParser(
        prog="flac_to_opus.py",
        description="Convert FLAC to Opus (default 192k), preserving tags and cover art. "
                    "Run with no arguments for the interactive wizard."
    )
    parser.add_argument('source', nargs='?', help="FLAC file or folder (skips the wizard)")
    parser.add_argument('dest', nargs='?', help="Destination folder (default: <source>_opus)")
    parser.add_argument('-b', '--bitrate', default=None, help=f"Opus bitrate (default: {DEFAULT_BITRATE})")
    parser.add_argument('-w', '--workers', type=int, default=None,
                        help="Parallel worker threads (default: CPU count, max 8)")
    parser.add_argument('--overwrite', action='store_true',
                        help="Re-encode files that already exist at the destination")
    parser.add_argument('--dry-run', action='store_true',
                        help="Show what would be converted without writing anything")
    parser.add_argument('--version', action='version', version=f"%(prog)s {ac.__version__}")

    args = parser.parse_args()
    if args.workers is not None and args.workers < 1:
        parser.error("--workers must be at least 1")
    ac.check_ffmpeg()
    workers = args.workers or ac.default_workers()

    if args.source:
        interactive = False
        print_banner()
        src = ac.clean_path(args.source)
        if not os.path.exists(src):
            print(f"{ac.C_RED}[ERROR] Source does not exist: {src}{ac.C_RESET}")
            sys.exit(1)
        bitrate = ac.parse_bitrate(args.bitrate or DEFAULT_BITRATE, PRESET_CODEC)
        if not bitrate:
            print(f"{ac.C_RED}[ERROR] Invalid bitrate '{args.bitrate}' (use e.g. 160k or 192k).{ac.C_RESET}")
            sys.exit(2)
        dst = ac.clean_path(args.dest) if args.dest else ac.default_destination(
            {'input_path': src, 'codec': PRESET_CODEC})
        skip_existing = not args.overwrite
        files = collect_flac_files(src)
    else:
        interactive = True
        src, dst, bitrate, skip_existing, files = interactive_mode()

    if not files:
        print(f"\n{ac.C_YELLOW}[!] No FLAC files found to convert.{ac.C_RESET}")
        if interactive:
            input(f"\n{ac.C_DIM}Press Enter to exit...{ac.C_RESET}")
        sys.exit(0)

    ok = ac.run_batch(files, dst, PRESET_CODEC, bitrate, skip_existing, False, workers, dry_run=args.dry_run)

    if interactive:
        input(f"\n{ac.C_DIM}Press Enter to exit...{ac.C_RESET}")
    else:
        sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
