#!/usr/bin/env python3
"""
POC Script: Playwright Autofill Testing
Tests ability to prefill Greenhouse and Lever application forms.

Three-tier testing strategy:
1. Local mock forms (safe testing)
2. Reconnaissance on real forms (inspect only, no submit)
3. Dry-run on real applications (user validation before submit)

Usage:
    # Test with local mock forms
    python poc/poc_autofill.py --mode mock

    # Inspect a real form (reconnaissance - no filling)
    python poc/poc_autofill.py --mode recon --url "https://boards.greenhouse.io/..."

    # Dry run on real form (fill but pause before submit)
    python poc/poc_autofill.py --mode dryrun --url "https://boards.greenhouse.io/..."
"""

import os
import sys
import json
import time
import argparse
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import answer bank
from answer_bank import get_answer_bank, AnswerBank


# =============================================================================
# Configuration
# =============================================================================

POC_DIR = Path(__file__).parent
MOCK_FORMS_DIR = POC_DIR / "test_forms"
SCREENSHOTS_DIR = POC_DIR / "screenshots"
REPORTS_DIR = POC_DIR / "reports"
STORAGE_DIR = POC_DIR.parent / "storage"
PROFILE_PATH = STORAGE_DIR / "profile.json"

# Interactive mode settings
INTERACTIVE_MODE = True  # Ask user for unknown fields


# =============================================================================
# Data Classes
# =============================================================================


class FormType(Enum):
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    WORKDAY = "workday"
    UNKNOWN = "unknown"
    MOCK_GREENHOUSE = "mock_greenhouse"
    MOCK_LEVER = "mock_lever"


class FieldType(Enum):
    TEXT = "text"
    EMAIL = "email"
    PHONE = "tel"
    URL = "url"
    FILE = "file"
    SELECT = "select"
    TEXTAREA = "textarea"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    UNKNOWN = "unknown"


@dataclass
class ApplicantProfile:
    """User data for form filling."""

    first_name: str = "Test"
    last_name: str = "User"
    full_name: str = "Test User"
    email: str = "test@example.com"
    phone: str = "+1-555-0123"
    location: str = "San Francisco, CA"
    linkedin: str = "https://linkedin.com/in/testuser"
    github: str = "https://github.com/testuser"
    website: str = "https://testuser.dev"
    resume_path: str = ""
    school: str = "Test University"
    graduation_year: str = "2026"
    graduation_month: str = "May"
    work_authorization: str = "yes"
    requires_sponsorship: str = "no"
    work_authorization_detail: str = "US Citizen"
    cover_letter: str = "I am excited to apply for this internship opportunity."

    @classmethod
    def load_from_file(cls, path: Path = PROFILE_PATH) -> "ApplicantProfile":
        """Load profile from JSON file."""
        if not path.exists():
            print(f"Profile not found at {path}")
            print("Run: python poc/setup_profile.py")
            return cls()

        with open(path) as f:
            data = json.load(f)

        return cls(
            first_name=data.get("first_name", "Test"),
            last_name=data.get("last_name", "User"),
            full_name=data.get("full_name", "Test User"),
            email=data.get("email", "test@example.com"),
            phone=data.get("phone", ""),
            location=data.get("location", ""),
            linkedin=data.get("linkedin", ""),
            github=data.get("github", ""),
            website=data.get("website", ""),
            resume_path=data.get("resume_path", ""),
            school=data.get("school", ""),
            graduation_year=data.get("graduation_year", "2026"),
            graduation_month=data.get("graduation_month", "May"),
            work_authorization=data.get("work_authorization", "yes"),
            requires_sponsorship=data.get("requires_sponsorship", "no"),
            work_authorization_detail=data.get("work_authorization_detail", ""),
            cover_letter=data.get("cover_letter", ""),
        )


@dataclass
class FormField:
    """Represents a detected form field."""

    field_type: FieldType
    label: str
    selector: str
    name: str
    required: bool = False
    value: str | None = None
    filled: bool = False
    error: str | None = None


@dataclass
class FormAnalysis:
    """Analysis results for a form."""

    form_type: FormType
    url: str
    fields_detected: list[FormField] = field(default_factory=list)
    fields_filled: int = 0
    fields_failed: int = 0
    success_rate: float = 0.0
    screenshot_path: str | None = None
    error: str | None = None
    analyzed_at: str = ""


# =============================================================================
# Field Mapping
# =============================================================================

