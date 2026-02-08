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
APPLIED_SHEET = "Applied"
NOT_INTERESTED_SHEET = "Not Interested"

# Column headers
HEADERS = ["Company", "Role", "Link", "Status", "Date Posted", "Date Added", "Platform"]
APPLIED_HEADERS = ["Company", "Role", "Link", "Date Applied", "Platform", "Job Description"]
NOT_INTERESTED_HEADERS = ["Company", "Role", "Link", "Date Dismissed", "Platform"]


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


@dataclass
class AppliedJob:
    """Represents a completed job application with description."""
    company: str
    role: str
    link: str
    date_applied: str = ""
    platform: str = ""
    job_description: str = ""

    def to_row(self) -> list:
        """Convert to spreadsheet row."""
        return [
            self.company,
            self.role,
            self.link,
            self.date_applied or datetime.now().strftime("%Y-%m-%d"),
            self.platform,
            self.job_description,
        ]

    @classmethod
    def from_row(cls, row: list) -> "AppliedJob":
        """Create from spreadsheet row."""
        while len(row) < 6:
            row.append("")
        return cls(
            company=row[0] if row[0] else "",
            role=row[1] if row[1] else "",
            link=row[2] if row[2] else "",
            date_applied=row[3] if row[3] else "",
            platform=row[4] if row[4] else "",
            job_description=row[5] if row[5] else "",
        )


