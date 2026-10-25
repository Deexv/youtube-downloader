"""Core download manager and yt-dlp integration.
Handles video and playlist extraction, ffmpeg stream merging, quality selection, and thread-safe progress tracking.
"""

import os
import shutil
import threading
import uuid
from typing import Any, Callable, Dict, List, Optional
import yt_dlp


def find_binary(name: str, common_paths: Optional[List[str]] = None) -> Optional[str]:
    """Find binary executable in PATH or fallback locations."""
    found = shutil.which(name)
    if found:
        return found
    if common_paths:
        for path in common_paths:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path
    return None


def get_ffmpeg_path() -> Optional[str]:
    """Locate ffmpeg binary."""
    return find_binary("ffmpeg", ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg"])


def get_node_path() -> Optional[str]:
    """Locate Node.js binary for JavaScript challenge solving."""
    home = os.path.expanduser("~")
    nvm_default = os.path.join(home, ".nvm/versions/node/v24.21.0/bin/node")
    return find_binary("node", [nvm_default, "/opt/homebrew/bin/node", "/usr/local/bin/node", "/usr/bin/node"])


def format_duration(seconds: Optional[int]) -> str:
    """Format duration in seconds to HH:MM:SS or MM:SS."""
    if seconds is None or seconds < 0:
        return "Unknown"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def get_base_ydl_opts() -> Dict[str, Any]:
    """Return common yt-dlp configuration options."""
    ffmpeg_bin = get_ffmpeg_path()
    node_bin = get_node_path()

    opts: Dict[str, Any] = {
        "quiet": True,
        "no_warnings": False,
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "ios", "web"]
            }
        },
        "remote_components": ["ejs:github"]
    }

    if ffmpeg_bin:
        opts["ffmpeg_location"] = os.path.dirname(ffmpeg_bin) if os.path.isabs(ffmpeg_bin) else ffmpeg_bin

    if node_bin:
        opts["js_runtimes"] = {
            "node": {"path": node_bin}
        }

    return opts


def extract_media_info(url: str, cookies_browser: Optional[str] = None) -> Dict[str, Any]:
    """
    Extract video or playlist information from a given URL without downloading.
    Returns normalized structure with entries and metadata.
    """
    opts = get_base_ydl_opts()
    opts["extract_flat"] = "in_playlist"
    opts["skip_download"] = True

    if cookies_browser:
        opts["cookiesfrombrowser"] = (cookies_browser,)

    with yt_dlp.YoutubeDL(opts) as ydl:
        raw_info = ydl.extract_info(url, download=False)

    if not raw_info:
        raise ValueError("No video or playlist found for this URL.")

    # Check if the result is a playlist
    is_playlist = raw_info.get("_type") == "playlist" or "entries" in raw_info

    entries: List[Dict[str, Any]] = []

    if is_playlist:
        raw_entries = raw_info.get("entries") or []
        for index, item in enumerate(raw_entries, start=1):
            if not item:
                continue
            entry_id = item.get("id") or str(index)
            video_url = item.get("url") or item.get("webpage_url")
            if not video_url and entry_id:
                video_url = f"https://www.youtube.com/watch?v={entry_id}"

            # Best available thumbnail
            thumbnail = item.get("thumbnail")
            if not thumbnail and item.get("thumbnails"):
                thumbnail = item["thumbnails"][-1].get("url")
            if not thumbnail and entry_id:
                thumbnail = f"https://i.ytimg.com/vi/{entry_id}/hqdefault.jpg"

            entries.append({
                "id": entry_id,
                "index": index,
                "title": item.get("title") or f"Video #{index}",
                "url": video_url,
                "duration": item.get("duration"),
                "duration_formatted": format_duration(item.get("duration")),
                "thumbnail": thumbnail or "",
                "channel": item.get("channel") or item.get("uploader") or "Unknown Channel",
            })

        return {
            "type": "playlist",
            "title": raw_info.get("title") or "YouTube Playlist",
            "id": raw_info.get("id") or "",
            "channel": raw_info.get("channel") or raw_info.get("uploader") or "Unknown Channel",
            "count": len(entries),
            "entries": entries,
        }

    # Single video
    video_id = raw_info.get("id") or ""
    video_url = raw_info.get("webpage_url") or url
    thumbnail = raw_info.get("thumbnail")
    if not thumbnail and raw_info.get("thumbnails"):
        thumbnail = raw_info["thumbnails"][-1].get("url")
    if not thumbnail and video_id:
        thumbnail = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"

    single_entry = {
        "id": video_id,
        "index": 1,
        "title": raw_info.get("title") or "YouTube Video",
        "url": video_url,
        "duration": raw_info.get("duration"),
        "duration_formatted": format_duration(raw_info.get("duration")),
        "thumbnail": thumbnail or "",
        "channel": raw_info.get("channel") or raw_info.get("uploader") or "Unknown Channel",
    }

    return {
        "type": "video",
        "title": raw_info.get("title") or "YouTube Video",
        "id": video_id,
        "channel": raw_info.get("channel") or raw_info.get("uploader") or "Unknown Channel",
        "count": 1,
        "entries": [single_entry],
    }