# Common field patterns for Greenhouse forms
GREENHOUSE_FIELD_PATTERNS = {
    "first_name": [
        'input[name="first_name"]',
        'input[id="first_name"]',
        'input[name*="first"]',
        'input[placeholder*="First"]',
    ],
    "last_name": [
        'input[name="last_name"]',
        'input[id="last_name"]',
        'input[name*="last"]',
        'input[placeholder*="Last"]',
    ],
    "email": [
        'input[type="email"]',
        'input[name="email"]',
        'input[id="email"]',
        'input[name*="email"]',
    ],
    "phone": [
        'input[type="tel"]',
        'input[name="phone"]',
        'input[id="phone"]',
        'input[name*="phone"]',
    ],
    "resume": [
        'input[type="file"][name*="resume"]',
        'input[type="file"][id*="resume"]',
        'input[type="file"][accept*=".pdf"]',
        'input[type="file"]',
    ],
    "linkedin": [
        'input[name*="linkedin"]',
        'input[id*="linkedin"]',
        'input[placeholder*="LinkedIn"]',
    ],
    "github": [
        'input[name*="github"]',
        'input[id*="github"]',
        'input[placeholder*="GitHub"]',
    ],
    "website": [
        'input[name*="website"]',
        'input[name*="portfolio"]',
        'input[id*="website"]',
        'input[placeholder*="Website"]',
    ],
    "cover_letter": [
        'textarea[name*="cover"]',
        'textarea[id*="cover"]',
        '#cover_letter',
    ],
}

# Common field patterns for Lever forms
LEVER_FIELD_PATTERNS = {
    "full_name": [
        'input[name="name"]',
        'input[name="fullName"]',
        '.application-input[name="name"]',
    ],
    "email": [
        'input[type="email"]',
        'input[name="email"]',
        '.application-input[name="email"]',
    ],
    "phone": [
        'input[type="tel"]',
        'input[name="phone"]',
        '.application-input[name="phone"]',
    ],
    "resume": [
        'input[type="file"]',
        'input[name="resume"]',
    ],
    "linkedin": [
        'input[name*="LinkedIn"]',
        'input[name="urls[LinkedIn]"]',
    ],
    "github": [
        'input[name*="GitHub"]',
        'input[name="urls[GitHub]"]',
    ],
    "website": [
        'input[name*="website"]',
        'input[name*="portfolio"]',
        'input[name="urls[Portfolio]"]',
    ],
    "comments": [
        'textarea[name="comments"]',
        'textarea[name*="additional"]',
        '.application-input[name="comments"]',
    ],
}

# Common field patterns for Workday forms
# Workday uses dynamic data-automation-id attributes
WORKDAY_FIELD_PATTERNS = {
    "first_name": [
        'input[data-automation-id="legalNameSection_firstName"]',
        'input[data-automation-id="firstName"]',
        'input[aria-label*="First Name"]',
        'input[aria-label*="first name"]',
        'input[placeholder*="First Name"]',
    ],
    "last_name": [
        'input[data-automation-id="legalNameSection_lastName"]',
        'input[data-automation-id="lastName"]',
        'input[aria-label*="Last Name"]',
        'input[aria-label*="last name"]',
        'input[placeholder*="Last Name"]',
    ],
    "email": [
        'input[data-automation-id="email"]',
        'input[data-automation-id="emailAddress"]',
        'input[type="email"]',
        'input[aria-label*="Email"]',
    ],
    "phone": [
        'input[data-automation-id="phone-number"]',
        'input[data-automation-id="phoneNumber"]',
        'input[type="tel"]',
        'input[aria-label*="Phone"]',
    ],
    "resume": [
        'input[data-automation-id="file-upload-input-ref"]',
        'input[type="file"]',
        'button[data-automation-id="uploadButton"]',
    ],
    "linkedin": [
        'input[data-automation-id*="linkedin"]',
        'input[aria-label*="LinkedIn"]',
        'input[placeholder*="LinkedIn"]',
    ],
    "address": [
        'input[data-automation-id="addressSection_addressLine1"]',
        'input[aria-label*="Address"]',
    ],
    "city": [
        'input[data-automation-id="addressSection_city"]',
        'input[aria-label*="City"]',
    ],
    "state": [
        'input[data-automation-id="addressSection_countryRegion"]',
        'button[data-automation-id="addressSection_countryRegion"]',
    ],
    "postal_code": [
        'input[data-automation-id="addressSection_postalCode"]',
        'input[aria-label*="Postal"]',
        'input[aria-label*="ZIP"]',
    ],
    "country": [
        'input[data-automation-id="countryDropdown"]',
        'button[data-automation-id="countryDropdown"]',
    ],
}


# =============================================================================
# Autofill Engine
# =============================================================================


