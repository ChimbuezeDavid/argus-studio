# Argus Studio Pro - Standalone Media & Batch Suite

A modern desktop application built on top of `yt-dlp`, `customtkinter`, and Node.js for Windows.

## Standalone Executable (.exe)

A fully packaged, single-file Windows executable is available in the `dist` directory:

- **Path**: `dist\ArgusStudio.exe`
- **Features**:
  - Completely standalone (does not require terminal or python commands).
  - Clean windowed mode (`--noconsole`).
  - All theme assets, fonts, Mutagen ID3 tagging, and extractors bundled.

### To Re-build the Executable:

Double-click **`build_exe.bat`**.

---

## Pro Features & Capabilities

1. **🎵 Audio Perfection (ID3 Tagging & Album Art)**:
   - High-fidelity audio extraction: **MP3 (320 kbps)**, **MP3 (192 kbps)**, **M4A (AAC)**, **FLAC (Lossless)**, **WAV**.
   - Embeds thumbnail directly as album cover art via `mutagen`.
   - Embeds complete metadata (Artist, Album, Title, Year) into ID3 tags.
2. **📂 Interactive Playlist & Channel Picker**:
   - Paste any playlist or channel link and click **📂 Playlist**.
   - Inspects all entries and lets you check/uncheck videos, with sequential track numbering (`01 - Title.mp4`, `02 - Title.mp4`).
3. **💬 Subtitles & Closed Captions (CC)**:
   - Download official or auto-generated subtitles.
   - Choose language (`English`, `Spanish`, `French`, `German`, or `All`).
   - Embed directly into the MP4 container or save as `.srt`.
4. **✂️ Timestamp / Section Clipper**:
   - Enter Start and End timestamps (e.g. `00:01:30` to `00:04:15`) to download only that exact clip.
5. **📋 Smart Clipboard Auto-Detector**:
   - Automatically detects when you copy a video link in Windows and presents a quick *"Load Link"* toast banner in the app.
6. **🚀 Bandwidth / Speed Limiter**:
   - Set download speed ceiling (`Unlimited`, `1 MB/s`, `2 MB/s`, `5 MB/s`, `10 MB/s`).
7. **📋 Multi-Download Background Queue**:
   - Multi-threaded worker pool with individual progress bars, live transfer speed, byte counters, and ETA.
8. **📁 Downloaded Media Library**:
   - Persistent history with one-click **▶ Play**, **📂 Show in Explorer**, and **🗑️ Clear Library** controls.
9. **🛡️ Windows Defender & Lock Shield**:
   - Direct-to-file writing (`nopart: True`) eliminates `[WinError 32]` file rename locks.
   - Automatic cookie-lock fallback prevents crashes if browser profiles are open.
