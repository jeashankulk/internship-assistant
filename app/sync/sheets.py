#!/usr/bin/env python3
"""
Google Sheets sync module.
Handles reading/writing application data to Google Sheets.

Two sheets:
- "Manual": Manually added job postings (prioritized in UI)
- "AI Searched": Jobs found by automatic discovery
"""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, asdict

# Google API imports
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
CREDENTIALS_PATH = PROJECT_ROOT / "credentials.json"
TOKEN_PATH = PROJECT_ROOT / "storage" / "token.json"

# Google Sheets API scope
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# Sheet names
MANUAL_SHEET = "Manual"
AI_SEARCHED_SHEET = "AI Searched"

# Column headers
HEADERS = ["Company", "Role", "Link", "Status", "Date Posted", "Date Added", "Platform"]


@dataclass
class JobApplication:
    """Represents a job application entry."""
    company: str
    role: str
    link: str
    status: str = "Not Yet Applied"  # "Not Yet Applied" or "Applied"
    date_posted: str = ""
    date_added: str = ""
    platform: str = ""  # "greenhouse", "lever", "workday", "other"

    def to_row(self) -> list:
        """Convert to spreadsheet row."""
        return [
            self.company,
            self.role,
            self.link,
            self.status,
            self.date_posted,
            self.date_added or datetime.now().strftime("%Y-%m-%d"),
            self.platform,
        ]

    @classmethod
    def from_row(cls, row: list) -> "JobApplication":
        """Create from spreadsheet row."""
        # Pad row if it's shorter than expected
        while len(row) < 7:
            row.append("")
        return cls(
            company=row[0] if row[0] else "",
            role=row[1] if row[1] else "",
            link=row[2] if row[2] else "",
            status=row[3] if row[3] else "Not Yet Applied",
            date_posted=row[4] if row[4] else "",
            date_added=row[5] if row[5] else "",
            platform=row[6] if row[6] else "",
        )


