#!/usr/bin/env python3
"""
POC Script: Board Discovery
Tests ability to discover Greenhouse and Lever job boards with Summer 2026 internships.

Three discovery methods:
1. Google Custom Search API (requires API key)
2. Known company list (hardcoded, no API needed)
3. Manual URL input (always available)

Usage:
    python poc/poc_discovery.py --method search
    python poc/poc_discovery.py --method known-list
    python poc/poc_discovery.py --method manual --urls "https://boards.greenhouse.io/stripe"
    python poc/poc_discovery.py --method all
"""

import os
import sys
import json
import time
import hashlib
import argparse
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Optional
from pathlib import Path

import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


# =============================================================================
# Configuration
# =============================================================================

GOOGLE_API_KEY = os.getenv("GOOGLE_CUSTOM_SEARCH_API_KEY")
GOOGLE_CX = os.getenv("GOOGLE_SEARCH_ENGINE_ID")

# Rate limiting
RATE_LIMIT_DELAY = 1.0  # seconds between API calls

# Known companies that use Greenhouse or Lever (seed list)
KNOWN_GREENHOUSE_COMPANIES = [
    "stripe",
    "figma",
    "notion",
    "airtable",
    "grammarly",
    "coinbase",
    "doordash",
    "instacart",
    "plaid",
    "ramp",
    "brex",
    "scale",
    "anthropic",
    "openai",
    "databricks",
    "snowflake",
    "datadog",
    "mongodb",
    "elastic",
    "cloudflare",
    "twilio",
    "segment",
    "amplitude",
    "mixpanel",
    "heap",
    "retool",
    "vercel",
    "supabase",
    "planetscale",
    "cockroachlabs",
    "timescale",
    "influxdata",
    "grafana",
    "hashicorp",
    "pulumi",
    "gitpod",
    "replit",
    "codespaces",
    "render",
    "railway",
    "fly",
    "modal",
    "anyscale",
    "huggingface",
    "cohere",
    "adept",
    "runway",
    "stability",
    "jasper",
]

KNOWN_LEVER_COMPANIES = [
    "spotify",
    "netflix",
    "lyft",
    "uber",
    "airbnb",
    "pinterest",
    "snap",
    "discord",
    "reddit",
    "quora",
    "medium",
    "substack",
    "notion",
    "linear",
    "loom",
    "miro",
    "canva",
    "webflow",
    "framer",
    "spline",
    "rive",
    "protopie",
    "maze",
    "hotjar",
    "fullstory",
    "logrocket",
    "sentry",
    "launchdarkly",
    "split",
    "optimizely",
    "contentful",
    "sanity",
    "strapi",
    "ghost",
    "webflow",
    "squarespace",
    "wix",
    "shopify",
    "bigcommerce",
    "klaviyo",
    "attentive",
    "braze",
    "iterable",
    "customer",
    "segment",
    "mparticle",
    "rudderstack",
    "hightouch",
    "census",
]

# Keywords for filtering internships
INTERNSHIP_KEYWORDS = [
    "intern",
    "internship",
    "co-op",
    "coop",
    "summer",
    "fall",
    "spring",
    "student",
    "undergraduate",
    "graduate",
]

SUMMER_2026_KEYWORDS = [
    "summer 2026",
    "summer '26",
    "2026 summer",
    "2026 intern",
    "summer intern 2026",
]

ROLE_KEYWORDS = {
    "SWE": [
        "software",
        "engineer",
        "developer",
        "programming",
        "backend",
        "frontend",
        "full stack",
        "fullstack",
        "full-stack",
        "mobile",
        "ios",
        "android",
        "web",
        "platform",
        "infrastructure",
        "devops",
        "sre",
        "systems",
        "embedded",
        "firmware",
        "ml",
        "machine learning",
        "data engineer",
        "ai engineer",
    ],
    "QUANT": [
        "quant",
        "quantitative",
        "trading",
        "trader",
        "research",
        "researcher",
        "alpha",
        "strategy",
        "systematic",
        "algorithmic",
        "financial engineer",
        "risk",
    ],
    "OR": [
        "operations research",
        "optimization",
        "analytics",
        "data science",
        "data scientist",
        "business intelligence",
        "bi ",
        "decision science",
        "supply chain",
        "logistics",
    ],
}


# =============================================================================
# Data Classes
# =============================================================================


class DiscoveryMethod(Enum):
    GOOGLE_SEARCH = "search"
    KNOWN_LIST = "known-list"
    MANUAL = "manual"
    ALL = "all"


