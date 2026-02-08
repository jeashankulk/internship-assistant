#!/usr/bin/env python3
"""
Web UI for Internship Application Assistant.
Simple Flask server that displays pending applications and handles apply workflow.
"""

import os
import json
import sys
import time
import webbrowser
from pathlib import Path
from flask import Flask, render_template, jsonify, request, redirect, url_for
from dotenv import load_dotenv

# Load environment variables from project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.sync.sheets import get_sheets_sync, JobApplication, AppliedJob, MANUAL_SHEET, AI_SEARCHED_SHEET, APPLIED_SHEET

app = Flask(__name__,
            template_folder=str(Path(__file__).parent / "templates"),
            static_folder=str(Path(__file__).parent / "static"))

# Global sheets sync instance - initialized lazily on first request
sheets_sync = None


def get_sync():
    """Get or create sheets sync instance with retry logic."""
    global sheets_sync
    if sheets_sync is None:
        # Try up to 3 times with delay between attempts
        import time
        for attempt in range(3):
            try:
                sheets_sync = get_sheets_sync()
                if sheets_sync:
                    break
            except Exception as e:
                if attempt < 2:
                    time.sleep(0.5)  # Brief delay before retry
                # On last attempt, just return None (don't crash)
    return sheets_sync


@app.route('/')
def index():
    """Main page - shows pending applications."""
    return render_template('index.html')


@app.route('/api/jobs')
def get_jobs():
    """API endpoint to get all pending jobs."""
    sync = get_sync()
    if not sync:
        return jsonify({
            'error': 'Google Sheets not configured. Please set GOOGLE_SPREADSHEET_ID in .env',
            'jobs': []
        })

    try:
        pending = sync.get_pending_jobs()
        jobs = []
        for job, source in pending:
            jobs.append({
                'company': job.company,
                'role': job.role,
                'link': job.link,
                'status': job.status,
                'date_posted': job.date_posted,
                'date_added': job.date_added,
                'platform': job.platform,
                'source': source,  # "Manual" or "AI Searched"
                'is_manual': source == MANUAL_SHEET,
            })
        return jsonify({'jobs': jobs, 'error': None})
    except Exception as e:
        return jsonify({'error': str(e), 'jobs': []})


@app.route('/api/jobs/applied', methods=['GET'])
def get_applied_jobs():
    """Get all applied jobs."""
    sync = get_sync()
    if not sync:
        return jsonify({'error': 'Google Sheets not configured', 'jobs': []})

    try:
        applied = sync.get_applied_jobs()
        jobs = []
        for job in applied:
            jobs.append({
                'company': job.company,
                'role': job.role,
                'link': job.link,
                'date_applied': job.date_applied,
                'platform': job.platform,
                'job_description': job.job_description,
            })
        return jsonify({'jobs': jobs, 'error': None})
    except Exception as e:
        return jsonify({'error': str(e), 'jobs': []})


