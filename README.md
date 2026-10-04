# Audio Converter & Metadata Engine

```text
                      █████╗ ██╗   ██╗██████╗ ██╗ ██████╗
                     ██╔══██╗██║   ██║██╔══██╗██║██╔═══██╗
                     ███████║██║   ██║██║  ██║██║██║   ██║
                     ██╔══██║██║   ██║██║  ██║██║██║   ██║
                     ██║  ██║╚██████╔╝██████╔╝██║╚██████╔╝
                     ╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚═╝ ╚═════╝
  ██████╗ ██████╗ ███╗   ██╗██╗   ██╗███████╗██████╗ ████████╗███████╗██████╗
 ██╔════╝██╔═══██╗████╗  ██║██║   ██║██╔════╝██╔══██╗╚══██╔══╝██╔════╝██╔══██╗
 ██║     ██║   ██║██╔██╗ ██║██║   ██║█████╗  ██████╔╝   ██║   █████╗  ██████╔╝
 ██║     ██║   ██║██║╚██╗██║╚██╗ ██╔╝██╔══╝  ██╔══██╗   ██║   ██╔══╝  ██╔══██╗
 ╚██████╗╚██████╔╝██║ ╚████║ ╚████╔╝ ███████╗██║  ██║   ██║   ███████╗██║  ██║
  ╚═════╝ ╚═════╝ ╚═╝  ╚═══╝  ╚═══╝  ╚══════╝╚═╝  ╚═╝   ╚═╝   ╚══════╝╚═╝  ╚═╝
```

<!-- Replace the block above with a screenshot once you have one:  ![Screenshot](docs/screenshot.png) -->

A multi-threaded batch audio converter with a step-by-step terminal wizard. It re-encodes whole music libraries between Opus, AAC, MP3, FLAC, ALAC, Ogg Vorbis and WAV while **keeping every metadata tag and embedded album art**.

## About

Audio Converter is a command-line utility and interactive tool for converting music files across modern audio codecs while strictly preserving audio metadata, tags, and embedded album art.

It is designed to solve common issues encountered in bulk audio processing:
- **Metadata and Artwork Retention**: Many encoders strip secondary tags, replaygain values, lyrics, or album covers. Audio Converter synchronizes both global and stream-level metadata and re-embeds source artwork directly into each format's native structure (Vorbis comments for Opus/FLAC/Ogg, ID3 APIC frames for MP3, and `covr` atoms for AAC/ALAC).
- **Protection Against Audio Degradation**: Converting lossy audio (e.g., MP3 or AAC) to lossless formats (FLAC, ALAC, WAV) increases file size up to 10× without restoring lost acoustic information. Built-in guardrails alert the user and offer to skip lossy inputs.
- **Copy vs. Re-encode Optimization**: When an input file already matches the selected target format and codec, the tool copies it untouched rather than degrading audio quality through unnecessary re-compression.
- **Interactive and Scriptable Interfaces**: Offers an interactive terminal wizard with navigation history (type `b` to go back, `q` to quit), drag-and-drop launcher scripts (`.bat` / `.sh`), and a full command-line flag interface for batch scripting.
- **Atomic Writes and Resilience**: Audio files are encoded to temporary `.partial` files before being atomically renamed, preventing half-written or corrupted files if a process is interrupted.

## Features

- **Interactive wizard** with a progress breadcrumb, remembered choices and a **back** key on every screen
- **Drag & drop** a file or folder onto the launcher, or use flags for scripting
- **Parallel encoding** (defaults to your CPU count, up to 8 threads)
- **Smart guardrails**: no pointless lossy → lossless conversions, no needless re-encoding of files already in the target format
- **Safe writes**: output is written to a `.partial` file and renamed when complete, so an interrupted run can be resumed without corrupt leftovers
- **Clean Ctrl+C**: finishes the files in progress, then prints a summary
- **Dry run** mode to preview exactly what would happen
- Tags (title, artist, album, year, track, lyrics, …) and cover art preserved across all formats

## Requirements

| Requirement | Notes |
| :--- | :--- |
| **Python 3.8+** | Windows, macOS and Linux |
| **FFmpeg** on your `PATH` | Standard builds include the Opus, MP3 and Vorbis encoders |
| **mutagen** | Installed automatically on first run (or `pip install -r requirements.txt`) |

Installing FFmpeg:

```text
Windows:         winget install Gyan.FFmpeg
macOS:           brew install ffmpeg
Debian / Ubuntu: sudo apt install ffmpeg
```

## Installation

```bash
git clone https://github.com/bennypepper/audio-converter.git
cd audio-converter
pip install -r requirements.txt   # optional - mutagen is also auto-installed
```

## Quick Start

### Windows
- **Drag & drop** a file or folder onto **`convert.bat`** to open the wizard with that source already filled in.
- **Double-click `convert.bat`**, then drag your music into the window when asked.
- **FLAC → Opus in one click**: drop a folder onto **`flac_to_opus_192k.bat`**.

### macOS / Linux
```bash
./convert.sh                       # interactive wizard
./convert.sh ~/Music/Album         # wizard with the source pre-filled
./flac_to_opus_192k.sh ~/Music/HiRes
```
(If needed: `chmod +x convert.sh flac_to_opus_192k.sh`.)

### Navigating the wizard

| Key | Action |
| :--- | :--- |
| `b` / `back` | Go back one step (your earlier choices are remembered) |
| `Enter` | Accept the default - the current choice is marked with ◀ |
| `q` / `quit` | Exit at any time |

