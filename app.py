"""Web server and REST API for the YouTube Video & Playlist Downloader.
Integrates with yt-dlp and ffmpeg for audio/video stream combining and quality control.
"""

import os
import subprocess
import sys
from flask import Flask, jsonify, render_template, request
from downloader import DownloadManager, extract_media_info, get_ffmpeg_path

app = Flask(__name__)
download_manager = DownloadManager()

DEFAULT_DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "YouTubeDownloads")


@app.route("/")
def index():
    ffmpeg_available = get_ffmpeg_path() is not None
    return render_template(
        "index.html",
        default_dir=DEFAULT_DOWNLOAD_DIR,
        ffmpeg_available=ffmpeg_available,
    )


@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify({
        "default_dir": DEFAULT_DOWNLOAD_DIR,
        "ffmpeg_path": get_ffmpeg_path(),
        "ffmpeg_available": get_ffmpeg_path() is not None,
    })


@app.route("/api/fetch", methods=["POST"])
def fetch_info():
    data = request.get_json(force=True, silent=True) or {}
    url = (data.get("url") or "").strip()
    cookies_browser = data.get("cookies_browser")
    output_dir = (data.get("output_dir") or "").strip() or DEFAULT_DOWNLOAD_DIR

    if not url:
        return jsonify({"success": False, "error": "Please provide a YouTube video or playlist URL."}), 400

    try:
        info = extract_media_info(url, cookies_browser=cookies_browser, output_dir=output_dir)
        return jsonify({"success": True, "data": info})
    except Exception as e:
        error_msg = str(e)
        if "\x1b" in error_msg:
            import re
            error_msg = re.sub(r"\x1b\[[0-9;]*m", "", error_msg)
        return jsonify({"success": False, "error": error_msg}), 500


@app.route("/api/download", methods=["POST"])
def start_download():
    data = request.get_json(force=True, silent=True) or {}
    items = data.get("items") or []
    quality = data.get("quality") or "best"
    output_dir = (data.get("output_dir") or "").strip() or DEFAULT_DOWNLOAD_DIR
    on_duplicate = data.get("on_duplicate") or "auto_rename"

    if not items:
        return jsonify({"success": False, "error": "No videos selected for download."}), 400

    job = download_manager.create_job(
        items=items,
        quality=quality,
        output_dir=output_dir,
        on_duplicate=on_duplicate,
    )
    return jsonify({
        "success": True,
        "job_id": job.job_id,
        "output_dir": job.output_dir,
        "total_items": len(items),
    })


@app.route("/api/status/<job_id>", methods=["GET"])
def job_status(job_id):
    job = download_manager.get_job(job_id)
    if not job:
        return jsonify({"success": False, "error": "Job not found"}), 404
    return jsonify({"success": True, "data": job.to_dict()})


@app.route("/api/cancel/<job_id>", methods=["POST"])
def cancel_job(job_id):
    cancelled = download_manager.cancel_job(job_id)
    return jsonify({"success": cancelled})


@app.route("/api/open-folder", methods=["POST"])
def open_folder():
    data = request.get_json(force=True, silent=True) or {}
    folder_path = (data.get("path") or "").strip() or DEFAULT_DOWNLOAD_DIR

    if not os.path.exists(folder_path):
        os.makedirs(folder_path, exist_ok=True)

    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", folder_path])
        elif sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", folder_path])
        elif sys.platform == "win32":
            os.startfile(folder_path)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(host="127.0.0.1", port=port, debug=False)