@app.route('/api/jobs/applied', methods=['POST'])
def mark_applied():
    """Mark a job as applied and save to Applied sheet. Auto-fetches job description."""
    sync = get_sync()
    if not sync:
        return jsonify({'success': False, 'error': 'Google Sheets not configured'})

    data = request.json
    link = data.get('link')
    job_description = data.get('job_description', '')

    if not link:
        return jsonify({'success': False, 'error': 'No link provided'})

    # Auto-fetch job description if not provided
    if not job_description:
        try:
            import sys
            poc_path = str(Path(__file__).parent.parent.parent / "poc")
            if poc_path not in sys.path:
                sys.path.insert(0, poc_path)

            from poc_discovery import fetch_job_details
            result = fetch_job_details(link)

            if result.get('success'):
                job_description = result.get('description', '')
        except Exception as e:
            print(f"Auto-fetch description failed: {e}")
            # Continue without description

    try:
        success = sync.mark_as_applied_with_description(link, job_description)
        return jsonify({'success': success, 'description_fetched': bool(job_description)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/jobs/not-interested', methods=['POST'])
def mark_not_interested():
    """Mark a job as not interested."""
    sync = get_sync()
    if not sync:
        return jsonify({'success': False, 'error': 'Google Sheets not configured'})

    data = request.json
    link = data.get('link', '')

    if not link:
        return jsonify({'success': False, 'error': 'Link is required'})

    try:
        success = sync.mark_as_not_interested(link)
        return jsonify({'success': success})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/jobs/not-interested', methods=['GET'])
def get_not_interested_jobs():
    """Get all jobs marked as not interested."""
    sync = get_sync()
    if not sync:
        return jsonify({'error': 'Google Sheets not configured', 'jobs': []})

    try:
        not_interested = sync.get_not_interested_jobs()
        return jsonify({
            'jobs': [{
                'company': job.company,
                'role': job.role,
                'link': job.link,
                'date_dismissed': job.date_dismissed,
                'platform': job.platform,
            } for job in not_interested]
        })
    except Exception as e:
        return jsonify({'error': str(e), 'jobs': []})


@app.route('/api/jobs/restore', methods=['POST'])
def restore_job():
    """Restore a job from Not Interested back to pending."""
    sync = get_sync()
    if not sync:
        return jsonify({'success': False, 'error': 'Google Sheets not configured'})

    data = request.json
    link = data.get('link', '')

    if not link:
        return jsonify({'success': False, 'error': 'Link is required'})

    try:
        success = sync.restore_from_not_interested(link)
        return jsonify({'success': success})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/jobs/unapply', methods=['POST'])
def unapply_job():
    """Move a job from Applied back to pending (Manual sheet)."""
    sync = get_sync()
    if not sync:
        return jsonify({'success': False, 'error': 'Google Sheets not configured'})

    data = request.json
    link = data.get('link', '')

    if not link:
        return jsonify({'success': False, 'error': 'Link is required'})

    try:
        success = sync.unapply_job(link)
        return jsonify({'success': success})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/jobs/clear', methods=['POST'])
def clear_jobs():
    """Clear all jobs from a specific sheet."""
    sync = get_sync()
    if not sync:
        return jsonify({'success': False, 'error': 'Google Sheets not configured'})

    data = request.json
    sheet_type = data.get('type', '')  # 'pending' or 'not-interested'

    # Map type to sheet names
    from app.sync.sheets import MANUAL_SHEET, AI_SEARCHED_SHEET, NOT_INTERESTED_SHEET

    if sheet_type == 'pending':
        # Clear both Manual and AI Searched
        success1 = sync.clear_sheet(MANUAL_SHEET)
        success2 = sync.clear_sheet(AI_SEARCHED_SHEET)
        return jsonify({'success': success1 or success2})
    elif sheet_type == 'ai-searched':
        success = sync.clear_sheet(AI_SEARCHED_SHEET)
        return jsonify({'success': success})
    elif sheet_type == 'manual':
        success = sync.clear_sheet(MANUAL_SHEET)
        return jsonify({'success': success})
    elif sheet_type == 'not-interested':
        success = sync.clear_sheet(NOT_INTERESTED_SHEET)
        return jsonify({'success': success})
    else:
        return jsonify({'success': False, 'error': 'Invalid sheet type'})


@app.route('/api/jobs/fetch', methods=['POST'])
def fetch_job_from_url():
    """Fetch job details (company, role, description, platform) from a URL."""
    data = request.json
    url = data.get('url', '')

    if not url:
        return jsonify({'success': False, 'error': 'No URL provided'})

    try:
        # Optimization: parsing logic only supports Greenhouse and Lever
        # Check basic patterns before importing heavy discovery module
        is_supported = False
        url_lower = url.lower()
        if "greenhouse.io" in url_lower or "lever.co" in url_lower or "gh_jid" in url_lower:
             is_supported = True
             
        if not is_supported:
             return jsonify({
                'success': False,
                'error': 'URL not supported for auto-fetch (Greenhouse/Lever only). Please enter details manually.',
                'platform': None,
                'company': '',
                'role': '',
                'description': '',
                'location': None,
            })

        # Import the fetch function from poc_discovery
        import sys
        poc_path = str(Path(__file__).parent.parent.parent / "poc")
        if poc_path not in sys.path:
            sys.path.insert(0, poc_path)

        from poc_discovery import fetch_job_details

        result = fetch_job_details(url)
        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'platform': None,
            'company': '',
            'role': '',
            'description': '',
            'location': None,
        })