class SheetsSync:
    """Handles Google Sheets synchronization."""

    def __init__(self, spreadsheet_id: str):
        self.spreadsheet_id = spreadsheet_id
        self.creds = None
        self.service = None
        self._authenticate()

    def _authenticate(self):
        """Authenticate with Google Sheets API."""
        # Load existing token
        if TOKEN_PATH.exists():
            self.creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

        # If no valid credentials, get new ones
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
            else:
                if not CREDENTIALS_PATH.exists():
                    raise FileNotFoundError(
                        f"credentials.json not found at {CREDENTIALS_PATH}\n"
                        "Please download OAuth credentials from Google Cloud Console."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(CREDENTIALS_PATH), SCOPES
                )
                self.creds = flow.run_local_server(port=0)

            # Save token for next time
            TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(TOKEN_PATH, 'w') as token:
                token.write(self.creds.to_json())

        self.service = build('sheets', 'v4', credentials=self.creds)

    def _ensure_headers(self, sheet_name: str):
        """Ensure the sheet has headers."""
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"{sheet_name}!A1:G1"
            ).execute()

            values = result.get('values', [])
            if not values or values[0] != HEADERS:
                # Set headers
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"{sheet_name}!A1:G1",
                    valueInputOption='RAW',
                    body={'values': [HEADERS]}
                ).execute()
        except HttpError as e:
            if 'Unable to parse range' in str(e):
                # Sheet doesn't exist, create it
                self._create_sheet(sheet_name)
                self._ensure_headers(sheet_name)
            else:
                raise

    def _create_sheet(self, sheet_name: str):
        """Create a new sheet tab."""
        try:
            request = {
                'requests': [{
                    'addSheet': {
                        'properties': {'title': sheet_name}
                    }
                }]
            }
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body=request
            ).execute()
        except HttpError as e:
            if 'already exists' not in str(e).lower():
                raise

    def get_all_jobs(self, sheet_name: str) -> list[JobApplication]:
        """Get all jobs from a sheet."""
        self._ensure_headers(sheet_name)

        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"{sheet_name}!A2:G1000"  # Skip header row
            ).execute()

            rows = result.get('values', [])
            return [JobApplication.from_row(row) for row in rows if any(row)]
        except HttpError as e:
            print(f"Error reading sheet: {e}")
            return []

    def get_pending_jobs(self) -> list[tuple[JobApplication, str]]:
        """
        Get all jobs that haven't been applied to yet.
        Returns list of (job, source_sheet) tuples.
        Manual jobs come first, then AI searched.
        """
        pending = []

        # Get manual jobs first (priority)
        manual_jobs = self.get_all_jobs(MANUAL_SHEET)
        for job in manual_jobs:
            if job.status.lower() != "applied":
                pending.append((job, MANUAL_SHEET))

        # Then AI searched jobs
        ai_jobs = self.get_all_jobs(AI_SEARCHED_SHEET)
        for job in ai_jobs:
            if job.status.lower() != "applied":
                pending.append((job, AI_SEARCHED_SHEET))

        return pending

    def add_job(self, job: JobApplication, sheet_name: str = MANUAL_SHEET):
        """Add a new job to the sheet."""
        self._ensure_headers(sheet_name)

        # Set date_added if not set
        if not job.date_added:
            job.date_added = datetime.now().strftime("%Y-%m-%d")

        try:
            self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=f"{sheet_name}!A:G",
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body={'values': [job.to_row()]}
            ).execute()
            return True
        except HttpError as e:
            print(f"Error adding job: {e}")
            return False

    def mark_as_applied(self, link: str) -> bool:
        """Mark a job as applied by its link."""
        # Search in both sheets
        for sheet_name in [MANUAL_SHEET, AI_SEARCHED_SHEET]:
            if self._mark_applied_in_sheet(link, sheet_name):
                return True
        return False

    def _mark_applied_in_sheet(self, link: str, sheet_name: str) -> bool:
        """Mark a job as applied in a specific sheet."""
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"{sheet_name}!A2:G1000"
            ).execute()

            rows = result.get('values', [])
            for i, row in enumerate(rows):
                if len(row) >= 3 and row[2] == link:  # Column C is link
                    # Update status to "Applied"
                    row_num = i + 2  # +2 for header and 0-indexing
                    self.service.spreadsheets().values().update(
                        spreadsheetId=self.spreadsheet_id,
                        range=f"{sheet_name}!D{row_num}",  # Column D is status
                        valueInputOption='RAW',
                        body={'values': [["Applied"]]}
                    ).execute()
                    return True
            return False
        except HttpError as e:
            print(f"Error marking as applied: {e}")
            return False

    def add_multiple_jobs(self, jobs: list[JobApplication], sheet_name: str = AI_SEARCHED_SHEET):
        """Add multiple jobs at once (for AI discovery results)."""
        self._ensure_headers(sheet_name)

        if not jobs:
            return

        # Get existing links to avoid duplicates
        existing_jobs = self.get_all_jobs(sheet_name)
        existing_links = {job.link for job in existing_jobs}

        # Filter out duplicates
        new_jobs = [job for job in jobs if job.link not in existing_links]

        if not new_jobs:
            print("No new jobs to add (all duplicates)")
            return

        # Set date_added for all
        for job in new_jobs:
            if not job.date_added:
                job.date_added = datetime.now().strftime("%Y-%m-%d")

        try:
            rows = [job.to_row() for job in new_jobs]
            self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=f"{sheet_name}!A:G",
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body={'values': rows}
            ).execute()
            print(f"Added {len(new_jobs)} new jobs to {sheet_name}")
        except HttpError as e:
            print(f"Error adding jobs: {e}")


def get_sheets_sync() -> Optional[SheetsSync]:
    """Get a SheetsSync instance using spreadsheet ID from .env."""
    from dotenv import load_dotenv
    load_dotenv()

    spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID")
    if not spreadsheet_id:
        print("GOOGLE_SPREADSHEET_ID not set in .env")
        return None

    try:
        return SheetsSync(spreadsheet_id)
    except FileNotFoundError as e:
        print(str(e))
        return None
    except Exception as e:
        print(f"Error connecting to Google Sheets: {e}")
        return None


if __name__ == "__main__":
    # Test the sheets sync
    sync = get_sheets_sync()
    if sync:
        print("Connected to Google Sheets!")

        # Test adding a job
        test_job = JobApplication(
            company="Test Company",
            role="Software Engineering Intern",
            link="https://example.com/apply",
            platform="greenhouse"
        )

        print("\nPending jobs:")
        pending = sync.get_pending_jobs()
        for job, source in pending:
            print(f"  [{source}] {job.company} - {job.role}")
