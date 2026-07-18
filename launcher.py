#!/usr/bin/env python3
"""
GC-MS AI Analyzer — Desktop Launcher
======================================
Double-click to start. Automatically:
  1. Checks Python environment
  2. Starts Streamlit web server
  3. Opens browser to the app

Does NOT require any NIST data — demo mode works instantly.
All analysis tools included: 50+ tools, 300K+ spectral library.
"""

import os
import sys
import time
import socket
import webbrowser
import subprocess
import threading
from pathlib import Path


def find_free_port(start=8501):
    """Find a free TCP port starting from `start`."""
    port = start
    while port < 8599:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', port))
                return port
            except OSError:
                port += 1
    return 8501


def main():
    app_dir = Path(__file__).parent.absolute()
    app_file = app_dir / 'app.py'

    if not app_file.exists():
        print(f"ERROR: app.py not found at {app_file}")
        print("Please make sure all files are extracted correctly.")
        input("Press Enter to exit...")
        sys.exit(1)

    # Check if streamlit is installed
    try:
        import streamlit
    except ImportError:
        print("Installing dependencies (first run only)...")
        req_file = app_dir / 'requirements.txt'
        if req_file.exists():
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', str(req_file), '-q'])
        else:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'streamlit', 'pandas', 'numpy', 'matplotlib', 'plotly', 'scipy', 'scikit-learn', 'openpyxl', 'python-docx', 'openai', '-q'])

    port = find_free_port(8501)

    print("=" * 60)
    print("  GC-MS AI Analyzer")
    print("  Open-Source NIST Alternative")
    print("=" * 60)
    print(f"\n  Starting server on http://localhost:{port}")
    print(f"  Press Ctrl+C to stop\n")

    # Start Streamlit
    cmd = [
        sys.executable, '-m', 'streamlit', 'run', str(app_file),
        '--server.port', str(port),
        '--server.headless', 'true',
        '--browser.gatherUsageStats', 'false',
        '--server.address', '127.0.0.1',
        '--theme.primaryColor', '#1a5276',
    ]

    # Suppress Streamlit welcome emails
    env = os.environ.copy()
    env['STREAMLIT_SERVER_HEADLESS'] = 'true'

    process = subprocess.Popen(
        cmd,
        cwd=str(app_dir),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Open browser after a short delay
    def open_browser():
        time.sleep(3)
        webbrowser.open(f'http://localhost:{port}')

    threading.Thread(target=open_browser, daemon=True).start()

    # Keep running
    try:
        process.wait()
    except KeyboardInterrupt:
        print("\n  Shutting down...")
        process.terminate()


if __name__ == '__main__':
    main()