@app.route('/api/jobs/add', methods=['POST'])
def add_job():
    """Add a new job manually. Can auto-fetch details from URL."""
    sync = get_sync()
    if not sync:
        return jsonify({'success': False, 'error': 'Google Sheets not configured'})

    data = request.json
    link = data.get('link', '')

    if not link:
        return jsonify({'success': False, 'error': 'Link is required'})

    # If company/role not provided, try to fetch from URL
    company = data.get('company', '')
    role = data.get('role', '')
    platform = data.get('platform', 'other')

    if not company or not role:
        try:
            # Optimization: check if URL supports auto-fetch
            # If not, skip import/fetch to avoid potential issues/delays
            is_supported = False
            link_lower = link.lower()
            if "greenhouse.io" in link_lower or "lever.co" in link_lower or "gh_jid" in link_lower:
                is_supported = True
            
            if is_supported:
                import sys
                poc_path = str(Path(__file__).parent.parent.parent / "poc")
                if poc_path not in sys.path:
                    sys.path.insert(0, poc_path)
    
                from poc_discovery import fetch_job_details
                result = fetch_job_details(link)
    
                if result.get('success'):
                    if not company:
                        company = result.get('company', '')
                    if not role:
                        role = result.get('role', '')
                    if platform == 'other' and result.get('platform'):
                        platform = result.get('platform')
        except Exception as e:
            print(f"Auto-fetch failed: {e}")
            # Continue with provided/empty values

    if not company:
        return jsonify({'success': False, 'error': 'Company is required (could not auto-detect)'})

    job = JobApplication(
        company=company,
        role=role or 'Position',
        link=link,
        platform=platform,
        date_posted=data.get('date_posted', ''),
    )

    try:
        success = sync.add_job(job, MANUAL_SHEET)
        return jsonify({'success': success, 'company': company, 'role': role})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/open', methods=['POST'])
def open_link():
    """Open a job link - use autofill for Greenhouse/Lever, browser for others."""
    data = request.json
    link = data.get('link')
    platform = data.get('platform', '').lower()

    if not link:
        return jsonify({'success': False, 'error': 'No link provided'})

    try:
        link_lower = link.lower()

        # For Workday, just open in browser (too complex for autofill)
        if 'workday' in platform or 'workday' in link_lower or 'myworkdayjobs' in link_lower:
            webbrowser.open(link)
            return jsonify({'success': True, 'method': 'browser', 'message': 'Opened in browser (Workday - manual only)'})

        # For Greenhouse/Lever, run autofill and return unfilled fields
        if 'greenhouse' in link_lower or 'lever' in link_lower or platform in ['greenhouse', 'lever']:
            return run_autofill_and_get_questions(link)

        # Default: just open in browser
        webbrowser.open(link)
        return jsonify({'success': True, 'method': 'browser'})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


# Global to hold the current autofill session
current_autofill_session = {
    'engine': None,
    'url': None,
    'unfilled_fields': []
}


def _close_existing_session():
    """Helper to cleanly close any existing autofill session."""
    global current_autofill_session
    if current_autofill_session.get('engine'):
        print("  [SESSION] Closing existing session...")
        try:
            current_autofill_session['engine'].__exit__(None, None, None)
        except Exception as e:
            print(f"  [SESSION] Error closing session: {e}")
        current_autofill_session['engine'] = None
        current_autofill_session['url'] = None
        current_autofill_session['unfilled_fields'] = []


