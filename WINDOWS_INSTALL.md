# 🪟 Complete Windows Installation Guide

## Step 1: Install Python

### Download Python
1. Go to: https://www.python.org/downloads/
2. Click "Download Python 3.11.x" (latest version)
3. **IMPORTANT**: During installation, CHECK ✅ "Add Python to PATH"
4. Click "Install Now"

### Verify Installation
Open Command Prompt (press Win+R, type `cmd`, press Enter):
```cmd
python --version
```
Should show: `Python 3.11.x`

```cmd
pip --version
```
Should show: `pip 23.x.x from ...`

---

## Step 2: Download the Project

### Option A: If you have Git
```cmd
git clone <your-repo-url>
cd chakshi2
```

### Option B: Download ZIP
1. Download the project as ZIP
2. Extract to `C:\Users\YourName\chakshi2`
3. Open Command Prompt in that folder

---

## Step 3: Install Dependencies

Open Command Prompt in the `chakshi2` folder:

```cmd
REM Create virtual environment
python -m venv venv

REM Activate it
venv\Scripts\activate

REM You should see (venv) at the beginning of your command prompt

REM Upgrade pip
python -m pip install --upgrade pip

REM Install all dependencies
pip install -r requirements.txt

REM Install Playwright browsers (this takes a few minutes)
python -m playwright install chromium
```

Wait for everything to install. This might take 5-10 minutes.

---

## Step 4: Run the Chatbot

### Start the Backend

```cmd
REM Make sure you're in chakshi2 folder and venv is activated
cd backend
python app.py
```

You should see:
```
INFO:     Started server process [xxxxx]
[INFO] eCourts Chatbot API starting up...
INFO:     Uvicorn running on http://0.0.0.0:8000
```

**Keep this window open!** This is your backend server.

### Open the Frontend

Open a web browser and:
- **Option 1**: Double-click `frontend\index.html`
- **Option 2**: Open new Command Prompt:
  ```cmd
  cd chakshi2\frontend
  python -m http.server 3000
  ```
  Then go to: http://localhost:3000

---

## Step 5: Search Your CNR Number

1. The chatbot will ask: "How would you like to search?"
2. Click "Search by CNR" or type "1"
3. Enter your CNR: **DLND010019612022**
4. Wait for the CAPTCHA image to appear
5. Type the CAPTCHA text you see
6. Click "Submit CAPTCHA"
7. View your case results!

---

## Troubleshooting

### "Python was not found"
- Reinstall Python and CHECK ✅ "Add Python to PATH"
- OR add manually: Settings → System → About → Advanced system settings → Environment Variables → Edit PATH → Add `C:\Python311` and `C:\Python311\Scripts`

### "pip is not recognized"
- Run: `python -m pip install --upgrade pip`

### "Permission denied" errors
- Run Command Prompt as Administrator (right-click → Run as administrator)

### Port 8000 already in use
- Kill the process: `taskkill /F /IM python.exe`
- Or change port in `.env` file

### CAPTCHA not showing
1. Check backend terminal for errors
2. Open browser console (F12) and check for errors
3. Make sure backend shows: `http://0.0.0.0:8000`

### Can't install Playwright browsers
- May need admin rights
- Try: `python -m playwright install chromium --force`
- Check your antivirus isn't blocking it

---

## Quick Start Script

Save this as `run_chatbot.bat` in chakshi2 folder:

```batch
@echo off
echo Starting eCourts Chatbot...
cd /d %~dp0
call venv\Scripts\activate
cd backend
start "eCourts Backend" python app.py
timeout /t 3
echo.
echo Backend is running!
echo Now open frontend\index.html in your browser
pause
```

Then just double-click `run_chatbot.bat` to start!

---

## What Your CNR Search Will Return

For **DLND010019612022**, you'll get:
- ✅ Case Number
- ✅ Filing Number
- ✅ Party Names (Petitioner/Respondent)
- ✅ Case Type
- ✅ Filing Date
- ✅ Current Status
- ✅ Next Hearing Date
- ✅ Judge/Court Details
- ✅ Acts & Sections
- ✅ Case History

All in neat formatted tables!

---

## Need Help?

1. Make sure Python is installed correctly
2. Make sure venv is activated (you see `(venv)` in command prompt)
3. Make sure backend is running before opening frontend
4. Check both frontend and backend terminals for error messages

If stuck, paste the error message and I'll help you fix it!
