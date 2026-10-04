# Releasing Audio Converter

This document details the step-by-step release process for Audio Converter and the portable Windows build.

## Release Process

1. **Bump Version:**
   Update `__version__ = "X.Y.Z"` in `audio_converter.py`.
   Ensure `README.md` references the updated version if applicable.

2. **Commit Changes:**
   Commit the version bump locally:
   ```bash
   git commit -am "chore: bump version to vX.Y.Z"
   ```

3. **Verify FFmpeg Lockfile:**
   Verify `packaging/ffmpeg.lock.json` has all 5 required fields populated with a pinned version, valid HTTPS download URL, SHA-256 checksum, license, and source code link.
   To compute the SHA-256 checksum of an FFmpeg archive:
   ```bash
   python packaging/download_ffmpeg.py --hash path/to/ffmpeg.zip
   ```

4. **Tag the Release:**
   Create an annotated git tag matching the version:
   ```bash
   git tag vX.Y.Z
   ```

5. **Push Tag to GitHub:**
   Ask the project owner for confirmation, then push the commit and tag:
   ```bash
   git push origin main
   git push origin vX.Y.Z
   ```

6. **Wait for GitHub Actions CI:**
   The `Build & release (Windows portable)` workflow will trigger automatically.
   It runs unit tests across platforms, stages FFmpeg, compiles with PyInstaller, runs full end-to-end smoke tests on all 7 codecs, packages the ZIP archive with checksums, and creates a **draft** release on GitHub.

7. **Review and Test the Draft Release:**
   - Download the generated `AudioConverter-vX.Y.Z-win64.zip` from the draft release.
   - Test on a clean Windows machine (e.g. Windows Sandbox):
     - Extract the full zip archive.
     - Double click `AudioConverter.exe` (confirm wizard opens).
     - Drag and drop an audio file onto `AudioConverter.exe`.
     - Test converting a track or album and verify metadata & album art.

8. **Publish Release:**
   Once verified, publish the draft release on GitHub.
