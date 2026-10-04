# Release Notes

## Windows Portable App
- Zero-installation portable distribution for Windows 10/11 (64-bit).
- Download `AudioConverter-vX.Y.Z-win64.zip` and extract the entire archive.
- Double-click `AudioConverter.exe` or drag and drop files/folders onto it.
- Bundles FFmpeg and Python runtime internally.

## Security & SmartScreen Notice
This release is unsigned. When first running on Windows, SmartScreen may show a prompt:
Click **More info** -> **Run anyway**.

## Verification
Verify the download using the provided SHA-256 checksum:
```powershell
Get-FileHash .\AudioConverter-vX.Y.Z-win64.zip
```
Compare the output against `AudioConverter-vX.Y.Z-win64.zip.sha256`.

## Licensing
Audio Converter is licensed under the GPL-2.0-or-later license. Third-party licenses and source notices are included in the `LICENSES/` folder.