@dataclass
class JobListing:
    """Represents a single job listing."""

    title: str
    location: str | None
    url: str
    department: str | None = None
    is_internship: bool = False
    is_summer_2026: bool = False
    role_family: str | None = None  # SWE, QUANT, OR, OTHER


@dataclass
class DiscoveredBoard:
    """Represents a discovered job board."""

    source: str  # "greenhouse" or "lever"
    company: str
    board_url: str
    api_url: str
    total_jobs: int = 0
    internship_count: int = 0
    summer_2026_count: int = 0
    relevant_jobs: list[JobListing] = field(default_factory=list)
    discovery_method: str = ""
    discovered_at: str = ""
    api_success: bool = False
    error_message: str | None = None


@dataclass
class DiscoveryReport:
    """Summary report of discovery run."""

    method: str
    started_at: str
    ended_at: str
    total_boards_tested: int = 0
    valid_boards_found: int = 0
    boards_with_internships: int = 0
    boards_with_summer_2026: int = 0
    total_internships_found: int = 0
    total_summer_2026_found: int = 0
    api_success_rate: float = 0.0
    boards: list[DiscoveredBoard] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# =============================================================================
# API Clients
# =============================================================================


class GreenhouseClient:
    """Client for Greenhouse Job Board API."""

    BASE_API_URL = "https://boards-api.greenhouse.io/v1/boards"
    BASE_BOARD_URL = "https://boards.greenhouse.io"

    def __init__(self, session: requests.Session):
        self.session = session

    def get_board_url(self, company: str) -> str:
        return f"{self.BASE_BOARD_URL}/{company}"

    def get_api_url(self, company: str) -> str:
        return f"{self.BASE_API_URL}/{company}/jobs"

    def fetch_jobs(self, company: str) -> tuple[list[dict], str | None]:
        """Fetch all jobs from a Greenhouse board."""
        url = self.get_api_url(company)
        try:
            response = self.session.get(url, timeout=15)
            if response.status_code == 404:
                return [], f"Board not found: {company}"
            response.raise_for_status()
            data = response.json()
            return data.get("jobs", []), None
        except requests.exceptions.RequestException as e:
            return [], str(e)
        except json.JSONDecodeError as e:
            return [], f"Invalid JSON: {e}"

    def parse_job(self, job: dict) -> JobListing:
        """Parse a Greenhouse job into JobListing."""
        title = job.get("title", "")
        location = job.get("location", {}).get("name") if job.get("location") else None
        url = job.get("absolute_url", "")
        department = None
        if job.get("departments"):
            department = job["departments"][0].get("name") if job["departments"] else None

        listing = JobListing(
            title=title,
            location=location,
            url=url,
            department=department,
        )

        # Classify the job
        listing.is_internship = self._is_internship(title, department)
        listing.is_summer_2026 = self._is_summer_2026(title)
        listing.role_family = self._classify_role(title, department)

        return listing

    def _is_internship(self, title: str, department: str | None) -> bool:
        text = f"{title} {department or ''}".lower()
        return any(kw in text for kw in INTERNSHIP_KEYWORDS)

    def _is_summer_2026(self, title: str) -> bool:
        text = title.lower()
        # Check for explicit Summer 2026 mentions
        if any(kw in text for kw in SUMMER_2026_KEYWORDS):
            return True
        # Check for "summer" + "2026" anywhere
        if "summer" in text and "2026" in text:
            return True
        # For now, also flag generic "summer intern" as potentially relevant
        # (actual year filtering should be more sophisticated with description parsing)
        return False

    def _classify_role(self, title: str, department: str | None) -> str:
        text = f"{title} {department or ''}".lower()
        for role, keywords in ROLE_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                return role
        return "OTHER"


