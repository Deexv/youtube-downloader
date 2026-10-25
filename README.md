# YouTube Video & Playlist Downloader

A simple, modern local web UI for downloading YouTube videos and playlists with video and audio streams merged using **yt-dlp** and **FFmpeg**.

## The Tool You Were Looking For

The tool that downloads YouTube videos and uses **FFmpeg** to merge audio and video tracks is **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** (the actively maintained successor to `youtube-dl`).

When YouTube serves 1080p, 2K, and 4K resolutions, it separates the video stream and audio stream into independent tracks. **yt-dlp** downloads both streams and calls **FFmpeg** to combine them into a single high-quality `.mp4` file.

## Features

- **Single Videos & Playlists**: Paste any video link or playlist link.
- **Selective Downloads**: Easily check or uncheck individual videos in a playlist before downloading, with "Select All" and "Deselect All" options.
- **Audio Combined with Video**: Automatically muxes video and audio streams into standard MP4 via FFmpeg.
- **Quality Selector**: Dropdown to select desired video resolution:
  - Best Available (Highest resolution)
  - 4K Ultra HD (2160p)
  - 2K Quad HD (1440p)
  - 1080p Full HD
  - 720p HD
  - 480p SD
  - 360p
  - Audio Only (MP3)
- **Live Progress & Stats**: Real-time progress bar, transfer speed, ETA, and current item status.
- **Download Destination**: Customizable save location with a one-click button to open the directory in Finder.
- **Cancel Support**: Abort active downloads at any time.

## Prerequisites

1. **Python 3**
2. **FFmpeg**: Installed at `/opt/homebrew/bin/ffmpeg` (or via `brew install ffmpeg`)
3. Dependencies: `yt-dlp` and `flask` (install with `pip install -r requirements.txt`)

## How to Run

Run the startup script:

```bash
./start.sh
```

Or run directly with Python:

```bash
python3 run.py
```

The application will start on `http://127.0.0.1:5050` and automatically open your default web browser.
