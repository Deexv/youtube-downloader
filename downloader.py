"""Core download manager and yt-dlp integration.
Handles video and playlist extraction, ffmpeg stream merging, quality selection, size estimation, and thread-safe progress tracking.
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


def format_bytes(num_bytes: Optional[int]) -> str:
    """Format byte count to readable string with units (B, KB, MB, GB)."""
    if num_bytes is None or num_bytes <= 0:
        return "0 B"
    val = float(num_bytes)
    for unit in ["B", "KB", "MB", "GB"]:
        if val < 1024.0:
            return f"{val:.1f} {unit}" if unit != "B" else f"{int(val)} B"
        val /= 1024.0
    return f"{val:.2f} TB"


def estimate_quality_sizes_from_duration(duration: Optional[int]) -> Dict[str, int]:
    """
    Estimate file size in bytes for various qualities given video duration in seconds.
    Based on standard YouTube average video+audio bitrates.
    """
    if not duration or duration <= 0:
        return {}

    rates = {
        "2160": 1150000,
        "1440": 580000,
        "1080": 160000,
        "720": 98000,
        "480": 62000,
        "360": 42000,
        "audio": 16500,
        "best": 1150000,
    }

    return {q: int(rate * duration) for q, rate in rates.items()}


def compute_single_video_sizes(raw_info: Dict[str, Any], ydl: yt_dlp.YoutubeDL) -> Dict[str, int]:
    """
    Compute accurate or approximate file size for each quality setting from actual format stream metadata.
    """
    qualities = ["2160", "1440", "1080", "720", "480", "360", "audio", "best"]
    size_map: Dict[str, int] = {}
    duration = raw_info.get("duration") or 0

    for q in qualities:
        if q == "audio":
            fmt_str = "bestaudio/best"
        elif q == "best":
            fmt_str = "bestvideo+bestaudio/best"
        else:
            fmt_str = f"bestvideo[height<={q}]+bestaudio/best[height<={q}]/best"

        try:
            selector = ydl.build_format_selector(fmt_str)
            matched = list(selector(raw_info))
            total_bytes = 0
            for f in matched:
                sz = f.get("filesize") or f.get("filesize_approx")
                if not sz and duration > 0:
                    bitrate = f.get("tbr") or ((f.get("vbr") or 0) + (f.get("abr") or 0))
                    if bitrate:
                        sz = int((bitrate * 1024 / 8) * duration)
                total_bytes += (sz or 0)
            if total_bytes > 0:
                size_map[q] = total_bytes
        except Exception:
            pass

    return size_map


def get_base_ydl_opts() -> Dict[str, Any]:
    """Return common yt-dlp configuration options."""
    ffmpeg_bin = get_ffmpeg_path()
    node_bin = get_node_path()

    opts: Dict[str, Any] = {
        "quiet": True,
        "no_warnings": False,
        "remote_components": ["ejs:github"],
        "extractor_args": {
            "youtube": {
                "player_client": ["tv_samsung", "web", "web_embedded", "mweb"]
            }
        },
        "socket_timeout": 30,
        "retries": 20,
        "fragment_retries": 20,
        "file_access_retries": 5,
        "extractor_retries": 5,
        "continuedl": True,
        "nopart": False,
        "http_chunk_size": 10485760,
    }

    if ffmpeg_bin:
        opts["ffmpeg_location"] = os.path.dirname(ffmpeg_bin) if os.path.isabs(ffmpeg_bin) else ffmpeg_bin

    if node_bin:
        opts["js_runtimes"] = {
            "node": {"path": node_bin}
        }

    return opts


def check_existing_media_file(output_dir: str, title: str, video_id: str) -> Dict[str, Any]:
    """
    Check if a completed file or unfinished (.part / .ytdl) download exists in output_dir.
    """
    if not os.path.exists(output_dir):
        return {
            "has_partial": False,
            "partial_bytes": 0,
            "partial_formatted": "0 B",
            "is_completed": False,
            "completed_filename": "",
        }

    sanitized_title = yt_dlp.utils.sanitize_filename(title)
    base = f"{sanitized_title} [{video_id}]"

    try:
        all_files = os.listdir(output_dir)
    except Exception:
        all_files = []

    part_files = [f for f in all_files if f.startswith(base) and (f.endswith(".part") or f.endswith(".ytdl"))]
    completed_files = [f for f in all_files if f.startswith(base) and not f.endswith(".part") and not f.endswith(".ytdl")]

    part_bytes = sum(
        os.path.getsize(os.path.join(output_dir, pf))
        for pf in part_files
        if os.path.isfile(os.path.join(output_dir, pf))
    )

    return {
        "has_partial": len(part_files) > 0,
        "partial_bytes": part_bytes,
        "partial_formatted": format_bytes(part_bytes),
        "is_completed": len(completed_files) > 0,
        "completed_filename": completed_files[0] if completed_files else "",
    }


def extract_media_info(url: str, cookies_browser: Optional[str] = None, output_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Extract video or playlist information from a given URL without downloading.
    Returns normalized structure with entries, thumbnails, duration, size maps, and partial/resume status.
    """
    if not output_dir:
        output_dir = os.path.join(os.path.expanduser("~"), "Downloads", "YouTubeDownloads")

    opts = get_base_ydl_opts()
    opts["extract_flat"] = "in_playlist"
    opts["skip_download"] = True

    if cookies_browser:
        opts["cookiesfrombrowser"] = (cookies_browser,)

    with yt_dlp.YoutubeDL(opts) as ydl:
        raw_info = ydl.extract_info(url, download=False)

    if not raw_info:
        raise ValueError("No video or playlist found for this URL.")

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

            thumbnail = item.get("thumbnail")
            if not thumbnail and item.get("thumbnails"):
                thumbnail = item["thumbnails"][-1].get("url")
            if not thumbnail and entry_id:
                thumbnail = f"https://i.ytimg.com/vi/{entry_id}/hqdefault.jpg"

            duration = item.get("duration")
            estimated_sizes = estimate_quality_sizes_from_duration(duration)
            formatted_sizes = {q: format_bytes(sz) for q, sz in estimated_sizes.items()}

            item_title = item.get("title") or f"Video #{index}"
            file_status = check_existing_media_file(output_dir, item_title, entry_id)

            entries.append({
                "id": entry_id,
                "index": index,
                "title": item_title,
                "url": video_url,
                "duration": duration,
                "duration_formatted": format_duration(duration),
                "thumbnail": thumbnail or "",
                "channel": item.get("channel") or item.get("uploader") or "Unknown Channel",
                "sizes": estimated_sizes,
                "sizes_formatted": formatted_sizes,
                "has_partial": file_status["has_partial"],
                "partial_bytes": file_status["partial_bytes"],
                "partial_formatted": file_status["partial_formatted"],
                "is_completed": file_status["is_completed"],
                "completed_filename": file_status["completed_filename"],
            })

        return {
            "type": "playlist",
            "title": raw_info.get("title") or "YouTube Playlist",
            "id": raw_info.get("id") or "",
            "channel": raw_info.get("channel") or raw_info.get("uploader") or "Unknown Channel",
            "count": len(entries),
            "entries": entries,
        }

    # Single video with exact format inspection
    video_id = raw_info.get("id") or ""
    video_url = raw_info.get("webpage_url") or url
    thumbnail = raw_info.get("thumbnail")
    if not thumbnail and raw_info.get("thumbnails"):
        thumbnail = raw_info["thumbnails"][-1].get("url")
    if not thumbnail and video_id:
        thumbnail = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"

    duration = raw_info.get("duration")

    with yt_dlp.YoutubeDL(opts) as ydl:
        exact_sizes = compute_single_video_sizes(raw_info, ydl)

    if not exact_sizes and duration:
        exact_sizes = estimate_quality_sizes_from_duration(duration)

    formatted_sizes = {q: format_bytes(sz) for q, sz in exact_sizes.items()}
    video_title = raw_info.get("title") or "YouTube Video"
    file_status = check_existing_media_file(output_dir, video_title, video_id)

    single_entry = {
        "id": video_id,
        "index": 1,
        "title": video_title,
        "url": video_url,
        "duration": duration,
        "duration_formatted": format_duration(duration),
        "thumbnail": thumbnail or "",
        "channel": raw_info.get("channel") or raw_info.get("uploader") or "Unknown Channel",
        "sizes": exact_sizes,
        "sizes_formatted": formatted_sizes,
        "has_partial": file_status["has_partial"],
        "partial_bytes": file_status["partial_bytes"],
        "partial_formatted": file_status["partial_formatted"],
        "is_completed": file_status["is_completed"],
        "completed_filename": file_status["completed_filename"],
    }

    return {
        "type": "video",
        "title": video_title,
        "id": video_id,
        "channel": raw_info.get("channel") or raw_info.get("uploader") or "Unknown Channel",
        "count": 1,
        "entries": [single_entry],
    }


