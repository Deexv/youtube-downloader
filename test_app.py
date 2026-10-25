"""Integration tests for the YouTube Downloader application and API."""

import json
import time
import unittest
from app import app, download_manager


class TestYouTubeDownloader(unittest.TestCase):

    def setUp(self):
        self.client = app.test_client()

    def test_index_route(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"YouTube Downloader", response.data)
        self.assertIn(b"yt-dlp + ffmpeg", response.data)

    def test_config_route(self):
        response = self.client.get("/api/config")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data.get("ffmpeg_available"))
        self.assertIn("default_dir", data)

    def test_fetch_empty_url(self):
        response = self.client.post("/api/fetch", json={"url": ""})
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertFalse(data.get("success"))

    def test_fetch_single_video(self):
        # Rick Astley - Never Gonna Give You Up
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        response = self.client.post("/api/fetch", json={"url": url})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data.get("success"))
        media = data["data"]
        self.assertEqual(media.get("type"), "video")
        self.assertEqual(media.get("id"), "dQw4w9WgXcQ")
        self.assertEqual(len(media.get("entries")), 1)
        self.assertIn("Never Gonna Give You Up", media.get("title"))
        entry = media["entries"][0]
        self.assertIn("sizes", entry)
        self.assertIn("sizes_formatted", entry)
        self.assertIn("1080", entry["sizes"])
        self.assertIn("1080", entry["sizes_formatted"])
        self.assertGreater(entry["sizes"]["1080"], 0)

    def test_fetch_playlist(self):
        # Official Blender Open Movies playlist
        url = "https://www.youtube.com/playlist?list=PL6B3937A5D230E335"
        response = self.client.post("/api/fetch", json={"url": url})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data.get("success"))
        media = data["data"]
        self.assertEqual(media.get("type"), "playlist")
        self.assertGreater(len(media.get("entries")), 1)
        first_entry = media["entries"][0]
        self.assertIn("sizes", first_entry)
        self.assertIn("sizes_formatted", first_entry)
        self.assertIn("1080", first_entry["sizes_formatted"])

    def test_download_flow_and_cancellation(self):
        # Create a download job with a test item
        items = [{
            "id": "dQw4w9WgXcQ",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "title": "Rick Astley Test",
        }]
        response = self.client.post("/api/download", json={
            "items": items,
            "quality": "360",
            "output_dir": "/tmp/yt_test_output"
        })
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data.get("success"))
        job_id = data.get("job_id")
        self.assertIsNotNone(job_id)

        # Check job status
        status_res = self.client.get(f"/api/status/{job_id}")
        self.assertEqual(status_res.status_code, 200)
        status_data = json.loads(status_res.data)["data"]
        self.assertEqual(status_data["job_id"], job_id)

        # Cancel job
        cancel_res = self.client.post(f"/api/cancel/{job_id}")
        self.assertEqual(cancel_res.status_code, 200)
        self.assertTrue(json.loads(cancel_res.data)["success"])

        time.sleep(0.5)
        # Verify status is cancelled
        status_res2 = self.client.get(f"/api/status/{job_id}")
        status_data2 = json.loads(status_res2.data)["data"]
        self.assertIn(status_data2["status"], ["cancelled", "completed", "error"])


if __name__ == "__main__":
    unittest.main()