class AutofillEngine:
    """Engine for detecting and filling form fields."""

    def __init__(self, profile: ApplicantProfile, headless: bool = False, skip_pause: bool = False, interactive: bool = True, stealth: bool = True):
        self.profile = profile
        self.headless = headless
        self.skip_pause = skip_pause or headless  # Auto-skip pause in headless mode
        self.interactive = interactive and not headless  # Can't be interactive in headless mode
        self.stealth = stealth  # Use stealth mode to avoid bot detection
        self.answer_bank = get_answer_bank()
        self.company = None  # Set when processing a job
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.unfilled_fields = []  # Track fields we couldn't fill

    def __enter__(self):
        from playwright.sync_api import sync_playwright

        self.playwright = sync_playwright().start()

        if self.stealth:
            # Use persistent context with stealth settings to avoid bot detection
            # This makes the browser appear more like a real user's browser
            user_data_dir = STORAGE_DIR / "browser_profile"
            user_data_dir.mkdir(parents=True, exist_ok=True)

            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                headless=self.headless,
                # Stealth settings
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-web-security',
                    '--disable-features=IsolateOrigins,site-per-process',
                ],
                ignore_default_args=['--enable-automation'],
                # Make it look like a real browser
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-US',
                timezone_id='America/New_York',
            )
            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()

            # Additional stealth: remove webdriver property
            self.page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                // Overwrite the plugins property to use a custom getter
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                // Overwrite the languages property
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                });
            """)
        else:
            self.browser = self.playwright.chromium.launch(headless=self.headless)
            self.page = self.browser.new_page()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    def detect_form_type(self, url: str) -> FormType:
        """Detect if form is Greenhouse, Lever, Workday, or mock."""
        url_lower = url.lower()
        if "boards.greenhouse.io" in url_lower or "greenhouse" in url_lower:
            return FormType.GREENHOUSE
        elif "jobs.lever.co" in url_lower or "lever" in url_lower:
            return FormType.LEVER
        elif "workday" in url_lower or "myworkdayjobs" in url_lower or "wd5.myworkday" in url_lower:
            return FormType.WORKDAY
        elif "mock_greenhouse" in url_lower or "greenhouse_mock" in url_lower:
            return FormType.MOCK_GREENHOUSE
        elif "mock_lever" in url_lower or "lever_mock" in url_lower:
            return FormType.MOCK_LEVER
        return FormType.UNKNOWN

    def analyze_form(self, url: str) -> FormAnalysis:
        """Analyze a form to identify all fields."""
        analysis = FormAnalysis(
            form_type=self.detect_form_type(url),
            url=url,
            analyzed_at=datetime.now().isoformat(),
        )

        try:
            # Navigate to the page - use longer timeout for Workday
            timeout = 60000 if analysis.form_type == FormType.WORKDAY else 30000
            self.page.goto(url, wait_until="networkidle", timeout=timeout)

            # Workday needs extra wait time for JS to load
            if analysis.form_type == FormType.WORKDAY:
                time.sleep(5)  # Workday is slow to load
                # Try to wait for common Workday elements
                try:
                    self.page.wait_for_selector('[data-automation-id]', timeout=10000)
                except Exception:
                    pass  # Continue even if selector not found
            else:
                time.sleep(2)  # Wait for any dynamic content

            # Detect all input fields
            fields = self._detect_fields()
            analysis.fields_detected = fields

            # Take screenshot
            SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = SCREENSHOTS_DIR / f"form_analysis_{timestamp}.png"
            self.page.screenshot(path=str(screenshot_path), full_page=True)
            analysis.screenshot_path = str(screenshot_path)

        except Exception as e:
            analysis.error = str(e)

        return analysis

    def _detect_fields(self) -> list[FormField]:
        """Detect all form fields on the page."""
        fields = []

        # Find all input elements - include Workday-specific selectors
        inputs = self.page.query_selector_all(
            "input, select, textarea, "
            "[data-automation-id*='input'], "
            "[data-automation-id*='textInput'], "
            "[data-automation-id*='dropdown'], "
            "[role='textbox'], "
            "[role='combobox']"
        )

        for element in inputs:
            try:
                tag_name = element.evaluate("el => el.tagName.toLowerCase()")
                input_type = element.get_attribute("type") or "text"
                name = element.get_attribute("name") or ""
                id_attr = element.get_attribute("id") or ""
                placeholder = element.get_attribute("placeholder") or ""
                required = element.get_attribute("required") is not None

                # Determine field type
                if tag_name == "select":
                    field_type = FieldType.SELECT
                elif tag_name == "textarea":
                    field_type = FieldType.TEXTAREA
                elif input_type == "email":
                    field_type = FieldType.EMAIL
                elif input_type == "tel":
                    field_type = FieldType.PHONE
                elif input_type == "url":
                    field_type = FieldType.URL
                elif input_type == "file":
                    field_type = FieldType.FILE
                elif input_type == "checkbox":
                    field_type = FieldType.CHECKBOX
                elif input_type == "radio":
                    field_type = FieldType.RADIO
                else:
                    field_type = FieldType.TEXT

                # Skip hidden fields
                if input_type == "hidden":
                    continue

                # Build selector
                if id_attr:
                    selector = f"#{id_attr}"
                elif name:
                    selector = f'[name="{name}"]'
                else:
                    continue

                # Get label
                label = self._find_label(element, name, id_attr, placeholder)

                field = FormField(
                    field_type=field_type,
                    label=label,
                    selector=selector,
                    name=name,
                    required=required,
                )
                fields.append(field)

            except Exception as e:
                # Skip fields that can't be processed
                continue

        return fields

    def _find_label(
        self, element, name: str, id_attr: str, placeholder: str
    ) -> str:
        """Find the label for a form field."""
        # Try aria-label first (important for Workday)
        try:
            aria_label = element.get_attribute("aria-label")
            if aria_label:
                return aria_label.strip()
        except Exception:
            pass

        # Try data-automation-id (Workday uses this)
        try:
            automation_id = element.get_attribute("data-automation-id")
            if automation_id:
                # Convert camelCase or snake_case to readable text
                label = automation_id.replace("_", " ").replace("-", " ")
                # Handle camelCase
                import re
                label = re.sub(r'([a-z])([A-Z])', r'\1 \2', label)
                return label.title()
        except Exception:
            pass

        # Try to find associated label element
        if id_attr:
            label_el = self.page.query_selector(f'label[for="{id_attr}"]')
            if label_el:
                return label_el.inner_text().strip()

        # Try placeholder
        if placeholder:
            return placeholder

        # Try name attribute
        if name:
            return name.replace("_", " ").replace("-", " ").title()

        return "Unknown"

    def fill_form(self, url: str, dry_run: bool = True, company: str = None) -> FormAnalysis:
        """Fill a form with profile data."""
        analysis = self.analyze_form(url)
        self.company = company  # Store company for answer bank
        self.unfilled_fields = []

        if analysis.error:
            return analysis

        form_type = analysis.form_type
        patterns = self._get_patterns_for_form(form_type)

        filled_count = 0
        failed_count = 0
        skipped_count = 0

        print(f"\nFilling {len(analysis.fields_detected)} detected fields...")

        for form_field in analysis.fields_detected:
            try:
                # First, try to get a value automatically
                value = self._get_value_for_field(form_field, patterns)

                element = self.page.query_selector(form_field.selector) if not value or form_field.field_type == FieldType.SELECT else None

                # If no automatic value, try interactive mode
                if not value and self.interactive:
                    element = self.page.query_selector(form_field.selector)
                    if element:
                        value = self._ask_user_for_field(form_field, element)

                if value:
                    success = self._fill_field(form_field, value)
                    if success:
                        form_field.filled = True
                        form_field.value = value
                        filled_count += 1
                        print(f"  [FILLED] {form_field.label}: {value[:30]}{'...' if len(str(value)) > 30 else ''}")
                    else:
                        failed_count += 1
                        form_field.error = "Failed to fill"
                        print(f"  [FAILED] {form_field.label}")
                else:
                    skipped_count += 1
                    self.unfilled_fields.append(form_field)
                    print(f"  [SKIPPED] {form_field.label}")
            except Exception as e:
                failed_count += 1
                form_field.error = str(e)
                print(f"  [ERROR] {form_field.label}: {e}")

        analysis.fields_filled = filled_count
        analysis.fields_failed = failed_count
        total = len(analysis.fields_detected)
        analysis.success_rate = filled_count / total if total > 0 else 0.0

        print(f"\nSummary: {filled_count} filled, {skipped_count} skipped, {failed_count} failed")

        # Take post-fill screenshot
        SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = SCREENSHOTS_DIR / f"form_filled_{timestamp}.png"
        self.page.screenshot(path=str(screenshot_path), full_page=True)
        analysis.screenshot_path = str(screenshot_path)

        if dry_run:
            self._pause_before_submit()

        return analysis

    def _get_patterns_for_form(self, form_type: FormType) -> dict:
        """Get field patterns based on form type."""
        if form_type in (FormType.GREENHOUSE, FormType.MOCK_GREENHOUSE):
            return GREENHOUSE_FIELD_PATTERNS
        elif form_type in (FormType.LEVER, FormType.MOCK_LEVER):
            return LEVER_FIELD_PATTERNS
        elif form_type == FormType.WORKDAY:
            return WORKDAY_FIELD_PATTERNS
        else:
            # Combine all for unknown forms
            combined = {}
            combined.update(GREENHOUSE_FIELD_PATTERNS)
            combined.update(LEVER_FIELD_PATTERNS)
            combined.update(WORKDAY_FIELD_PATTERNS)
            return combined

    def _get_value_for_field(self, form_field: FormField, patterns: dict) -> str | None:
        """Get the appropriate value for a field based on its type and label."""
        label_lower = form_field.label.lower()
        name_lower = form_field.name.lower()
        combined = f"{label_lower} {name_lower}"

        # Map fields to profile values
        if any(x in combined for x in ["first", "fname"]):
            return self.profile.first_name
        elif any(x in combined for x in ["last", "lname"]):
            return self.profile.last_name
        elif "full" in combined and "name" in combined:
            return self.profile.full_name
        elif form_field.field_type == FieldType.EMAIL or "email" in combined:
            return self.profile.email
        elif form_field.field_type == FieldType.PHONE or "phone" in combined:
            return self.profile.phone
        elif "linkedin" in combined:
            return self.profile.linkedin
        elif "github" in combined:
            return self.profile.github
        elif any(x in combined for x in ["website", "portfolio", "personal"]):
            return self.profile.website
        elif any(x in combined for x in ["school", "university", "college"]):
            return self.profile.school
        elif "graduation" in combined or "grad year" in combined:
            return self.profile.graduation_year
        elif form_field.field_type == FieldType.FILE:
            return self.profile.resume_path if self.profile.resume_path else None
        elif form_field.field_type == FieldType.TEXTAREA:
            if any(x in combined for x in ["cover", "letter", "why", "interest"]):
                return self.profile.cover_letter
            return None
        elif form_field.field_type == FieldType.SELECT:
            # Handle common dropdowns with smart matching
            if "authorization" in combined or "work auth" in combined:
                return self.profile.work_authorization
            if "sponsor" in combined:
                return self.profile.requires_sponsorship
            if "graduation" in combined or "grad date" in combined:
                return f"{self.profile.graduation_month} {self.profile.graduation_year}"
            # Check answer bank for this question
            stored = self.answer_bank.get_answer(form_field.label, self.company)
            if stored:
                return stored
            return None

        # For any field, check the answer bank as last resort
        stored = self.answer_bank.get_answer(form_field.label, self.company)
        if stored:
            return stored

        return None

    def _get_dropdown_options(self, element) -> list[tuple[str, str]]:
        """Get all options from a dropdown as (value, text) tuples."""
        options = []
        try:
            option_elements = element.query_selector_all("option")
            for opt in option_elements:
                value = opt.get_attribute("value") or ""
                text = opt.inner_text().strip()
                if value or text:  # Skip empty options
                    options.append((value, text))
        except Exception:
            pass
        return options

    def _ask_user_for_field(self, form_field: FormField, element) -> Optional[str]:
        """Interactively ask user to provide a value for an unknown field."""
        if not self.interactive:
            return None

        print(f"\n{'='*60}")
        print(f"UNKNOWN FIELD: {form_field.label}")
        print(f"{'='*60}")
        print(f"Type: {form_field.field_type.value}")
        print(f"Required: {'Yes' if form_field.required else 'No'}")

        if form_field.field_type == FieldType.SELECT:
            options = self._get_dropdown_options(element)
            if options:
                print("\nAvailable options:")
                for i, (val, text) in enumerate(options, 1):
                    print(f"  {i}) {text}")

                print("\nEnter the number of your choice (or 's' to skip, 'v' to view in browser):")
                while True:
                    choice = input("> ").strip().lower()
                    if choice == 's':
                        return None
                    if choice == 'v':
                        print("Look at the browser window, then enter your choice...")
                        continue
                    try:
                        idx = int(choice) - 1
                        if 0 <= idx < len(options):
                            selected_value, selected_text = options[idx]
                            # Store for future use
                            self.answer_bank.store_answer(form_field.label, selected_value, self.company)
                            print(f"  Saved '{selected_text}' for future applications!")
                            return selected_value
                    except ValueError:
                        pass
                    print("Invalid choice. Enter a number, 's' to skip, or 'v' to view browser.")
        else:
            print("\nEnter your answer (or 's' to skip):")
            answer = input("> ").strip()
            if answer.lower() == 's':
                return None
            if answer:
                # Store for future use
                self.answer_bank.store_answer(form_field.label, answer, self.company)
                print(f"  Saved for future applications!")
                return answer

        return None

    def _fill_field(self, form_field: FormField, value: str) -> bool:
        """Fill a single field with a value."""
        try:
            element = self.page.query_selector(form_field.selector)
            if not element:
                return False

            if form_field.field_type == FieldType.FILE:
                if value and Path(value).exists():
                    element.set_input_files(value)
                else:
                    return False
            elif form_field.field_type == FieldType.SELECT:
                # Try to select by value first, then by label text
                try:
                    element.select_option(value, timeout=5000)
                except Exception:
                    # Try matching by partial text in option labels
                    options = element.query_selector_all("option")
                    for opt in options:
                        opt_text = opt.inner_text().lower()
                        opt_value = opt.get_attribute("value") or ""
                        if value.lower() in opt_text or value.lower() in opt_value.lower():
                            element.select_option(value=opt_value, timeout=5000)
                            return True
                    # If no match found, skip this field
                    return False
            elif form_field.field_type == FieldType.CHECKBOX:
                if not element.is_checked():
                    element.check()
            else:
                # Text, email, phone, url, textarea
                element.fill(value)

            return True

        except Exception as e:
            print(f"Error filling {form_field.selector}: {e}")
            return False

    def _pause_before_submit(self):
        """Pause and wait for user confirmation before any submission."""
        if self.skip_pause:
            print("\n[Headless mode: skipping pause]")
            return

        print("\n" + "=" * 60)
        print("PAUSED BEFORE SUBMIT")
        print("=" * 60)
        print("Form has been filled. Review the form in the browser.")
        print("The submit button has NOT been clicked.")
        print("\nPress Enter to close the browser...")
        print("(To submit, do it manually in the browser window)")
        try:
            input()
        except EOFError:
            pass  # Handle non-interactive mode

    def fill_workday_form(self, url: str, company: str = None) -> FormAnalysis:
        """Special handling for Workday forms with login flow."""
        self.company = company
        self.unfilled_fields = []

        analysis = FormAnalysis(
            form_type=FormType.WORKDAY,
            url=url,
            analyzed_at=datetime.now().isoformat(),
        )

        try:
            # Step 1: Navigate to job page
            print("\n[Step 1] Opening job page...")
            self.page.goto(url, wait_until="networkidle", timeout=60000)
            time.sleep(3)

            # Step 2: Look for and click Apply button
            print("[Step 2] Looking for Apply button...")
            apply_clicked = False

            # Common Workday Apply button selectors
            apply_selectors = [
                'a[data-automation-id="jobPostingApplyButton"]',
                'button[data-automation-id="jobPostingApplyButton"]',
                '[data-automation-id="applyButton"]',
                'a:has-text("Apply")',
                'button:has-text("Apply")',
                'a.css-1uoqz99',  # Common Workday class
                '[aria-label*="Apply"]',
            ]

            for selector in apply_selectors:
                try:
                    apply_btn = self.page.query_selector(selector)
                    if apply_btn and apply_btn.is_visible():
                        print(f"  Found Apply button: {selector}")
                        apply_btn.click()
                        apply_clicked = True
                        time.sleep(3)
                        break
                except Exception:
                    continue

            if not apply_clicked:
                print("  Could not find Apply button automatically.")
                print("  Please click the Apply button in the browser.")
                input("  Press Enter after clicking Apply...")

            # Step 2b: Look for "Apply with Resume" or similar secondary button
            print("[Step 2b] Looking for 'Apply with Resume' button...")
            time.sleep(2)

            apply_resume_selectors = [
                'button[data-automation-id="applyWithResume"]',
                'a[data-automation-id="applyWithResume"]',
                '[data-automation-id="applyManually"]',
                'button:has-text("Apply with Resume")',
                'a:has-text("Apply with Resume")',
                'button:has-text("Apply Manually")',
                'a:has-text("Apply Manually")',
                'button:has-text("Upload Resume")',
                '[aria-label*="Apply with Resume"]',
                '[aria-label*="Apply Manually"]',
            ]

            for selector in apply_resume_selectors:
                try:
                    btn = self.page.query_selector(selector)
                    if btn and btn.is_visible():
                        print(f"  Found 'Apply with Resume' button: {selector}")
                        btn.click()
                        time.sleep(3)
                        break
                except Exception:
                    continue

            # Step 3: Check if login is required
            print("\n[Step 3] Checking for login requirement...")
            time.sleep(2)

            # Check for common login indicators
            login_indicators = [
                '[data-automation-id="signIn"]',
                'input[data-automation-id="email"]',
                'input[type="password"]',
                '[data-automation-id="createAccountLink"]',
                'button:has-text("Sign In")',
                'a:has-text("Sign In")',
                '[data-automation-id="signInLink"]',
            ]

            needs_login = False
            for selector in login_indicators:
                try:
                    if self.page.query_selector(selector):
                        needs_login = True
                        break
                except Exception:
                    continue

            if needs_login:
                print("\n" + "=" * 60)
                print("LOGIN REQUIRED")
                print("=" * 60)
                print("Please log in to your Workday account in the browser.")
                print("(Create an account if you don't have one)")
                print("\nAfter logging in and reaching the application form,")
                input("press Enter to continue with autofill...")

                # Wait a moment for the page to stabilize after login
                time.sleep(3)

            # Step 4: Now we should be on the application form
            print("\n[Step 4] Detecting form fields...")

            # Wait for form to load
            try:
                self.page.wait_for_selector('[data-automation-id]', timeout=15000)
            except Exception:
                pass

            time.sleep(2)

            # Detect fields
            fields = self._detect_fields()
            analysis.fields_detected = fields
            print(f"  Found {len(fields)} fields")

            # Step 5: Fill fields
            print("\n[Step 5] Filling form fields...")
            patterns = WORKDAY_FIELD_PATTERNS
            filled_count = 0
            failed_count = 0
            skipped_count = 0

            for form_field in fields:
                try:
                    value = self._get_value_for_field(form_field, patterns)

                    # If no automatic value, try interactive mode
                    if not value and self.interactive:
                        element = self.page.query_selector(form_field.selector)
                        if element:
                            value = self._ask_user_for_field(form_field, element)

                    if value:
                        success = self._fill_field(form_field, value)
                        if success:
                            form_field.filled = True
                            form_field.value = value
                            filled_count += 1
                            print(f"  [FILLED] {form_field.label}: {value[:30]}{'...' if len(str(value)) > 30 else ''}")
                        else:
                            failed_count += 1
                            form_field.error = "Failed to fill"
                            print(f"  [FAILED] {form_field.label}")
                    else:
                        skipped_count += 1
                        self.unfilled_fields.append(form_field)
                        print(f"  [SKIPPED] {form_field.label}")
                except Exception as e:
                    failed_count += 1
                    form_field.error = str(e)
                    print(f"  [ERROR] {form_field.label}: {e}")

            analysis.fields_filled = filled_count
            analysis.fields_failed = failed_count
            total = len(fields)
            analysis.success_rate = filled_count / total if total > 0 else 0.0

            print(f"\nSummary: {filled_count} filled, {skipped_count} skipped, {failed_count} failed")

            # Take screenshot
            SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = SCREENSHOTS_DIR / f"workday_filled_{timestamp}.png"
            self.page.screenshot(path=str(screenshot_path), full_page=True)
            analysis.screenshot_path = str(screenshot_path)

            # Step 6: Pause before submit
            self._pause_before_submit()

        except Exception as e:
            analysis.error = str(e)
            print(f"\nError: {e}")

        return analysis


# =============================================================================
# Mock Form Testing
# =============================================================================


def run_mock_form_test(profile: ApplicantProfile, headless: bool = False) -> list[FormAnalysis]:
    """Test autofill against local mock forms."""
    results = []

    mock_forms = [
        ("greenhouse_mock.html", FormType.MOCK_GREENHOUSE),
        ("lever_mock.html", FormType.MOCK_LEVER),
    ]

    for filename, expected_type in mock_forms:
        mock_path = MOCK_FORMS_DIR / filename
        if not mock_path.exists():
            print(f"Mock form not found: {mock_path}")
            continue

        url = f"file://{mock_path.absolute()}"
        print(f"\nTesting mock form: {filename}")

        with AutofillEngine(profile, headless=headless) as engine:
            analysis = engine.fill_form(url, dry_run=True)
            results.append(analysis)

            print(f"  Form type: {analysis.form_type.value}")
            print(f"  Fields detected: {len(analysis.fields_detected)}")
            print(f"  Fields filled: {analysis.fields_filled}")
            print(f"  Success rate: {analysis.success_rate:.1%}")
            if analysis.error:
                print(f"  Error: {analysis.error}")

    return results


def run_recon(url: str, profile: ApplicantProfile, headless: bool = False) -> FormAnalysis:
    """Run reconnaissance on a real form (analyze only, no filling)."""
    print(f"\nReconnaissance: {url}")

    with AutofillEngine(profile, headless=headless) as engine:
        analysis = engine.analyze_form(url)

        print(f"  Form type: {analysis.form_type.value}")
        print(f"  Fields detected: {len(analysis.fields_detected)}")

        print("\n  Detected fields:")
        for field in analysis.fields_detected:
            req = "*" if field.required else ""
            print(f"    - [{field.field_type.value}] {field.label}{req}")
            print(f"      Selector: {field.selector}")

        if analysis.screenshot_path:
            print(f"\n  Screenshot: {analysis.screenshot_path}")

        if analysis.error:
            print(f"  Error: {analysis.error}")

        return analysis


def extract_company_from_url(url: str) -> str | None:
    """Extract company name from a Greenhouse, Lever, or Workday URL."""
    import re
    # Greenhouse: https://boards.greenhouse.io/company/...
    match = re.search(r'boards\.greenhouse\.io/([^/]+)', url)
    if match:
        return match.group(1)
    # Lever: https://jobs.lever.co/company/...
    match = re.search(r'jobs\.lever\.co/([^/]+)', url)
    if match:
        return match.group(1)
    # Workday: https://company.wd5.myworkdayjobs.com/... or similar
    match = re.search(r'([^.]+)\.wd\d+\.myworkdayjobs\.com', url)
    if match:
        return match.group(1)
    # Workday alternate: https://workday.com/company/...
    match = re.search(r'myworkdayjobs\.com/([^/]+)', url)
    if match:
        return match.group(1)
    return None


def run_dryrun(url: str, profile: ApplicantProfile, headless: bool = False) -> FormAnalysis:
    """Run dry-run on a real form (fill but pause before submit)."""
    company = extract_company_from_url(url)
    form_type = None

    # Detect form type from URL
    url_lower = url.lower()
    if "workday" in url_lower or "myworkdayjobs" in url_lower:
        form_type = FormType.WORKDAY

    print(f"\nDry run: {url}")
    if company:
        print(f"Company: {company}")
    if form_type == FormType.WORKDAY:
        print("\n[WORKDAY DETECTED]")
        print("Workday apps will open in your browser for manual completion.")
        print("(No autofill - Workday is too complex for automation)")
        confirm = input("\nOpen in browser? (y/n): ")
    else:
        print("\nWARNING: This will fill a REAL application form.")
        print("The form will NOT be submitted - you can review and submit manually.")
        print("For unknown fields, you'll be asked to provide answers (saved for next time).")
        confirm = input("\nContinue? (y/n): ")

    if confirm.lower() != "y":
        print("Aborted.")
        return FormAnalysis(
            form_type=FormType.UNKNOWN,
            url=url,
            error="Aborted by user",
            analyzed_at=datetime.now().isoformat(),
        )

    # Special handling for Workday - just open the URL, no autofill
    if form_type == FormType.WORKDAY:
        import webbrowser
        print("\n[WORKDAY] Opening in your default browser...")
        print("Workday applications are manual-only (no autofill).")
        webbrowser.open(url)
        print("\nApplication opened. Complete it manually.")
        return FormAnalysis(
            form_type=FormType.WORKDAY,
            url=url,
            analyzed_at=datetime.now().isoformat(),
            fields_filled=0,
            success_rate=0.0,
        )

    with AutofillEngine(profile, headless=headless, interactive=True) as engine:
        analysis = engine.fill_form(url, dry_run=True, company=company)

        print(f"\n  Form type: {analysis.form_type.value}")
        print(f"  Fields filled: {analysis.fields_filled}/{len(analysis.fields_detected)}")
        print(f"  Success rate: {analysis.success_rate:.1%}")

        if analysis.screenshot_path:
            print(f"\n  Screenshot: {analysis.screenshot_path}")

        return analysis


# =============================================================================
# Report Generation
# =============================================================================


def print_report(analyses: list[FormAnalysis]):
    """Print a summary report of autofill testing."""
    print("\n" + "=" * 60)
    print("AUTOFILL POC REPORT")
    print("=" * 60)

    total_fields = sum(len(a.fields_detected) for a in analyses)
    total_filled = sum(a.fields_filled for a in analyses)
    total_failed = sum(a.fields_failed for a in analyses)

    print(f"Forms tested: {len(analyses)}")
    print(f"Total fields detected: {total_fields}")
    print(f"Total fields filled: {total_filled}")
    print(f"Total fields failed: {total_failed}")

    if total_fields > 0:
        overall_rate = total_filled / total_fields
        print(f"Overall fill rate: {overall_rate:.1%}")

    # Per-form breakdown
    print("\n" + "-" * 60)
    print("PER-FORM BREAKDOWN")
    print("-" * 60)

    for analysis in analyses:
        print(f"\n  {analysis.form_type.value}: {analysis.url}")
        print(f"    Fields: {len(analysis.fields_detected)}")
        print(f"    Filled: {analysis.fields_filled}")
        print(f"    Rate: {analysis.success_rate:.1%}")
        if analysis.error:
            print(f"    Error: {analysis.error}")


def save_report(analyses: list[FormAnalysis], output_dir: Path):
    """Save the autofill report to JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = output_dir / f"autofill_report_{timestamp}.json"

    # Convert to serializable dict
    data = [asdict(a) for a in analyses]
    for item in data:
        item["form_type"] = item["form_type"].value if item["form_type"] else None
        for field in item.get("fields_detected", []):
            field["field_type"] = field["field_type"].value if field["field_type"] else None

    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, default=str)

    print(f"\nReport saved to: {filepath}")
    return filepath