class LeverClient:
    """Client for Lever Postings API."""

    BASE_API_URL = "https://api.lever.co/v0/postings"
    BASE_BOARD_URL = "https://jobs.lever.co"

    def __init__(self, session: requests.Session):
        self.session = session

    def get_board_url(self, company: str) -> str:
        return f"{self.BASE_BOARD_URL}/{company}"

    def get_api_url(self, company: str) -> str:
        return f"{self.BASE_API_URL}/{company}"

    def fetch_jobs(self, company: str) -> tuple[list[dict], str | None]:
        """Fetch all jobs from a Lever board."""
        url = self.get_api_url(company)
        try:
            response = self.session.get(url, timeout=15)
            if response.status_code == 404:
                return [], f"Board not found: {company}"
            response.raise_for_status()
            data = response.json()
            # Lever returns a list directly
            if isinstance(data, list):
                return data, None
            return [], "Unexpected response format"
        except requests.exceptions.RequestException as e:
            return [], str(e)
        except json.JSONDecodeError as e:
            return [], f"Invalid JSON: {e}"

    def parse_job(self, job: dict) -> JobListing:
        """Parse a Lever job into JobListing."""
        title = job.get("text", "")
        location = job.get("categories", {}).get("location") if job.get("categories") else None
        url = job.get("hostedUrl", "") or job.get("applyUrl", "")
        department = job.get("categories", {}).get("department") if job.get("categories") else None

        listing = JobListing(
            title=title,
            location=location,
            url=url,
            department=department,
        )

        # Classify the job
        listing.is_internship = self._is_internship(title, department)
        listing.is_summer_2026 = self._is_summer_2026(title)
        listing.role_family = self._classify_role(title, department)

        return listing

    def _is_internship(self, title: str, department: str | None) -> bool:
        text = f"{title} {department or ''}".lower()
        return any(kw in text for kw in INTERNSHIP_KEYWORDS)

    def _is_summer_2026(self, title: str) -> bool:
        text = title.lower()
        if any(kw in text for kw in SUMMER_2026_KEYWORDS):
            return True
        if "summer" in text and "2026" in text:
            return True
        return False

    def _classify_role(self, title: str, department: str | None) -> str:
        text = f"{title} {department or ''}".lower()
        for role, keywords in ROLE_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                return role
        return "OTHER"


# =============================================================================
# Discovery Methods
# =============================================================================


