# Audio Converter v1.1.0

Audio Converter v1.1.0 introduces a standalone, zero-installation Windows distribution alongside core engine optimizations and preset integration.

## Release Highlights

### Standalone Windows Distribution
- Portable 64-bit Windows binary (`AudioConverter.exe`) requiring no prior installation of Python, pip, or FFmpeg.
- Bundles a verified, pinned release of FFmpeg 8.1.3 and Python runtime dependencies in an isolated directory structure.
- Suppresses background console window flashing during audio encoding subprocess calls.

### Workflow & Preset Integration
- Added `--preset flac_to_opus` flag to execute opinionated FLAC-to-Opus conversions directly through the main executable.
- Preserved complete backward compatibility with existing command-line arguments and launcher scripts (`convert.bat`, `convert.sh`, `flac_to_opus_192k.bat`, `flac_to_opus_192k.sh`).

### Codec & Tagging Preservation
- Full support for Opus, AAC/M4A, MP3, FLAC, ALAC, Ogg Vorbis, and WAV.
- Automatic preservation of metadata tags (title, artist, album, track numbers, year, lyrics) and native album artwork embedding across all supported formats.
- Smart guardrails to prevent lossy-to-lossless transcoding quality bloat and redundant re-encoding of same-format files.

## Installation and Execution (Windows)

1. Download `AudioConverter-v1.1.0-win64.zip` and the accompanying checksum file `AudioConverter-v1.1.0-win64.zip.sha256`.
2. Extract the entire ZIP archive into a destination directory. Do not run the executable from within the compressed preview.
3. Launch `AudioConverter.exe` by double-clicking or dragging audio files and folders directly onto the application.

> **Windows Defender SmartScreen Notice:**
> As this portable binary is independently built and unsigned, Windows Defender SmartScreen may display an initial warning. Click **More info** followed by **Run anyway**.

## Checksum Verification

Verify the integrity of the downloaded archive using PowerShell:

```powershell
Get-FileHash .\AudioConverter-v1.1.0-win64.zip -Algorithm SHA256
```

Compare the resulting hash against `AudioConverter-v1.1.0-win64.zip.sha256`.

## Licensing

Audio Converter is distributed under the GNU General Public License v2.0 or later (GPL-2.0-or-later). Third-party license notices, including FFmpeg and Mutagen, are included within the `LICENSES/` directory of the application bundle.
