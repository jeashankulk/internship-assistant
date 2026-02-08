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
    degree: str = "Bachelor's"
    major: str = "Computer Science"
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
            degree=data.get("degree", "Bachelor's"),
            major=data.get("major", ""),
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
    iframe_url: str = ""  # URL of the iframe if the field is inside one


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

        # AI SETUP
        try:
            from app.ai.llm import LLMClient
            self.llm = LLMClient()
        except Exception as e:
            print(f"[WARNING] AI initialization failed: {e}")
            self.llm = None

        # Load resume text if available
        self.resume_text = ""
        if self.profile.resume_path and Path(self.profile.resume_path).exists():
            if self.profile.resume_path.lower().endswith('.pdf'):
                try:
                    from pypdf import PdfReader
                    reader = PdfReader(self.profile.resume_path)
                    for page in reader.pages:
                        self.resume_text += page.extract_text() + "\n"
                except Exception as e:
                    print(f"[WARNING] Failed to load resume text: {e}")

    def __enter__(self):
        from playwright.sync_api import sync_playwright

        self.playwright = sync_playwright().start()

        if self.stealth:
            # Use persistent context with stealth settings to avoid bot detection
            # This makes the browser appear more like a real user's browser
            user_data_dir = STORAGE_DIR / "browser_profile"
            user_data_dir.mkdir(parents=True, exist_ok=True)

            try:
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
                    viewport={'width': 1200, 'height': 900},
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    locale='en-US',
                    timezone_id='America/New_York',
                )
                self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
                self._is_persistent_context = True
            except Exception as e:
                # If persistent context fails (profile locked/corrupted), fall back to regular browser
                print(f"[WARNING] Persistent browser context failed: {e}")
                print("[INFO] Falling back to fresh browser session...")

                # Try to clean up corrupted profile
                import shutil
                try:
                    if user_data_dir.exists():
                        shutil.rmtree(user_data_dir)
                        print(f"[INFO] Removed corrupted browser profile at {user_data_dir}")
                except Exception:
                    pass

                # Launch regular browser with stealth settings
                self.browser = self.playwright.chromium.launch(
                    headless=self.headless,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--no-sandbox',
                    ],
                )
                self.context = self.browser.new_context(
                    viewport={'width': 1200, 'height': 900},
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    locale='en-US',
                    timezone_id='America/New_York',
                )
                self.page = self.context.new_page()
                self._is_persistent_context = False

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
            self._is_persistent_context = False

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Close resources gracefully to avoid Chrome "unexpectedly quit" errors
        try:
            if self.context:
                self.context.close()
        except Exception:
            pass

        # Only close browser if we created one (non-persistent context case)
        if not getattr(self, '_is_persistent_context', True):
            try:
                if self.browser:
                    self.browser.close()
            except Exception:
                pass

        try:
            if self.playwright:
                self.playwright.stop()
        except Exception:
            pass

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

    def _click_apply_button_if_present(self) -> bool:
        """Click Apply button if we're on a job description page (not the form yet).

        Handles the case where clicking Apply opens a new tab - switches to new tab
        and closes the old one.
        """
        # First, check if we're already on an application form
        # Look for typical form input fields (name, email, resume upload, etc.)
        # But be strict - need multiple indicators to be sure it's a real form
        form_indicators = [
            'input[name*="name" i]',
            'input[name*="email" i]',
            'input[type="file"]',
            'input[name*="resume" i]',
            'input[name*="phone" i]',
            '#first_name',
            '#last_name',
            '#email',
        ]
        form_field_count = 0
        for indicator in form_indicators:
            try:
                el = self.page.query_selector(indicator)
                if el and el.is_visible():
                    form_field_count += 1
            except:
                continue

        # Only skip if we find at least 2 form indicators (to avoid false positives)
        if form_field_count >= 2:
            print(f"  [AUTO-CLICK] Already on form (found {form_field_count} form fields), skipping Apply button search")
            return False

        print(f"  [AUTO-CLICK] Found {form_field_count} form indicators, looking for Apply button...")

        apply_selectors = [
            # Greenhouse selectors
            'a[data-job-action="apply"]',
            '#apply_button',
            'a.job-board-apply-link',
            '.job-post-actions a:has-text("Apply")',
            'a.application-link',
            # Company-hosted Greenhouse pages
            'a[href*="#application"]',
            'a[href*="#app"]',
            'button[data-test*="apply"]',
            'a[data-test*="apply"]',
            '[class*="apply-button"]',
            '[class*="ApplyButton"]',
            '[class*="apply_button"]',
            # Generic Apply buttons
            'a:has-text("Apply for this job")',
            'a:has-text("Apply Now")',
            'a:has-text("Apply for this position")',
            'button:has-text("Apply for this job")',
            'button:has-text("Apply Now")',
            'button:has-text("Apply for this position")',
            # Lever selectors
            'a.postings-btn-wrapper',
            'a[href*="/apply"]',
            'a.posting-btn-submit',
            # Last resort - generic Apply text
            'a:has-text("Apply")',
            'button:has-text("Apply")',
            # Even more generic - any clickable with Apply
            'div:has-text("Apply"):not(:has(div:has-text("Apply")))',  # Innermost div with Apply
            '[role="button"]:has-text("Apply")',
            'text=Apply',  # Playwright text selector
        ]

        print(f"  [AUTO-CLICK] Searching {len(apply_selectors)} selectors...")
        for selector in apply_selectors:
            try:
                btn = self.page.query_selector(selector)
                if btn and btn.is_visible():
                    # Check it's not a disabled or tiny button
                    box = btn.bounding_box()
                    if box and box['width'] > 30 and box['height'] > 15:
                        print(f"  [AUTO-CLICK] Found Apply button: {selector}")

                        old_page = self.page
                        old_url = self.page.url

                        # Use expect_page to catch new tab opening
                        try:
                            with self.context.expect_page(timeout=5000) as new_page_info:
                                btn.click()

                            # New tab was opened
                            new_page = new_page_info.value
                            print(f"  [AUTO-CLICK] New tab opened: {new_page.url[:60]}...")

                            # Wait for the new page to load
                            try:
                                new_page.wait_for_load_state("networkidle", timeout=10000)
                            except:
                                time.sleep(2)

                            # Switch to new page
                            self.page = new_page
                            print(f"  [AUTO-CLICK] Switched to new tab")

                            # Close old tab
                            try:
                                old_page.close()
                                print(f"  [AUTO-CLICK] Closed old tab")
                            except Exception as e:
                                print(f"  [AUTO-CLICK] Could not close old tab: {e}")

                        except Exception as e:
                            # No new tab opened - check if same page navigated
                            print(f"  [AUTO-CLICK] No new tab (clicking in same page)")
                            time.sleep(2)
                            try:
                                new_url = self.page.url
                                if new_url != old_url:
                                    print(f"  [AUTO-CLICK] Page navigated to: {new_url[:60]}...")
                            except:
                                pass

                        return True
            except Exception as e:
                print(f"  [AUTO-CLICK] Error with selector {selector}: {e}")
                continue

        # Debug: print what clickable elements exist on the page with "apply" text
        print("  [AUTO-CLICK] No Apply button found. Searching for any Apply-like elements...")
        try:
            # Search all elements, not just a/button
            apply_elements = self.page.query_selector_all('a, button, div, span, [role="button"], [onclick]')
            found_any = False
            for el in apply_elements[:100]:  # Check first 100 elements
                try:
                    text = el.inner_text().strip().lower()
                    if 'apply' in text and len(text) < 50:
                        href = el.get_attribute('href') or ''
                        classes = el.get_attribute('class') or ''
                        tag = el.evaluate('el => el.tagName')
                        print(f"  [AUTO-CLICK] Found '{tag}' with 'apply': text='{text[:30]}', class='{classes[:40]}'")
                        found_any = True
                except:
                    pass
            if not found_any:
                # Print page title and some content to verify page loaded
                title = self.page.title()
                print(f"  [AUTO-CLICK] Page title: '{title}'")
                body_text = self.page.inner_text('body')[:200]
                print(f"  [AUTO-CLICK] Page content preview: '{body_text[:100]}...'")
        except Exception as e:
            print(f"  [AUTO-CLICK] Error searching for apply elements: {e}")

        return False

    def _inject_autofill_button(self):
        """Inject a floating status indicator onto the page."""
        self.page.evaluate("""
            // Remove existing container if any
            const existing = document.getElementById('autofill-helper-container');
            if (existing) existing.remove();

            // Create floating status container
            const container = document.createElement('div');
            container.id = 'autofill-helper-container';
            container.style.cssText = `
                position: fixed;
                top: 10px;
                right: 10px;
                z-index: 99999;
                display: flex;
                flex-direction: column;
                gap: 4px;
                background: rgba(255,255,255,0.95);
                padding: 10px 14px;
                border-radius: 8px;
                box-shadow: 0 4px 15px rgba(0,0,0,0.15);
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            `;

            // Create header
            const header = document.createElement('div');
            header.id = 'autofill-helper-btn';
            header.innerHTML = '🤖 Autofill Assistant';
            header.style.cssText = `
                font-size: 13px;
                font-weight: bold;
                color: #333;
            `;

            // Create status text
            const status = document.createElement('div');
            status.id = 'autofill-status';
            status.style.cssText = `
                font-size: 11px;
                color: #666;
            `;
            status.textContent = 'Use main UI button to autofill';

            container.appendChild(header);
            container.appendChild(status);
            document.body.appendChild(container);
        """)

    def _update_autofill_button_status(self, message: str, success: bool = True):
        """Update the injected button's status message."""
        color = '#22c55e' if success else '#ef4444'
        self.page.evaluate(f"""
            const btn = document.getElementById('autofill-helper-btn');
            const status = document.getElementById('autofill-status');
            if (btn) {{
                btn.innerHTML = '🔄 Autofill';
                btn.disabled = false;
            }}
            if (status) {{
                status.textContent = '{message}';
                status.style.color = '{color}';
            }}
        """)

    def _check_autofill_requested(self) -> bool:
        """Check if user clicked the injected Autofill button."""
        try:
            requested = self.page.evaluate("window.__AUTOFILL_REQUESTED__")
            if requested:
                self.page.evaluate("window.__AUTOFILL_REQUESTED__ = false")
                return True
        except Exception:
            pass
        return False

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

            # Inject the floating Autofill button onto the page
            self._inject_autofill_button()

            # Try to click Apply button if we're on a job description page
            # This handles cases where the URL goes to job listing, not the form
            if self._click_apply_button_if_present():
                print("  [INFO] Clicked Apply button, waiting for form to load...")
                time.sleep(2)
                # Re-inject button after page navigation
                self._inject_autofill_button()

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
        # Find all input elements - include Workday-specific selectors
        # Store (element, iframe_url) tuples
        all_elements = []

        try:
            # 1. Main Page
            main_inputs = self.page.query_selector_all(
                "input, select, textarea, "
                "[data-automation-id*='input'], "
                "[data-automation-id*='textInput'], "
                "[data-automation-id*='dropdown'], "
                "[role='textbox'], "
                "[role='combobox']"
            )
            print(f"  [DEBUG] Found {len(main_inputs)} total input elements on main page")
            for el in main_inputs:
                all_elements.append((el, ""))

            # 2. Iframes
            iframes = self.page.frames
            if len(iframes) > 1:
                print(f"  [DEBUG] Page has {len(iframes)} frames - checking all")
                for frame in iframes:
                    try:
                        if frame == self.page.main_frame:
                            continue
                        frame_url = frame.url
                        frame_inputs = frame.query_selector_all("input, select, textarea")
                        # print(f"  [DEBUG] Found {len(frame_inputs)} inputs in iframe: {frame_url[:50]}...")
                        for el in frame_inputs:
                            all_elements.append((el, frame_url))
                    except:
                        pass
        except Exception as e:
            print(f"  [DEBUG] Error checking iframes: {e}")

        visible_count = 0
        skipped_hidden_count = 0

        for item in all_elements:
            try:
                element = item[0]
                iframe_url = item[1]
                # Use a lenient visibility check - only skip if truly hidden
                # (display:none, visibility:hidden, or type=hidden)
                try:
                    is_hidden = element.evaluate("""el => {
                        const style = window.getComputedStyle(el);
                        // Only skip if explicitly hidden
                        if (style.display === 'none') return true;
                        if (style.visibility === 'hidden') return true;
                        if (el.type === 'hidden') return true;
                        // Check if inside a hidden parent
                        let parent = el.parentElement;
                        while (parent) {
                            const parentStyle = window.getComputedStyle(parent);
                            if (parentStyle.display === 'none') return true;
                            parent = parent.parentElement;
                        }
                        return false;
                    }""")
                except:
                    is_hidden = False  # Assume visible if check fails

                if is_hidden:
                    skipped_hidden_count += 1
                    continue
                visible_count += 1

                tag_name = element.evaluate("el => el.tagName.toLowerCase()")
                input_type = element.get_attribute("type") or "text"
                name = element.get_attribute("name") or ""
                id_attr = element.get_attribute("id") or ""
                placeholder = element.get_attribute("placeholder") or ""
                required = element.get_attribute("required") is not None

                # Skip elements inside cookie consent dialogs (but log it)
                if self._is_inside_cookie_banner(element):
                    print(f"  [DEBUG] Skipping cookie banner field: {name or id_attr}")
                    continue

                # Skip fields with cookie-related names/ids
                field_text = f"{name} {id_attr} {placeholder}".lower()
                if self._is_cookie_related(field_text):
                    print(f"  [DEBUG] Skipping cookie-related field: {name or id_attr}")
                    continue

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

                # Build selector - try multiple strategies
                selector = self._build_selector(element, id_attr, name, placeholder, tag_name, input_type)
                if not selector:
                    print(f"  [DEBUG] Skipping field - no valid selector found")
                    continue

                # Get label
                label = self._find_label(element, name, id_attr, placeholder)

                # Skip fields with noise/meaningless labels
                if self._is_noise_label(label, name, id_attr):
                    print(f"  [DEBUG] Skipping noise label: '{label}' (name={name}, id={id_attr})")
                    continue

                print(f"  [DEBUG] Found valid field: '{label}' (type={field_type}, selector={selector})")
                field = FormField(
                    field_type=field_type,
                    label=label,
                    selector=selector,
                    name=name,
                    required=required,
                    iframe_url=iframe_url
                )
                fields.append(field)

            except Exception as e:
                # Skip fields that can't be processed
                print(f"  [DEBUG] Error processing element: {e}")
                continue

        print(f"  [DEBUG] Summary: {visible_count} visible, {skipped_hidden_count} hidden, {len(fields)} valid fields")
        return fields

    def _build_selector(self, element, id_attr: str, name: str, placeholder: str,
                         tag_name: str, input_type: str) -> str:
        """Build a unique CSS selector for a form field."""
        # Strategy 1: Use id
        if id_attr:
            return f"#{id_attr}"

        # Strategy 2: Use name
        if name:
            return f'[name="{name}"]'

        # Strategy 3: Use data attributes
        try:
            data_attrs = element.evaluate("""el => {
                const attrs = {};
                for (const attr of el.attributes) {
                    if (attr.name.startsWith('data-') && attr.value) {
                        attrs[attr.name] = attr.value;
                    }
                }
                return attrs;
            }""")
            # Prefer specific data attributes
            for attr_name in ['data-automation-id', 'data-testid', 'data-field', 'data-qa']:
                if attr_name in data_attrs:
                    return f'[{attr_name}="{data_attrs[attr_name]}"]'
            # Use any unique data attribute
            if data_attrs:
                attr_name, attr_val = next(iter(data_attrs.items()))
                return f'[{attr_name}="{attr_val}"]'
        except:
            pass

        # Strategy 4: Use aria-label
        try:
            aria_label = element.get_attribute("aria-label")
            if aria_label:
                # Escape quotes in aria-label
                aria_label_escaped = aria_label.replace('"', '\\"')
                return f'[aria-label="{aria_label_escaped}"]'
        except:
            pass

        # Strategy 5: Use placeholder
        if placeholder:
            placeholder_escaped = placeholder.replace('"', '\\"')
            return f'[placeholder="{placeholder_escaped}"]'

        # Strategy 6: Use autocomplete attribute
        try:
            autocomplete = element.get_attribute("autocomplete")
            if autocomplete and autocomplete not in ['off', 'on']:
                return f'{tag_name}[autocomplete="{autocomplete}"]'
        except:
            pass

        # Strategy 7: Generate a unique path using nth-of-type
        try:
            selector = element.evaluate("""el => {
                const path = [];
                let current = el;
                while (current && current.tagName) {
                    let selector = current.tagName.toLowerCase();
                    if (current.id) {
                        return '#' + current.id + ' ' + path.join(' > ');
                    }
                    // Add nth-of-type if needed
                    const parent = current.parentElement;
                    if (parent) {
                        const siblings = parent.querySelectorAll(':scope > ' + selector);
                        if (siblings.length > 1) {
                            const index = Array.from(siblings).indexOf(current) + 1;
                            selector += ':nth-of-type(' + index + ')';
                        }
                    }
                    path.unshift(selector);
                    current = parent;
                    // Stop at form or main content
                    if (current && (current.tagName === 'FORM' || current.tagName === 'MAIN')) {
                        path.unshift(current.tagName.toLowerCase() + (current.id ? '#' + current.id : ''));
                        break;
                    }
                }
                return path.join(' > ');
            }""")
            if selector:
                return selector
        except:
            pass

        return ""

    def _is_inside_cookie_banner(self, element) -> bool:
        """Check if element is inside a cookie consent banner."""
        try:
            # Check if any ancestor has cookie-related class/id
            is_cookie = element.evaluate("""el => {
                let parent = el;
                while (parent) {
                    const id = (parent.id || '').toLowerCase();
                    const className = (parent.className || '').toLowerCase();
                    const role = (parent.getAttribute('role') || '').toLowerCase();

                    // Cookie banner indicators
                    if (id.includes('cookie') || id.includes('consent') ||
                        id.includes('gdpr') || id.includes('onetrust') ||
                        id.includes('cookiebot') || id.includes('cc-') ||
                        className.includes('cookie') || className.includes('consent') ||
                        className.includes('gdpr') || className.includes('onetrust') ||
                        className.includes('cookiebot') || className.includes('cc-banner') ||
                        role === 'dialog' && (id.includes('cookie') || className.includes('cookie'))) {
                        return true;
                    }
                    parent = parent.parentElement;
                }
                return false;
            }""")
            return is_cookie
        except:
            return False

    def _is_cookie_related(self, text: str) -> bool:
        """Check if field text suggests it's cookie-related."""
        cookie_keywords = [
            'cookie', 'consent', 'gdpr', 'tracking', 'analytics',
            'performance', 'functional', 'targeting', 'advertising',
            'onetrust', 'cookiebot', 'privacy-policy', 'cookie-policy'
        ]
        return any(kw in text for kw in cookie_keywords)

    def _is_noise_label(self, label: str, name: str = "", id_attr: str = "") -> bool:
        """Check if a label is noise/meaningless.

        We're more lenient here - only skip clearly cookie-related fields.
        Fields with 'Unknown' labels but valid names might still be legitimate.
        """
        label_lower = (label or "").lower().strip()
        name_lower = (name or "").lower()
        id_lower = (id_attr or "").lower()

        # Exact noise labels to skip (only if no meaningful name/id)
        noise_labels = [
            'checkbox label',
            'button',
            'submit',
            'cookie list search',
            'tothr',
        ]
        if label_lower in noise_labels:
            # But if it has a meaningful name, keep it
            if name_lower and not self._is_cookie_related(name_lower):
                return False
            return True

        # Cookie-related patterns to skip
        cookie_patterns = [
            'cookie',
            'consent',
            'gdpr',
            'onetrust',
            'cookiebot',
        ]
        if any(pattern in label_lower for pattern in cookie_patterns):
            return True
        if any(pattern in name_lower for pattern in cookie_patterns):
            return True
        if any(pattern in id_lower for pattern in cookie_patterns):
            return True

        return False

        return False

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

        # Try ID attribute as last resort (often contains semantic names like school--0)
        if id_attr:
             # Remove common suffixes/prefixes
             clean_id = id_attr.replace("--", " ").replace("-", " ").replace("_", " ")
             # Remove trailing numbers often used for arrays
             import re
             clean_id = re.sub(r'\d+$', '', clean_id).strip()
             if clean_id and len(clean_id) > 2:
                 return clean_id.title()

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

                element = self._get_element(form_field) if not value or form_field.field_type == FieldType.SELECT else None

                # If no automatic value, try interactive mode
                if not value and self.interactive:
                    element = self._get_element(form_field)
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

        # Update the injected button status
        if total == 0:
            self._update_autofill_button_status("No form fields found - navigate to form & click Autofill", success=False)
        elif filled_count == total:
            self._update_autofill_button_status(f"Filled all {filled_count} fields!", success=True)
        elif filled_count > 0:
            self._update_autofill_button_status(f"Filled {filled_count}/{total} fields", success=True)
        else:
            self._update_autofill_button_status("Could not fill fields - check form", success=False)

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
        # print(f"DEBUG: Checking field '{combined}' (Type: {form_field.field_type})")
        
        # Verify profile is loaded
        if "degree" in combined:
             print(f"DEBUG: Degree detected. Profile degree: '{self.profile.degree}'")

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
        elif any(x in combined for x in ["website", "portfolio", "personal"]) and len(combined) < 20:
            return self.profile.website
        elif form_field.field_type == FieldType.FILE:
            return self.profile.resume_path if self.profile.resume_path else None
        elif form_field.field_type == FieldType.TEXTAREA:
            if any(x in combined for x in ["cover", "letter", "why", "interest"]):
                return self.profile.cover_letter
            # Continue to AI/Bank for other textareas

        elif form_field.field_type == FieldType.SELECT:
             # Check answer bank (Exact match) first for SELECT (optimization)
             stored = self.answer_bank.get_answer(form_field.label, self.company)
             if stored:
                 return stored

        # --- FALLBACK FOR ALL FIELDS (Text, Select, TextArea, etc.) ---
        
        # 1. Check Answer Bank (Exact Match)
        stored = self.answer_bank.get_answer(form_field.label, self.company)
        if stored:
            return stored
            
        # 2. Check Answer Bank (AI Context Match)
        if self.llm and self.llm.is_available():
             print(f"  [AI] Checking answer bank context for: {form_field.label}...")
             context_match = self.llm.check_answer_bank(form_field.label, self.answer_bank.answers)
             if context_match:
                 print(f"  [AI] Found context match: {context_match[:30]}...")
                 return context_match

        # 3. AI Generate from Resume
        if self.llm and self.llm.is_available() and self.resume_text:
            print(f"  [AI] Generating answer from resume for: {form_field.label}...")
            
            # For Select fields, get options to constrain the AI
            options = []
            if form_field.field_type == FieldType.SELECT:
                options_tuples = self._get_dropdown_options(self._get_element(form_field))
                options = [text for _, text in options_tuples]
            
            # For pseudo-dropdowns (text fields acting as select), try to find options too?
            # Hard to get options if it's not a select tag. 
            # But the user mentioned "textbox/dropdowns". 
            # We'll rely on AI to generate a good string.
            
            generated = self.llm.generate_answer_from_resume(form_field.label, self.resume_text, options)
            if generated:
                print(f"  [AI] Generated: {generated[:30]}...")
                return generated

        return None

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
        return None

    def _get_element(self, form_field: FormField):
        """Get the element handle, handling iframes if necessary."""
        if form_field.iframe_url:
            # Find the frame
            for frame in self.page.frames:
                if frame.url == form_field.iframe_url:
                    return frame.query_selector(form_field.selector)
            # Fallback if frame URL changed or not found
            print(f"  [DEBUG] Frame not found for URL: {form_field.iframe_url[:30]}...")
            return None
        else:
            return self.page.query_selector(form_field.selector)

    def _fill_field(self, form_field: FormField, value: str) -> bool:
        """Fill a single field with a value."""
        try:
            print(f"DEBUG: _fill_field called for '{form_field.label}' with value '{value}'")
            element = self._get_element(form_field)
            if not element:
                 print(f"  [DEBUG] Element not found: {form_field.selector} (Frame: {form_field.iframe_url[:30]}...)")
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
                # Check if it's a "pseudo-dropdown" (text input that requires selection)
                try:
                    is_dropdown = False
                    placeholder = element.get_attribute("placeholder") or ""
                    outer_html = element.evaluate("el => el.outerHTML")
                    print(f"  [DEBUG] Checking text field: '{form_field.label}' | Placeholder: '{placeholder}' | HTML: {outer_html[:100]}...")
                    
                    if "select" in placeholder.lower() or "choose" in placeholder.lower():
                         is_dropdown = True
                    
                    # Also check for common "combobox" patterns
                    if element.get_attribute("role") == "combobox":
                        is_dropdown = True

                    # Check for class names indicating a dropdown/select input
                    class_attr = element.get_attribute("class") or ""
                    if "select" in class_attr.lower() or "dropdown" in class_attr.lower():
                        is_dropdown = True
                        
                    if is_dropdown:
                        print(f"  [DEBUG] Detected pseudo-dropdown: {form_field.label}")
                        # 1. Click to open
                        element.click()
                        self.page.wait_for_timeout(500)
                        # 2. Type value to filter
                        element.fill(value)
                        self.page.wait_for_timeout(1000)
                        # 3. Press Enter to select
                        element.press("Enter")
                    else:
                        element.fill(value)
                except Exception as e:
                     print(f"  [DEBUG] Error filling text field (falling back to standard fill): {e}")
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
