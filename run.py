#!/usr/bin/env python3
"""Launcher script for the YouTube Downloader application.
Starts the Flask server and opens the web UI in the default browser.
"""

import os
import sys
import threading
import time
import webbrowser
from app import app


def open_browser(port: int):
    """Wait for server to bind then launch browser."""
    time.sleep(1.0)
    webbrowser.open(f"http://127.0.0.1:{port}")


def main():
    port = int(os.environ.get("PORT", 5050))
    print(f"Starting YouTube Downloader on http://127.0.0.1:{port}")
    print("Press Ctrl+C to stop the server.")

    # Launch browser automatically in a separate thread
    threading.Thread(target=open_browser, args=(port,), daemon=True).start()

    # Run Flask server
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    main()
