# 🚀 Quick Start Guide

Get the eCourts Chatbot running in 5 minutes!

## Prerequisites

- Python 3.10+ installed
- Internet connection

## Installation (First Time Only)

### Linux/Mac:

```bash
# 1. Navigate to project directory
cd chakshi2

# 2. Create virtual environment
python -m venv venv

# 3. Activate virtual environment
source venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Install Playwright browsers
python -m playwright install chromium
```

### Windows:

```cmd
# 1. Navigate to project directory
cd chakshi2

# 2. Create virtual environment
python -m venv venv

# 3. Activate virtual environment
venv\Scripts\activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Install Playwright browsers
python -m playwright install chromium
```

## Running the Application

### Option 1: Using the Start Script (Recommended)

**Linux/Mac:**
```bash
./start.sh
```

**Windows:**
```cmd
start.bat
```

### Option 2: Manual Start

**Terminal 1 - Backend:**
```bash
# Activate venv first
source venv/bin/activate  # Linux/Mac
# OR
venv\Scripts\activate     # Windows

# Start backend
cd backend
python app.py
```

**Terminal 2 - Frontend (Optional):**
```bash
cd frontend
python -m http.server 3000
```

Then open in browser:
- http://localhost:3000 (if using local server)
- OR just double-click `frontend/index.html`

## Using the Chatbot

1. **Open** `frontend/index.html` in your browser
2. **Choose** search method: CNR or Party Name
3. **Enter** the required information when asked
4. **Solve** the CAPTCHA when it appears
5. **View** your case results!

## Example Search

```
Bot: How would you like to search?
You: Party Name

Bot: Please enter the party name
You: Krishna Builders

Bot: Which state?
You: Maharashtra

Bot: Which district?
You: Mumbai

Bot: [Shows CAPTCHA]
You: [Enter CAPTCHA text]

Bot: [Shows case results]
```

## Troubleshooting

### Backend won't start?
- Make sure virtual environment is activated
- Check if port 8000 is available
- Ensure all dependencies are installed

### CAPTCHA not showing?
- Check browser console for errors
- Ensure backend is running on http://localhost:8000
- Try refreshing the page

### Results not displaying?
- The CAPTCHA might be incorrect - try again
- eCourts website might be down - try later
- Check backend terminal for error messages

## Need More Help?

See the full [README.md](README.md) for:
- Detailed documentation
- Configuration options
- API documentation
- Troubleshooting guide
- Advanced features

## Support

- Check logs in terminal where backend is running
- API docs: http://localhost:8000/docs
- GitHub Issues: [Create an issue](../../issues)

---

Happy searching! 🏛️
