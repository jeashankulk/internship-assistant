#!/usr/bin/env python3
"""
Web UI for Internship Application Assistant.
Simple Flask server that displays pending applications and handles apply workflow.
"""

import os
import sys
import webbrowser
from pathlib import Path
from flask import Flask, render_template, jsonify, request, redirect, url_for

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.sync.sheets import get_sheets_sync, JobApplication, MANUAL_SHEET, AI_SEARCHED_SHEET

app = Flask(__name__,
            template_folder=str(Path(__file__).parent / "templates"),
            static_folder=str(Path(__file__).parent / "static"))

# Global sheets sync instance
sheets_sync = None


def get_sync():
    """Get or create sheets sync instance."""
    global sheets_sync
    if sheets_sync is None:
        sheets_sync = get_sheets_sync()
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


@app.route('/api/jobs/applied', methods=['POST'])
def mark_applied():
    """Mark a job as applied."""
    sync = get_sync()
    if not sync:
        return jsonify({'success': False, 'error': 'Google Sheets not configured'})

    data = request.json
    link = data.get('link')

    if not link:
        return jsonify({'success': False, 'error': 'No link provided'})

    try:
        success = sync.mark_as_applied(link)
        return jsonify({'success': success})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/jobs/add', methods=['POST'])
def add_job():
    """Add a new job manually."""
    sync = get_sync()
    if not sync:
        return jsonify({'success': False, 'error': 'Google Sheets not configured'})

    data = request.json
    job = JobApplication(
        company=data.get('company', ''),
        role=data.get('role', ''),
        link=data.get('link', ''),
        platform=data.get('platform', 'other'),
        date_posted=data.get('date_posted', ''),
    )

    if not job.company or not job.link:
        return jsonify({'success': False, 'error': 'Company and link are required'})

    try:
        success = sync.add_job(job, MANUAL_SHEET)
        return jsonify({'success': success})
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


def run_autofill_and_get_questions(url: str):
    """Run autofill and return any unfilled fields for UI to display."""
    global current_autofill_session

    try:
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
                    try:
                        element = engine.page.query_selector(field.selector)
                        if element:
                            option_els = element.query_selector_all("option")
                            for opt in option_els:
                                val = opt.get_attribute("value") or ""
                                text = opt.inner_text().strip()
                                if val or text:
                                    options.append({'value': val, 'text': text})
                    except:
                        pass

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
        if current_autofill_session.get('engine'):
            try:
                current_autofill_session['engine'].__exit__(None, None, None)
            except:
                pass
            current_autofill_session['engine'] = None
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
                value = answers[selector]
                try:
                    element = engine.page.query_selector(selector)
                    if element:
                        if field_type == 'select':
                            element.select_option(value)
                        else:
                            element.fill(value)
                        filled_count += 1

                        # Save to answer bank for future use
                        answer_bank.store_answer(label, value)
                except Exception as e:
                    print(f"Error filling {selector}: {e}")

        return jsonify({
            'success': True,
            'filled_count': filled_count,
            'message': f'Filled {filled_count} additional fields. Review and submit manually.'
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

        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })

        greenhouse = GreenhouseClient(session)
        lever = LeverClient(session)

        all_jobs = []
        jobs_limit = 20  # Target 10-20 jobs

        # Check ALL known Greenhouse companies to find enough internships
        import random
        companies_to_check = KNOWN_GREENHOUSE_COMPANIES.copy()
        random.shuffle(companies_to_check)

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

        # Check ALL known Lever companies
        companies_to_check = KNOWN_LEVER_COMPANIES.copy()
        random.shuffle(companies_to_check)

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
                    url = job.get("hostedUrl", "")
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


def run_server(port=5000, debug=False, open_browser=True):
    """Run the Flask server."""
    print(f"\n{'='*60}")
    print("INTERNSHIP APPLICATION ASSISTANT")
    print(f"{'='*60}")
    print(f"\nStarting server at http://localhost:{port}")

    if open_browser:
        webbrowser.open(f"http://localhost:{port}")

    app.run(host='0.0.0.0', port=port, debug=debug)


if __name__ == '__main__':
    run_server(debug=True)