@app.route('/api/open-browser', methods=['POST'])
def open_browser_only():
    """Open a job link in Playwright browser without auto-filling."""
    global current_autofill_session

    data = request.json
    link = data.get('link')
    platform = data.get('platform', '').lower()

    if not link:
        return jsonify({'success': False, 'error': 'No link provided'})

    try:
        link_lower = link.lower()

        # For Workday, just open in regular browser
        if 'workday' in platform or 'workday' in link_lower or 'myworkdayjobs' in link_lower:
            webbrowser.open(link)
            return jsonify({'success': True, 'method': 'browser', 'message': 'Opened in browser (Workday - manual only)'})

        # Close any existing session properly
        _close_existing_session()

        # Import autofill components
        import sys
        poc_path = str(Path(__file__).parent.parent.parent / "poc")
        if poc_path not in sys.path:
            sys.path.insert(0, poc_path)

        from poc_autofill import AutofillEngine, ApplicantProfile, PROFILE_PATH

        # Load profile
        profile = ApplicantProfile.load_from_file(PROFILE_PATH)

        # Create engine with visible browser
        engine = AutofillEngine(profile, headless=False, skip_pause=True, interactive=False)
        engine.__enter__()

        # Store for later use
        current_autofill_session['engine'] = engine
        current_autofill_session['url'] = link
        current_autofill_session['unfilled_fields'] = []

        # Navigate to the page
        print(f"  [OPEN] Navigating to: {link[:60]}...")
        engine.page.goto(link, wait_until="networkidle", timeout=30000)
        time.sleep(2)
        print(f"  [OPEN] Page loaded: {engine.page.url[:60]}...")

        # Try to click Apply button if we're on a job description page
        print("  [OPEN] Checking for Apply button...")
        clicked = engine._click_apply_button_if_present()
        if clicked:
            print("  [OPEN] Clicked Apply button, waiting for form...")
            time.sleep(2)
            print(f"  [OPEN] Now on: {engine.page.url[:60]}...")
        else:
            print("  [OPEN] No Apply button clicked (already on form or not found)")

        # Inject the floating status indicator
        engine._inject_autofill_button()

        return jsonify({'success': True, 'method': 'playwright'})

    except Exception as e:
        import traceback
        traceback.print_exc()
        # Clean up on error
        _close_existing_session()
        return jsonify({'success': False, 'error': str(e)})