def check_success_criteria(analyses: list[FormAnalysis]):
    """Check if POC meets success criteria."""
    print("\n" + "=" * 60)
    print("SUCCESS CRITERIA CHECK")
    print("=" * 60)

    # Check form type detection
    type_detection_correct = all(
        a.form_type != FormType.UNKNOWN for a in analyses if not a.error
    )

    # Check field detection rate
    total_fields = sum(len(a.fields_detected) for a in analyses)
    field_detection_ok = total_fields > 0

    # Check fill success rate
    total_filled = sum(a.fields_filled for a in analyses)
    fill_rate = total_filled / total_fields if total_fields > 0 else 0
    fill_rate_ok = fill_rate >= 0.90

    # No submissions (hard requirement)
    no_submissions = True  # We never submit in this POC

    criteria = [
        ("Form type detection (100%)", type_detection_correct, type_detection_correct),
        ("Field detection (>0 fields)", field_detection_ok, total_fields),
        ("Fill success rate (>=90%)", fill_rate_ok, f"{fill_rate:.1%}"),
        ("Zero submissions", no_submissions, no_submissions),
    ]

    all_passed = True
    for name, passed, value in criteria:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}: {value}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("POC #2 RESULT: SUCCESS - Autofill is feasible!")
    else:
        print("POC #2 RESULT: PARTIAL - Some criteria not met")
    print("=" * 60)


