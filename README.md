<div align="center">

<img src="app_icon.png" alt="Argus Studio Logo" width="120" height="120" />

# 🎬 Argus Studio Pro
### *The Ultimate YouTube Video & Audio Downloader Suite for Windows*

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![UI](https://img.shields.io/badge/GUI-CustomTkinter-blueviolet.svg)](https://github.com/TomSchimansky/CustomTkinter)
[![Core Engine](https://img.shields.io/badge/Engine-yt--dlp-red.svg?logo=youtube&logoColor=white)](https://github.com/yt-dlp/yt-dlp)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%2F%2011-0078D6.svg?logo=windows&logoColor=white)](https://microsoft.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Argus Studio** is a powerhouse desktop media downloader engineered specifically to solve modern YouTube downloading restrictions, bot detection barriers, and file-locking bottlenecks on Windows.

[Key Features](#-key-features) • [Why Argus Studio?](#-why-argus-studio) • [Installation & Usage](#-installation--usage) • [Building from Source](#-building-from-source) • [License](#-license)

</div>

---

## 🎯 The Core Problem: Downloading YouTube Videos in 2026

Modern YouTube updates have made video downloading notoriously unreliable for standard tools:
* ⚠️ **JavaScript Challenges & Bot Detection**: YouTube frequently blocks requests with errors like `"Sign in to confirm you're not a bot"` or `"This video is not available"`.
* ⚠️ **Complex Streams (DASH/SABR)**: High-resolution streams (1080p, 1440p, 4K, 8K) separate audio and video tracks, requiring precise on-the-fly muxing.
* ⚠️ **Windows File Rename Locks (`[WinError 32]`)**: Antivirus and Windows Search Indexers lock `.part` files right as downloads finish, crashing downloaders during rename operations.
* ⚠️ **Browser Cookie Conflicts**: Active browser sessions lock SQLite cookie databases, preventing tools from reading session tokens.

### 🛡️ How Argus Studio Solves This:
1. **Automated JavaScript Challenge Solving**: Integrates Node.js execution and dynamic challenge solving (`remote_components: {'ejs:github'}`) to bypass bot challenges natively.
2. **Direct-to-File Stream Architecture**: Employs `nopart: True` with progressive retry guards (`file_access_retries: 10`) to eliminate Windows Defender file-locking errors completely.
3. **Fail-Safe Cookie Extraction**: Automatically strips locked database handles and falls back seamlessly to public stream endpoints without interrupting your queue.

---

## ✨ Key Features

### 🎥 High-Resolution YouTube Video Downloading
- Download single videos, YouTube Shorts, or full channels.
- Select from **Best Available**, **4K (2160p)**, **1440p (2K)**, **1080p (Full HD)**, **720p (HD)**, **480p**, or **360p**.
- Clean container packaging into **MP4** or **MKV**.

### 🎵 Audiophile MP3 & Audio Extraction with ID3 Cover Art
- Extract studio-quality audio: **MP3 (320 kbps)**, **MP3 (192 kbps)**, **M4A (AAC)**, **FLAC (Lossless)**, or **WAV**.
- Automatically fetches video thumbnails and embeds them directly as **front album cover art** into the audio file.
- Automatically writes full **ID3 tags** (Artist, Title, Album, Year) using Mutagen.

### 📂 Interactive YouTube Playlist & Channel Inspector
- Paste any YouTube playlist or channel link and click **📂 Playlist**.
- View complete video lists with thumbnails, durations, and titles.
- Select/deselect individual tracks, select all, and enable **Sequential Track Numbering** (`01 - Video Title.mp4`).

### ✂️ Precision Timestamp & Section Trimmer
- Download only the specific segment of a video you need without downloading gigabytes of unwanted footage.
- Enter **Start Time** and **End Time** (e.g. `00:01:30` to `00:04:15`) to extract the exact clip directly from the YouTube stream.

### 💬 YouTube Subtitles & Closed Captions (CC)
- Fetch official subtitles or YouTube auto-generated captions.
- Select languages: **English**, **Spanish**, **French**, **German**, or **All Languages**.
- Option to **embed subtitles** directly into the MP4 video container or export as standalone `.srt` files.

### 📋 Smart Clipboard Auto-Detector
- Detects when you copy a YouTube link anywhere in Windows (`youtube.com/watch`, `youtu.be/`, `shorts/`, `playlist`).
- Displays a quick, non-intrusive *"Load YouTube Link"* banner directly inside the app.

### 🚀 Multi-Threaded Background Queue
- Concurrent download queue with configurable worker pool (1 to 5 concurrent jobs).
- Live progress indicators showing **percentage, transfer speed (MB/s), downloaded bytes, and ETA**.
- Global **Bandwidth Limiter** (Unlimited, 1 MB/s, 2 MB/s, 5 MB/s, 10 MB/s).

### 📁 Built-in Media Library
- Automatically tracks all finished downloads.
- Quick action buttons to **▶ Play** directly in your default media player, **📂 Show in Explorer**, or remove entries.

---

## 🚀 Installation & Usage

### Option 1: Windows Installer (Recommended)
Download and run the setup wizard (`ArgusStudio-Setup.exe`) from the repository releases:
- Automatically installs to `AppData\Local\Programs\ArgusStudio`.
- Creates desktop shortcuts and Start Menu entries.
- Includes a clean uninstaller.

### Option 2: Standalone Portable Executable
1. Download `ArgusStudio.exe`.
2. Place it in any folder and run it directly. No installation or Python setup required!

---

## 🛠️ Building from Source

### Prerequisites
- **Python 3.10+**
- **Node.js** (required for solving YouTube JavaScript challenges)
- **FFmpeg** (recommended for video/audio merging and ID3 conversion)

### Setup
```bash
# 1. Clone the repository
git clone https://github.com/ChimbuezeDavid/argus-studio.git
cd argus-studio

# 2. Install dependencies
pip install -r requirements.txt

# 3. Launch the application
python app.py
```

### Packaging into Standalone .exe
```bash
# Run the automated build script
build_exe.bat
```
This produces `dist\ArgusStudio.exe` bundled with all CustomTkinter theme assets, Mutagen ID3 hooks, and windowed launcher flags.

### Compiling the Windows Installer
If you have [Inno Setup 6](https://jrsoftware.org/isdl.php) installed:
```bash
iscc installer.iss
```
This generates `dist\ArgusStudio-Setup.exe`.

---

## 📋 Technical Architecture

| Component | Technology | Responsibility |
| :--- | :--- | :--- |
| **GUI Framework** | `customtkinter` | Modern dark-mode responsive desktop interface |
| **Download Engine** | `yt-dlp` | Video/Audio extraction, stream muxing, challenge resolution |
| **JS Runtime** | `Node.js` | Headless execution of YouTube player challenge scripts |
| **Audio Tagging** | `mutagen` | ID3v2.3 tag writing & high-res APIC cover art embedding |
| **Queue Manager** | Python `threading` & `Queue` | Asynchronous multi-worker download queue |
| **Packaging** | `PyInstaller` & `Inno Setup` | Single-binary executable & Windows setup wizard |

---

## 📄 License

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for more details.

---

<div align="center">
Developed by <b>Chimbueze David Okoroji</b> • Star ⭐ this repository if Argus Studio helped you!
</div>
