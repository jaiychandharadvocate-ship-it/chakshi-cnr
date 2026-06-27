# 🏛️ eCourts Chatbot - Automated Case Search Assistant

A fully functional chatbot that automates form filling on the eCourts India website, captures CAPTCHA for human verification, and retrieves case details in a conversational manner.

> 🧠 **The bigger picture — Chakshi as an Indian Legal Intelligence Engine:**
> see [`docs/CHAKSHI_ARCHITECTURE.md`](docs/CHAKSHI_ARCHITECTURE.md) for the
> 7-brains / 6-phases blueprint, and [`backend/intelligence/`](backend/intelligence/)
> for the implemented structured-intelligence layer (turns raw judgments into
> facts → issues → ratio → relief → strategy → drafting → citation graph).
>
> 📚 **Data sources for the legal knowledge base & model fine-tuning:** see
> [`docs/INDIAN_LEGAL_DATA_SOURCES.md`](docs/INDIAN_LEGAL_DATA_SOURCES.md) — a curated,
> verified catalog of Indian judgments, bare acts, government APIs, Indic-language
> corpora, and tooling, with licensing notes and a recommended build pipeline.

## 📋 Features

- **Conversational Interface**: Natural, one-question-at-a-time chat flow
- **Multiple Search Modes**:
  - Search by CNR (Case Number Reference)
  - Search by Party Name
  - Court Orders lookup
  - Cause List search
  - Caveat Search
- **CAPTCHA Handling**: Captures CAPTCHA image and displays it to the user for manual entry (legal compliance)
- **Automated Form Filling**: Uses Playwright to navigate and fill eCourts forms
- **Result Scraping**: Extracts and formats case details from result pages
- **Modern UI**: Clean, responsive chat interface with smooth animations
- **Session Management**: Handles multiple concurrent searches

## 🚨 Legal Notice

This tool is designed for **legal and authorized use only**:
- ✅ Human solves the CAPTCHA (no bypass attempts)
- ✅ Automation only handles navigation and form filling
- ✅ Complies with eCourts Terms of Service
- ❌ Do NOT use for unauthorized scraping or CAPTCHA bypass
- ❌ Use only for legitimate legal research and case tracking

## 🛠️ Tech Stack

### Backend
- **FastAPI**: Modern Python web framework
- **Playwright**: Browser automation library
- **Pydantic**: Data validation
- **Python 3.10+**: Core programming language

### Frontend
- **Pure HTML/CSS/JavaScript**: No framework dependencies
- **Responsive Design**: Works on desktop and mobile
- **Modern UI/UX**: Clean chat interface with animations

## 📁 Project Structure

```
chakshi2/
├── backend/
│   └── app.py              # FastAPI backend with Playwright automation
├── frontend/
│   └── index.html          # Chat interface
├── .env.example            # Environment variables template
├── .gitignore             # Git ignore rules
├── requirements.txt        # Python dependencies
└── README.md              # This file
```

## 🚀 Installation & Setup

### Prerequisites

- Python 3.10 or higher
- pip (Python package manager)
- Modern web browser (Chrome, Firefox, or Edge)

### Step 1: Clone the Repository

```bash
git clone <your-repo-url>
cd chakshi2
```

### Step 2: Create Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Linux/Mac:
source venv/bin/activate

# On Windows:
venv\Scripts\activate
```

### Step 3: Install Dependencies

```bash
# Install Python packages
pip install -r requirements.txt

# Install Playwright browsers
python -m playwright install chromium
```

### Step 4: Configure Environment (Optional)

```bash
# Copy example environment file
cp .env.example .env

# Edit .env file with your preferences (optional)
# The defaults work fine for local development
```

### Step 5: Run the Backend

```bash
# From the project root directory
cd backend
python app.py

# Or use uvicorn directly:
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

You should see output like:
```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
[INFO] eCourts Chatbot API starting up...
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Step 6: Open the Frontend

Open `frontend/index.html` in your web browser:

**Option 1**: Double-click the file
**Option 2**: Right-click → Open with → Your Browser
**Option 3**: Use a local server (recommended for production):

```bash
# Using Python's built-in server
cd frontend
python -m http.server 3000

# Then open: http://localhost:3000
```

## 💬 Usage Guide

### Basic Flow

1. **Open the chatbot** in your browser
2. **Choose search method**: CNR or Party Name
3. **Provide required information**:
   - For CNR: Enter the 16-digit CNR number
   - For Party Name: Enter party name, state, district, etc.
4. **Solve CAPTCHA**: The bot will display the CAPTCHA image
5. **Enter CAPTCHA text** and submit
6. **View results**: Case details will be displayed in formatted tables

### Example Conversations

#### Example 1: Search by CNR

```
Bot: How would you like to search?
You: Search by CNR

Bot: Please enter the CNR number
You: MHMM01-0123-456789-2023

Bot: [Shows CAPTCHA image]
You: [Enter CAPTCHA text]

Bot: [Displays case details]
```

#### Example 2: Search by Party Name

```
Bot: How would you like to search?
You: Search by Party Name

Bot: Please enter the party name
You: Krishna Builders

Bot: Which state?
You: Maharashtra

Bot: Which district?
You: Mumbai

Bot: What type of case?
You: Civil

Bot: Which year?
You: 2023

Bot: [Shows CAPTCHA image]
You: [Enter CAPTCHA text]

