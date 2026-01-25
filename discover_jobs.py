#!/usr/bin/env python3
"""
Discover internships and add them to Google Sheets.
Run: python discover_jobs.py
"""

import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "poc"))

from poc.poc_discovery import (
    search_greenhouse_boards,
    search_lever_boards,
    get_greenhouse_jobs,
    get_lever_jobs,
    filter_internships,
)
from app.sync.sheets import get_sheets_sync, JobApplication, AI_SEARCHED_SHEET


def detect_platform(url: str) -> str:
    """Detect platform from URL."""
    url_lower = url.lower()
    if "greenhouse" in url_lower:
        return "greenhouse"
    elif "lever" in url_lower:
        return "lever"
    elif "workday" in url_lower or "myworkdayjobs" in url_lower:
        return "workday"
    return "other"


def run_discovery():
    print("=" * 60)
    print("INTERNSHIP DISCOVERY")
    print("=" * 60)

    # Get sheets sync
    sync = get_sheets_sync()
    if not sync:
        print("\nERROR: Google Sheets not configured.")
        print("Make sure GOOGLE_SPREADSHEET_ID is set in .env")
        return

    all_jobs = []

    # Discover Greenhouse jobs
    print("\n[1/4] Searching for Greenhouse boards...")
    greenhouse_boards = search_greenhouse_boards()
    print(f"Found {len(greenhouse_boards)} Greenhouse boards")

    print("\n[2/4] Fetching Greenhouse jobs...")
    for board in greenhouse_boards[:10]:  # Limit to 10 boards
        company = board.get("company", "Unknown")
        board_token = board.get("board_token", "")
        if board_token:
            jobs = get_greenhouse_jobs(board_token)
            internships = filter_internships(jobs)
            for job in internships[:5]:  # Limit to 5 per company
                all_jobs.append(JobApplication(
                    company=company,
                    role=job.get("title", "Internship"),
                    link=job.get("absolute_url", ""),
                    platform="greenhouse",
                    date_posted=job.get("updated_at", "")[:10] if job.get("updated_at") else "",
                ))
            print(f"  {company}: {len(internships)} internships")

    # Discover Lever jobs
    print("\n[3/4] Searching for Lever boards...")
    lever_boards = search_lever_boards()
    print(f"Found {len(lever_boards)} Lever boards")

    print("\n[4/4] Fetching Lever jobs...")
    for board in lever_boards[:10]:  # Limit to 10 boards
        company = board.get("company", "Unknown")
        company_slug = board.get("company_slug", "")
        if company_slug:
            jobs = get_lever_jobs(company_slug)
            internships = filter_internships(jobs)
            for job in internships[:5]:  # Limit to 5 per company
                all_jobs.append(JobApplication(
                    company=company,
                    role=job.get("text", "Internship"),
                    link=job.get("hostedUrl", ""),
                    platform="lever",
                    date_posted="",
                ))
            print(f"  {company}: {len(internships)} internships")

    # Add to Google Sheets
    print(f"\n{'=' * 60}")
    print(f"ADDING {len(all_jobs)} JOBS TO GOOGLE SHEETS")
    print("=" * 60)

    if all_jobs:
        sync.add_multiple_jobs(all_jobs, AI_SEARCHED_SHEET)
        print(f"\nDone! Added jobs to '{AI_SEARCHED_SHEET}' sheet.")
        print("Refresh the UI to see them.")
    else:
        print("\nNo jobs found. Try again later or add jobs manually.")


if __name__ == "__main__":
    run_discovery()
