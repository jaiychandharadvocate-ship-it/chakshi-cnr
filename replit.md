# eCourts Chatbot

## Overview

A conversational chatbot that automates case searches on the eCourts India website. The system uses OpenAI for natural language understanding to collect search parameters through conversation, browser automation to navigate and fill forms, captures CAPTCHA images for human verification (maintaining legal compliance), and retrieves case details through a modern chat interface.

Key capabilities:
- **AI-Powered Conversation** - Natural language chat that understands user intent and initiates appropriate search flows
- **CNR Search** - Search by Case Number Reference (16-character alphanumeric)
- **Interactive Party Name Search** - Multi-step dropdown selection scraping live options from eCourts:
  - State selection (37 states)
  - District selection (varies by state)
  - Court complex selection
  - Establishment selection (mandatory)
  - Party name and year input
  - Pending/Disposed/Both selection (radio button style UI)
- **Interactive CAPTCHA** - User fills CAPTCHA for legal compliance
- **Case List Results** - Displays matching cases in a proper table format with Sr No, Case Type/Number/Year, Petitioner vs Respondent, and View button columns
- **View Case Details** - Click "View" button on any case to scrape and display full details (CNR, dates, parties, status, etc.)
- **Duplicate Question Prevention** - Smart status tracking with unique status keys prevents asking same dropdown selection multiple times
- **Persistent Browser Sessions** - Browser stays alive after search completion to allow viewing multiple case details
- **Session Timeout Warning** - 5-minute viewing window for case details with clear disclaimer
- **Help Text Filtering** - Scrapes only actual case results from `#dispTable`, validating rows have numeric Sr No to filter out help/instruction rows

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Frontend
- **Pure HTML/CSS/JavaScript** - Single-page chat interface with no framework dependencies
- Located in `frontend/index.html`
- Responsive design with modern UI animations
- Communicates with backend via REST API

### Backend
- **FastAPI** - Python web framework handling API endpoints
- **Playwright** - Browser automation for navigating eCourts website and filling forms
- **OpenAI Integration** - Powers conversational chat functionality (optional, degrades gracefully if not configured)
- Located in `backend/app.py`

### Key Design Decisions

1. **Browser Automation over Direct API Calls**
   - eCourts doesn't provide a public API
   - Playwright handles JavaScript-heavy pages and dynamic content
   - Human CAPTCHA solving ensures legal compliance

2. **In-Memory Session Storage**
   - Simple dict-based storage for development
   - Session timeout configurable via `SESSION_TIMEOUT` env var
   - Note: Should use Redis for production deployments

3. **Headless Browser Mode**
   - Configurable via `HEADLESS_MODE` environment variable
   - Essential for server deployments (Replit, etc.)

4. **eCourts Form Navigation**
   - Party Name search flow: Select state/district → Court complex → Establishment → Party name → Year → Pending/Disposed/Both → CAPTCHA
   - State dropdown uses `select#sess_state_code` selector
   - District/court complex use JS fallbacks for reliability
   - Form uses adaptive selectors with multiple fallback strategies

5. **Case Result Scraping**
   - Results container: `#res_party`
   - Results table: `#dispTable`  
   - Results rows: `#dispTable tbody tr`
   - NEVER use: `#showList`, `#showList1`, `#caseListResult` (those are WRONG)
   - Wait for `#dispTable tbody tr` after CAPTCHA submit to ensure AJAX loaded
   - Valid rows have: serial number, case type/number/year, party name, View button

6. **Case Details Scraping (View button)**
   - Container: `div#partynametab` (tab-pane fade show active border)
   - Case Details: `table.case_details_table` - Case Type, Filing Number/Date, Registration Number/Date, CNR Number
   - Case Status: `table.case_status_table` - First Hearing Date, Next Hearing Date, Case Stage, Court Number and Judge
   - Petitioner/Advocate: Look after h3 "Petitioner and Advocate"
   - Respondent/Advocate: Look after h3 "Respondent and Advocate"
   - Acts: `table.acts_table` - Under Act(s), Under Section(s)
   - Case History: `table#historyheading` - Judge, Business on Date, Hearing Date, Purpose of Hearing
   - Interim Orders: Table after h3 "Interim Orders"
   - Case Transfer Details: Table with Registration Number, Transfer Date, From/To Court

### Running the Application

```bash
cd backend && python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

Playwright browsers must be installed first:
```bash
python -m playwright install chromium
```

## External Dependencies

### Python Packages
- `fastapi` + `uvicorn` - Web server
- `playwright` - Browser automation
- `openai` - Chat AI (optional)
- `beautifulsoup4` - HTML parsing
- `pydantic` - Data validation
- `python-dotenv` - Environment configuration
- `aiofiles` - Async file operations

### External Services
- **eCourts India** (`services.ecourts.gov.in`) - Target website for case searches
- **OpenAI API** (optional) - Powers natural language chat; set `OPENAI_API_KEY_MY` environment variable

### Environment Variables
- `OPENAI_API_KEY_MY` - OpenAI API key for chat functionality
- `SESSION_TIMEOUT` - Session expiry in seconds (default: 1800)
- `HEADLESS_MODE` - Run browser without GUI (set to "true" for server deployments)