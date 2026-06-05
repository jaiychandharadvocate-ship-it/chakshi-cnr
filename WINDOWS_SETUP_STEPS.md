# 🪟 Windows Setup - Step by Step Commands

## Problem: Virtual Environment Error

If you see this error:
```
'venv\Scripts\activate.bat' is not recognized as an internal or external command
[ERROR] Failed to activate virtual environment
```

**It means the virtual environment doesn't exist yet.**

---

## ✅ Solution: Follow These Steps EXACTLY

### Step 1: Open Command Prompt

1. Press `Windows Key + R`
2. Type: `cmd`
3. Press Enter

### Step 2: Navigate to Project Folder

```cmd
cd C:\Users\User\chakshi2
```
*(Replace with YOUR actual path where you extracted the project)*

To verify you're in the right folder:
```cmd
dir
```
You should see: `backend`, `frontend`, `README.md`, etc.

### Step 3: Create Virtual Environment

```cmd
python -m venv venv
```

Wait for it to complete (takes 30-60 seconds).

### Step 4: Activate Virtual Environment

```cmd
venv\Scripts\activate
```

You should now see `(venv)` at the beginning of your command prompt line:
```cmd
(venv) C:\Users\User\chakshi2>
```

### Step 5: Install Dependencies

```cmd
pip install -r requirements.txt
```

This will take 2-3 minutes. Wait for it to complete.

### Step 6: Install Playwright Browser

```cmd
python -m playwright install chromium
```

This will take 5-10 minutes. Wait for it to complete.

### Step 7: Start the Backend

```cmd
cd backend
python app.py
```

You should see:
```
INFO:     Started server process [xxxxx]
[INFO] eCourts Chatbot API starting up...
INFO:     Uvicorn running on http://0.0.0.0:8000
```

**✅ Keep this window open!** This is your backend server running.

### Step 8: Open the Frontend

Open a NEW window:
1. Open File Explorer
2. Navigate to: `C:\Users\User\chakshi2\frontend`
3. Double-click: `index.html`

Your browser will open with the chatbot!

---

## 🎯 Quick Version (Copy-Paste All)

**Open Command Prompt and paste these commands ONE BY ONE:**

```cmd
cd C:\Users\User\chakshi2
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
cd backend
python app.py
```

Then open `frontend\index.html` in your browser!

---

## 🚀 Even Easier: Use New Startup Script

I created a better script that does everything automatically:

**Just double-click: `SETUP_AND_RUN.bat`**

This new script will:
- ✅ Check Python is installed
- ✅ Create virtual environment automatically
- ✅ Install all dependencies
- ✅ Install Playwright browsers
- ✅ Start the backend server

Then just open `frontend\index.html`!

---

## 🐛 Troubleshooting

### "Python is not recognized"

**Fix:**
1. Install Python from: https://www.python.org/downloads/
2. During installation, **CHECK ✅ "Add Python to PATH"**
3. Restart Command Prompt

### "pip is not recognized"

**Fix:**
```cmd
python -m pip install --upgrade pip
```

### "Access denied" or "Permission denied"

**Fix:**
1. Right-click Command Prompt
2. Select "Run as administrator"
3. Try again

### "Port 8000 already in use"

**Fix:**
```cmd
taskkill /F /IM python.exe
```
Then start again.

### Virtual environment won't activate

**Fix: Delete and recreate it:**
```cmd
rmdir /s /q venv
python -m venv venv
venv\Scripts\activate
```

---

## ✅ Verify Everything Works

After setup, test it:

```cmd
cd C:\Users\User\chakshi2
python test_setup.py
```

Should show all green checkmarks ✓

---

## 🎯 To Search CNR: DLND010019612022

Once backend is running and frontend is open:

1. Bot asks: "How would you like to search?"
2. You click: **"Search by CNR"**
3. Bot asks: "Please enter the CNR number"
4. You type: **DLND010019612022**
5. Bot shows CAPTCHA image
6. You type what you see in the CAPTCHA
7. Bot fetches and displays all case details!

---

## 📞 Still Having Issues?

Run this diagnostic:
```cmd
cd C:\Users\User\chakshi2
python --version
pip --version
where python
```

Send me the output and I'll help debug!

---

**Remember:** The virtual environment needs to be created BEFORE you can activate it. That's what the new `SETUP_AND_RUN.bat` script does automatically!