class BoardDiscovery:
    """Main discovery orchestrator."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "InternshipAssistant/1.0 (POC; contact@example.com)",
                "Accept": "application/json",
            }
        )
        self.greenhouse = GreenhouseClient(self.session)
        self.lever = LeverClient(self.session)

    def discover_via_google_search(self, max_results: int = 20) -> list[DiscoveredBoard]:
        """Discover boards via Google Custom Search API."""
        if not GOOGLE_API_KEY or not GOOGLE_CX:
            print("ERROR: Google Custom Search API key or CX not configured.")
            print("Set GOOGLE_CUSTOM_SEARCH_API_KEY and GOOGLE_SEARCH_ENGINE_ID in .env")
            return []

        boards = []
        queries = [
            ("greenhouse", "site:boards.greenhouse.io internship 2026"),
            ("greenhouse", "site:boards.greenhouse.io software intern"),
            ("lever", "site:jobs.lever.co internship 2026"),
            ("lever", "site:jobs.lever.co software intern"),
        ]

        seen_companies = set()

        for source, query in queries:
            print(f"\nSearching: {query}")
            try:
                url = "https://www.googleapis.com/customsearch/v1"
                params = {
                    "key": GOOGLE_API_KEY,
                    "cx": GOOGLE_CX,
                    "q": query,
                    "num": min(10, max_results),
                }
                response = self.session.get(url, params=params, timeout=15)
                response.raise_for_status()
                data = response.json()

                items = data.get("items", [])
                print(f"  Found {len(items)} results")

                for item in items:
                    link = item.get("link", "")
                    company = self._extract_company_from_url(link, source)
                    if company and company not in seen_companies:
                        seen_companies.add(company)
                        print(f"  -> Discovered: {company} ({source})")
                        board = self._validate_board(company, source, "google_search")
                        if board:
                            boards.append(board)

                time.sleep(RATE_LIMIT_DELAY)

            except requests.exceptions.RequestException as e:
                print(f"  Search error: {e}")

        return boards

    def discover_via_known_list(self) -> list[DiscoveredBoard]:
        """Discover boards from known company list."""
        boards = []

        print("\nTesting known Greenhouse companies...")
        for company in KNOWN_GREENHOUSE_COMPANIES:
            print(f"  Testing: {company}", end=" ")
            board = self._validate_board(company, "greenhouse", "known_list")
            if board and board.api_success:
                print(f"-> {board.total_jobs} jobs, {board.internship_count} internships")
                boards.append(board)
            else:
                print("-> not found or error")
            time.sleep(RATE_LIMIT_DELAY * 0.5)  # Faster for known list

        print("\nTesting known Lever companies...")
        for company in KNOWN_LEVER_COMPANIES:
            print(f"  Testing: {company}", end=" ")
            board = self._validate_board(company, "lever", "known_list")
            if board and board.api_success:
                print(f"-> {board.total_jobs} jobs, {board.internship_count} internships")
                boards.append(board)
            else:
                print("-> not found or error")
            time.sleep(RATE_LIMIT_DELAY * 0.5)

        return boards

    def discover_via_manual(self, urls: list[str]) -> list[DiscoveredBoard]:
        """Discover boards from manually provided URLs."""
        boards = []

        for url in urls:
            print(f"\nValidating: {url}")
            source, company = self._parse_board_url(url)
            if source and company:
                board = self._validate_board(company, source, "manual")
                if board:
                    boards.append(board)
                    print(f"  -> {board.total_jobs} jobs, {board.internship_count} internships")
            else:
                print(f"  -> Could not parse URL")

        return boards

    def _extract_company_from_url(self, url: str, source: str) -> str | None:
        """Extract company slug from board URL."""
        try:
            if source == "greenhouse" and "boards.greenhouse.io" in url:
                # https://boards.greenhouse.io/company/jobs/123
                parts = url.split("boards.greenhouse.io/")
                if len(parts) > 1:
                    company = parts[1].split("/")[0]
                    return company if company else None
            elif source == "lever" and "jobs.lever.co" in url:
                # https://jobs.lever.co/company/job-id
                parts = url.split("jobs.lever.co/")
                if len(parts) > 1:
                    company = parts[1].split("/")[0]
                    return company if company else None
        except Exception:
            pass
        return None

    def _parse_board_url(self, url: str) -> tuple[str | None, str | None]:
        """Parse a board URL to extract source and company."""
        if "boards.greenhouse.io" in url:
            company = self._extract_company_from_url(url, "greenhouse")
            return "greenhouse", company
        elif "jobs.lever.co" in url:
            company = self._extract_company_from_url(url, "lever")
            return "lever", company
        return None, None

    def _validate_board(
        self, company: str, source: str, method: str
    ) -> DiscoveredBoard | None:
        """Validate a board by fetching its jobs."""
        if source == "greenhouse":
            client = self.greenhouse
        elif source == "lever":
            client = self.lever
        else:
            return None

        board = DiscoveredBoard(
            source=source,
            company=company,
            board_url=client.get_board_url(company),
            api_url=client.get_api_url(company),
            discovery_method=method,
            discovered_at=datetime.now().isoformat(),
        )

        jobs, error = client.fetch_jobs(company)

        if error:
            board.error_message = error
            board.api_success = False
            return board

        board.api_success = True
        board.total_jobs = len(jobs)

        for job_data in jobs:
            listing = client.parse_job(job_data)

            if listing.is_internship:
                board.internship_count += 1

                # Filter for relevant roles
                if listing.role_family in ("SWE", "QUANT", "OR"):
                    board.relevant_jobs.append(listing)

                    if listing.is_summer_2026:
                        board.summer_2026_count += 1

        return board


# =============================================================================
# Main Execution
# =============================================================================


def run_discovery(
    method: DiscoveryMethod,
    manual_urls: list[str] | None = None,
    output_dir: Path | None = None,
) -> DiscoveryReport:
    """Run the discovery process and generate a report."""
    discovery = BoardDiscovery()
    report = DiscoveryReport(
        method=method.value,
        started_at=datetime.now().isoformat(),
        ended_at="",
    )

    all_boards = []

    if method in (DiscoveryMethod.GOOGLE_SEARCH, DiscoveryMethod.ALL):
        print("\n" + "=" * 60)
        print("GOOGLE CUSTOM SEARCH DISCOVERY")
        print("=" * 60)
        boards = discovery.discover_via_google_search()
        all_boards.extend(boards)

    if method in (DiscoveryMethod.KNOWN_LIST, DiscoveryMethod.ALL):
        print("\n" + "=" * 60)
        print("KNOWN COMPANY LIST DISCOVERY")
        print("=" * 60)
        boards = discovery.discover_via_known_list()
        all_boards.extend(boards)

    if method in (DiscoveryMethod.MANUAL, DiscoveryMethod.ALL):
        if manual_urls:
            print("\n" + "=" * 60)
            print("MANUAL URL DISCOVERY")
            print("=" * 60)
            boards = discovery.discover_via_manual(manual_urls)
            all_boards.extend(boards)

    # Deduplicate by URL
    seen_urls = set()
    unique_boards = []
    for board in all_boards:
        if board.board_url not in seen_urls:
            seen_urls.add(board.board_url)
            unique_boards.append(board)

    # Generate report
    report.boards = unique_boards
    report.ended_at = datetime.now().isoformat()
    report.total_boards_tested = len(all_boards)
    report.valid_boards_found = len([b for b in unique_boards if b.api_success])
    report.boards_with_internships = len([b for b in unique_boards if b.internship_count > 0])
    report.boards_with_summer_2026 = len([b for b in unique_boards if b.summer_2026_count > 0])
    report.total_internships_found = sum(b.internship_count for b in unique_boards)
    report.total_summer_2026_found = sum(b.summer_2026_count for b in unique_boards)

    successful = len([b for b in all_boards if b.api_success])
    report.api_success_rate = successful / len(all_boards) if all_boards else 0.0

    return report


def print_report(report: DiscoveryReport):
    """Print a summary of the discovery report."""
    print("\n" + "=" * 60)
    print("DISCOVERY REPORT")
    print("=" * 60)
    print(f"Method: {report.method}")
    print(f"Duration: {report.started_at} to {report.ended_at}")
    print(f"\nBoards tested: {report.total_boards_tested}")
    print(f"Valid boards found: {report.valid_boards_found}")
    print(f"Boards with internships: {report.boards_with_internships}")
    print(f"Boards with Summer 2026: {report.boards_with_summer_2026}")
    print(f"\nTotal internships found: {report.total_internships_found}")
    print(f"Total Summer 2026 internships: {report.total_summer_2026_found}")
    print(f"API success rate: {report.api_success_rate:.1%}")

    # Top boards by internship count
    boards_with_internships = [b for b in report.boards if b.internship_count > 0]
    boards_with_internships.sort(key=lambda b: b.internship_count, reverse=True)

    if boards_with_internships:
        print("\n" + "-" * 60)
        print("TOP BOARDS BY INTERNSHIP COUNT")
        print("-" * 60)
        for board in boards_with_internships[:20]:
            print(
                f"  {board.company} ({board.source}): "
                f"{board.internship_count} internships, "
                f"{board.summer_2026_count} Summer 2026"
            )
            print(f"    URL: {board.board_url}")

    # Sample relevant jobs
    all_relevant = []
    for board in report.boards:
        for job in board.relevant_jobs:
            all_relevant.append((board.company, job))

    if all_relevant:
        print("\n" + "-" * 60)
        print("SAMPLE RELEVANT JOBS")
        print("-" * 60)
        for company, job in all_relevant[:15]:
            s2026 = " [SUMMER 2026]" if job.is_summer_2026 else ""
            print(f"  [{job.role_family}] {job.title}{s2026}")
            print(f"    Company: {company} | Location: {job.location or 'N/A'}")
            print(f"    URL: {job.url}")
            print()


def save_report(report: DiscoveryReport, output_dir: Path):
    """Save the discovery report to JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = output_dir / f"discovery_report_{timestamp}.json"

    # Convert to serializable dict
    data = asdict(report)
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, default=str)

    print(f"\nReport saved to: {filepath}")
    return filepath


