# YouTube Video & Playlist Downloader (yt-dlp Web UI)

A lightweight local web interface and API for downloading YouTube videos and complete playlists. Built on Python, Flask, **yt-dlp**, and **FFmpeg** to merge high-resolution video streams with audio automatically.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://www.python.org/)
[![yt--dlp](https://img.shields.io/badge/Engine-yt--dlp-red.svg)](https://github.com/yt-dlp/yt-dlp)
[![FFmpeg](https://img.shields.io/badge/Muxer-FFmpeg-green.svg)](https://ffmpeg.org/)

## Features

- **Full Video and Playlist Support**. Paste any single video, playlist, or YouTube Short link to inspect titles, authors, durations, and thumbnails.
- **Selective Playlist Downloading**. Pick individual videos from playlists using checkboxes. Includes Select All and Deselect All controls with active count tracking.
- **Automatic Audio and Video Merging**. Merges separate video and audio streams into single `.mp4` files using FFmpeg.
- **Resolution Control**. Select preferred output resolution from 4K (2160p), 2K (1440p), 1080p Full HD, 720p HD, 480p, 360p, or Audio Only (MP3).
- **Accurate Download Size Estimates**. Shows estimated file size for each video and total batch size before you download. Updates instantly when switching qualities or toggling checkboxes.
- **Live Transfer Metrics**. Displays real-time download byte progress (e.g. `24.5 MB / 65.2 MB`), speed in MB/s, estimated time remaining, and current status.
- **Automated Resume and Network Recovery**. Uses HTTP range chunking (`http_chunk_size`). If a connection drops, it automatically retries and continues from the exact byte on disk.
- **Restart Persistence**. Detects partial downloads (`.part` files) on disk even if you close the browser or restart the server. Displays existing progress badges and resumes without restarting from zero.
- **Bot Check and Age Gate Bypass**. Employs multi-client negotiation (`web_embedded`, `tv_samsung`, `mweb`) and optional browser cookie import (`Chrome`, `Safari`, `Firefox`) to bypass verification prompts.
- **File Collision Handling**. Choose between auto-renaming duplicate files (`(1)`, `(2)`) or overwriting existing files.
- **Finder and File Manager Integration**. Includes a direct button to open the destination download folder in your operating system.

## Prerequisites

Before running the application, make sure you have:

1. **Python 3.10 or higher**. Check with `python3 --version`.
2. **FFmpeg**. Used to merge high-definition video and audio tracks.
   - On macOS: `brew install ffmpeg`
   - On Ubuntu or Debian: `sudo apt-get update && sudo apt-get install -y ffmpeg`
   - On Windows: `winget install Gyan.FFmpeg`
3. **Node.js** (optional but recommended). Allows yt-dlp to solve JavaScript signature challenges.

## Quickstart

### 1. Clone the repository

```bash
git clone https://github.com/Deexv/youtube-downloader.git
cd youtube-downloader
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Start the application

Run the startup script:

```bash
./start.sh
```

Or run directly using Python:

```bash
python3 run.py
```

The application starts on `http://127.0.0.1:5050` and automatically opens in your default web browser.

## How to Use

1. **Paste a Link**. Enter any YouTube video URL or playlist URL into the input field and click **Fetch Info**.
2. **Choose Resolution**. Use the dropdown to choose your desired quality (for example, `1080p Full HD + Combined Audio` or `4K Ultra HD`).
3. **Inspect File Sizes**. Review estimated file sizes on each video card. The total size updates dynamically as you select or deselect items.
4. **Configure Settings**. Choose your destination directory, duplicate handling preference, and optional browser cookies if downloading private or restricted videos.
5. **Download**. Click **Download Selected**. Track real-time progress, speed, and ETA. Click **Open Folder** to reveal your downloaded media once complete.

## API Reference

The server exposes a clean REST API:

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/` | `GET` | Serves the web interface. |
| `/api/config` | `GET` | Returns system paths and FFmpeg detection status. |
| `/api/fetch` | `POST` | Inspects a URL and returns video or playlist metadata with size maps. |
| `/api/download` | `POST` | Initiates a background download job for selected items. |
| `/api/status/<job_id>` | `GET` | Returns live progress, current item, transfer speed, and byte counts. |
| `/api/cancel/<job_id>` | `POST` | Cancels an ongoing download job. |
| `/api/open-folder` | `POST` | Opens the target destination directory in your system file manager. |

## Running Tests

Run the automated integration test suite:

```bash
python3 test_app.py
```

The tests verify:
- Application startup and configuration endpoints.
- Single video and playlist metadata parsing.
- Pre-download size mapping.
- Unfinished `.part` file detection on disk.
- Duplicate filename resolution.
- Download lifecycle and cancellation.

## Contributing

Contributions are welcome. Feel free to open an issue or submit a pull request.

1. Fork the repository.
2. Create your feature branch (`git checkout -b feature/new-capability`).
3. Commit your changes (`git commit -m "feat: add new capability"`).
4. Run tests to ensure all checks pass (`python3 test_app.py`).
5. Push to your branch (`git push origin feature/new-capability`).
6. Open a Pull Request.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
