# 🌐 Run eCourts Chatbot Online (FREE)

No Python installation needed! Run directly in your browser.

---

## ⚡ EASIEST: Replit (Recommended)

### Setup (2 minutes):

1. **Go to Replit**: https://replit.com

2. **Sign up/Login** (free account)

3. **Import from GitHub**:
   - Click "+ Create Repl"
   - Choose "Import from GitHub"
   - Paste your repo URL
   - Click "Import from GitHub"

4. **Configure Replit**:
   - Replit will auto-detect it's a Python project
   - Click "Run" button

5. **Access the chatbot**:
   - Backend will start automatically
   - Click the URL Replit shows you
   - Or open the "Webview" tab

**Done!** Your chatbot is running online!

### Replit Configuration:

Create a file called `.replit` in your project:

```toml
run = "cd backend && python app.py"
language = "python3"

[env]
HEADLESS_MODE = "true"

[nix]
channel = "stable-23_11"
```

Create a file called `replit.nix`:

```nix
{ pkgs }: {
  deps = [
    pkgs.python311
    pkgs.chromium
  ];
}
```

---

## 🚀 Option 2: Render.com (Production-Ready)

### Setup (5 minutes):

1. **Go to Render**: https://render.com

2. **Sign up** (free account)

3. **New Web Service**:
   - Click "New +"
   - Select "Web Service"
   - Connect your GitHub repo

4. **Configure**:
   ```
   Name: ecourts-chatbot
   Environment: Python 3
   Build Command: pip install -r requirements.txt && playwright install chromium
   Start Command: cd backend && uvicorn app:app --host 0.0.0.0 --port $PORT
   ```

5. **Deploy**:
   - Click "Create Web Service"
   - Wait 5-10 minutes for deployment

6. **Access**:
   - Render gives you a URL like: https://ecourts-chatbot.onrender.com
   - Your chatbot is live!

---

## 🎯 Option 3: Railway.app (Very Easy)

### Setup (3 minutes):

1. **Go to Railway**: https://railway.app

2. **Sign up** with GitHub

3. **New Project**:
   - Click "New Project"
   - Choose "Deploy from GitHub repo"
   - Select your chakshi2 repo

4. **Add Start Command**:
   - Go to Settings
   - Add start command: `cd backend && python app.py`

5. **Generate Domain**:
   - Settings → Generate Domain
   - Railway gives you a URL

**Done!** Chatbot is online!

---

## 🔧 Option 4: PythonAnywhere (Good for Python)

### Setup (5 minutes):

1. **Go to PythonAnywhere**: https://www.pythonanywhere.com

2. **Create free account**

3. **Upload your code**:
   - Files → Upload a file
   - Or use Git: `git clone your-repo-url`

4. **Install dependencies**:
   - Open Bash console
   - Run: `pip install -r requirements.txt --user`
   - Run: `playwright install chromium`

5. **Create Web App**:
   - Web → Add a new web app
   - Choose Manual configuration
   - Python 3.10

6. **Configure WSGI**:
   - Edit wsgi file to point to your FastAPI app

**Your chatbot is live!**

---

## 📱 Option 5: Google Cloud Run (Scalable)

Free tier includes 2 million requests/month!

### Quick Deploy:

```bash
# Install gcloud CLI
# Then:
gcloud run deploy ecourts-chatbot \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated
```

---

## 🎨 Best Option for You:

### If you want EASIEST:
👉 **Replit** - Just click Run, no config needed!

### If you want FREE & RELIABLE:
👉 **Render.com** - Auto-deploys from GitHub, free SSL

### If you want FASTEST setup:
👉 **Railway.app** - Deploy in 3 clicks

---

## 🌐 Making Frontend Work Online

Once backend is deployed, update frontend to use the online URL:

Edit `frontend/index.html`, find this line:
```javascript
const API_URL = 'http://localhost:8000';
```

Change to your online URL:
```javascript
const API_URL = 'https://your-app-name.onrender.com';  // or your Replit URL
```

---

## ⚡ QUICK START: Replit (Right Now!)

1. **Go here**: https://replit.com
2. **Sign up** (2 seconds with Google/GitHub)
3. **Import from GitHub**: Paste your repo URL
4. **Click RUN** ▶️
5. **Done!** Chatbot is online!

**Frontend URL will be**: `https://your-repl-name.your-username.repl.co`

---

## 🎯 Recommended: Replit

**Why Replit?**
- ✅ 100% free
- ✅ No credit card needed
- ✅ Runs in browser
- ✅ Auto-installs dependencies
- ✅ Built-in code editor
- ✅ Public URL automatically
- ✅ Can see frontend immediately

**Perfect for testing your chatbot!**

---

## 🔗 Access Your Online Chatbot

Once deployed on Replit/Render/Railway:

1. **Backend API**: Your deployed URL (e.g., https://myapp.onrender.com)
2. **API Docs**: https://myapp.onrender.com/docs
3. **Frontend**: Open `frontend/index.html` locally but it connects to online backend

Or deploy frontend too:
- **Netlify**: Drag & drop `frontend` folder
- **Vercel**: Connect GitHub repo
- **GitHub Pages**: Free static hosting

---

## 💡 Recommendation

**For testing CNR DLND010019612022 RIGHT NOW:**

1. Open **Replit.com**
2. Import your GitHub repo
3. Click **Run**
4. Wait 2 minutes
5. **Search your CNR!**

**No Python installation, no hassle!** 🎉

---

## 🆘 Need Help with Replit?

1. Create account: https://replit.com/signup
2. New Repl → Import from GitHub
3. Paste: Your chakshi2 repo URL
4. Click Run ▶️
5. Open Webview tab
6. Search CNR: DLND010019612022

**Works in any browser, on any device!**
