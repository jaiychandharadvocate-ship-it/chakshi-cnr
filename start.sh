#!/bin/bash

# eCourts Chatbot Startup Script

echo "🏛️  Starting eCourts Chatbot..."
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found!"
    echo "Please run: python -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# Activate virtual environment
echo "✅ Activating virtual environment..."
source venv/bin/activate

# Check if dependencies are installed
if ! python -c "import fastapi" 2>/dev/null; then
    echo "❌ Dependencies not installed!"
    echo "Please run: pip install -r requirements.txt"
    exit 1
fi

# Check if Playwright browsers are installed
if [ ! -d "$HOME/.cache/ms-playwright/chromium-"* ]; then
    echo "⚠️  Playwright browsers not found. Installing..."
    python -m playwright install chromium
fi

# Start the backend
echo "✅ Starting FastAPI backend on http://localhost:8000 ..."
echo ""
echo "📝 Backend logs:"
echo "─────────────────────────────────────────────────"

cd backend
python app.py &
BACKEND_PID=$!

# Wait a bit for backend to start
sleep 3

# Check if backend started successfully
if ps -p $BACKEND_PID > /dev/null; then
    echo ""
    echo "─────────────────────────────────────────────────"
    echo "✅ Backend is running!"
    echo ""
    echo "🌐 Open the frontend:"
    echo "   Option 1: Open frontend/index.html in your browser"
    echo "   Option 2: Run in another terminal: cd frontend && python -m http.server 3000"
    echo ""
    echo "📖 API Documentation: http://localhost:8000/docs"
    echo ""
    echo "Press Ctrl+C to stop the server"
    echo ""

    # Keep the script running
    wait $BACKEND_PID
else
    echo ""
    echo "❌ Failed to start backend"
    exit 1
fi