def check_existing_media_file(output_dir: str, title: str, video_id: str) -> Dict[str, Any]:
    """
    Check if a completed file or unfinished (.part / .ytdl) download exists in output_dir.
    """
    if not os.path.exists(output_dir):
        return {
            "has_partial": False,
            "partial_bytes": 0,
            "partial_formatted": "0 B",
            "is_completed": False,
            "completed_filename": "",
        }

    sanitized_title = yt_dlp.utils.sanitize_filename(title)
    base = f"{sanitized_title} [{video_id}]"

    try:
        all_files = os.listdir(output_dir)
    except Exception:
        all_files = []

    part_files = [f for f in all_files if f.startswith(base) and (f.endswith(".part") or f.endswith(".ytdl"))]
    completed_files = [f for f in all_files if f.startswith(base) and not f.endswith(".part") and not f.endswith(".ytdl")]

    part_bytes = sum(
        os.path.getsize(os.path.join(output_dir, pf))
        for pf in part_files
        if os.path.isfile(os.path.join(output_dir, pf))
    )

    return {
        "has_partial": len(part_files) > 0,
        "partial_bytes": part_bytes,
        "partial_formatted": format_bytes(part_bytes),
        "is_completed": len(completed_files) > 0,
        "completed_filename": completed_files[0] if completed_files else "",
    }