def run_autofill_and_get_questions(url: str):
    """Run autofill and return any unfilled fields for UI to display."""
    global current_autofill_session

    try:
        # Close any existing session properly first
        _close_existing_session()

        import sys
        poc_path = str(Path(__file__).parent.parent.parent / "poc")
        if poc_path not in sys.path:
            sys.path.insert(0, poc_path)

        from poc_autofill import AutofillEngine, ApplicantProfile, PROFILE_PATH

        # Load profile
        profile = ApplicantProfile.load_from_file(PROFILE_PATH)

        # Create engine with visible browser, non-interactive (we'll handle questions in UI)
        engine = AutofillEngine(profile, headless=False, skip_pause=True, interactive=False)
        engine.__enter__()

        # Store for later use
        current_autofill_session['engine'] = engine
        current_autofill_session['url'] = url

        # Analyze and fill form
        analysis = engine.fill_form(url, dry_run=True)

        # Get unfilled fields
        unfilled = []
        for field in analysis.fields_detected:
            if not field.filled and field.label != "Unknown":
                # Get dropdown options if applicable
                options = []
                if field.field_type.value == 'select':
                    print(f"  [DEBUG] Getting options for UI (field: {field.label})")
                    try:
                        # Use engine's helper to handle iframes
                        element = None
                        if hasattr(engine, '_get_element'):
                            element = engine._get_element(field)
                        else:
                            element = engine.page.query_selector(field.selector)
                            
                        if element:
                            # Use the engine's method if available, else manual
                            if hasattr(engine, '_get_dropdown_options'):
                                options_tuples = engine._get_dropdown_options(element)
                                options = [{'value': v, 'text': t} for v, t in options_tuples]
                            else:
                                # Fallback (should normally use engine's method)
                                option_els = element.query_selector_all("option")
                                for opt in option_els:
                                    val = opt.get_attribute("value") or ""
                                    text = opt.inner_text().strip()
                                    if val or text:
                                        options.append({'value': val, 'text': text})
                        print(f"  [DEBUG] Found {len(options)} options for {field.label}")
                    except Exception as e:
                        print(f"  [DEBUG] Error getting options: {e}")

                unfilled.append({
                    'label': field.label,
                    'selector': field.selector,
                    'type': field.field_type.value,
                    'required': field.required,
                    'options': options
                })

        current_autofill_session['unfilled_fields'] = unfilled

        return jsonify({
            'success': True,
            'method': 'autofill',
            'filled_count': analysis.fields_filled,
            'total_fields': len(analysis.fields_detected),
            'unfilled_fields': unfilled,
            'message': f'Filled {analysis.fields_filled}/{len(analysis.fields_detected)} fields'
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        # Clean up on error
        _close_existing_session()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/autofill/answer', methods=['POST'])
def submit_autofill_answers():
    """Submit answers for unfilled fields."""
    global current_autofill_session

    engine = current_autofill_session.get('engine')
    if not engine:
        return jsonify({'success': False, 'error': 'No active autofill session'})

    try:
        data = request.json
        answers = data.get('answers', {})  # {selector: value}

        # Import answer bank to save answers
        import sys
        poc_path = str(Path(__file__).parent.parent.parent / "poc")
        if poc_path not in sys.path:
            sys.path.insert(0, poc_path)
        from answer_bank import get_answer_bank

        answer_bank = get_answer_bank()

        # Fill each field with the provided answer
        filled_count = 0
        for field_info in current_autofill_session.get('unfilled_fields', []):
            selector = field_info['selector']
            label = field_info['label']
            field_type = field_info['type']

            if selector in answers and answers[selector]:
                answer_data = answers[selector]
                # Handle both old format (string) and new format (dict with type)
                if isinstance(answer_data, dict):
                    value = answer_data.get('value')
                    answer_type = answer_data.get('type', 'text')
                else:
                    value = answer_data
                    answer_type = field_type

                try:
                    # Construct a temporary FormField object
                    # We need the FieldType enum, so import it or use string matching
                    from poc.poc_autofill import FieldType, FormField
                    
                    # Map string type to FieldType enum
                    ft = FieldType.TEXT
                    if field_type == 'select': ft = FieldType.SELECT
                    elif field_type == 'email': ft = FieldType.EMAIL
                    elif field_type == 'tel': ft = FieldType.PHONE
                    elif field_type == 'url': ft = FieldType.URL
                    elif field_type == 'textarea': ft = FieldType.TEXTAREA
                    elif field_type == 'checkbox': ft = FieldType.CHECKBOX
                    elif field_type == 'radio': ft = FieldType.RADIO
                    elif field_type == 'file': ft = FieldType.FILE

                    temp_field = FormField(
                        field_type=ft,
                        label=label,
                        selector=selector,
                        name="", # Name not strored here but not critical for filling
                        iframe_url="" # Assuming main frame for now as selector should handle it? 
                        # Wait, selector might need iframe context. 
                        # Ideally we should use the engine's list of fields but that might be stale.
                        # Let's try filling with the new robust _fill_field logic.
                    )
                    
                    # _fill_field handles finding the element (including iframes if logic supports it)
                    # and doing the specific interaction (click-type-enter for pseudo-dropdowns)
                    if engine._fill_field(temp_field, str(value)):
                        print(f"  [FILL] Successfully filled {label}: {value}")
                        filled_count += 1
                        answer_bank.store_answer(label, str(value))
                    else:
                        print(f"  [FILL] Failed to fill {label}")

                except Exception as e:
                    print(f"Error filling {label}: {e}")

        return jsonify({
            'success': True,
            'filled_count': filled_count,
            'message': f'Filled {filled_count} additional fields. Review and submit manually.'
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/autofill/refill', methods=['POST'])
def refill_autofill():
    """Re-run autofill on the current page (for when user navigates to form)."""
    global current_autofill_session

    engine = current_autofill_session.get('engine')
    if not engine:
        return jsonify({'success': False, 'error': 'No active autofill session. Click "Open" on a job first.'})

    # Check if the browser/page is still valid, try to recover if not
    try:
        # Quick check - try to access the page URL
        _ = engine.page.url
    except Exception as e:
        # Page might be closed - try to find another open page in the context
        try:
            if engine.context and len(engine.context.pages) > 0:
                # Switch to the first available page
                engine.page = engine.context.pages[-1]  # Use the last/newest page
                print(f"  [REFILL] Switched to available page: {engine.page.url[:60]}...")
            else:
                # No pages available - session is truly dead
                current_autofill_session['engine'] = None
                current_autofill_session['unfilled_fields'] = []
                return jsonify({'success': False, 'error': 'Browser session expired. Click "Open" on a job to start a new session.'})
        except:
            current_autofill_session['engine'] = None
            current_autofill_session['unfilled_fields'] = []
            return jsonify({'success': False, 'error': 'Browser session expired. Click "Open" on a job to start a new session.'})

    try:
        # Re-inject the autofill button (in case page changed)
        engine._inject_autofill_button()

        # Re-detect fields on current page
        fields = engine._detect_fields()

        # Get patterns for the form type
        form_type = engine.detect_form_type(engine.page.url)
        patterns = engine._get_patterns_for_form(form_type)

        # Fill detected fields
        filled_count = 0
        skipped_count = 0
        unfilled = []

        for form_field in fields:
            value = engine._get_value_for_field(form_field, patterns)
            if value:
                success = engine._fill_field(form_field, value)
                if success:
                    form_field.filled = True
                    filled_count += 1
            else:
                skipped_count += 1
                if form_field.label != "Unknown":
                    # Get options for select elements
                    options = []
                    if form_field.field_type.value == 'select':
                        print(f"  [DEBUG] Getting options for SELECT field: {form_field.label}")
                        try:
                            element = engine.page.query_selector(form_field.selector)
                            if element:
                                option_elements = element.query_selector_all("option")
                                print(f"  [DEBUG] Found {len(option_elements)} option elements")
                                for opt in option_elements:
                                    opt_value = opt.get_attribute("value") or ""
                                    opt_text = opt.inner_text().strip()
                                    # Include options with text (value can be empty for placeholder)
                                    if opt_text:
                                        options.append({'value': opt_value or opt_text, 'text': opt_text})
                                print(f"  [DEBUG] Collected {len(options)} options: {options[:3]}...")
                            else:
                                print(f"  [DEBUG] Could not find element with selector: {form_field.selector}")
                        except Exception as e:
                            print(f"  [DEBUG] Error getting options for {form_field.selector}: {e}")

                    unfilled.append({
                        'label': form_field.label,
                        'selector': form_field.selector,
                        'type': form_field.field_type.value,
                        'required': form_field.required,
                        'options': options
                    })

        # Update button status
        total = len(fields)
        if total == 0:
            engine._update_autofill_button_status("No form fields found", success=False)
        elif filled_count == total:
            engine._update_autofill_button_status(f"Filled all {filled_count} fields!", success=True)
        else:
            engine._update_autofill_button_status(f"Filled {filled_count}/{total} fields", success=True)

        current_autofill_session['unfilled_fields'] = unfilled

        return jsonify({
            'success': True,
            'filled_count': filled_count,
            'total_fields': total,
            'unfilled_fields': unfilled,
            'message': f'Filled {filled_count}/{total} fields'
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/autofill/close', methods=['POST'])
def close_autofill():
    """Close the autofill browser session."""
    global current_autofill_session

    engine = current_autofill_session.get('engine')
    if engine:
        try:
            engine.__exit__(None, None, None)
        except:
            pass
        current_autofill_session['engine'] = None
        current_autofill_session['url'] = None
        current_autofill_session['unfilled_fields'] = []

    return jsonify({'success': True})


@app.route('/api/autofill', methods=['POST'])
def autofill():
    """Open a job with autofill (for Greenhouse/Lever)."""
    data = request.json
    link = data.get('link')
    platform = data.get('platform', '').lower()

    if not link:
        return jsonify({'success': False, 'error': 'No link provided'})

    # For Workday, just open in browser
    if 'workday' in platform or 'workday' in link.lower() or 'myworkdayjobs' in link.lower():
        webbrowser.open(link)
        return jsonify({'success': True, 'method': 'browser'})

    # For Greenhouse/Lever, we could trigger autofill
    # For now, just open in browser
    # TODO: Integrate with poc_autofill.py
    webbrowser.open(link)
    return jsonify({'success': True, 'method': 'browser'})


def load_role_config():
    """Load role configuration from config/roles.json."""
    config_path = Path(__file__).parent.parent.parent / "config" / "roles.json"
    default_config = {
        "include_keywords": ["software", "engineer", "developer", "data", "intern"],
        "exclude_keywords": ["marketing", "sales", "hr"],
        "must_contain": ["intern"]
    }

    try:
        if config_path.exists():
            import json
            with open(config_path) as f:
                return json.load(f)
    except Exception as e:
        print(f"Warning: Could not load roles.json: {e}")

    return default_config


def is_relevant_internship(title: str) -> bool:
    """Check if a job title is relevant based on config/roles.json."""
    title_lower = title.lower()

    config = load_role_config()

    # Check must_contain (e.g., "intern")
    must_contain = config.get("must_contain", ["intern"])
    if not any(word in title_lower for word in must_contain):
        return False

    # Check exclusions first
    exclude_keywords = config.get("exclude_keywords", [])
    for keyword in exclude_keywords:
        if keyword.lower() in title_lower:
            return False

    # Check if matches any relevant role
    include_keywords = config.get("include_keywords", [])
    for keyword in include_keywords:
        if keyword.lower() in title_lower:
            return True

    return False


@app.route('/api/discover', methods=['POST'])
def discover_jobs():
    """Discover new internships and add to Google Sheets."""
    sync = get_sync()
    if not sync:
        return jsonify({'success': False, 'error': 'Google Sheets not configured'})

    try:
        # Import discovery classes
        import sys
        import requests
        poc_path = str(Path(__file__).parent.parent.parent / "poc")
        if poc_path not in sys.path:
            sys.path.insert(0, poc_path)

        from poc_discovery import (
            GreenhouseClient,
            LeverClient,
            KNOWN_GREENHOUSE_COMPANIES,
            KNOWN_LEVER_COMPANIES,
        )

        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        # Create session with retry logic for transient SSL errors
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })

        greenhouse = GreenhouseClient(session)
        lever = LeverClient(session)

        all_jobs = []
        jobs_limit = 20  # Target 10-20 jobs

        # Check a random sample of known Greenhouse companies
        import random
        companies_to_check = KNOWN_GREENHOUSE_COMPANIES.copy()
        random.shuffle(companies_to_check)
        companies_to_check = companies_to_check[:20]  # Limit to 20 to avoid timeout

        for company in companies_to_check:
            if len(all_jobs) >= jobs_limit:
                break
            try:
                jobs, error = greenhouse.fetch_jobs(company)
                if error:
                    continue
                for job in jobs:
                    if len(all_jobs) >= jobs_limit:
                        break
                    title = job.get("title", "")
                    url = job.get("absolute_url", "")
                    # Add #app anchor to go directly to application form
                    if url and "#" not in url:
                        url = url + "#app"
                    # Use our strict filter
                    if is_relevant_internship(title) and url:
                        all_jobs.append(JobApplication(
                            company=company.title(),
                            role=title,
                            link=url,
                            platform="greenhouse",
                            date_posted="",
                        ))
            except Exception:
                continue

        # Check a random sample of known Lever companies
        companies_to_check = KNOWN_LEVER_COMPANIES.copy()
        random.shuffle(companies_to_check)
        companies_to_check = companies_to_check[:20]  # Limit to 20 to avoid timeout

        for company in companies_to_check:
            if len(all_jobs) >= jobs_limit:
                break
            try:
                jobs, error = lever.fetch_jobs(company)
                if error:
                    continue
                for job in jobs:
                    if len(all_jobs) >= jobs_limit:
                        break
                    title = job.get("text", "")
                    # Prefer applyUrl (direct application) over hostedUrl (listing page)
                    url = job.get("applyUrl", "") or job.get("hostedUrl", "")
                    # Use our strict filter
                    if is_relevant_internship(title) and url:
                        all_jobs.append(JobApplication(
                            company=company.title(),
                            role=title,
                            link=url,
                            platform="lever",
                            date_posted="",
                        ))
            except Exception:
                continue

        # Add to Google Sheets
        if all_jobs:
            from app.sync.sheets import AI_SEARCHED_SHEET
            sync.add_multiple_jobs(all_jobs, AI_SEARCHED_SHEET)
            return jsonify({'success': True, 'count': len(all_jobs)})
        else:
            return jsonify({'success': True, 'count': 0, 'message': 'No new internships found matching SWE/Quant/Data roles'})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/answers')
def answers_page():
    """Serve the Answer Bank UI."""
    return render_template('answers.html')


@app.route('/api/answers', methods=['GET'])
def get_answers():
    """Get all stored answers."""
    try:
        import sys
        poc_path = str(Path(__file__).parent.parent.parent / "poc")
        if poc_path not in sys.path:
            sys.path.insert(0, poc_path)
            
        from poc_autofill import get_answer_bank
        
        bank = get_answer_bank()
        return jsonify({'success': True, 'answers': bank.get_all_answers()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/answers/update', methods=['POST'])
def update_answer():
    """Update an answer."""
    try:
        data = request.json
        type_ = data.get('type')
        key = data.get('key')
        answer = data.get('answer')
        company = data.get('company')
        
        from poc_autofill import get_answer_bank
        bank = get_answer_bank()
        
        bank.update_answer(type_, key, answer, company)
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/answers/delete', methods=['POST'])
def delete_answer():
    """Delete an answer."""
    try:
        data = request.json
        type_ = data.get('type')
        key = data.get('key')
        company = data.get('company')
        
        from poc_autofill import get_answer_bank
        bank = get_answer_bank()
        
        bank.delete_answer(type_, key, company)
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# =============================================================================
# Resume / Profile Routes
# =============================================================================


@app.route('/profile')
def profile_page():
    """Serve the Profile Setup UI."""
    # Try to load existing profile
    profile_data = None
    profile_path = PROJECT_ROOT / "storage" / "profile.json"
    if profile_path.exists():
        try:
             with open(profile_path, 'r') as f:
                 profile_data = json.load(f)
        except Exception:
             pass
             
    return render_template('profile.html', existing_profile=profile_data)


@app.route('/api/profile/upload', methods=['POST'])
def upload_resume():
    """Handle resume upload and extract data."""
    if 'resume' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'})
    
    file = request.files['resume']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'})
    
    try:
        from pypdf import PdfReader
        from app.ai.llm import LLMClient
        
        # Save temp file
        temp_dir = PROJECT_ROOT / "storage" / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / file.filename
        file.save(temp_path)
        
        # Extract text
        reader = PdfReader(temp_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
            
        # Call AI to parse
        llm = LLMClient()
        if not llm.is_available():
             # Basic extraction if no LLM
             return jsonify({
                 'success': True,
                 'profile': {
                     'resume_path': str(temp_path),
                     'full_name': 'Manual Entry (OpenAI Key Missing)',
                     'email': '',
                     'phone': '',
                     'school': '',
                     'degree': "Bachelor's",
                     'major': '',
                     'graduation_year': '2026'
                 }
             })

        profile_data = llm.parse_resume(text)
        if not profile_data:
             print("[ERROR] LLM parse_resume returned None")
             return jsonify({'success': False, 'error': 'Failed to parse resume with AI'})
             
        profile_data['resume_path'] = str(temp_path)
        
        return jsonify({'success': True, 'profile': profile_data})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/profile/save', methods=['POST'])
def save_profile():
    """Save the profile to storage."""
    try:
        data = request.json
        storage_dir = PROJECT_ROOT / "storage"
        storage_dir.mkdir(parents=True, exist_ok=True)
        profile_path = storage_dir / "profile.json"
        
        # Ensure default fields
        if 'target_roles' not in data:
             data['target_roles'] = ["Software Engineering"] # Default
             
        with open(profile_path, "w") as f:
            json.dump(data, f, indent=2)
            
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


def run_server(port=5000, debug=False, open_browser=True):
    """Run the Flask server."""
    print(f"\n{'='*60}")
    print("INTERNSHIP APPLICATION ASSISTANT")
    print(f"{'='*60}")
    print(f"\nStarting server at http://localhost:{port}")

    if open_browser and not os.environ.get('WERKZEUG_RUN_MAIN'):
        webbrowser.open(f"http://localhost:{port}")

    # Use threaded=False for Playwright compatibility (strict thread affinity)
    # Disable reloader to prevent browser sessions from being killed on file changes
    app.run(host='0.0.0.0', port=port, debug=debug, threaded=False, use_reloader=False)


if __name__ == '__main__':
    run_server(debug=True)