The wizard steps are **Source → Codec → Quality → Output → Confirm**. Steps that don't apply (for example *Quality* for lossless targets) are skipped automatically.

## Smart Guardrails

1. **Lossy → lossless guard**: converting MP3/AAC/Opus/Ogg/WMA to FLAC, ALAC or WAV inflates file size 5-10× without restoring any lost detail. The wizard offers to skip lossy files (recommended). In CLI mode they are skipped unless you pass `--include-lossy`.
2. **Same-format files are copied, not re-encoded**: an `.opus` file being "converted" to Opus is copied as-is, because encoding lossy audio a second time only degrades it. AAC vs ALAC inside `.m4a` is detected correctly. Use `--force-reencode` (or the wizard's *Re-encode anyway* option) to override, for example to lower a bitrate.
3. **Skip existing**: resume an interrupted batch without redoing finished files. Incomplete files never count as finished.

## Codecs & Bitrate Tiers

| Codec | Extension | Type | Presets |
| :--- | :--- | :--- | :--- |
| **Opus** | `.opus` | Lossy | `128k`, `160k`, `192k` *(Recommended)*, `256k`, or custom |
| **AAC / M4A** | `.m4a` | Lossy | `128k`, `192k`, `256k` *(Apple Music standard)*, `320k`, or custom |
| **MP3** | `.mp3` | Lossy | `192k`, `256k`, `320k` *(CBR, recommended)*, `V0` VBR (~245k), or custom |
| **FLAC** | `.flac` | Lossless | Compression level 8 |
| **ALAC** | `.m4a` | Lossless | Apple Lossless |
| **Ogg Vorbis** | `.ogg` | Lossy | `128k`, `160k`, `192k`, `256k`, or custom |
| **WAV** | `.wav` | Lossless | Uncompressed 16-bit PCM |

## Command Line Usage

```bash
python audio_converter.py                          # interactive wizard
python audio_converter.py "D:\Music\Album"         # wizard, source pre-filled
python audio_converter.py -i <INPUT> -o <OUTPUT> -f <FORMAT> -b <BITRATE>   # no prompts
```

| Flag | Description | Default |
| :--- | :--- | :--- |
| `PATH` | *(positional)* Pre-fill the wizard with a file or folder | - |
| `-i`, `--input` | Source file or folder; **skips the wizard** | - |
| `-o`, `--output` | Destination folder | `<input>_<format>` |
| `-f`, `--format` | `opus`, `mp3`, `m4a`, `flac`, `alac`, `ogg`, `wav` | `opus` |
| `-b`, `--bitrate` | `128k`, `192k`, `320k`, `v0` (MP3 only), … ignored for lossless | codec default |
| `-w`, `--workers` | Parallel threads | CPU count (max 8) |
| `--skip-existing` | Skip outputs that already exist | off |
| `--force-reencode` | Re-encode files already in the target format instead of copying | off |
| `--include-lossy` | Allow lossy sources when the target is lossless | off |
| `--dry-run` | Show what would be encoded / copied / skipped, write nothing | off |
| `--version` | Print the version | - |

Exit codes: `0` success · `1` some files failed, were interrupted, or the input was missing · `2` invalid arguments.

Examples:

```bash
python audio_converter.py -i ~/Music/Albums -f mp3 -b v0 --skip-existing
python audio_converter.py -i ~/Music/Albums -f flac --dry-run
```

## FLAC → Opus Preset

`flac_to_opus.py` is a focused front-end (with its own **FLAC ▸ OPUS** banner) built on the same engine.

```bash
python flac_to_opus.py                        # wizard
python flac_to_opus.py ~/Music/HiRes          # one-shot, 192k -> ~/Music/HiRes_opus
python flac_to_opus.py ~/Music/HiRes ~/Music/Portable -b 160k
```

Options: `-b/--bitrate`, `-w/--workers`, `--overwrite` (re-encode existing outputs), `--dry-run`, `--version`.

## Metadata & Album Art

1. **FFmpeg pass** keeps all text tags via `-map_metadata 0`.
2. **Mutagen** extracts the source cover and re-embeds it in each format's native way: `METADATA_BLOCK_PICTURE` for Opus/Ogg, `APIC` for MP3, the `covr` atom for M4A, and a picture block for FLAC.

If a cover can't be embedded, the file is still converted and the summary tells you how many were affected. WAV has no standard cover-art support.

## Project Structure

```text
.
├── audio_converter.py        # Main converter: wizard, CLI and batch engine
├── flac_to_opus.py           # FLAC -> Opus preset with its own banner
├── convert.bat / convert.sh                  # Launchers (Windows / macOS+Linux)
├── flac_to_opus_192k.bat / flac_to_opus_192k.sh
├── tests/test_audio_converter.py
├── requirements.txt
├── LICENSE
└── README.md
```

## Tests

```bash
python -m unittest discover tests
```

## Troubleshooting

- **`'ffmpeg' is not found`**: install FFmpeg (see Requirements) and reopen your terminal so `PATH` refreshes.
- **Strange characters or no colours on Windows**: use Windows Terminal or a recent PowerShell/CMD (Windows 10+).
- **Nothing happened for some files**: they were probably skipped (already exist, lossy → lossless guard, or already in the target format). The batch summary lists the counts.
- **Leftover `*.partial.*` files**: an interrupted run's temporary files; they are safe to delete and are overwritten on the next run.

## License

[MIT](LICENSE)
