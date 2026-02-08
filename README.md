# Internship Application Assistant

A web-based tool that streamlines the internship application process. It discovers jobs from Greenhouse and Lever job boards, tracks applications via Google Sheets, and auto-fills application forms using Playwright — so you spend less time on repetitive data entry and more time on applications that matter.

## Features

- **Job Discovery** — Searches 100+ company job boards on Greenhouse and Lever, filtering for internship roles matching your configured keywords
- **Manual Job Addition** — Paste any Greenhouse/Lever job URL and the app auto-fetches the company name, role, location, and description from the API
- **Application Tracking** — Two-tab Google Sheets backend (Manual + AI Searched) with status tracking and one-click "Applied" marking
- **Auto-Fill** — Opens Greenhouse/Lever applications in a Playwright browser with your profile fields pre-filled (name, email, phone, resume, etc.)
- **Answer Bank** — Remembers your answers to application questions using fuzzy matching, so repeat questions are filled automatically
- **AI Answer Generation** — When no saved answer exists, uses OpenAI to generate answers from your resume (if API key configured)
- **Resume Parsing** — Upload a PDF resume on the profile page and AI extracts your details automatically
- **Web UI** — Clean interface to manage your application queue, edit your profile, and review saved answers

## Setup

### 1. Clone and Install

```bash
git clone https://github.com/jeashankulk/internship-assistant.git
cd internship-assistant
pip install -e .
pip install flask playwright
playwright install chromium
```

### 2. Set Up Google Sheets

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project and enable the **Google Sheets API**
3. Create OAuth credentials (Desktop app) and download as `credentials.json` in the project root
4. Add yourself as a test user under OAuth consent screen

### 3. Create Your Spreadsheet

1. Create a new spreadsheet in [Google Sheets](https://sheets.google.com)
2. Add two tabs at the bottom: `Manual` and `AI Searched`
3. Copy the spreadsheet ID from the URL: `https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit`

### 4. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and set your spreadsheet ID:
```
GOOGLE_SPREADSHEET_ID=your_spreadsheet_id_here
```

Optionally add an OpenAI API key for AI-powered answer generation and resume parsing:
```
OPENAI_API_KEY=your_key_here
```

### 5. Run the App

```bash
python run_ui.py
```

The app opens at http://localhost:8080. On first run you'll be prompted to authorize Google Sheets access.

### 6. Set Up Your Profile

1. Click **Edit Profile** in the app (or go to `/profile`)
2. Upload your PDF resume — AI extracts your details automatically
3. Review the parsed fields and click Save

That's it. Your profile is stored locally in `storage/profile.json` and used to auto-fill applications.

## Usage

### Finding Jobs

Click **Find Jobs** to scan Greenhouse and Lever boards for internships matching your configured role keywords. Discovered jobs appear in the "AI Searched" tab.

### Adding Jobs Manually

Click **+ Add Job Manually**, paste a Greenhouse or Lever job URL, and click **Fetch**. The app pulls the job title, company name, description, and location directly from the platform's API. Manual jobs appear first in your queue.

### Applying

1. Click **Open** on any job
2. A Playwright browser opens with your profile fields pre-filled
3. If there are unfilled questions, a modal appears in the UI for you to answer them (answers are saved for next time)
4. Review the form and submit manually — the app never submits for you

### Tracking

Click **Applied** after submitting to move the job out of your queue and update the status in Google Sheets.

### Managing Saved Answers

Go to the **Answers** page (`/answers`) to view, edit, or delete saved answers from previous applications.

## Project Structure

```
internship-assistant/
├── app/
│   ├── ai/              # LLM client (resume parsing, answer generation)
│   ├── web/             # Flask web UI (server, templates, static)
│   └── sync/            # Google Sheets integration
├── poc/
│   ├── poc_autofill.py  # Playwright auto-fill engine
│   ├── poc_discovery.py # Job board discovery + API clients
│   ├── answer_bank.py   # Question-answer storage with fuzzy matching
│   └── setup_profile.py # Legacy CLI profile setup
├── config/
│   └── roles.json       # Target role keywords configuration
├── storage/             # Local data (gitignored)
│   ├── profile.json     # Your profile
│   └── answers.json     # Saved answers
├── .env.example         # Environment variable template
├── run_ui.py            # Entry point
└── pyproject.toml
```

## Supported Platforms

| Platform | Auto-Fill | Discovery |
|----------|-----------|-----------|
| Greenhouse | Full | Yes |
| Lever | Full | Yes |
| Workday | Browser only | No |

Workday applications open in your default browser for manual completion.

## Configuration

### Role Keywords

Edit `config/roles.json` to control which roles are matched during discovery:

```json
{
  "include_keywords": ["software", "engineer", "developer", "swe"],
  "exclude_keywords": ["senior", "staff", "manager"],
  "must_contain": ["intern"]
}
```

### Adding Companies

Edit the company lists in `poc/poc_discovery.py`:
- `KNOWN_GREENHOUSE_COMPANIES`
- `KNOWN_LEVER_COMPANIES`

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "Google Sheets not configured" | Set `GOOGLE_SPREADSHEET_ID` in `.env` and place `credentials.json` in project root |
| Port already in use | Change port in `run_ui.py` or kill the process on :8080 |
| Auto-fill not working | Run `playwright install chromium` and verify `storage/profile.json` exists |
| AI features not working | Set `OPENAI_API_KEY` in `.env` |

## Disclaimer

This tool assists with managing your job applications. It never submits applications automatically — you always review and submit manually. Only public job board APIs are accessed.