Bot: [Displays case details]
```

## 🔧 Configuration

### Environment Variables (.env)

```bash
# OpenAI API Key (for future AI enhancements - not currently used)
OPENAI_API_KEY=your_key_here

# Backend Configuration
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000

# Browser Configuration
HEADLESS_MODE=true          # Set to false to see browser window
BROWSER_TIMEOUT=30000       # Browser timeout in milliseconds

# Session Configuration
SESSION_TIMEOUT=1800        # Session timeout in seconds (30 minutes)
```

### Headless Mode

For debugging, you can set `HEADLESS_MODE=false` in your `.env` file to see the browser window:

```bash
HEADLESS_MODE=false
```

This helps you understand what the bot is doing and debug selector issues.

## 🐛 Troubleshooting

### Issue: "CAPTCHA not found"

**Cause**: The DOM selectors don't match the current eCourts page structure

**Solution**:
1. Set `HEADLESS_MODE=false` in `.env`
2. Run the bot and observe the browser
3. Inspect the CAPTCHA element on the page
4. Update selectors in `backend/app.py` → `capture_captcha()` function

### Issue: "Could not fill party name"

**Cause**: Form field selectors have changed

**Solution**:
1. Inspect the eCourts form
2. Update selectors in `backend/app.py` → `fill_party_name_form()` function

### Issue: Backend not connecting

**Cause**: CORS or network issues

**Solution**:
1. Ensure backend is running on `http://localhost:8000`
2. Check browser console for CORS errors
3. Ensure `allow_origins=["*"]` is set in CORS middleware

### Issue: Results not displaying

**Cause**: Result page structure doesn't match scraping logic

**Solution**:
1. Set `HEADLESS_MODE=false`
2. Observe the result page structure
3. Update `scrape_results()` function in `backend/app.py`

## 📚 API Documentation

Once the backend is running, visit:
- **Interactive API docs**: http://localhost:8000/docs
- **Alternative docs**: http://localhost:8000/redoc

### Key Endpoints

#### POST /start-search
Start a new search session

**Request Body**:
```json
{
  "mode": "party_name",
  "party_name": "Krishna Builders",
  "state_code": "Maharashtra",
  "district_code": "Mumbai",
  "case_type": "civil",
  "case_year": "2023"
}
```

**Response**:
```json
{
  "session_id": "abc123xyz",
  "status": "started",
  "message": "Search initiated successfully"
}
```

#### GET /captcha/{session_id}
Get CAPTCHA image for a session

**Response**:
```json
{
  "status": "awaiting_captcha",
  "captcha_b64": "iVBORw0KGgoAAAANSUhEUgAA..."
}
```

#### POST /submit-captcha
Submit CAPTCHA and get results

**Request Body**:
```json
{
  "session_id": "abc123xyz",
  "captcha_text": "AB123"
}
```

**Response**:
```json
{
  "status": "completed",
  "results": {
    "tables": [...],
    "raw_text": [...],
    "cases": [...]
  }
}
```

## 🎨 Customization

### Modifying the UI

Edit `frontend/index.html`:
- Colors: Change the gradient values in `<style>` section
- Layout: Modify `.container`, `.chat-container` classes
- Messages: Update message styling in `.message` classes

### Adding New eCourts Endpoints

1. Add endpoint to `ECOURTS_ENDPOINTS` dict in `backend/app.py`:
```python
ECOURTS_ENDPOINTS = {
    'your_new_mode': 'https://services.ecourts.gov.in/...',
    # ... other endpoints
}
```

2. Create a new form filling function:
```python
async def fill_your_form(page: Page, params: Dict[str, Any]):
    # Your form filling logic
    pass
```

3. Add mode handling in `run_search()` function

### Improving Result Parsing

Edit the `scrape_results()` function in `backend/app.py`:
- Add more specific CSS selectors
- Parse specific case fields (CNR, parties, dates, etc.)
- Format results for better display

## 🔒 Security Considerations

1. **API Keys**: Never commit `.env` file - it's in `.gitignore`
2. **CORS**: In production, restrict `allow_origins` to specific domains
3. **Rate Limiting**: Add rate limiting to prevent abuse
4. **Session Storage**: Use Redis or database instead of in-memory dict for production
5. **Input Validation**: All inputs are validated by Pydantic models

## 📈 Future Enhancements

- [ ] Add authentication/authorization
- [ ] Integrate OpenAI for natural language understanding
- [ ] Add more eCourts search types (Filing Number, Advocate Name, etc.)
- [ ] Export results to PDF/Excel
- [ ] Email notifications for case updates
- [ ] Multi-language support
- [ ] Mobile app (React Native/Flutter)
- [ ] Case tracking and bookmarking
- [ ] Historical search analytics

## 🤝 Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

This project is for educational and legal research purposes. Ensure compliance with eCourts Terms of Service and applicable laws in your jurisdiction.

## 💡 Support

For issues, questions, or suggestions:
1. Check the Troubleshooting section
2. Review API documentation
3. Open an issue on GitHub
4. Contact the development team

## 🙏 Acknowledgments

- eCourts India for providing the public case search interface
- Playwright team for the excellent browser automation library
- FastAPI team for the modern Python web framework

---

**Disclaimer**: This tool is provided as-is for legal and educational purposes. Users are responsible for ensuring their use complies with all applicable laws and terms of service.