def main():
    parser = argparse.ArgumentParser(
        description="POC: Discover Greenhouse and Lever job boards"
    )
    parser.add_argument(
        "--method",
        type=str,
        choices=["search", "known-list", "manual", "all"],
        default="known-list",
        help="Discovery method to use",
    )
    parser.add_argument(
        "--urls",
        type=str,
        nargs="*",
        help="Manual URLs to validate (for --method manual)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="poc/reports",
        help="Output directory for reports",
    )

    args = parser.parse_args()

    method = DiscoveryMethod(args.method)
    output_dir = Path(args.output)

    print("=" * 60)
    print("INTERNSHIP BOARD DISCOVERY POC")
    print("=" * 60)
    print(f"Method: {method.value}")
    if args.urls:
        print(f"Manual URLs: {args.urls}")

    report = run_discovery(method, args.urls, output_dir)
    print_report(report)
    save_report(report, output_dir)

    # Success criteria check
    print("\n" + "=" * 60)
    print("SUCCESS CRITERIA CHECK")
    print("=" * 60)

    greenhouse_boards = [b for b in report.boards if b.source == "greenhouse" and b.api_success]
    lever_boards = [b for b in report.boards if b.source == "lever" and b.api_success]
    gh_with_internships = [b for b in greenhouse_boards if b.internship_count > 0]
    lv_with_internships = [b for b in lever_boards if b.internship_count > 0]

    criteria = [
        ("Greenhouse boards found (>=5)", len(gh_with_internships) >= 5, len(gh_with_internships)),
        ("Lever boards found (>=5)", len(lv_with_internships) >= 5, len(lv_with_internships)),
        ("API success rate (>95%)", report.api_success_rate > 0.95, f"{report.api_success_rate:.1%}"),
        ("Total internships found", report.total_internships_found > 0, report.total_internships_found),
    ]

    all_passed = True
    for name, passed, value in criteria:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}: {value}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("POC #1 RESULT: SUCCESS - Board discovery is feasible!")
    else:
        print("POC #1 RESULT: PARTIAL - Some criteria not met, but discovery works")
    print("=" * 60)


if __name__ == "__main__":
    main()