class DownloadCancelledException(Exception):
    """Raised when a download job is cancelled by the user."""
    pass


class DownloadJob:
    """Represents a download job for one or more videos."""

    def __init__(self, job_id: str, items: List[Dict[str, Any]], quality: str, output_dir: str):
        self.job_id = job_id
        self.items = items
        self.quality = quality
        self.output_dir = output_dir
        self.status = "queued"
        self.is_cancelled = False
        self.current_index = 0
        self.current_title = ""
        self.current_item_id = ""
        self.item_percent = 0.0
        self.total_percent = 0.0
        self.speed_str = ""
        self.eta_str = ""
        self.completed_items: List[str] = []
        self.failed_items: List[Dict[str, str]] = []
        self.status_message = "Waiting in queue"
        self.error_message: Optional[str] = None
        self.lock = threading.Lock()

    def cancel(self):
        with self.lock:
            self.is_cancelled = True
            self.status = "cancelled"
            self.status_message = "Cancelled by user"

    def to_dict(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "job_id": self.job_id,
                "status": self.status,
                "is_cancelled": self.is_cancelled,
                "total_items": len(self.items),
                "current_index": self.current_index,
                "current_title": self.current_title,
                "current_item_id": self.current_item_id,
                "item_percent": round(self.item_percent, 1),
                "total_percent": round(self.total_percent, 1),
                "speed": self.speed_str,
                "eta": self.eta_str,
                "completed_count": len(self.completed_items),
                "failed_count": len(self.failed_items),
                "failed_items": list(self.failed_items),
                "status_message": self.status_message,
                "error_message": self.error_message,
                "output_dir": self.output_dir,
            }


