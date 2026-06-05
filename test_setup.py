#!/usr/bin/env python3
"""
eCourts Chatbot - Setup Verification Script
This script checks if all dependencies are installed correctly
"""

import sys
import subprocess

def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")

def print_check(name, success, message=""):
    status = "✓" if success else "✗"
    status_text = "OK" if success else "FAILED"
    print(f"[{status}] {name}: {status_text}")
    if message:
        print(f"    {message}")

def check_python_version():
    """Check Python version"""
    version = sys.version_info
    required = (3, 10)
    success = version >= required
    message = f"Python {version.major}.{version.minor}.{version.micro}"
    if not success:
        message += f" (Required: {required[0]}.{required[1]}+)"
    return success, message

def check_import(module_name, package_name=None):
    """Check if a Python package can be imported"""
    try:
        __import__(module_name)
        return True, f"{package_name or module_name} is installed"
    except ImportError as e:
        return False, f"{package_name or module_name} not found: {e}"

def check_playwright_browsers():
    """Check if Playwright browsers are installed"""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
                browser.close()
                return True, "Chromium browser is installed"
            except Exception as e:
                return False, f"Chromium not installed: {e}"
    except Exception as e:
        return False, f"Cannot check browsers: {e}"

def main():
    print_header("eCourts Chatbot - Setup Verification")

    all_checks = []

    # Check Python version
    print("Checking Python installation...")
    success, msg = check_python_version()
    print_check("Python Version", success, msg)
    all_checks.append(success)

    # Check required packages
    print("\nChecking Python packages...")

    packages = [
        ("fastapi", "FastAPI"),
        ("uvicorn", "Uvicorn"),
        ("playwright", "Playwright"),
        ("pydantic", "Pydantic"),
        ("dotenv", "python-dotenv"),
        ("aiofiles", "aiofiles"),
    ]

    for module, name in packages:
        success, msg = check_import(module, name)
        print_check(name, success, msg)
        all_checks.append(success)

    # Check Playwright browsers
    print("\nChecking Playwright browsers...")
    success, msg = check_playwright_browsers()
    print_check("Playwright Browser", success, msg)
    all_checks.append(success)

    # Check project files
    print("\nChecking project files...")
    import os

    required_files = [
        "backend/app.py",
        "frontend/index.html",
        "requirements.txt",
        "README.md",
    ]

    for file_path in required_files:
        exists = os.path.exists(file_path)
        print_check(file_path, exists, "Found" if exists else "Missing")
        all_checks.append(exists)

    # Summary
    print_header("Summary")

    passed = sum(all_checks)
    total = len(all_checks)

    print(f"Passed: {passed}/{total} checks")

    if all(all_checks):
        print("\n🎉 SUCCESS! All checks passed.")
        print("\nYou can now run the chatbot:")
        print("  1. Windows: Double-click RUN_CHATBOT.bat")
        print("  2. Linux/Mac: ./start.sh")
        print("  3. Manual: cd backend && python app.py")
        return 0
    else:
        print("\n❌ FAILED! Some checks did not pass.")
        print("\nPlease fix the issues above and try again.")
        print("\nCommon fixes:")
        print("  - Install Python 3.10+: https://www.python.org/downloads/")
        print("  - Install packages: pip install -r requirements.txt")
        print("  - Install browsers: python -m playwright install chromium")
        return 1

if __name__ == "__main__":
    try:
        exit_code = main()
        print("\n" + "="*60)
        input("\nPress Enter to exit...")
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nError during verification: {e}")
        import traceback
        traceback.print_exc()
        input("\nPress Enter to exit...")
        sys.exit(1)
