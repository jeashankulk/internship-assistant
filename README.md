# Internship Application Assistant

A web-based tool that helps you discover internships, track applications, and auto-fill job applications on Greenhouse and Lever platforms.

## Features

- **Job Discovery**: Automatically find internships from 100+ tech companies using Greenhouse and Lever APIs
- **Smart Filtering**: Configure which roles you're interested in (SWE, Data, Quant, Design, Marketing, etc.)
- **Application Tracking**: Sync your application list with Google Sheets
- **Auto-Fill**: Automatically fill Greenhouse/Lever applications with your profile info
- **Learning System**: Remembers your answers to questions for future applications
- **Web UI**: Clean interface to manage your application queue

## Screenshots

The UI shows your pending applications with Manual jobs prioritized over AI-discovered ones. Click "Open" to launch auto-fill, or "Find Jobs" to discover new internships.

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/internship-assistant.git
cd internship-assistant
```

### 2. Install Dependencies

Requires Python 3.11+

```bash
pip install -e .
pip install flask playwright
playwright install chromium
```

### 3. Set Up Google Sheets

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or use existing)
3. Enable **Google Sheets API**: APIs & Services → Library → Search "Google Sheets API" → Enable
4. Create credentials: APIs & Services → Credentials → Create Credentials → OAuth client ID → Desktop app
5. Download the JSON file and save as `credentials.json` in the project root
6. Add yourself as a test user: OAuth consent screen → Test users → Add your email

### 4. Create Your Google Sheet

1. Go to [Google Sheets](https://sheets.google.com) and create a new spreadsheet
2. Name it "Internship Applications" (or anything you want)
3. Create two sheet tabs at the bottom:
   - `Manual` (for jobs you add manually - shown first in UI)
   - `AI Searched` (for auto-discovered jobs)
4. Copy the spreadsheet ID from the URL: `https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit`

### 5. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and add your spreadsheet ID:
```
GOOGLE_SPREADSHEET_ID=your_spreadsheet_id_here
```

### 6. Set Up Your Profile

```bash
python poc/setup_profile.py
```

This interactive wizard will:
- Create `storage/profile.json` with your info for auto-filling applications
- Configure `config/roles.json` with your target role preferences

The wizard will ask what types of internships you're looking for:
- Software Engineering
- Data Science / ML / AI
- Quantitative / Trading
- Product / Program Management
- Design / UX / UI
- Finance / Accounting
- Marketing / Growth

You can select multiple categories by entering comma-separated numbers (e.g., `1,2,3`).

### 7. Advanced: Manual Role Configuration (Optional)

You can also manually edit `config/roles.json` to fine-tune your search:

```json
{
  "include_keywords": ["design", "ux", "ui", "product design"],
  "exclude_keywords": ["engineering", "software"],
  "must_contain": ["intern"]
}
```

### 8. Run the App

```bash
python run_ui.py
```

Open http://localhost:8080 in your browser.

## Usage

### Finding Jobs

Click **"Find Jobs"** to automatically discover internships from known tech companies. The tool searches Greenhouse and Lever job boards and filters for roles matching your configured keywords.

### Adding Jobs Manually

Click **"+ Add Job Manually"** to add a specific job you found elsewhere. Manual jobs appear first in your queue.

### Applying to Jobs

1. Click **"Open"** on any job
2. For Greenhouse/Lever: A browser opens with auto-filled fields
3. If there are unfilled questions, a modal appears in the UI
4. Fill in your answers (they're saved for future applications!)
5. Review the form and submit manually

### Marking Jobs as Applied

Click **"✓ Applied"** after submitting. This:
- Removes the job from your UI queue
- Updates Google Sheets status to "Applied"

## Project Structure

```
internship-assistant/
├── app/
│   ├── web/           # Flask web UI
│   └── sync/          # Google Sheets integration
├── poc/
│   ├── poc_autofill.py    # Playwright auto-fill engine
│   ├── poc_discovery.py   # Job board discovery
│   ├── setup_profile.py   # Profile setup wizard
│   └── answer_bank.py     # Learns your answers
├── config/
│   └── roles.json     # Configure target roles
├── storage/           # Local data (gitignored)
│   ├── profile.json   # Your profile
│   └── answers.json   # Saved answers
├── .env.example       # Environment template
├── run_ui.py          # Main entry point
└── README.md
```

## Supported Platforms

| Platform | Auto-Fill | Discovery |
|----------|-----------|-----------|
| Greenhouse | ✅ Full | ✅ Yes |
| Lever | ✅ Full | ✅ Yes |
| Workday | ❌ Browser only | ❌ No |

Workday applications open in your browser for manual completion (their forms are too complex for automation).

## Customization

### Adding More Companies

Edit `poc/poc_discovery.py` and add companies to:
- `KNOWN_GREENHOUSE_COMPANIES`
- `KNOWN_LEVER_COMPANIES`

### Changing Target Roles

Edit `config/roles.json`:

**For Design roles:**
```json
{
  "include_keywords": ["design", "ux", "ui", "product design", "visual"],
  "exclude_keywords": ["engineering", "software", "backend"],
  "must_contain": ["intern"]
}
```

**For Finance roles:**
```json
{
  "include_keywords": ["finance", "accounting", "investment", "banking"],
  "exclude_keywords": ["software", "engineering"],
  "must_contain": ["intern"]
}
```

## Troubleshooting

### "Google Sheets not configured"
- Make sure `GOOGLE_SPREADSHEET_ID` is set in `.env`
- Make sure `credentials.json` exists in project root

### "Port already in use"
- Edit `run_ui.py` and change the port number
- Or kill the process: `lsof -i :8080` then `kill -9 <PID>`

### Auto-fill not working
- Make sure Playwright is installed: `playwright install chromium`
- Check that your profile exists: `storage/profile.json`

## Contributing

Contributions welcome! Please open an issue or PR.

## License

MIT License - see LICENSE file for details.

## Disclaimer

This tool is for personal use to help manage your job applications. Always review auto-filled forms before submitting. The tool never submits applications automatically - you always have final control.