def resolve_output_template(output_dir: str, title: str, video_id: str, on_duplicate: str) -> str:
    """
    Generate an output template path.
    Only COMPLETED files (excluding temporary .part and .ytdl files) count as duplicates.
    If an unfinished download (.part file) exists, it targets the same template to resume seamlessly.
    """
    if on_duplicate == "auto_rename" and os.path.exists(output_dir):
        sanitized_title = yt_dlp.utils.sanitize_filename(title)
        base = f"{sanitized_title} [{video_id}]"
        existing_completed = [
            f for f in os.listdir(output_dir)
            if f.startswith(base) and not f.endswith(".part") and not f.endswith(".ytdl")
        ]
        if existing_completed:
            counter = 1
            while any(f.startswith(f"{base} ({counter})") and not f.endswith(".part") and not f.endswith(".ytdl") for f in existing_completed):
                counter += 1
            return os.path.join(output_dir, f"%(title)s [%(id)s] ({counter}).%(ext)s")
    return os.path.join(output_dir, "%(title)s [%(id)s].%(ext)s")


class DownloadCancelledException(Exception):
    """Raised when a download job is cancelled by the user."""
    pass


class DownloadJob:
    """Represents a download job for one or more videos."""

    def __init__(self, job_id: str, items: List[Dict[str, Any]], quality: str, output_dir: str, on_duplicate: str = "auto_rename", cookies_browser: Optional[str] = None):
        self.job_id = job_id
        self.items = items
        self.quality = quality
        self.output_dir = output_dir
        self.on_duplicate = on_duplicate
        self.cookies_browser = cookies_browser
        self.status = "queued"
        self.is_cancelled = False
        self.current_index = 0
        self.current_title = ""
        self.current_item_id = ""
        self.item_percent = 0.0
        self.total_percent = 0.0
        self.speed_str = ""
        self.eta_str = ""
        self.item_downloaded_bytes = 0
        self.item_total_bytes = 0
        self.item_downloaded_str = "0 B"
        self.item_total_str = "0 B"
        self.size_progress_str = ""
        self.batch_completed_bytes = 0
        self.batch_total_bytes = 0
        self.batch_size_str = ""
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
                "item_downloaded_bytes": self.item_downloaded_bytes,
                "item_total_bytes": self.item_total_bytes,
                "item_downloaded_str": self.item_downloaded_str,
                "item_total_str": self.item_total_str,
                "size_progress": self.size_progress_str,
                "batch_size_str": self.batch_size_str,
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

    def create_job(self, items: List[Dict[str, Any]], quality: str, output_dir: Optional[str] = None, on_duplicate: str = "auto_rename", cookies_browser: Optional[str] = None) -> DownloadJob:
        if not output_dir:
            home = os.path.expanduser("~")
            output_dir = os.path.join(home, "Downloads", "YouTubeDownloads")

        os.makedirs(output_dir, exist_ok=True)

        job_id = str(uuid.uuid4())
        job = DownloadJob(job_id, items, quality, output_dir, on_duplicate=on_duplicate, cookies_browser=cookies_browser)

        est_total = 0
        for itm in items:
            sizes = itm.get("sizes") or {}
            est_total += sizes.get(quality, sizes.get("best", 0))
        job.batch_total_bytes = est_total

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

            existing_info = check_existing_media_file(job.output_dir, video_title, video_id)
            is_resuming = existing_info["has_partial"]

            with job.lock:
                job.current_index = idx
                job.current_title = video_title
                job.current_item_id = video_id
                job.item_percent = 0.0
                job.item_downloaded_bytes = existing_info["partial_bytes"]
                job.item_total_bytes = 0
                job.item_downloaded_str = existing_info["partial_formatted"]
                job.item_total_str = "0 B"
                job.size_progress_str = (
                    f"Resuming from {existing_info['partial_formatted']}..."
                    if is_resuming
                    else "Preparing..."
                )
                job.status_message = (
                    f"Resuming unfinished download ({existing_info['partial_formatted']} on disk) for: {video_title}"
                    if is_resuming
                    else f"Downloading item {idx} of {total_items}: {video_title}"
                )

            stream_state = {
                "completed_stream_bytes": 0,
                "current_stream_total": 0,
            }

            def progress_hook(d: Dict[str, Any]):
                if job.is_cancelled:
                    raise DownloadCancelledException("Download cancelled by user.")

                status = d.get("status")
                if status == "downloading":
                    stream_downloaded = d.get("downloaded_bytes") or 0
                    stream_total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    stream_state["current_stream_total"] = stream_total

                    total_item_downloaded = stream_state["completed_stream_bytes"] + stream_downloaded
                    total_item_expected = stream_state["completed_stream_bytes"] + stream_total

                    percent = (stream_downloaded / stream_total * 100) if stream_total > 0 else 0.0
                    speed = d.get("_speed_str") or ""
                    eta = d.get("_eta_str") or ""

                    downloaded_str = format_bytes(total_item_downloaded)
                    expected_str = format_bytes(total_item_expected) if total_item_expected > 0 else "estimating..."

                    size_prog = f"{downloaded_str} / {expected_str}"

                    with job.lock:
                        job.item_percent = percent
                        job.speed_str = speed
                        job.eta_str = eta
                        job.item_downloaded_bytes = total_item_downloaded
                        job.item_total_bytes = total_item_expected
                        job.item_downloaded_str = downloaded_str
                        job.item_total_str = expected_str
                        job.size_progress_str = size_prog

                        completed_frac = (idx - 1) + (percent / 100.0)
                        job.total_percent = min(100.0, (completed_frac / total_items) * 100.0)
                        job.status_message = f"Downloading {idx}/{total_items}: {video_title} ({size_prog})"

                elif status == "finished":
                    stream_state["completed_stream_bytes"] += stream_state["current_stream_total"]
                    with job.lock:
                        job.item_percent = 100.0
                        total_done_str = format_bytes(stream_state["completed_stream_bytes"])
                        job.size_progress_str = f"{total_done_str} (downloaded)"
                        job.status_message = f"Processing audio & video stream merge for {video_title} ({total_done_str})..."

            def postprocessor_hook(d: Dict[str, Any]):
                if job.is_cancelled:
                    raise DownloadCancelledException("Download cancelled by user.")
                status = d.get("status")
                if status == "started":
                    with job.lock:
                        job.status_message = f"Merging video and audio via FFmpeg ({job.item_total_str}) for: {video_title}..."
                elif status == "finished":
                    with job.lock:
                        job.status_message = f"Finished merging {video_title}."

            target_outtmpl = resolve_output_template(
                job.output_dir,
                video_title,
                video_id,
                job.on_duplicate,
            )

            ydl_opts = get_base_ydl_opts()
            ydl_opts["overwrites"] = True
            ydl_opts["continuedl"] = True
            ydl_opts["nopart"] = False
            ydl_opts["progress_hooks"] = [progress_hook]
            ydl_opts["postprocessor_hooks"] = [postprocessor_hook]
            ydl_opts["outtmpl"] = target_outtmpl

            if job.cookies_browser:
                ydl_opts["cookiesfrombrowser"] = (job.cookies_browser,)

            for k, v in format_spec.items():
                ydl_opts[k] = v

            max_retries = 5
            download_succeeded = False
            last_err_msg = ""

            for attempt in range(1, max_retries + 1):
                if job.is_cancelled:
                    break
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([video_url])
                    download_succeeded = True
                    break
                except DownloadCancelledException:
                    with job.lock:
                        job.status = "cancelled"
                        job.status_message = "Download cancelled by user"
                    return
                except Exception as e:
                    last_err_msg = str(e)
                    if "\x1b" in last_err_msg:
                        import re
                        last_err_msg = re.sub(r"\x1b\[[0-9;]*m", "", last_err_msg)

                    is_bot_check = (
                        "confirm you’re not a bot" in last_err_msg
                        or "confirm you're not a bot" in last_err_msg
                        or "Sign in" in last_err_msg
                        or "Please sign in" in last_err_msg
                    )

                    if is_bot_check:
                        # Auto-switch to alternate client profile on retry
                        ydl_opts["extractor_args"] = {
                            "youtube": {
                                "player_client": ["web_embedded", "mweb", "android"]
                            }
                        }

                    if attempt < max_retries and not job.is_cancelled:
                        import time
                        wait_seconds = min(2 * attempt, 6)
                        notice = (
                            f"YouTube bot challenge detected. Bypassing and resuming in {wait_seconds}s (attempt {attempt}/{max_retries})..."
                            if is_bot_check
                            else f"Connection interrupted ({last_err_msg}). Resuming download from where it left off in {wait_seconds}s (attempt {attempt}/{max_retries})..."
                        )
                        with job.lock:
                            job.status_message = notice
                        time.sleep(wait_seconds)
                    else:
                        break

            if download_succeeded:
                with job.lock:
                    job.completed_items.append(video_id)
                    job.batch_completed_bytes += stream_state["completed_stream_bytes"]
                    completed_frac = float(idx)
                    job.total_percent = min(100.0, (completed_frac / total_items) * 100.0)
            elif not job.is_cancelled:
                with job.lock:
                    job.failed_items.append({
                        "id": video_id,
                        "title": video_title,
                        "error": last_err_msg or "Download failed after multiple retries",
                    })

        with job.lock:
            if not job.is_cancelled:
                job.total_percent = 100.0
                job.item_percent = 100.0
                total_downloaded_str = format_bytes(job.batch_completed_bytes)
                if len(job.failed_items) == 0:
                    job.status = "completed"
                    job.status_message = f"All {total_items} item(s) downloaded successfully ({total_downloaded_str} total)."
                elif len(job.completed_items) > 0:
                    job.status = "completed"
                    job.status_message = f"Completed with warnings: {len(job.completed_items)} succeeded ({total_downloaded_str}), {len(job.failed_items)} failed."
                else:
                    job.status = "error"
                    job.status_message = "All downloads failed."
                    job.error_message = job.failed_items[0]["error"] if job.failed_items else "Unknown error"