@dataclass
class NotInterestedJob:
    """Represents a job the user is not interested in."""
    company: str
    role: str
    link: str
    date_dismissed: str = ""
    platform: str = ""

    def to_row(self) -> list:
        """Convert to spreadsheet row."""
        return [
            self.company,
            self.role,
            self.link,
            self.date_dismissed or datetime.now().strftime("%Y-%m-%d"),
            self.platform,
        ]

    @classmethod
    def from_row(cls, row: list) -> "NotInterestedJob":
        """Create from spreadsheet row."""
        while len(row) < 5:
            row.append("")
        return cls(
            company=row[0] if row[0] else "",
            role=row[1] if row[1] else "",
            link=row[2] if row[2] else "",
            date_dismissed=row[3] if row[3] else "",
            platform=row[4] if row[4] else "",
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
        import time
        import ssl

        # Load existing token
        if TOKEN_PATH.exists():
            self.creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

        # If no valid credentials, get new ones
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                # Retry token refresh up to 3 times for transient SSL errors
                for attempt in range(3):
                    try:
                        self.creds.refresh(Request())
                        break
                    except ssl.SSLError:
                        if attempt < 2:
                            time.sleep(1)  # Wait before retry
                        else:
                            raise
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

        # Build the service with retry logic for transient SSL errors
        for attempt in range(3):
            try:
                self.service = build('sheets', 'v4', credentials=self.creds)
                break
            except ssl.SSLError:
                if attempt < 2:
                    time.sleep(1)  # Wait before retry
                else:
                    raise

    def _ensure_headers(self, sheet_name: str):
        """Ensure the sheet has headers."""
        # Use different headers for each sheet type
        if sheet_name == APPLIED_SHEET:
            headers = APPLIED_HEADERS
            col_range = "A1:F1"
        elif sheet_name == NOT_INTERESTED_SHEET:
            headers = NOT_INTERESTED_HEADERS
            col_range = "A1:E1"
        else:
            headers = HEADERS
            col_range = "A1:G1"

        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"{sheet_name}!{col_range}"
            ).execute()

            values = result.get('values', [])
            if not values or values[0] != headers:
                # Set headers
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"{sheet_name}!{col_range}",
                    valueInputOption='RAW',
                    body={'values': [headers]}
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

        # Get all tracked links to avoid duplicates (including Applied and Not Interested)
        existing_links = self.get_all_tracked_links()

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

    def get_applied_jobs(self) -> list[AppliedJob]:
        """Get all applied jobs from the Applied sheet."""
        self._ensure_headers(APPLIED_SHEET)

        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"{APPLIED_SHEET}!A2:F1000"
            ).execute()

            rows = result.get('values', [])
            return [AppliedJob.from_row(row) for row in rows if any(row)]
        except HttpError as e:
            print(f"Error reading applied jobs: {e}")
            return []

    def add_applied_job(self, job: AppliedJob) -> bool:
        """Add a job to the Applied sheet."""
        self._ensure_headers(APPLIED_SHEET)

        if not job.date_applied:
            job.date_applied = datetime.now().strftime("%Y-%m-%d")

        try:
            self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=f"{APPLIED_SHEET}!A:F",
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body={'values': [job.to_row()]}
            ).execute()
            return True
        except HttpError as e:
            print(f"Error adding applied job: {e}")
            return False

    def mark_as_applied_with_description(self, link: str, job_description: str = "") -> bool:
        """Mark a job as applied and save it to the Applied sheet with description."""
        # First find the job in Manual or AI Searched sheets
        job_data = None
        source_sheet = None

        for sheet_name in [MANUAL_SHEET, AI_SEARCHED_SHEET]:
            jobs = self.get_all_jobs(sheet_name)
            for job in jobs:
                if job.link == link:
                    job_data = job
                    source_sheet = sheet_name
                    break
            if job_data:
                break

        if not job_data:
            return False

        # Create AppliedJob and add to Applied sheet
        applied_job = AppliedJob(
            company=job_data.company,
            role=job_data.role,
            link=job_data.link,
            date_applied=datetime.now().strftime("%Y-%m-%d"),
            platform=job_data.platform,
            job_description=job_description,
        )

        if not self.add_applied_job(applied_job):
            return False

        # Update status in source sheet
        return self._mark_applied_in_sheet(link, source_sheet)

    def get_not_interested_jobs(self) -> list[NotInterestedJob]:
        """Get all jobs from the Not Interested sheet."""
        self._ensure_headers(NOT_INTERESTED_SHEET)

        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"{NOT_INTERESTED_SHEET}!A2:E1000"
            ).execute()

            rows = result.get('values', [])
            return [NotInterestedJob.from_row(row) for row in rows if any(row)]
        except HttpError as e:
            print(f"Error reading not interested jobs: {e}")
            return []

    def get_all_tracked_links(self) -> set[str]:
        """Get all job links from all sheets (Manual, AI Searched, Applied, Not Interested)."""
        all_links = set()

        # Get links from pending jobs (Manual and AI Searched)
        for sheet_name in [MANUAL_SHEET, AI_SEARCHED_SHEET]:
            try:
                jobs = self.get_all_jobs(sheet_name)
                for job in jobs:
                    if job.link:
                        all_links.add(job.link)
            except Exception:
                pass

        # Get links from Applied sheet
        try:
            applied = self.get_applied_jobs()
            for job in applied:
                if job.link:
                    all_links.add(job.link)
        except Exception:
            pass

        # Get links from Not Interested sheet
        try:
            not_interested = self.get_not_interested_jobs()
            for job in not_interested:
                if job.link:
                    all_links.add(job.link)
        except Exception:
            pass

        return all_links

    def mark_as_not_interested(self, link: str) -> bool:
        """Move a job to the Not Interested sheet and remove from source."""
        # First find the job in Manual or AI Searched sheets
        job_data = None
        source_sheet = None
        row_index = None

        for sheet_name in [MANUAL_SHEET, AI_SEARCHED_SHEET]:
            try:
                result = self.service.spreadsheets().values().get(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"{sheet_name}!A2:G1000"
                ).execute()
                rows = result.get('values', [])
                for i, row in enumerate(rows):
                    if len(row) >= 3 and row[2] == link:
                        job_data = JobApplication.from_row(row)
                        source_sheet = sheet_name
                        row_index = i + 2  # +2 for header and 0-indexing
                        break
            except HttpError:
                continue
            if job_data:
                break

        if not job_data:
            return False

        # Create NotInterestedJob and add to Not Interested sheet
        not_interested_job = NotInterestedJob(
            company=job_data.company,
            role=job_data.role,
            link=job_data.link,
            date_dismissed=datetime.now().strftime("%Y-%m-%d"),
            platform=job_data.platform,
        )

        self._ensure_headers(NOT_INTERESTED_SHEET)

        try:
            # Add to Not Interested sheet
            self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=f"{NOT_INTERESTED_SHEET}!A:E",
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body={'values': [not_interested_job.to_row()]}
            ).execute()

            # Delete from source sheet
            self._delete_row(source_sheet, row_index)
            return True
        except HttpError as e:
            print(f"Error marking as not interested: {e}")
            return False

    def restore_from_not_interested(self, link: str) -> bool:
        """Restore a job from Not Interested back to AI Searched."""
        # Find the job in Not Interested sheet
        job_data = None
        row_index = None

        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"{NOT_INTERESTED_SHEET}!A2:E1000"
            ).execute()
            rows = result.get('values', [])
            for i, row in enumerate(rows):
                if len(row) >= 3 and row[2] == link:
                    job_data = NotInterestedJob.from_row(row)
                    row_index = i + 2  # +2 for header and 0-indexing
                    break
        except HttpError:
            return False

        if not job_data:
            return False

        # Create JobApplication and add to AI Searched sheet
        restored_job = JobApplication(
            company=job_data.company,
            role=job_data.role,
            link=job_data.link,
            status="Not Yet Applied",
            date_added=datetime.now().strftime("%Y-%m-%d"),
            platform=job_data.platform,
        )

        try:
            # Add to AI Searched sheet
            self._ensure_headers(AI_SEARCHED_SHEET)
            self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=f"{AI_SEARCHED_SHEET}!A:G",
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body={'values': [restored_job.to_row()]}
            ).execute()

            # Delete from Not Interested sheet
            self._delete_row(NOT_INTERESTED_SHEET, row_index)
            return True
        except HttpError as e:
            print(f"Error restoring job: {e}")
            return False

    def unapply_job(self, link: str) -> bool:
        """Move a job from Applied back to Manual sheet (undo applied)."""
        # Find the job in Applied sheet
        job_data = None
        row_index = None

        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"{APPLIED_SHEET}!A2:F1000"
            ).execute()
            rows = result.get('values', [])
            for i, row in enumerate(rows):
                if len(row) >= 3 and row[2] == link:
                    job_data = AppliedJob.from_row(row)
                    row_index = i + 2  # +2 for header and 0-indexing
                    break
        except HttpError:
            return False

        if not job_data:
            return False

        # Create JobApplication and add to Manual sheet
        restored_job = JobApplication(
            company=job_data.company,
            role=job_data.role,
            link=job_data.link,
            status="Not Yet Applied",
            date_added=datetime.now().strftime("%Y-%m-%d"),
            platform=job_data.platform,
        )

        try:
            # Add to Manual sheet
            self._ensure_headers(MANUAL_SHEET)
            self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=f"{MANUAL_SHEET}!A:G",
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body={'values': [restored_job.to_row()]}
            ).execute()

            # Delete from Applied sheet
            self._delete_row(APPLIED_SHEET, row_index)
            return True
        except HttpError as e:
            print(f"Error unapplying job: {e}")
            return False

    def clear_sheet(self, sheet_name: str) -> bool:
        """Clear all data rows from a sheet (keeps headers)."""
        # Only allow clearing certain sheets for safety
        allowed_sheets = [MANUAL_SHEET, AI_SEARCHED_SHEET, NOT_INTERESTED_SHEET]
        if sheet_name not in allowed_sheets:
            print(f"Cannot clear sheet: {sheet_name}")
            return False

        try:
            # Clear all rows except header (row 1)
            self.service.spreadsheets().values().clear(
                spreadsheetId=self.spreadsheet_id,
                range=f"{sheet_name}!A2:G1000"
            ).execute()
            print(f"Cleared all jobs from {sheet_name}")
            return True
        except HttpError as e:
            print(f"Error clearing sheet: {e}")
            return False

    def _delete_row(self, sheet_name: str, row_index: int) -> bool:
        """Delete a row from a sheet by clearing its contents."""
        try:
            # Clear the row contents (effectively removing it)
            self.service.spreadsheets().values().clear(
                spreadsheetId=self.spreadsheet_id,
                range=f"{sheet_name}!A{row_index}:G{row_index}"
            ).execute()
            return True
        except HttpError as e:
            print(f"Error deleting row: {e}")
            return False


def get_sheets_sync() -> Optional[SheetsSync]:
    """Get a SheetsSync instance using spreadsheet ID from .env."""
    from dotenv import load_dotenv
    env_path = PROJECT_ROOT / ".env"
    load_dotenv(env_path)

    spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID")
    if not spreadsheet_id:
        print("GOOGLE_SPREADSHEET_ID not set in .env")
        return None

    try:
        sync = SheetsSync(spreadsheet_id)
        return sync
    except FileNotFoundError as e:
        print(f"Credentials not found: {e}")
        return None
    except Exception as e:
        print(f"Sheets connection error: {type(e).__name__}: {e}")
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