class DownloadManager:
    """Manages concurrent/sequential download jobs."""

    def __init__(self):
        self.jobs: Dict[str, DownloadJob] = {}
        self.lock = threading.Lock()

    def create_job(self, items: List[Dict[str, Any]], quality: str, output_dir: Optional[str] = None) -> DownloadJob:
        if not output_dir:
            home = os.path.expanduser("~")
            output_dir = os.path.join(home, "Downloads", "YouTubeDownloads")

        os.makedirs(output_dir, exist_ok=True)

        job_id = str(uuid.uuid4())
        job = DownloadJob(job_id, items, quality, output_dir)

        with self.lock:
            self.jobs[job_id] = job

        worker_thread = threading.Thread(target=self._run_job, args=(job,), daemon=True)
        worker_thread.start()

        return job

    def get_job(self, job_id: str) -> Optional[DownloadJob]:
        with self.lock:
            return self.jobs.get(job_id)

    def cancel_job(self, job_id: str) -> bool:
        job = self.get_job(job_id)
        if job:
            job.cancel()
            return True
        return False

    def _get_format_spec(self, quality: str) -> Dict[str, Any]:
        """Generate format string and postprocessors according to quality selection."""
        # Quality options:
        # 'best' -> best available video + best audio merged with ffmpeg
        # '2160' / '1440' / '1080' / '720' / '480' / '360' -> capped height + best audio merged
        # 'audio' -> extract audio only to mp3

        if quality == "audio":
            return {
                "format": "bestaudio/best",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
            }

        height_caps = {
            "2160": 2160,
            "1440": 1440,
            "1080": 1080,
            "720": 720,
            "480": 480,
            "360": 360,
        }

        if quality in height_caps:
            h = height_caps[quality]
            format_spec = f"bestvideo[height<={h}]+bestaudio/best[height<={h}]/best"
        else:
            format_spec = "bestvideo+bestaudio/best"

        return {
            "format": format_spec,
            "merge_output_format": "mp4",
        }

    def _run_job(self, job: DownloadJob):
        total_items = len(job.items)
        if total_items == 0:
            with job.lock:
                job.status = "completed"
                job.status_message = "No items to download"
            return

        with job.lock:
            job.status = "downloading"
            job.status_message = "Starting download..."

        format_spec = self._get_format_spec(job.quality)

        for idx, item in enumerate(job.items, start=1):
            if job.is_cancelled:
                break

            video_url = item.get("url")
            video_title = item.get("title", f"Video {idx}")
            video_id = item.get("id", str(idx))

            with job.lock:
                job.current_index = idx
                job.current_title = video_title
                job.current_item_id = video_id
                job.item_percent = 0.0
                job.status_message = f"Downloading item {idx} of {total_items}: {video_title}"

            def progress_hook(d: Dict[str, Any]):
                if job.is_cancelled:
                    raise DownloadCancelledException("Download cancelled by user.")

                status = d.get("status")
                if status == "downloading":
                    total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    downloaded = d.get("downloaded_bytes") or 0
                    percent = (downloaded / total_bytes * 100) if total_bytes > 0 else 0.0

                    speed = d.get("_speed_str") or ""
                    eta = d.get("_eta_str") or ""

                    with job.lock:
                        job.item_percent = percent
                        job.speed_str = speed
                        job.eta_str = eta
                        # Calculate total progress
                        completed_frac = (idx - 1) + (percent / 100.0)
                        job.total_percent = min(100.0, (completed_frac / total_items) * 100.0)
                        job.status_message = f"Downloading {idx}/{total_items}: {video_title} ({percent:.1f}%)"

                elif status == "finished":
                    with job.lock:
                        job.item_percent = 100.0
                        job.status_message = f"Processing audio & video stream merge for {video_title}..."

            def postprocessor_hook(d: Dict[str, Any]):
                if job.is_cancelled:
                    raise DownloadCancelledException("Download cancelled by user.")
                status = d.get("status")
                if status == "started":
                    with job.lock:
                        job.status_message = f"Merging video and audio via ffmpeg for: {video_title}..."
                elif status == "finished":
                    with job.lock:
                        job.status_message = f"Finished merging {video_title}."

            ydl_opts = get_base_ydl_opts()
            ydl_opts["progress_hooks"] = [progress_hook]
            ydl_opts["postprocessor_hooks"] = [postprocessor_hook]
            ydl_opts["outtmpl"] = os.path.join(job.output_dir, "%(title)s [%(id)s].%(ext)s")

            # Apply format specifications
            for k, v in format_spec.items():
                ydl_opts[k] = v

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([video_url])

                with job.lock:
                    job.completed_items.append(video_id)
                    completed_frac = float(idx)
                    job.total_percent = min(100.0, (completed_frac / total_items) * 100.0)

            except DownloadCancelledException:
                with job.lock:
                    job.status = "cancelled"
                    job.status_message = "Download cancelled by user"
                return

            except Exception as e:
                err_msg = str(e)
                # Remove ANSI escape color sequences if present
                if "\x1b" in err_msg:
                    import re
                    err_msg = re.sub(r"\x1b\[[0-9;]*m", "", err_msg)
                with job.lock:
                    job.failed_items.append({
                        "id": video_id,
                        "title": video_title,
                        "error": err_msg,
                    })

        with job.lock:
            if not job.is_cancelled:
                job.total_percent = 100.0
                job.item_percent = 100.0
                if len(job.failed_items) == 0:
                    job.status = "completed"
                    job.status_message = f"All {total_items} item(s) downloaded successfully."
                elif len(job.completed_items) > 0:
                    job.status = "completed"
                    job.status_message = f"Completed with warnings: {len(job.completed_items)} succeeded, {len(job.failed_items)} failed."
                else:
                    job.status = "error"
                    job.status_message = "All downloads failed."
                    job.error_message = job.failed_items[0]["error"] if job.failed_items else "Unknown error"
