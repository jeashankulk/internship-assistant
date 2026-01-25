#!/usr/bin/env python3
"""
Quick launcher for the Internship Application Assistant Web UI.
Run: python run_ui.py
"""

import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from app.web.server import run_server

if __name__ == "__main__":
    print("\n" + "="*60)
    print("INTERNSHIP APPLICATION ASSISTANT")
    print("="*60)
    print("\nBefore starting, make sure you have:")
    print("  1. Set GOOGLE_SPREADSHEET_ID in .env")
    print("  2. Downloaded credentials.json from Google Cloud Console")
    print("  3. Created 'Manual' and 'AI Searched' sheets in your spreadsheet")
    print("\nPress Ctrl+C to stop the server.\n")

    run_server(port=8080, debug=True, open_browser=True)