# =============================================================================
# Main Execution
# =============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="POC: Test Playwright form autofill"
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["mock", "recon", "dryrun"],
        default="mock",
        help="Test mode: mock (local forms), recon (analyze real form), dryrun (fill real form)",
    )
    parser.add_argument(
        "--url",
        type=str,
        help="URL for recon or dryrun mode",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode",
    )
    parser.add_argument(
        "--resume",
        type=str,
        help="Path to resume PDF for testing file upload",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="poc/reports",
        help="Output directory for reports",
    )

    args = parser.parse_args()

    # Load profile from file, or use defaults
    if PROFILE_PATH.exists():
        profile = ApplicantProfile.load_from_file()
        print("=" * 60)
        print("PLAYWRIGHT AUTOFILL POC")
        print("=" * 60)
        print(f"Loaded profile: {profile.full_name} ({profile.email})")
    else:
        profile = ApplicantProfile()
        print("=" * 60)
        print("PLAYWRIGHT AUTOFILL POC")
        print("=" * 60)
        print("WARNING: No profile found. Using test data.")
        print("Run 'python poc/setup_profile.py' to create your profile.")

    # Override resume path if provided via command line
    if args.resume:
        profile.resume_path = args.resume

    print(f"Mode: {args.mode}")
    if args.url:
        print(f"URL: {args.url}")
    print(f"Headless: {args.headless}")
    if profile.resume_path:
        print(f"Resume: {profile.resume_path}")

    analyses = []

    if args.mode == "mock":
        analyses = run_mock_form_test(profile, headless=args.headless)
    elif args.mode == "recon":
        if not args.url:
            print("ERROR: --url is required for recon mode")
            sys.exit(1)
        analysis = run_recon(args.url, profile, headless=args.headless)
        analyses = [analysis]
    elif args.mode == "dryrun":
        if not args.url:
            print("ERROR: --url is required for dryrun mode")
            sys.exit(1)
        analysis = run_dryrun(args.url, profile, headless=args.headless)
        analyses = [analysis]

    if analyses:
        print_report(analyses)
        save_report(analyses, Path(args.output))
        check_success_criteria(analyses)


if __name__ == "__main__":
    main()
