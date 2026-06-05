# backend/app.py
import asyncio
import base64
import os
import time
import json
import re
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
from dotenv import load_dotenv
from openai import OpenAI
from bs4 import BeautifulSoup

load_dotenv()

app = FastAPI(title="eCourts Chatbot API", version="1.0.0")

# Initialize OpenAI client with validation
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY_MY")
if not OPENAI_API_KEY:
    print("[WARN] OPENAI_API_KEY_MY not set - chat functionality will be limited")
    openai_client = None
else:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Conversation storage
CONVERSATIONS: Dict[str, Dict[str, Any]] = {}

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session storage (use Redis in production)
SESSIONS: Dict[str, Dict[str, Any]] = {}
SESSION_TIMEOUT = int(os.getenv("SESSION_TIMEOUT", "1800"))  # 30 minutes

# Multi-step party search statuses
PARTY_SEARCH_STEPS = [
    'awaiting_state',
    'awaiting_district', 
    'awaiting_court_complex',
    'awaiting_establishment',
    'awaiting_party_details',
    'awaiting_year',
    'awaiting_disposition',  # Pending/Disposed/Both selection
    'awaiting_captcha',
    'completed'
]

# Session timeout for viewing cases (5 minutes)
CASE_VIEW_TIMEOUT = 300  # 5 minutes in seconds

# eCourts endpoints mapping
ECOURTS_ENDPOINTS = {
    'case_status': 'https://services.ecourts.gov.in/ecourtindia_v6/?p=casestatus/index&app_token=8eb5ae802d0fe79f9422df57fd2da3f9ad2bb3dbcdcf8e1c85ecd7a71e3bf284',
    'cnr': 'https://services.ecourts.gov.in/ecourtindia_v6/?p=home/index&app_token=fa23b5de9baffe7a33e6e6660618657f5fe17815915b76bf2fb119b31f0f9e8a',
    'court_orders': 'https://services.ecourts.gov.in/ecourtindia_v6/?p=courtorder/index&app_token=ba399f32dca434c5d3844f1bbf1a3cc10893f2a89e6341134d88d49e0c786d48',
    'cause_list': 'https://services.ecourts.gov.in/ecourtindia_v6/?p=cause_list/index&app_token=db2fc03676d94555026470a0d4bb63f2bd62e754c559b0d90b5f54c0b3a5107c',
    'caveat': 'https://services.ecourts.gov.in/ecourtindia_v6/?p=caveat_search/index&app_token=e132fafaac1274ecaa49b10213b05dfbe216bb32f66a123b10931f1c7d3fd714',
    'party_name': 'https://services.ecourts.gov.in/ecourtindia_v6/?p=casestatus/index&app_token=8eb5ae802d0fe79f9422df57fd2da3f9ad2bb3dbcdcf8e1c85ecd7a71e3bf284'
}


class SearchRequest(BaseModel):
    mode: str  # 'cnr', 'party_name', 'case_status', 'court_orders', 'cause_list', 'caveat'
    party_name: Optional[str] = None
    state_code: Optional[str] = None
    district_code: Optional[str] = None
    court_code: Optional[str] = None
    case_type: Optional[str] = None
    case_number: Optional[str] = None
    case_year: Optional[str] = None
    cnr_number: Optional[str] = None
    filing_number: Optional[str] = None


class CaptchaSubmit(BaseModel):
    session_id: str
    captcha_text: str


class ChatMessage(BaseModel):
    conversation_id: Optional[str] = None
    message: str


class ChatResponse(BaseModel):
    conversation_id: str
    response: str
    action: Optional[str] = None
    search_session_id: Optional[str] = None
    captcha_b64: Optional[str] = None
    results: Optional[Dict[str, Any]] = None


# Indian States and their codes for party name search
INDIAN_STATES = {
    "andhra pradesh": "1", "arunachal pradesh": "2", "assam": "3", "bihar": "4",
    "chhattisgarh": "5", "goa": "6", "gujarat": "7", "haryana": "8",
    "himachal pradesh": "9", "jharkhand": "10", "karnataka": "11", "kerala": "12",
    "madhya pradesh": "13", "maharashtra": "14", "manipur": "15", "meghalaya": "16",
    "mizoram": "17", "nagaland": "18", "odisha": "19", "punjab": "20",
    "rajasthan": "21", "sikkim": "22", "tamil nadu": "23", "telangana": "24",
    "tripura": "25", "uttar pradesh": "26", "uttarakhand": "27", "west bengal": "28",
    "delhi": "29", "jammu and kashmir": "30", "ladakh": "31",
    "andaman and nicobar": "32", "chandigarh": "33", "dadra and nagar haveli": "34",
    "daman and diu": "35", "lakshadweep": "36", "puducherry": "37"
}

SYSTEM_PROMPT = """You are an eCourts Case Search Assistant for Indian courts. You help users search for case details.

Your capabilities:
1. Search by CNR Number (Case Number Record) - a 16-character unique identifier
2. Search by Party Name - interactive dropdown selection from eCourts website

CONVERSATION FLOW:
- Greet users and ask how you can help
- Detect if user wants to search by CNR or Party Name
- For CNR search: Ask for the CNR number (format: 16 alphanumeric characters like DLND010019612022)
- For Party Name search: START IMMEDIATELY when user mentions "party name", "party search", "search by name", or similar. The system will guide them through dropdown selections.

IMPORTANT RULES:
- Be conversational and helpful
- For CNR: validate format (16 alphanumeric characters)
- For Party Name: trigger start_party_search action IMMEDIATELY when user wants to search by party name. Do NOT ask for state/district - the system will present dropdown options from the live eCourts website.

OUTPUT FORMAT:
Always respond with valid JSON:
{
  "message": "Your conversational response",
  "action": null or "start_cnr_search" or "start_party_search",
  "search_params": {
    "mode": "cnr" or "party_name",
    "cnr_number": "CNR if applicable"
  },
  "missing_info": []
}

TRIGGER start_party_search when:
- User says "party name", "search by name", "party search"
- User mentions a person's name to search
- User wants to find a case but doesn't have CNR
"""


def get_ai_response(conversation_history: List[Dict[str, str]], user_message: str) -> Dict[str, Any]:
    """Get AI response from OpenAI"""
    
    # Fallback if OpenAI client not available
    if not openai_client:
        # Basic pattern matching fallback
        lower_msg = user_message.lower()
        if 'cnr' in lower_msg or len(re.findall(r'[A-Z]{4}\d{12}', user_message.upper())) > 0:
            cnr_match = re.search(r'[A-Z]{4}\d{12}', user_message.upper())
            if cnr_match:
                return {
                    "message": f"Starting search for CNR: {cnr_match.group()}",
                    "action": "start_cnr_search",
                    "search_params": {"mode": "cnr", "cnr_number": cnr_match.group()},
                    "missing_info": []
                }
        return {
            "message": "Please provide a CNR number (16 characters like DLND010019612022) or tell me the party name you want to search.",
            "action": None,
            "search_params": None,
            "missing_info": []
        }
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(conversation_history)
    messages.append({"role": "user", "content": user_message})
    
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
            max_tokens=500
        )
        
        content = response.choices[0].message.content
        
        # Try to parse as JSON
        try:
            # Clean up the response - remove markdown code blocks if present
            cleaned = content.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r'^```(?:json)?\n?', '', cleaned)
                cleaned = re.sub(r'\n?```$', '', cleaned)
            
            result = json.loads(cleaned)
            
            # Validate required keys
            if 'message' not in result:
                result['message'] = "How can I help you with your case search?"
            if 'action' not in result:
                result['action'] = None
            if 'search_params' not in result:
                result['search_params'] = None
            if 'missing_info' not in result:
                result['missing_info'] = []
                
            return result
        except json.JSONDecodeError:
            # If not valid JSON, return as plain message
            return {
                "message": content,
                "action": None,
                "search_params": None,
                "missing_info": []
            }
    except Exception as e:
        print(f"[ERROR] OpenAI API error: {e}")
        return {
            "message": "I apologize, but I'm having trouble processing your request. Could you please try again?",
            "action": None,
            "search_params": None,
            "missing_info": []
        }


def format_case_results(results: Dict[str, Any]) -> str:
    """Format case results into a readable message"""
    if not results:
        return "No results found."
    
    if results.get('error'):
        return f"Error: {results['error']}"
    
    case_details = results.get('case_details', {})
    tables = results.get('tables', [])
    
    formatted = []
    
    if case_details:
        formatted.append("📋 **Case Details Found:**\n")
        
        field_labels = {
            'cnr_number': '🔢 CNR Number',
            'case_type': '📁 Case Type',
            'filing_number': '📄 Filing Number',
            'filing_date': '📅 Filing Date',
            'registration_number': '🔖 Registration Number',
            'registration_date': '📅 Registration Date',
            'petitioner': '👤 Petitioner',
            'respondent': '👥 Respondent',
            'petitioner_advocate': '⚖️ Petitioner Advocate',
            'respondent_advocate': '⚖️ Respondent Advocate',
            'under_act': '📜 Under Act',
            'under_section': '📖 Under Section',
            'court_name': '🏛️ Court',
            'judge': '👨‍⚖️ Judge',
            'case_status': '📊 Status',
            'next_hearing_date': '📆 Next Hearing',
            'disposal_date': '✅ Disposal Date',
            'nature_of_disposal': '📋 Nature of Disposal'
        }
        
        for key, label in field_labels.items():
            if key in case_details and case_details[key]:
                formatted.append(f"{label}: {case_details[key]}")
    
    # Add case history from tables if present
    if tables and len(tables) > 1:
        for table in tables:
            if 'Case History' in str(table.get('data', [])) or table.get('index', 0) > 3:
                formatted.append("\n📜 **Case History:**")
                for row in table.get('data', [])[:5]:  # Show last 5 hearings
                    if len(row) >= 3:
                        formatted.append(f"  • {' | '.join(str(cell) for cell in row[:4])}")
                break
    
    if not formatted:
        # Check if we have case items from list-group (party search often returns a list)
        cases = results.get('cases', [])
        if cases and isinstance(cases, list) and len(cases) > 0:
            formatted.append("📋 **Search Results - Cases Found:**\n")
            for i, case in enumerate(cases[:10], 1):
                if isinstance(case, dict):
                    # Structured case details
                    case_str = []
                    for key in ['cnr_number', 'case_type', 'petitioner', 'respondent', 'case_status']:
                        if key in case:
                            case_str.append(f"{key.replace('_', ' ').title()}: {case[key]}")
                    if case_str:
                        formatted.append(f"\n**Case {i}:**")
                        for item in case_str:
                            formatted.append(f"  • {item}")
                elif isinstance(case, str) and len(case) > 20:
                    # Clean the case text - remove navigation/form elements
                    clean_case = case.strip()
                    if not any(skip in clean_case.lower() for skip in ['select state', 'select district', 'andaman', 'andhra']):
                        formatted.append(f"\n**Case {i}:**\n{clean_case[:500]}")
            if len(formatted) > 1:
                return "\n".join(formatted)
        
        # Check if we have tables with case list
        tables = results.get('tables', [])
        if tables:
            formatted.append("📋 **Search Results:**\n")
            for table in tables[:3]:
                for row in table.get('data', [])[:10]:
                    if len(row) >= 2:
                        row_text = ' | '.join(str(cell) for cell in row[:5])
                        # Skip rows with dropdown content
                        if not any(skip in row_text.lower() for skip in ['select state', 'andaman', 'andhra pradesh']):
                            formatted.append(f"• {row_text}")
            if len(formatted) > 1:
                return "\n".join(formatted)
        
        # Fallback to raw text (already filtered from navigation)
        raw_text = results.get('raw_text', [])
        if raw_text and len(raw_text[0]) > 30:
            # Double-check that raw text isn't just dropdown content
            if not any(skip in raw_text[0].lower() for skip in ['andaman', 'andhra pradesh', 'select state']):
                return "📋 **Case Information:**\n" + raw_text[0][:1500]
        
        return "No matching records found for your search criteria. Please verify the party name, state, district, court, and year."
    
    return "\n".join(formatted)


async def cleanup_old_sessions():
    """Remove sessions older than SESSION_TIMEOUT"""
    current_time = time.time()
    to_remove = []

    for session_id, session in SESSIONS.items():
        if current_time - session.get('created_at', 0) > SESSION_TIMEOUT:
            to_remove.append(session_id)
            # Clean up browser resources
            try:
                if 'context' in session:
                    await session['context'].close()
                if 'browser' in session:
                    await session['browser'].close()
                if 'pw' in session:
                    await session['pw'].stop()
            except Exception:
                pass

    for session_id in to_remove:
        del SESSIONS[session_id]


async def start_browser(headless: bool = True):
    """Initialize Playwright browser"""
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=headless,
        args=['--disable-blink-features=AutomationControlled']
    )
    return pw, browser


async def wait_for_element(page: Page, selectors: list, timeout: int = 5000):
    """Try multiple selectors and return first found element"""
    for selector in selectors:
        try:
            element = await page.wait_for_selector(selector, timeout=timeout)
            if element:
                return element, selector
        except Exception:
            continue
    return None, None


async def scrape_dropdown_options(page: Page, selector: str) -> List[Dict[str, str]]:
    """Scrape options from a dropdown element"""
    options = []
    try:
        option_elements = await page.query_selector_all(f'{selector} option')
        for opt in option_elements:
            value = await opt.get_attribute('value')
            text = await opt.text_content()
            if value and text and value.strip() and text.strip() != 'Select':
                options.append({'value': value.strip(), 'text': text.strip()})
    except Exception as e:
        print(f"[DEBUG] Error scraping dropdown {selector}: {e}")
    return options


async def init_party_search_session(session_id: str):
    """Initialize a party name search session - navigate to eCourts and scrape state options"""
    pw = None
    browser = None
    
    try:
        SESSIONS[session_id]['status'] = 'initializing'
        
        url = ECOURTS_ENDPOINTS['party_name']
        print(f"[INFO] Initializing party search session {session_id}")
        
        headless = os.getenv('HEADLESS_MODE', 'true').lower() == 'true'
        pw, browser = await start_browser(headless=headless)
        
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        
        page = await context.new_page()
        
        print(f"[INFO] Navigating to {url}")
        await page.goto(url, wait_until='networkidle', timeout=60000)
        await page.wait_for_timeout(2000)
        
        # Scrape state options
        state_selectors = ['select#sess_state_code', 'select#state_code', 'select[name="state_code"]']
        state_options = []
        used_selector = None
        
        for sel in state_selectors:
            state_options = await scrape_dropdown_options(page, sel)
            if state_options:
                used_selector = sel
                print(f"[DEBUG] Found {len(state_options)} states using {sel}")
                break
        
        if not state_options:
            raise Exception("Could not scrape state options from eCourts")
        
        # Store session data
        SESSIONS[session_id].update({
            'status': 'awaiting_state',
            'page': page,
            'context': context,
            'browser': browser,
            'pw': pw,
            'state_options': state_options,
            'state_selector': used_selector,
            'selected_state': None,
            'selected_district': None,
            'selected_court_complex': None,
            'selected_establishment': None,
            'district_options': [],
            'court_complex_options': [],
            'establishment_options': []
        })
        
        print(f"[INFO] Party search session {session_id} ready with {len(state_options)} states")
        
    except Exception as e:
        print(f"[ERROR] Error initializing party search session {session_id}: {e}")
        SESSIONS[session_id]['status'] = 'error'
        SESSIONS[session_id]['error'] = str(e)
        
        try:
            if browser:
                await browser.close()
            if pw:
                await pw.stop()
        except Exception:
            pass


async def select_state_and_get_districts(session_id: str, state_value: str, state_text: str):
    """Select a state and scrape available districts"""
    session = SESSIONS.get(session_id)
    if not session:
        return
    
    try:
        page = session['page']
        state_selector = session.get('state_selector', 'select#sess_state_code')
        
        # Select the state
        await page.select_option(state_selector, state_value)
        print(f"[DEBUG] Selected state: {state_text} ({state_value})")
        
        # Wait for district dropdown to populate (AJAX)
        await page.wait_for_timeout(2500)
        
        # Scrape district options
        district_selectors = ['select#sess_dist_code', 'select#dist_code', 'select[name="dist_code"]']
        district_options = []
        used_selector = None
        
        for sel in district_selectors:
            district_options = await scrape_dropdown_options(page, sel)
            if district_options:
                used_selector = sel
                print(f"[DEBUG] Found {len(district_options)} districts using {sel}")
                break
        
        session.update({
            'status': 'awaiting_district',
            'selected_state': {'value': state_value, 'text': state_text},
            'district_options': district_options,
            'district_selector': used_selector
        })
        
    except Exception as e:
        print(f"[ERROR] Error selecting state: {e}")
        session['status'] = 'error'
        session['error'] = str(e)


async def select_district_and_get_courts(session_id: str, district_value: str, district_text: str):
    """Select a district and scrape available court complexes"""
    session = SESSIONS.get(session_id)
    if not session:
        return
    
    try:
        page = session['page']
        district_selector = session.get('district_selector', 'select#sess_dist_code')
        
        # Select the district
        await page.select_option(district_selector, district_value)
        print(f"[DEBUG] Selected district: {district_text} ({district_value})")
        
        # Wait for court complex dropdown to populate
        await page.wait_for_timeout(2500)
        
        # Scrape court complex options
        court_selectors = ['select#court_complex_code', 'select[name="court_complex_code"]']
        court_options = []
        used_selector = None
        
        for sel in court_selectors:
            court_options = await scrape_dropdown_options(page, sel)
            if court_options:
                used_selector = sel
                print(f"[DEBUG] Found {len(court_options)} court complexes using {sel}")
                break
        
        session.update({
            'status': 'awaiting_court_complex',
            'selected_district': {'value': district_value, 'text': district_text},
            'court_complex_options': court_options,
            'court_complex_selector': used_selector
        })
        
    except Exception as e:
        print(f"[ERROR] Error selecting district: {e}")
        session['status'] = 'error'
        session['error'] = str(e)


async def select_court_complex_and_get_establishments(session_id: str, court_value: str, court_text: str):
    """Select a court complex and scrape available establishments"""
    session = SESSIONS.get(session_id)
    if not session:
        return
    
    try:
        page = session['page']
        court_selector = session.get('court_complex_selector', 'select#court_complex_code')
        
        if court_value and court_value != 'skip':
            await page.select_option(court_selector, court_value)
            print(f"[DEBUG] Selected court complex: {court_text} ({court_value})")
            await page.wait_for_timeout(2000)
        
        # Scrape establishment options
        est_selectors = ['select#court_est_code', 'select[name="court_est_code"]', 'select#establishment_code']
        est_options = []
        used_selector = None
        
        for sel in est_selectors:
            est_options = await scrape_dropdown_options(page, sel)
            if est_options:
                used_selector = sel
                print(f"[DEBUG] Found {len(est_options)} establishments using {sel}")
                break
        
        session.update({
            'status': 'awaiting_establishment',
            'selected_court_complex': {'value': court_value, 'text': court_text} if court_value != 'skip' else None,
            'establishment_options': est_options,
            'establishment_selector': used_selector
        })
        
    except Exception as e:
        print(f"[ERROR] Error selecting court complex: {e}")
        session['status'] = 'error'
        session['error'] = str(e)


async def select_establishment_and_prepare_form(session_id: str, est_value: str, est_text: str):
    """Select an establishment and prepare for party name entry"""
    session = SESSIONS.get(session_id)
    if not session:
        return
    
    try:
        page = session['page']
        
        if est_value and est_value != 'skip':
            est_selector = session.get('establishment_selector', 'select#court_est_code')
            await page.select_option(est_selector, est_value)
            print(f"[DEBUG] Selected establishment: {est_text} ({est_value})")
            await page.wait_for_timeout(1000)
        
        session.update({
            'status': 'awaiting_party_details',
            'selected_establishment': {'value': est_value, 'text': est_text} if est_value != 'skip' else None
        })
        
    except Exception as e:
        print(f"[ERROR] Error selecting establishment: {e}")
        session['status'] = 'error'
        session['error'] = str(e)


async def fill_party_details_and_captcha(session_id: str, party_name: str, year: str):
    """Fill party name and year, then capture CAPTCHA"""
    session = SESSIONS.get(session_id)
    if not session:
        return
    
    try:
        page = session['page']
        
        # Click Party Name tab
        party_tab_selectors = [
            'a:has-text("Party Name")',
            'li a:has-text("Party Name")',
            '#partyname-tab',
            'a[href="#partyname"]'
        ]
        
        tab_clicked = False
        for selector in party_tab_selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    await element.click()
                    await page.wait_for_timeout(1500)
                    tab_clicked = True
                    print(f"[DEBUG] Clicked Party Name tab using: {selector}")
                    break
            except:
                pass
        
        if not tab_clicked:
            await page.evaluate("""
                const links = document.querySelectorAll('a');
                for (const link of links) {
                    if (link.textContent.toLowerCase().includes('party name')) {
                        link.click();
                        break;
                    }
                }
            """)
            await page.wait_for_timeout(1500)
        
        # Fill party name using JS (most reliable)
        await page.evaluate(f"""
            const inputs = document.querySelectorAll('input[type="text"]');
            for (const inp of inputs) {{
                const id = (inp.id || '').toLowerCase();
                const name = (inp.name || '').toLowerCase();
                const placeholder = (inp.placeholder || '').toLowerCase();
                if (id.includes('pet') || name.includes('pet') || 
                    placeholder.includes('petitioner') || placeholder.includes('respondent')) {{
                    inp.focus();
                    inp.value = '{party_name.upper()}';
                    inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    break;
                }}
            }}
        """)
        print(f"[DEBUG] Filled party name: {party_name.upper()}")
        
        # Fill year
        if year:
            await page.evaluate(f"""
                const inputs = document.querySelectorAll('input');
                for (const inp of inputs) {{
                    const placeholder = (inp.placeholder || '').toLowerCase();
                    const id = (inp.id || '').toLowerCase();
                    if (placeholder.includes('year') || id.includes('year') || id.includes('rgyear')) {{
                        inp.value = '{year}';
                        inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        break;
                    }}
                }}
            """)
            print(f"[DEBUG] Filled year: {year}")
        
        await page.wait_for_timeout(1000)
        
        # Capture CAPTCHA
        captcha_b64, selector_used = await capture_captcha(page)
        
        if not captcha_b64:
            session['status'] = 'error'
            session['error'] = 'Could not capture CAPTCHA image'
            return
        
        session.update({
            'status': 'awaiting_captcha',
            'captcha_b64': captcha_b64,
            'captcha_selector': selector_used,
            'party_name': party_name,
            'case_year': year
        })
        
        print(f"[INFO] CAPTCHA captured for session {session_id}")
        
    except Exception as e:
        print(f"[ERROR] Error filling party details: {e}")
        session['status'] = 'error'
        session['error'] = str(e)


async def fill_party_details_and_captcha_with_disposition(session_id: str, party_name: str, year: str, disposition: str):
    """Fill party name, year, and disposition (Pending/Disposed/Both), then capture CAPTCHA"""
    session = SESSIONS.get(session_id)
    if not session:
        return
    
    try:
        page = session['page']
        
        # Click Party Name tab
        party_tab_selectors = [
            'a:has-text("Party Name")',
            'li a:has-text("Party Name")',
            '#partyname-tab',
            'a[href="#partyname"]'
        ]
        
        tab_clicked = False
        for selector in party_tab_selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    await element.click()
                    await page.wait_for_timeout(1500)
                    tab_clicked = True
                    print(f"[DEBUG] Clicked Party Name tab using: {selector}")
                    break
            except:
                pass
        
        if not tab_clicked:
            await page.evaluate("""
                const links = document.querySelectorAll('a');
                for (const link of links) {
                    if (link.textContent.toLowerCase().includes('party name')) {
                        link.click();
                        break;
                    }
                }
            """)
            await page.wait_for_timeout(1500)
        
        # Fill party name using JS (most reliable)
        await page.evaluate(f"""
            const inputs = document.querySelectorAll('input[type="text"]');
            for (const inp of inputs) {{
                const id = (inp.id || '').toLowerCase();
                const name = (inp.name || '').toLowerCase();
                const placeholder = (inp.placeholder || '').toLowerCase();
                if (id.includes('pet') || name.includes('pet') || 
                    placeholder.includes('petitioner') || placeholder.includes('respondent') ||
                    placeholder.includes('party')) {{
                    inp.focus();
                    inp.value = '{party_name.upper()}';
                    inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    break;
                }}
            }}
        """)
        print(f"[DEBUG] Filled party name: {party_name.upper()}")
        
        # Fill year
        if year:
            await page.evaluate(f"""
                const inputs = document.querySelectorAll('input');
                for (const inp of inputs) {{
                    const placeholder = (inp.placeholder || '').toLowerCase();
                    const id = (inp.id || '').toLowerCase();
                    if (placeholder.includes('year') || id.includes('year') || id.includes('rgyear')) {{
                        inp.value = '{year}';
                        inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        break;
                    }}
                }}
            """)
            print(f"[DEBUG] Filled year: {year}")
        
        # Select disposition (Pending/Disposed/Both)
        disposition_map = {
            'pending': 'P',
            'disposed': 'D',
            'both': 'B'
        }
        disp_value = disposition_map.get(disposition, 'B')
        
        # Try to click the correct radio button
        await page.evaluate(f"""
            // Find and click the disposition radio button
            const radios = document.querySelectorAll('input[type="radio"]');
            for (const radio of radios) {{
                const id = (radio.id || '').toLowerCase();
                const value = (radio.value || '').toUpperCase();
                const labelText = radio.parentElement ? (radio.parentElement.textContent || '').toLowerCase() : '';
                
                if ('{disposition}' === 'pending' && (value === 'P' || id.includes('pending') || labelText.includes('pending'))) {{
                    radio.click();
                    break;
                }} else if ('{disposition}' === 'disposed' && (value === 'D' || id.includes('disposed') || labelText.includes('disposed'))) {{
                    radio.click();
                    break;
                }} else if ('{disposition}' === 'both' && (value === 'B' || id.includes('both') || labelText.includes('both'))) {{
                    radio.click();
                    break;
                }}
            }}
        """)
        print(f"[DEBUG] Selected disposition: {disposition}")
        
        await page.wait_for_timeout(1000)
        
        # Capture CAPTCHA
        captcha_b64, selector_used = await capture_captcha(page)
        
        if not captcha_b64:
            session['status'] = 'error'
            session['error'] = 'Could not capture CAPTCHA image'
            return
        
        session.update({
            'status': 'awaiting_captcha',
            'captcha_b64': captcha_b64,
            'captcha_selector': selector_used,
            'party_name': party_name,
            'case_year': year,
            'disposition': disposition,
            'captcha_loading': False,  # Clear loading flag
            'case_view_start': time.time()  # Track when results are available for viewing
        })
        
        print(f"[INFO] CAPTCHA captured for session {session_id}")
        
    except Exception as e:
        print(f"[ERROR] Error filling party details with disposition: {e}")
        session['status'] = 'error'
        session['error'] = str(e)


def format_options_message(options: List[Dict[str, str]], title: str, allow_skip: bool = False) -> str:
    """Format dropdown options as a numbered list for user selection"""
    if not options:
        return f"No {title.lower()} options available."
    
    lines = [f"Please select a {title}:"]
    for i, opt in enumerate(options, 1):
        lines.append(f"{i}. {opt['text']}")
    
    if allow_skip:
        lines.append(f"\nOr type 'skip' to skip this selection.")
    
    lines.append(f"\nReply with the number of your choice (1-{len(options)}).")
    return "\n".join(lines)


async def fill_party_name_form(page: Page, params: Dict[str, Any]):
    """Fill the party name search form on Case Status page - AJAX-aware version
    
    eCourts flow:
    1. Select state at top -> triggers getDistricts()
    2. Select district -> triggers getCourtComplex()
    3. Select court complex (optional)
    4. Click Party Name tab
    5. Fill party name and year in the tab's form
    6. Submit -> triggers getPartyDetails()
    """
    print(f"[DEBUG] Filling party name form with params: {params}")

    # Wait for page to load fully
    await page.wait_for_load_state('networkidle', timeout=60000)
    await page.wait_for_timeout(2000)

    # STEP 1: Select state at TOP of page (BEFORE clicking Party Name tab)
    state = params.get('state_code', '')
    if state:
        state_selectors = ['select#state_code', 'select#sess_state_code', 'select[name="state_code"]']
        state_selected = False
        for state_selector in state_selectors:
            try:
                el = await page.query_selector(state_selector)
                if not el:
                    continue
                options = await page.query_selector_all(f'{state_selector} option')
                state_value = None
                for option in options:
                    text = await option.text_content()
                    if text and state.lower() in text.lower():
                        state_value = await option.get_attribute('value')
                        if state_value:
                            print(f"[DEBUG] Found state '{text}' with value '{state_value}'")
                            break
                if state_value:
                    await page.select_option(state_selector, state_value)
                    print(f"[DEBUG] Selected state using: {state_selector}")
                    state_selected = True
                    await page.wait_for_timeout(2000)  # Wait for district dropdown to populate
                    break
            except Exception as e:
                print(f"[DEBUG] State selector {state_selector} failed: {e}")
        
        if not state_selected:
            # JS fallback for state
            try:
                await page.evaluate(f"""
                    const selects = document.querySelectorAll('select');
                    for (const sel of selects) {{
                        const id = (sel.id || '').toLowerCase();
                        if (id.includes('state')) {{
                            for (const opt of sel.options) {{
                                if (opt.text.toLowerCase().includes('{state.lower()}')) {{
                                    sel.value = opt.value;
                                    sel.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                    break;
                                }}
                            }}
                            break;
                        }}
                    }}
                """)
                print(f"[DEBUG] Selected state using JS fallback")
                await page.wait_for_timeout(2000)
            except Exception as e:
                print(f"[DEBUG] JS state selection failed: {e}")

    # STEP 2: Select district at TOP of page
    district = params.get('district_code', '')
    if district:
        district_selectors = ['select#dist_code', 'select#sess_dist_code', 'select[name="dist_code"]']
        district_selected = False
        for district_selector in district_selectors:
            try:
                el = await page.query_selector(district_selector)
                if not el:
                    continue
                options = await page.query_selector_all(f'{district_selector} option')
                district_value = None
                for option in options:
                    text = await option.text_content()
                    if text and district.lower() in text.lower():
                        district_value = await option.get_attribute('value')
                        if district_value:
                            print(f"[DEBUG] Found district '{text}' with value '{district_value}'")
                            break
                if district_value:
                    await page.select_option(district_selector, district_value)
                    print(f"[DEBUG] Selected district using: {district_selector}")
                    district_selected = True
                    await page.wait_for_timeout(2000)  # Wait for court dropdown
                    break
            except Exception as e:
                print(f"[DEBUG] District selector {district_selector} failed: {e}")
        
        if not district_selected:
            # JS fallback for district
            try:
                await page.evaluate(f"""
                    const selects = document.querySelectorAll('select');
                    for (const sel of selects) {{
                        const id = (sel.id || '').toLowerCase();
                        if (id.includes('dist')) {{
                            for (const opt of sel.options) {{
                                if (opt.text.toLowerCase().includes('{district.lower()}')) {{
                                    sel.value = opt.value;
                                    sel.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                    break;
                                }}
                            }}
                            break;
                        }}
                    }}
                """)
                print(f"[DEBUG] Selected district using JS fallback")
                await page.wait_for_timeout(2000)
            except Exception as e:
                print(f"[DEBUG] JS district selection failed: {e}")

    # STEP 3: Select court complex if available (optional at TOP of page)
    court_complex_selector = 'select#court_complex_code'
    try:
        court_complex = await page.query_selector(court_complex_selector)
        if court_complex:
            options = await page.query_selector_all(f'{court_complex_selector} option')
            if len(options) > 1:  # More than just "Select" option
                # Select first available court complex
                for option in options[1:]:  # Skip first "Select" option
                    value = await option.get_attribute('value')
                    if value:
                        try:
                            async with page.expect_response(
                                lambda resp: 'getCourtEstablishments' in resp.url or 'establishment' in resp.url.lower(),
                                timeout=10000
                            ) as response_info:
                                await page.select_option(court_complex_selector, value)
                                print(f"[DEBUG] Selected court complex, waiting for AJAX...")
                            response = await response_info.value
                            print(f"[DEBUG] Court establishments AJAX completed: {response.status}")
                        except:
                            await page.select_option(court_complex_selector, value)
                            print(f"[DEBUG] Selected court complex (no AJAX wait)")
                        await page.wait_for_timeout(1000)
                        break
    except Exception as e:
        print(f"[DEBUG] Court complex selection skipped: {e}")

    # STEP 4: NOW click on "Party Name" tab (after location is set)
    party_tab_selectors = [
        'a:has-text("Party Name")',
        'li a:has-text("Party Name")',
        'a[onclick*="partyname"]',
        '#partyname-tab',
        'a[href="#partyname"]',
        '[data-toggle="tab"]:has-text("Party Name")'
    ]

    tab_clicked = False
    for selector in party_tab_selectors:
        try:
            element = await page.query_selector(selector)
            if element:
                await element.click()
                await page.wait_for_timeout(1500)
                tab_clicked = True
                print(f"[DEBUG] Clicked party name tab using: {selector}")
                break
        except Exception as e:
            pass

    if not tab_clicked:
        try:
            await page.evaluate("""
                const links = document.querySelectorAll('a');
                for (const link of links) {
                    if (link.textContent.toLowerCase().includes('party name')) {
                        link.click();
                        break;
                    }
                }
            """)
            await page.wait_for_timeout(1500)
            print("[DEBUG] Clicked party name tab using JS evaluation")
            tab_clicked = True
        except Exception as e:
            print(f"[DEBUG] JS tab click failed: {e}")

    # STEP 5: Fill party name in the form (now visible after clicking tab)
    party_name = params.get('party_name', '')
    if party_name:
        # Extract just the first party name if "vs" is present
        if ' vs ' in party_name.lower():
            party_name = party_name.lower().split(' vs ')[0].strip()
        elif ' v/s ' in party_name.lower():
            party_name = party_name.lower().split(' v/s ')[0].strip()
        
        # Use the correct selector based on eCourts structure
        party_selectors = [
            'input#pet_name',
            'input[name="pet_name"]',
            'input#petres_name',
            'input[name="petres_name"]',
            'input[placeholder*="Petitioner"]',
            'input[placeholder*="Enter Petitioner"]'
        ]
        
        filled = False
        for selector in party_selectors:
            try:
                element = await page.query_selector(selector)
                if element and await element.is_visible():
                    # Clear and fill with real typing events
                    await element.click()
                    await element.fill('')
                    await element.type(party_name.upper(), delay=50)  # Real typing with delay
                    # Trigger validation events
                    await page.keyboard.press('Tab')
                    print(f"[DEBUG] Filled party name '{party_name.upper()}' using: {selector}")
                    filled = True
                    break
            except Exception as e:
                print(f"[DEBUG] Could not fill party name with {selector}: {e}")
        
        if not filled:
            # JS fallback with proper events
            try:
                await page.evaluate(f"""
                    const inputs = document.querySelectorAll('input[type="text"]');
                    for (const inp of inputs) {{
                        const id = (inp.id || '').toLowerCase();
                        const name = (inp.name || '').toLowerCase();
                        const placeholder = (inp.placeholder || '').toLowerCase();
                        if (id.includes('pet') || name.includes('pet') || 
                            placeholder.includes('petitioner') || placeholder.includes('respondent')) {{
                            inp.focus();
                            inp.value = '{party_name.upper()}';
                            inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            inp.dispatchEvent(new Event('keyup', {{ bubbles: true }}));
                            break;
                        }}
                    }}
                """)
                print(f"[DEBUG] Filled party name using JS fallback with events")
            except Exception as e:
                print(f"[DEBUG] JS party name fill failed: {e}")

    # STEP 6: Fill registration year
    year = params.get('case_year', '')
    if year:
        year_selectors = [
            'input#rgyear',
            'input[name="rgyear"]',
            'input[placeholder*="Year"]',
            'input[placeholder*="Enter Year"]'
        ]
        year_filled = False
        for selector in year_selectors:
            try:
                element = await page.query_selector(selector)
                if element and await element.is_visible():
                    await element.click()
                    await element.fill(str(year))
                    await page.keyboard.press('Tab')
                    print(f"[DEBUG] Filled year '{year}' using: {selector}")
                    year_filled = True
                    break
            except Exception as e:
                pass
        
        if not year_filled:
            try:
                await page.evaluate(f"""
                    const inputs = document.querySelectorAll('input');
                    for (const inp of inputs) {{
                        const placeholder = (inp.placeholder || '').toLowerCase();
                        if (placeholder.includes('year')) {{
                            inp.value = '{year}';
                            inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            break;
                        }}
                    }}
                """)
                print(f"[DEBUG] Filled year using JS fallback")
            except Exception as e:
                print(f"[DEBUG] JS year fill failed: {e}")


async def fill_cnr_form(page: Page, params: Dict[str, Any]):
    """Fill the CNR search form"""
    print(f"[DEBUG] Filling CNR form with params: {params}")

    await page.wait_for_load_state('domcontentloaded', timeout=30000)

    # Try to click on CNR radio button or tab
    cnr_tab_selectors = [
        'input[value="cnr"]',
        'input[id*="cnr"]',
        'a:has-text("CNR")',
        'label:has-text("CNR")'
    ]

    for selector in cnr_tab_selectors:
        try:
            element = await page.query_selector(selector)
            if element:
                await element.click()
                await page.wait_for_timeout(300)
                break
        except Exception:
            pass

    # Fill CNR number
    if params.get('cnr_number'):
        cnr_input_selectors = [
            'input[name="cnr_number"]',
            'input[id="cnr_number"]',
            'input[name="cnrno"]',
            'input[placeholder*="CNR"]'
        ]

        for selector in cnr_input_selectors:
            try:
                await page.fill(selector, params['cnr_number'])
                print(f"[DEBUG] Filled CNR using selector: {selector}")
                break
            except Exception:
                pass


async def capture_captcha(page: Page):
    """Capture CAPTCHA image from the page"""
    print("[DEBUG] Attempting to capture CAPTCHA")

    # Wait for CAPTCHA to load
    await page.wait_for_timeout(1000)

    # Try multiple CAPTCHA selectors
    captcha_selectors = [
        'img#captcha_image',
        'img#captchaimg',
        'img.captcha',
        'img[src*="captcha"]',
        'img[alt*="captcha" i]',
        'img[alt*="Captcha" i]',
        'img[id*="captcha" i]',
        'canvas#captcha'  # Some sites use canvas
    ]

    captcha_element = None
    successful_selector = None

    for selector in captcha_selectors:
        try:
            element = await page.query_selector(selector)
            if element:
                # Check if element is visible
                is_visible = await element.is_visible()
                if is_visible:
                    captcha_element = element
                    successful_selector = selector
                    print(f"[DEBUG] Found CAPTCHA using selector: {selector}")
                    break
        except Exception as e:
            print(f"[DEBUG] Selector {selector} failed: {e}")

    if not captcha_element:
        print("[DEBUG] CAPTCHA element not found, taking full page screenshot")
        # Fallback: take a screenshot of the whole page
        screenshot_bytes = await page.screenshot(full_page=False)
        return base64.b64encode(screenshot_bytes).decode(), 'full_page'

    # Screenshot the CAPTCHA element
    try:
        captcha_bytes = await captcha_element.screenshot()
        b64_image = base64.b64encode(captcha_bytes).decode()
        print(f"[DEBUG] CAPTCHA captured successfully using {successful_selector}")
        return b64_image, successful_selector
    except Exception as e:
        print(f"[DEBUG] Error capturing CAPTCHA screenshot: {e}")
        # Fallback to full page screenshot
        screenshot_bytes = await page.screenshot(full_page=False)
        return base64.b64encode(screenshot_bytes).decode(), 'full_page'


async def submit_form_and_scrape(page: Page, captcha_text: str):
    """Submit form with CAPTCHA and scrape results"""
    print(f"[DEBUG] Submitting form with captcha: {captcha_text}")
    
    # Track dialog/alert messages - eCourts uses JS alerts for errors
    dialog_messages = []
    captcha_invalid = False
    
    async def handle_dialog(dialog):
        nonlocal captcha_invalid
        msg = dialog.message.lower()
        dialog_messages.append(dialog.message)
        print(f"[DEBUG] Caught dialog alert: {dialog.message}")
        
        if 'captcha' in msg and ('invalid' in msg or 'wrong' in msg or 'incorrect' in msg or 'mismatch' in msg):
            captcha_invalid = True
            print("[DEBUG] Invalid CAPTCHA detected via dialog")
        elif 'no record' in msg or 'not found' in msg:
            print("[DEBUG] No records found - detected via dialog")
        
        await dialog.accept()  # Dismiss the dialog
    
    # Register dialog handler
    page.on('dialog', handle_dialog)

    # Fill CAPTCHA input - use query_selector first to avoid timeout issues
    captcha_input_selectors = [
        'input#captcha',
        'input[name="captcha"]',
        'input[id*="captcha" i]',
        'input[placeholder*="Captcha" i]',
        'input[placeholder*="captcha" i]',
        'input[type="text"][name*="captcha" i]'
    ]

    filled = False
    for selector in captcha_input_selectors:
        try:
            element = await page.query_selector(selector)
            if element:
                is_visible = await element.is_visible()
                if is_visible:
                    await element.fill(captcha_text)
                    print(f"[DEBUG] Filled CAPTCHA using selector: {selector}")
                    filled = True
                    break
        except Exception as e:
            print(f"[DEBUG] Could not fill CAPTCHA with {selector}: {e}")

    if not filled:
        print("[DEBUG] Trying to find any visible text input near CAPTCHA image")
        try:
            all_inputs = await page.query_selector_all('input[type="text"]')
            for inp in all_inputs:
                try:
                    is_visible = await inp.is_visible()
                    if is_visible:
                        await inp.fill(captcha_text)
                        print("[DEBUG] Filled a visible text input as fallback")
                        filled = True
                        break
                except:
                    pass
        except Exception as e:
            print(f"[DEBUG] Fallback input search failed: {e}")

    if not filled:
        raise Exception("Could not find CAPTCHA input field")

    # Small delay before clicking submit
    await page.wait_for_timeout(300)

    # Click submit button - eCourts uses button.btn.btn-primary for "Go" button
    # Priority: visible Go button > Search button > other submit buttons
    submit_selectors = [
        'button.btn.btn-primary:has-text("Go")',
        'button.btn-primary:has-text("Go")',
        'button:has-text("Go")',
        'input[value="Go"]',
        'button.btn.btn-primary',
        'button:has-text("Search")',
        'input[value="Search"]',
        'button[type="submit"]',
        'input[type="submit"]'
    ]

    clicked = False
    ajax_response_received = False
    
    # Try to click button and wait for AJAX response
    for selector in submit_selectors:
        try:
            button = await page.query_selector(selector)
            if button:
                is_visible = await button.is_visible()
                if is_visible:
                    # Try to click and wait for getPartyDetails AJAX
                    try:
                        async with page.expect_response(
                            lambda resp: 'getPartyDetails' in resp.url or 'party' in resp.url.lower() or 'search' in resp.url.lower(),
                            timeout=30000
                        ) as response_info:
                            await button.click()
                            print(f"[DEBUG] Clicked submit button: {selector}, waiting for AJAX...")
                        
                        response = await response_info.value
                        print(f"[DEBUG] Search AJAX completed: {response.status} - {response.url}")
                        clicked = True
                        ajax_response_received = True
                        break
                    except Exception as e:
                        # AJAX wait failed, but button was clicked
                        await button.click()
                        print(f"[DEBUG] Clicked submit button: {selector} (no AJAX wait)")
                        clicked = True
                        break
        except Exception as e:
            pass

    # JS fallback - click visible Go/Search button
    if not clicked:
        try:
            clicked = await page.evaluate("""() => {
                // Find the Go button first
                const goButtons = document.querySelectorAll('button.btn.btn-primary');
                for (const btn of goButtons) {
                    if (btn.textContent.trim().toLowerCase() === 'go' && btn.offsetParent !== null) {
                        btn.click();
                        return true;
                    }
                }
                // Fallback to any visible submit-like button
                const buttons = document.querySelectorAll('button, input[type="submit"], input[type="button"]');
                for (const btn of buttons) {
                    const text = (btn.textContent || btn.value || '').toLowerCase().trim();
                    if ((text === 'go' || text === 'search') && btn.offsetParent !== null) {
                        btn.click();
                        return true;
                    }
                }
                return false;
            }""")
            if clicked:
                print("[DEBUG] Clicked submit button using JS fallback")
        except Exception as e:
            print(f"[DEBUG] JS submit click failed: {e}")

    if not clicked:
        print("[DEBUG] Trying Enter key as fallback")
        await page.keyboard.press('Enter')

    # Wait for results
    print("[DEBUG] Waiting for results to load...")
    
    # Wait for result container with longer timeout (eCourts is slow: 60-90s typical)
    # Use DOM-based polling instead of AJAX waiting for better reliability
    print("[DEBUG] Polling for result containers (up to 90s)...")
    
    # Primary result selectors for party name search - based on eCourts actual structure
    # CRITICAL: The REAL results appear ONLY inside #res_party > #dispTable
    # NEVER use #showList, #showList1, #caseListResult - those are WRONG!
    result_selectors = [
        '#dispTable tbody tr',  # PRIMARY: The ONLY correct results table
        '#res_party #dispTable tbody tr',  # With parent container
        '#dispTable',  # Results table container
        '#res_party',  # Results container
        '#history_cnr table tbody tr',  # CNR history (different search type)
    ]
    
    found_results = False
    start_time = time.time()
    timeout_seconds = 90  # 90 second timeout for slow eCourts
    
    while (time.time() - start_time) < timeout_seconds:
        # Check if we caught an invalid CAPTCHA dialog
        if captcha_invalid:
            print("[DEBUG] Breaking out of polling - invalid CAPTCHA detected via dialog")
            break
        
        # Check if any dialog was captured (may indicate completion)
        if dialog_messages:
            print(f"[DEBUG] Dialog detected, checking content: {dialog_messages}")
            await page.wait_for_timeout(1000)  # Brief wait after dialog
            break
        
        for selector in result_selectors:
            try:
                elem = await page.query_selector(selector)
                if elem:
                    is_visible = await elem.is_visible()
                    if is_visible:
                        print(f"[DEBUG] Found result container: {selector}")
                        found_results = True
                        break
            except:
                pass
        
        if found_results:
            break
        
        # Check for table with "View" buttons using JavaScript (more reliable)
        try:
            has_view_buttons = await page.evaluate("""() => {
                const tables = document.querySelectorAll('table');
                for (const table of tables) {
                    const viewBtns = table.querySelectorAll('a, button');
                    for (const btn of viewBtns) {
                        if (btn.textContent && btn.textContent.trim().toLowerCase() === 'view' && btn.offsetParent !== null) {
                            return true;
                        }
                    }
                }
                return false;
            }""")
            if has_view_buttons:
                print("[DEBUG] Found table with View buttons via JS check")
                found_results = True
                break
        except:
            pass
            
        # Also check for error messages in DOM that indicate search completed
        try:
            page_text = await page.inner_text('body')
            if 'invalid captcha' in page_text.lower() or 'no record found' in page_text.lower():
                print("[DEBUG] Search completed with error/no results")
                found_results = True
                break
            # Also check for "Total number of cases" text which indicates results loaded
            if 'total number of cases' in page_text.lower():
                print("[DEBUG] Found 'Total number of cases' - results loaded")
                found_results = True
                break
        except:
            pass
        
        await page.wait_for_timeout(2000)  # Poll every 2 seconds
        elapsed = int(time.time() - start_time)
        if elapsed % 10 == 0:
            print(f"[DEBUG] Still waiting for results... ({elapsed}s)")
    
    # Remove dialog handler to avoid memory leak
    page.remove_listener('dialog', handle_dialog)
    
    if not found_results and not captcha_invalid and not dialog_messages:
        print("[DEBUG] No result container found after 90s, checking page state...")
    
    # If CAPTCHA was invalid, return error immediately
    if captcha_invalid:
        return {
            'raw_text': [],
            'tables': [],
            'cases': [],
            'case_details': {},
            'error': 'The CAPTCHA you entered was incorrect or expired. Please try again.',
            'captcha_error': True
        }
    
    # Additional wait for AJAX content to fully render
    await page.wait_for_timeout(2000)

    # Take debug screenshot
    try:
        screenshot_bytes = await page.screenshot(full_page=True)
        debug_b64 = base64.b64encode(screenshot_bytes).decode()
        print(f"[DEBUG] Captured result page screenshot ({len(debug_b64)} bytes)")
    except Exception as e:
        print(f"[DEBUG] Could not capture debug screenshot: {e}")
        debug_b64 = None

    # Scrape results
    results = await scrape_results(page)
    if debug_b64:
        results['debug_screenshot'] = debug_b64
    return results


def normalize_case_details(raw_details: dict) -> dict:
    """Normalize scraped case detail labels to canonical snake_case keys.
    
    Maps labels from eCourts DOM to the exact keys expected by format_case_results.
    """
    label_mappings = {
        # Case details table
        'case type': 'case_type',
        'casetype': 'case_type',
        'filing number': 'filing_number',
        'filing no': 'filing_number',
        'filing date': 'filing_date',
        'date of filing': 'filing_date',
        'registration number': 'registration_number',
        'reg. no': 'registration_number',
        'case no': 'registration_number',
        'registration date': 'registration_date',
        'date of registration': 'registration_date',
        'cnr number': 'cnr_number',
        'cnr no': 'cnr_number',
        'cnr': 'cnr_number',
        # Case status table
        'first hearing date': 'first_hearing_date',
        'next hearing date': 'next_hearing_date',
        'next date': 'next_hearing_date',
        'next hearing': 'next_hearing_date',
        'case stage': 'case_stage',
        'stage': 'case_stage',
        'case status': 'case_status',
        'status': 'case_status',
        # Court and Judge - format_case_results expects court_name and judge separately
        'court number and judge': 'court_name',  # Will also extract judge below
        'court name and number': 'court_name',
        'court hall / judge': 'court_name',
        'court hall and judge': 'court_name',
        'court no. and judge': 'court_name',
        'court name': 'court_name',
        'court no': 'court_name',
        'court no.': 'court_name',
        'court hall': 'court_name',
        'court': 'court_name',
        'courtroom': 'court_name',
        'judge': 'judge',
        'presiding officer': 'judge',
        'presiding judge': 'judge',
        'hon\'ble judge': 'judge',
        'honorable judge': 'judge',
        'coram': 'judge',
        'bench': 'judge',
        # Parties - include all plural/variant forms from eCourts DOM
        'petitioner and advocate': 'petitioner_advocate',
        'petitioner(s) and advocate(s)': 'petitioner_advocate',
        'petitioners and advocates': 'petitioner_advocate',
        'petitioner advocate': 'petitioner_advocate',
        'petitioner(s) advocate': 'petitioner_advocate',
        'petitioner(s) advocate(s)': 'petitioner_advocate',
        'advocate for petitioner': 'petitioner_advocate',
        'advocate(s) for petitioner': 'petitioner_advocate',
        'advocate(s) for petitioner(s)': 'petitioner_advocate',
        'petitioner name': 'petitioner',
        'petitioner': 'petitioner',
        'petitioner(s)': 'petitioner',
        'petitioners': 'petitioner',
        'plaintiff': 'petitioner',
        'plaintiff(s)': 'petitioner',
        'complainant': 'petitioner',
        'complainant(s)': 'petitioner',
        'applicant': 'petitioner',
        'applicant(s)': 'petitioner',
        'respondent and advocate': 'respondent_advocate',
        'respondent(s) and advocate(s)': 'respondent_advocate',
        'respondents and advocates': 'respondent_advocate',
        'respondent advocate': 'respondent_advocate',
        'respondent(s) advocate': 'respondent_advocate',
        'respondent(s) advocate(s)': 'respondent_advocate',
        'advocate for respondent': 'respondent_advocate',
        'advocate(s) for respondent': 'respondent_advocate',
        'advocate(s) for respondent(s)': 'respondent_advocate',
        'respondent name': 'respondent',
        'respondent': 'respondent',
        'respondent(s)': 'respondent',
        'respondents': 'respondent',
        'defendant': 'respondent',
        'defendant(s)': 'respondent',
        'accused': 'respondent',
        'accused(s)': 'respondent',
        'opposite party': 'respondent',
        'opposite party(s)': 'respondent',
        # Acts and sections - format_case_results expects under_act and under_section
        'acts': 'under_act',
        'under act': 'under_act',
        'under act(s)': 'under_act',
        'act': 'under_act',
        'under section': 'under_section',
        'under section(s)': 'under_section',
        'section': 'under_section',
        # History
        'case history': 'case_history',
        'history': 'case_history',
        # Other
        'interim orders': 'interim_orders',
        'case transfer details': 'case_transfer_details',
        'transfer details': 'case_transfer_details',
        'disposal date': 'disposal_date',
        'date of disposal': 'disposal_date',
        'date of decision': 'disposal_date',
        'nature of disposal': 'nature_of_disposal',
        'disposal': 'nature_of_disposal',
    }
    
    normalized = {}
    for key, value in raw_details.items():
        key_lower = key.lower().strip()
        normalized_key = label_mappings.get(key_lower, key_lower.replace(' ', '_').replace('(', '').replace(')', ''))
        normalized[normalized_key] = value
        
        # Special handling: Extract judge from "Court Number and Judge" field
        if 'court number and judge' in key_lower or 'court name and' in key_lower:
            # Value might be like "Court No. 1 - Judge Name" - try to extract judge
            if '-' in value:
                parts = value.split('-', 1)
                if len(parts) == 2:
                    normalized['court_name'] = parts[0].strip()
                    normalized['judge'] = parts[1].strip()
    
    return normalized


async def scrape_case_details_page(page: Page, results: dict):
    """Scrape case details from View page (div#partynametab structure)."""
    print("[DEBUG] Scraping case details page...")
    
    try:
        case_details = await page.evaluate("""
            () => {
                const details = {};
                
                // Case Details Table (.case_details_table)
                const caseTable = document.querySelector('.case_details_table, table.case_details_table');
                if (caseTable) {
                    caseTable.querySelectorAll('tr').forEach(tr => {
                        const cells = tr.querySelectorAll('td');
                        if (cells.length >= 2) {
                            const label = cells[0].innerText.trim().replace(':', '');
                            const value = cells[1].innerText.trim();
                            if (label && value) details[label] = value;
                        }
                    });
                }
                
                // Case Status Table (.case_status_table)
                const statusTable = document.querySelector('.case_status_table, table.case_status_table');
                if (statusTable) {
                    statusTable.querySelectorAll('tr').forEach(tr => {
                        const cells = tr.querySelectorAll('td');
                        if (cells.length >= 2) {
                            const label = cells[0].innerText.trim().replace(':', '');
                            const value = cells[1].innerText.trim();
                            if (label && value) details[label] = value;
                        }
                    });
                }
                
                // Petitioner and Advocate section
                const petH3 = document.evaluate("//h3[contains(text(), 'Petitioner')]", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                if (petH3) {
                    const nextEl = petH3.nextElementSibling;
                    if (nextEl) details['Petitioner and Advocate'] = nextEl.innerText.trim();
                }
                
                // Respondent and Advocate section
                const resH3 = document.evaluate("//h3[contains(text(), 'Respondent')]", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                if (resH3) {
                    const nextEl = resH3.nextElementSibling;
                    if (nextEl) details['Respondent and Advocate'] = nextEl.innerText.trim();
                }
                
                // Acts table (.acts_table)
                const actsTable = document.querySelector('.acts_table, table.acts_table');
                if (actsTable) {
                    const actRows = [];
                    actsTable.querySelectorAll('tbody tr').forEach(tr => {
                        const cells = [...tr.querySelectorAll('td')].map(td => td.innerText.trim());
                        if (cells.length >= 2) actRows.push(cells.join(' - '));
                    });
                    if (actRows.length > 0) details['Acts'] = actRows.join('; ');
                }
                
                // Case History (#historyheading)
                const historyTable = document.querySelector('#historyheading, table#historyheading');
                if (historyTable) {
                    const historyRows = [];
                    historyTable.querySelectorAll('tbody tr').forEach(tr => {
                        const cells = [...tr.querySelectorAll('td')].map(td => td.innerText.trim());
                        if (cells.length >= 3) historyRows.push(cells.join(' | '));
                    });
                    if (historyRows.length > 0) details['Case History'] = historyRows.join('\\n');
                }
                
                // Interim Orders
                const interimH3 = document.evaluate("//h3[contains(text(), 'Interim')]", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                if (interimH3) {
                    const nextEl = interimH3.nextElementSibling;
                    if (nextEl && nextEl.tagName === 'TABLE') {
                        details['Interim Orders'] = nextEl.innerText.trim();
                    }
                }
                
                // Case Transfer Details
                const transferH3 = document.evaluate("//h3[contains(text(), 'Transfer')]", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                if (transferH3) {
                    const nextEl = transferH3.nextElementSibling;
                    if (nextEl && nextEl.tagName === 'TABLE') {
                        details['Case Transfer Details'] = nextEl.innerText.trim();
                    }
                }
                
                return details;
            }
        """)
        
        if case_details and len(case_details) > 0:
            # Normalize labels to canonical snake_case keys
            normalized = normalize_case_details(case_details)
            results['case_details'] = normalized
            # Also add to cases list for compatibility
            results['cases'].append(normalized)
            print(f"[DEBUG] Scraped {len(normalized)} case detail fields")
        
        # Get raw text from container
        raw_text = await page.evaluate("""
            () => {
                const container = document.querySelector('div#partynametab, div#CSpartyName, .case-container');
                return container ? container.innerText.trim() : '';
            }
        """)
        
        if raw_text and len(raw_text) > 20:
            results['raw_text'].append(raw_text[:3000])
        
    except Exception as e:
        print(f"[DEBUG] Error scraping case details page: {e}")
        results['error'] = f"Error scraping case details: {str(e)}"


async def scrape_generic_results(page: Page, results: dict):
    """Generic fallback scraping for unknown search types."""
    print("[DEBUG] Scraping generic results...")
    
    try:
        # Try common result selectors
        selectors = [
            '#srchRslt table',
            '#caseDetails table',
            '.dataTables_wrapper table',
            'table.dataTable',
            'table.display'
        ]
        
        for selector in selectors:
            tables = await page.query_selector_all(selector)
            if tables and len(tables) > 0:
                print(f"[DEBUG] Found generic table: {selector}")
                
                for idx, table in enumerate(tables[:5]):
                    table_data = await table.evaluate("""
                        (el) => {
                            const rows = [];
                            el.querySelectorAll('tr').forEach(tr => {
                                const cells = [...tr.querySelectorAll('td, th')].map(td => td.innerText.trim());
                                if (cells.length > 0) rows.push(cells);
                            });
                            return rows;
                        }
                    """)
                    
                    if table_data and len(table_data) > 0:
                        results['tables'].append({
                            'index': idx,
                            'rows': len(table_data),
                            'data': table_data
                        })
                
                if results['tables']:
                    break
        
        # Get raw text from body
        raw_text = await page.inner_text('body')
        if raw_text and len(raw_text) > 50:
            results['raw_text'].append(raw_text[:2000])
        
    except Exception as e:
        print(f"[DEBUG] Error in generic scraping: {e}")
        results['error'] = f"Error scraping results: {str(e)}"


async def scrape_cnr_results(page: Page, results: dict):
    """Scrape CNR search results from #history_cnr and case details tables."""
    print("[DEBUG] Scraping CNR results...")
    
    try:
        # Wait for CNR result container
        await page.wait_for_selector('#history_cnr, #CNRDetails, .case_details_table', timeout=10000)
        
        # Scrape case details using JavaScript
        case_details = await page.evaluate("""
            () => {
                const details = {};
                
                // Case Details Table
                const caseTable = document.querySelector('.case_details_table, #caseDetails table');
                if (caseTable) {
                    caseTable.querySelectorAll('tr').forEach(tr => {
                        const cells = tr.querySelectorAll('td');
                        if (cells.length >= 2) {
                            const label = cells[0].innerText.trim().replace(':', '');
                            const value = cells[1].innerText.trim();
                            if (label && value) {
                                details[label] = value;
                            }
                        }
                    });
                }
                
                // Case Status Table
                const statusTable = document.querySelector('.case_status_table');
                if (statusTable) {
                    statusTable.querySelectorAll('tr').forEach(tr => {
                        const cells = tr.querySelectorAll('td');
                        if (cells.length >= 2) {
                            const label = cells[0].innerText.trim().replace(':', '');
                            const value = cells[1].innerText.trim();
                            if (label && value) {
                                details[label] = value;
                            }
                        }
                    });
                }
                
                // Petitioner/Respondent sections
                const petH3 = document.evaluate("//h3[contains(text(), 'Petitioner')]", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                if (petH3) {
                    const nextTable = petH3.nextElementSibling;
                    if (nextTable && nextTable.tagName === 'TABLE') {
                        details['Petitioner and Advocate'] = nextTable.innerText.trim();
                    }
                }
                
                const resH3 = document.evaluate("//h3[contains(text(), 'Respondent')]", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                if (resH3) {
                    const nextTable = resH3.nextElementSibling;
                    if (nextTable && nextTable.tagName === 'TABLE') {
                        details['Respondent and Advocate'] = nextTable.innerText.trim();
                    }
                }
                
                // Acts table
                const actsTable = document.querySelector('.acts_table');
                if (actsTable) {
                    details['Acts'] = actsTable.innerText.trim();
                }
                
                // Case History
                const historyTable = document.querySelector('#historyheading, .history_table');
                if (historyTable) {
                    const historyRows = [];
                    historyTable.querySelectorAll('tbody tr').forEach(tr => {
                        const cells = [...tr.querySelectorAll('td')].map(td => td.innerText.trim());
                        if (cells.length >= 3) {
                            historyRows.push(cells.join(' | '));
                        }
                    });
                    if (historyRows.length > 0) {
                        details['Case History'] = historyRows.join('\\n');
                    }
                }
                
                return details;
            }
        """)
        
        if case_details and len(case_details) > 0:
            # Normalize labels to canonical snake_case keys
            normalized = normalize_case_details(case_details)
            results['case_details'] = normalized
            # Also add to cases list for compatibility
            results['cases'].append(normalized)
            print(f"[DEBUG] Scraped {len(normalized)} CNR case detail fields")
        
        # Get raw text from CNR container
        raw_text = await page.evaluate("""
            () => {
                const container = document.querySelector('#history_cnr, #CNRDetails, .case-container');
                return container ? container.innerText.trim() : '';
            }
        """)
        
        if raw_text and len(raw_text) > 20:
            results['raw_text'].append(raw_text[:2000])
        
    except Exception as e:
        print(f"[DEBUG] Error scraping CNR results: {e}")
        results['error'] = f"Error scraping CNR case details: {str(e)}"


async def scrape_results(page: Page, search_type: str = 'auto'):
    """Scrape case details from result page.
    
    Auto-detects search type from page content:
    - Party Name: Uses ONLY #res_party > #dispTable
    - CNR: Uses #history_cnr and case detail tables
    - Other: Falls back to generic table scraping
    
    NEVER use #showList, #showList1, #caseListResult for party name search!
    """
    print(f"[DEBUG] Scraping results (search_type={search_type})")

    results = {
        'raw_text': [],
        'tables': [],
        'cases': [],
        'case_details': {}
    }

    try:
        # Wait a moment for any dynamic content
        await page.wait_for_timeout(1000)
        
        # Detect search type from page content
        page_url = page.url
        detected_type = 'unknown'
        
        # Check for party name result container with actual case rows in #dispTable
        # This takes HIGHEST priority for party name search results
        party_container = await page.query_selector('#res_party')
        disp_table_rows = await page.query_selector_all('#dispTable tbody tr')
        
        if party_container:
            if len(disp_table_rows) > 0:
                # Check if any row has data (relaxed check - just needs cells with content)
                has_valid_rows = await page.evaluate("""
                    () => {
                        const rows = document.querySelectorAll('#dispTable tbody tr');
                        for (const row of rows) {
                            const tds = row.querySelectorAll('td');
                            // Valid row has at least 3 cells and first cell has some content
                            if (tds.length >= 3) {
                                const firstCell = tds[0].innerText.trim();
                                // Accept numeric values (1, 2, 3...) or formatted like "1." or "S.No" header
                                // Strip punctuation and check if it's a number
                                const stripped = firstCell.replace(/[^0-9]/g, '');
                                if (stripped.length > 0 && parseInt(stripped) > 0) {
                                    return true;
                                }
                            }
                        }
                        return false;
                    }
                """)
                if has_valid_rows:
                    detected_type = 'party_name'
                    print(f"[DEBUG] Detected party name search from #res_party with {len(disp_table_rows)} valid rows")
                else:
                    # Check if there's at least 2 rows - could still be valid data
                    if len(disp_table_rows) >= 2:
                        detected_type = 'party_name'
                        print(f"[DEBUG] Detected party name search from #res_party with {len(disp_table_rows)} rows (relaxed)")
                    else:
                        detected_type = 'party_name_no_results'
                        print("[DEBUG] #res_party found but no valid case rows in #dispTable")
            else:
                # #res_party exists but #dispTable is empty
                detected_type = 'party_name_no_results'
                print("[DEBUG] #res_party found but #dispTable is empty")
        
        # Check for CNR-specific elements (only if not party_name)
        if detected_type == 'unknown':
            cnr_container = await page.query_selector('#history_cnr, #CNRDetails, .cnr-details')
            if cnr_container or 'cnr' in page_url.lower():
                detected_type = 'cnr'
                print("[DEBUG] Detected CNR search from page elements")
        
        # Check for case details page (View button clicked) - only if not already detected
        if detected_type == 'unknown':
            case_details_container = await page.query_selector('div#partynametab .case_details_table, div#CSpartyName .case_details_table')
            if case_details_container:
                detected_type = 'case_details'
                print("[DEBUG] Detected case details page")
        
        # Override with explicit search_type if provided
        if search_type != 'auto':
            detected_type = search_type
        
        print(f"[DEBUG] Final detected type: {detected_type}")
        
        # Route to appropriate scraping logic
        if detected_type == 'cnr':
            print("[DEBUG] Scraping CNR search results...")
            await scrape_cnr_results(page, results)
            return results
        
        if detected_type == 'case_details':
            print("[DEBUG] Scraping case details (View page)...")
            await scrape_case_details_page(page, results)
            return results
        
        if detected_type == 'party_name_no_results':
            # Party search context but no valid case rows - check for error messages
            print("[DEBUG] Party name search returned no valid case rows, checking for errors...")
            page_text = await page.inner_text('body')
            page_text_lower = page_text.lower()
            
            # Check for specific error conditions
            if 'invalid captcha' in page_text_lower or 'captcha mismatch' in page_text_lower:
                results['raw_text'].append('The CAPTCHA you entered was incorrect. Please try the search again.')
            elif 'record not found' in page_text_lower or 'no record found' in page_text_lower:
                results['raw_text'].append('No cases found matching your search criteria.')
            elif 'no case' in page_text_lower:
                results['raw_text'].append('No cases found matching your search criteria.')
            else:
                results['raw_text'].append('No matching cases found. Try different search criteria or check the CAPTCHA.')
            return results
        
        if detected_type == 'party_name':
            # PARTY NAME SEARCH: Use #dispTable ONLY
            print("[DEBUG] Waiting for #dispTable to load...")
            try:
                await page.wait_for_selector('#res_party', timeout=15000)
                await page.wait_for_selector('#dispTable tbody tr', timeout=15000)
                print("[DEBUG] Found #dispTable with rows")
            except Exception as e:
                print(f"[DEBUG] #dispTable not found: {e}")
        else:
            # Unknown type - try generic table scraping
            print("[DEBUG] Unknown search type, trying generic scraping...")
            await scrape_generic_results(page, results)
            return results
        
        # Use JavaScript to scrape #dispTable - relaxed matching for Sr No variations
        disp_table_cases = await page.evaluate("""
            () => {
                const rows = document.querySelectorAll('#dispTable tbody tr');
                const cases = [];
                rows.forEach((tr, index) => {
                    const tds = [...tr.querySelectorAll('td')].map(td => td.innerText.trim());
                    if (tds.length >= 3) {
                        // Relaxed Sr No check: extract digits, accept "1", "1.", "01", etc.
                        const firstCell = tds[0];
                        const stripped = firstCell.replace(/[^0-9]/g, '');
                        const srNo = stripped.length > 0 ? stripped : String(index + 1);
                        
                        // Skip header rows or empty rows
                        if (parseInt(srNo) > 0 && tds[1].length > 0) {
                            cases.push({
                                sr_no: srNo,
                                case_number: tds[1],
                                parties: tds.length > 2 ? tds[2] : '',
                                has_view_button: tr.querySelector('a, button, input[value="View"]') !== null
                            });
                        }
                    }
                });
                return cases;
            }
        """)
        
        if disp_table_cases and len(disp_table_cases) > 0:
            print(f"[DEBUG] Scraped {len(disp_table_cases)} cases from #dispTable")
            for case in disp_table_cases:
                # Parse petitioner vs respondent from parties string
                parties = case.get('parties', '')
                petitioner = ''
                respondent = ''
                if ' vs ' in parties.lower():
                    parts = parties.lower().split(' vs ')
                    if len(parts) == 2:
                        petitioner = parts[0].strip().upper()
                        respondent = parts[1].strip().upper()
                
                structured_case = {
                    'sr_no': case.get('sr_no', ''),
                    'case_number': case.get('case_number', ''),
                    'petitioner': petitioner,
                    'respondent': respondent,
                    'parties': parties,
                    'text': f"Case #{case.get('sr_no', '')}: {case.get('case_number', '')} - {parties}"
                }
                results['cases'].append(structured_case)
            
            # Add table data for display
            results['tables'].append({
                'index': 0,
                'rows': len(disp_table_cases),
                'data': [[c['sr_no'], c['case_number'], c['parties'], 'View'] for c in disp_table_cases]
            })
            
            # Return early if we found results from #dispTable
            return results

        # #dispTable was checked but no results - check for error messages
        page_text = await page.inner_text('body')
        page_text_lower = page_text.lower()
        
        # Check for specific error conditions with clear user messages
        error_conditions = [
            # CAPTCHA errors
            ('invalid captcha', 'The CAPTCHA you entered was incorrect. Please try the search again.'),
            ('captcha mismatch', 'The CAPTCHA you entered was incorrect. Please try the search again.'),
            ('wrong captcha', 'The CAPTCHA you entered was incorrect. Please try the search again.'),
            ('captcha error', 'The CAPTCHA you entered was incorrect. Please try the search again.'),
            # No records found
            ('no record found', 'No matching records found for your search criteria. Please verify the party name, state, district, and year.'),
            ('no records found', 'No matching records found for your search criteria. Please verify the party name, state, district, and year.'),
            ('record not found', 'No matching records found for your search criteria. Please verify the party name, state, district, and year.'),
            ('no data available', 'No matching records found for your search criteria. Please verify the party name, state, district, and year.'),
            ('no case found', 'No matching cases found for your search criteria. Please verify the details.'),
            # Session errors
            ('session expired', 'Your session has expired. Please start a new search.'),
            ('session timeout', 'Your session has timed out. Please start a new search.'),
            # Server errors
            ('server error', 'The eCourts website is experiencing issues. Please try again later.'),
            ('internal error', 'The eCourts website is experiencing issues. Please try again later.'),
            ('service unavailable', 'The eCourts website is temporarily unavailable. Please try again later.'),
            ('under maintenance', 'The eCourts website is under maintenance. Please try again later.'),
            ('technical error', 'The eCourts website encountered a technical error. Please try again later.'),
        ]
        
        for pattern, message in error_conditions:
            if pattern in page_text_lower:
                results['error'] = message
                print(f"[DEBUG] Found error pattern: {pattern}")
                return results
        
        # CRITICAL: For party name search, we ONLY use #dispTable
        # If #dispTable has no results and no error messages found, return no results message
        # DO NOT fall back to any other tables (they would be wrong)
        print("[DEBUG] #dispTable had no rows and no error messages detected")
        results['error'] = 'No matching records found for your search criteria. The search completed but no cases matched.'
        return results

    except Exception as e:
        results['error'] = f"Error scraping results: {str(e)}"
        print(f"[DEBUG] Error in scrape_results: {e}")

    return results


@app.on_event("startup")
async def startup_event():
    """Run on application startup"""
    print("[INFO] eCourts Chatbot API starting up...")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    print("[INFO] Cleaning up sessions...")
    for session_id in list(SESSIONS.keys()):
        try:
            session = SESSIONS[session_id]
            if 'context' in session:
                await session['context'].close()
            if 'browser' in session:
                await session['browser'].close()
            if 'pw' in session:
                await session['pw'].stop()
        except Exception:
            pass


@app.get("/health")
async def health():
    """API health check"""
    return {
        "status": "running",
        "version": "1.0.0",
        "message": "eCourts Chatbot API"
    }


@app.post("/start-search")
async def start_search(request: SearchRequest):
    """Initialize a new search session"""
    try:
        # Clean up old sessions
        await cleanup_old_sessions()

        # Generate session ID
        session_id = base64.urlsafe_b64encode(os.urandom(12)).decode().rstrip('=')

        # Store initial session data
        SESSIONS[session_id] = {
            'status': 'starting',
            'created_at': time.time(),
            'params': request.dict()
        }

        print(f"[INFO] Starting new search session: {session_id}")
        print(f"[INFO] Search parameters: {request.dict()}")

        # Start the search in background
        asyncio.create_task(run_search(session_id, request.dict()))

        return {
            'session_id': session_id,
            'status': 'started',
            'message': 'Search initiated successfully'
        }

    except Exception as e:
        print(f"[ERROR] Error starting search: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def run_search(session_id: str, params: Dict[str, Any]):
    """Execute the search and capture CAPTCHA"""
    pw = None
    browser = None

    try:
        SESSIONS[session_id]['status'] = 'running'
        print(f"[INFO] Running search for session {session_id}")

        # Determine which endpoint to use
        mode = params.get('mode', 'party_name')
        url = ECOURTS_ENDPOINTS.get(mode, ECOURTS_ENDPOINTS['party_name'])

        print(f"[INFO] Using endpoint: {url}")

        # Start browser
        headless = os.getenv('HEADLESS_MODE', 'true').lower() == 'true'
        pw, browser = await start_browser(headless=headless)

        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )

        page = await context.new_page()

        # Navigate to the URL
        print(f"[INFO] Navigating to {url}")
        await page.goto(url, wait_until='networkidle', timeout=30000)

        # Fill the form based on mode
        if mode == 'cnr':
            await fill_cnr_form(page, params)
        else:
            await fill_party_name_form(page, params)

        # Capture CAPTCHA
        captcha_b64, selector_used = await capture_captcha(page)

        if not captcha_b64:
            SESSIONS[session_id]['status'] = 'error'
            SESSIONS[session_id]['error'] = 'Could not capture CAPTCHA image'
            return

        # Update session with CAPTCHA and browser objects
        SESSIONS[session_id].update({
            'status': 'awaiting_captcha',
            'captcha_b64': captcha_b64,
            'captcha_selector': selector_used,
            'page': page,
            'context': context,
            'browser': browser,
            'pw': pw
        })

        print(f"[INFO] CAPTCHA captured for session {session_id}, awaiting user input")

    except Exception as e:
        print(f"[ERROR] Error in run_search for session {session_id}: {e}")
        SESSIONS[session_id]['status'] = 'error'
        SESSIONS[session_id]['error'] = str(e)

        # Cleanup on error
        try:
            if browser:
                await browser.close()
            if pw:
                await pw.stop()
        except Exception:
            pass


@app.get("/captcha/{session_id}")
async def get_captcha(session_id: str):
    """Get CAPTCHA image for a session"""
    session = SESSIONS.get(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    status = session.get('status')

    if status == 'error':
        return {
            'status': 'error',
            'error': session.get('error', 'Unknown error')
        }

    if status != 'awaiting_captcha':
        return {
            'status': status,
            'message': f'Session is in {status} state'
        }

    return {
        'status': 'awaiting_captcha',
        'captcha_b64': session.get('captcha_b64'),
        'selector_used': session.get('captcha_selector')
    }


@app.post("/submit-captcha")
async def submit_captcha(body: CaptchaSubmit):
    """Submit CAPTCHA and get results"""
    session = SESSIONS.get(body.session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.get('status') != 'awaiting_captcha':
        raise HTTPException(
            status_code=400,
            detail=f"Session is not awaiting CAPTCHA. Current status: {session.get('status')}"
        )

    try:
        print(f"[INFO] Processing CAPTCHA submission for session {body.session_id}")

        page = session['page']

        # Submit form and scrape results
        results = await submit_form_and_scrape(page, body.captcha_text)

        # Update session
        session['status'] = 'completed'
        session['results'] = results
        session['completed_at'] = time.time()

        # NOTE: Do NOT cleanup browser resources here - keep browser alive for View Case feature
        # Browser will be cleaned up by session expiry or when user starts a new search
        print(f"[INFO] Browser session kept alive for View Case feature")

        print(f"[INFO] Search completed for session {body.session_id}")

        return {
            'status': 'completed',
            'results': results
        }

    except Exception as e:
        print(f"[ERROR] Error submitting CAPTCHA for session {body.session_id}: {e}")
        session['status'] = 'error'
        session['error'] = str(e)

        return {
            'status': 'error',
            'error': str(e)
        }


@app.get("/results/{session_id}")
async def get_results(session_id: str):
    """Get results for a completed session"""
    session = SESSIONS.get(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        'status': session.get('status'),
        'results': session.get('results'),
        'error': session.get('error')
    }


@app.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """Delete a session and cleanup resources"""
    session = SESSIONS.get(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        # Cleanup browser resources
        if 'context' in session:
            await session['context'].close()
        if 'browser' in session:
            await session['browser'].close()
        if 'pw' in session:
            await session['pw'].stop()
    except Exception:
        pass

    del SESSIONS[session_id]

    return {'status': 'deleted', 'session_id': session_id}


@app.get("/", response_class=FileResponse)
async def serve_frontend():
    """Serve the frontend HTML"""
    return FileResponse(os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html"))


@app.post("/chat")
async def chat(body: ChatMessage):
    """Handle conversational chat with the user"""
    try:
        conversation_id = body.conversation_id
        
        # Create new conversation if needed
        if not conversation_id or conversation_id not in CONVERSATIONS:
            conversation_id = base64.urlsafe_b64encode(os.urandom(12)).decode().rstrip('=')
            CONVERSATIONS[conversation_id] = {
                'history': [],
                'search_params': {},
                'created_at': time.time()
            }
        
        conversation = CONVERSATIONS[conversation_id]
        user_msg = body.message.strip()
        
        # Check if we have an active multi-step search session
        search_session_id = conversation.get('current_search_session')
        if search_session_id and search_session_id in SESSIONS:
            session = SESSIONS[search_session_id]
            status = session.get('status')
            
            # Handle multi-step dropdown selection
            if status == 'awaiting_state':
                return await handle_state_selection(conversation_id, search_session_id, session, user_msg)
            elif status == 'awaiting_district':
                return await handle_district_selection(conversation_id, search_session_id, session, user_msg)
            elif status == 'awaiting_court_complex':
                return await handle_court_complex_selection(conversation_id, search_session_id, session, user_msg)
            elif status == 'awaiting_establishment':
                return await handle_establishment_selection(conversation_id, search_session_id, session, user_msg)
            elif status == 'awaiting_party_details':
                return await handle_party_details(conversation_id, search_session_id, session, user_msg)
            elif status == 'awaiting_year':
                return await handle_year_input(conversation_id, search_session_id, session, user_msg)
            elif status == 'awaiting_disposition':
                return await handle_disposition_selection(conversation_id, search_session_id, session, user_msg)
            elif status == 'awaiting_captcha':
                # If we have captcha_b64 and user sent a message, treat it as CAPTCHA input
                if session.get('captcha_b64'):
                    return await handle_captcha_input(conversation_id, search_session_id, session, user_msg)
                else:
                    # CAPTCHA still loading
                    return {
                        'conversation_id': conversation_id,
                        'response': "CAPTCHA is still loading, please wait...",
                        'search_session_id': search_session_id
                    }
        
        # Get AI response for normal conversation
        ai_response = get_ai_response(conversation['history'], user_msg)
        
        # Update conversation history
        conversation['history'].append({"role": "user", "content": user_msg})
        conversation['history'].append({"role": "assistant", "content": json.dumps(ai_response)})
        
        # Keep history manageable (last 20 messages)
        if len(conversation['history']) > 20:
            conversation['history'] = conversation['history'][-20:]
        
        response_data = {
            'conversation_id': conversation_id,
            'response': ai_response.get('message', ''),
            'action': ai_response.get('action'),
            'missing_info': ai_response.get('missing_info', [])
        }
        
        # If action is to start a search, initiate it
        if ai_response.get('action') in ['start_cnr_search', 'start_party_search']:
            search_params = ai_response.get('search_params', {})
            
            # Build search request
            if ai_response['action'] == 'start_cnr_search':
                search_request = SearchRequest(
                    mode='cnr',
                    cnr_number=search_params.get('cnr_number', '')
                )
                # Start CNR search directly
                session_id = base64.urlsafe_b64encode(os.urandom(12)).decode().rstrip('=')
                SESSIONS[session_id] = {
                    'status': 'starting',
                    'created_at': time.time(),
                    'params': search_request.dict(),
                    'conversation_id': conversation_id
                }
                asyncio.create_task(run_search(session_id, search_request.dict()))
                response_data['search_session_id'] = session_id
                conversation['current_search_session'] = session_id
            else:
                # For party name search, start multi-step selection flow
                session_id = base64.urlsafe_b64encode(os.urandom(12)).decode().rstrip('=')
                SESSIONS[session_id] = {
                    'status': 'starting',
                    'created_at': time.time(),
                    'mode': 'party_name',
                    'conversation_id': conversation_id
                }
                conversation['current_search_session'] = session_id
                
                # Start initialization in background
                asyncio.create_task(init_party_search_session(session_id))
                
                response_data['search_session_id'] = session_id
                response_data['response'] = "Starting party name search. Please wait while I load the available options from eCourts..."
        
        return response_data
        
    except Exception as e:
        print(f"[ERROR] Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def handle_state_selection(conversation_id: str, session_id: str, session: dict, user_msg: str):
    """Handle user's state selection"""
    options = session.get('state_options', [])
    
    try:
        choice = int(user_msg)
        if 1 <= choice <= len(options):
            selected = options[choice - 1]
            asyncio.create_task(select_state_and_get_districts(session_id, selected['value'], selected['text']))
            return {
                'conversation_id': conversation_id,
                'response': f"Selected: {selected['text']}",
                'search_session_id': session_id
            }
        else:
            return {
                'conversation_id': conversation_id,
                'response': f"Please enter a number between 1 and {len(options)}.",
                'search_session_id': session_id
            }
    except ValueError:
        return {
            'conversation_id': conversation_id,
            'response': f"Please enter a number (1-{len(options)}).",
            'search_session_id': session_id
        }


async def handle_district_selection(conversation_id: str, session_id: str, session: dict, user_msg: str):
    """Handle user's district selection"""
    options = session.get('district_options', [])
    
    if not options:
        # No districts available, skip to court complex
        asyncio.create_task(select_district_and_get_courts(session_id, '', ''))
        return {
            'conversation_id': conversation_id,
            'response': "Proceeding...",
            'search_session_id': session_id
        }
    
    try:
        choice = int(user_msg)
        if 1 <= choice <= len(options):
            selected = options[choice - 1]
            asyncio.create_task(select_district_and_get_courts(session_id, selected['value'], selected['text']))
            return {
                'conversation_id': conversation_id,
                'response': f"Selected: {selected['text']}",
                'search_session_id': session_id
            }
        else:
            return {
                'conversation_id': conversation_id,
                'response': f"Please enter a number between 1 and {len(options)}.",
                'search_session_id': session_id
            }
    except ValueError:
        return {
            'conversation_id': conversation_id,
            'response': f"Please enter a number (1-{len(options)}).",
            'search_session_id': session_id
        }


async def handle_court_complex_selection(conversation_id: str, session_id: str, session: dict, user_msg: str):
    """Handle user's court complex selection"""
    options = session.get('court_complex_options', [])
    
    if not options:
        # No options available - proceed
        asyncio.create_task(select_court_complex_and_get_establishments(session_id, '', ''))
        return {
            'conversation_id': conversation_id,
            'response': "Proceeding...",
            'search_session_id': session_id
        }
    
    try:
        choice = int(user_msg)
        if 1 <= choice <= len(options):
            selected = options[choice - 1]
            asyncio.create_task(select_court_complex_and_get_establishments(session_id, selected['value'], selected['text']))
            return {
                'conversation_id': conversation_id,
                'response': f"Selected: {selected['text']}",
                'search_session_id': session_id
            }
        else:
            return {
                'conversation_id': conversation_id,
                'response': f"Please enter a number between 1 and {len(options)}.",
                'search_session_id': session_id
            }
    except ValueError:
        return {
            'conversation_id': conversation_id,
            'response': f"Please enter a number (1-{len(options)}).",
            'search_session_id': session_id
        }


async def handle_establishment_selection(conversation_id: str, session_id: str, session: dict, user_msg: str):
    """Handle user's establishment selection - establishment is REQUIRED"""
    options = session.get('establishment_options', [])
    
    if not options:
        # No options available - proceed with empty
        asyncio.create_task(select_establishment_and_prepare_form(session_id, '', ''))
        return {
            'conversation_id': conversation_id,
            'response': "Proceeding...",
            'search_session_id': session_id
        }
    
    # Reject skip attempts - establishment is mandatory
    if user_msg.lower() == 'skip':
        return {
            'conversation_id': conversation_id,
            'response': f"Establishment selection is required. Please enter a number (1-{len(options)}).",
            'search_session_id': session_id
        }
    
    try:
        choice = int(user_msg)
        if 1 <= choice <= len(options):
            selected = options[choice - 1]
            asyncio.create_task(select_establishment_and_prepare_form(session_id, selected['value'], selected['text']))
            return {
                'conversation_id': conversation_id,
                'response': f"Selected: {selected['text']}",
                'search_session_id': session_id
            }
        else:
            return {
                'conversation_id': conversation_id,
                'response': f"Please enter a number between 1 and {len(options)}.",
                'search_session_id': session_id
            }
    except ValueError:
        return {
            'conversation_id': conversation_id,
            'response': f"Please enter a number (1-{len(options)}).",
            'search_session_id': session_id
        }


async def handle_party_details(conversation_id: str, session_id: str, session: dict, user_msg: str):
    """Handle party name input"""
    # Check if user wants to use detected party name or enter their own
    if user_msg.lower() in ['yes', 'y', 'use it', 'ok', 'okay']:
        party_name = session.get('detected_party_name', user_msg)
    else:
        party_name = user_msg
    
    session['party_name_entered'] = party_name
    session['status'] = 'awaiting_year'
    return {
        'conversation_id': conversation_id,
        'response': f"Party name set: {party_name}. Now enter the case registration year (e.g., 2022):",
        'search_session_id': session_id
    }


async def handle_year_input(conversation_id: str, session_id: str, session: dict, user_msg: str):
    """Handle year input and proceed to disposition selection"""
    year = '' if user_msg.lower() == 'any' else user_msg.strip()
    session['year_entered'] = year
    session['status'] = 'awaiting_disposition'
    
    return {
        'conversation_id': conversation_id,
        'response': f"Year: {year}. Select case status:",
        'search_session_id': session_id,
        'options': [
            {'value': 'pending', 'text': 'Pending'},
            {'value': 'disposed', 'text': 'Disposed'},
            {'value': 'both', 'text': 'Both'}
        ],
        'options_type': 'disposition'
    }


async def handle_disposition_selection(conversation_id: str, session_id: str, session: dict, user_msg: str):
    """Handle disposition selection (Pending/Disposed/Both) and proceed to CAPTCHA"""
    
    # Check if we already have a CAPTCHA or are loading one (prevent duplicate triggers)
    current_status = session.get('status')
    if current_status == 'awaiting_captcha':
        if session.get('captcha_b64'):
            return {
                'conversation_id': conversation_id,
                'response': "Please enter the CAPTCHA text shown in the image:",
                'search_session_id': session_id,
                'captcha_b64': session.get('captcha_b64')
            }
        else:
            return {
                'conversation_id': conversation_id,
                'response': "Loading CAPTCHA, please wait...",
                'search_session_id': session_id
            }
    
    # Check captcha_loading flag as additional guard
    if session.get('captcha_loading'):
        return {
            'conversation_id': conversation_id,
            'response': "CAPTCHA is loading, please wait...",
            'search_session_id': session_id
        }
    
    disposition = user_msg.lower().strip()
    if disposition not in ['pending', 'disposed', 'both']:
        # Try to match partial input
        if 'pend' in disposition:
            disposition = 'pending'
        elif 'dispos' in disposition:
            disposition = 'disposed'
        else:
            disposition = 'both'
    
    # IMMEDIATELY update status to prevent duplicate calls
    session['disposition'] = disposition
    session['status'] = 'awaiting_captcha'  # Set status NOW before async task
    session['captcha_loading'] = True  # Mark that we're loading CAPTCHA
    
    party_name = session.get('party_name_entered', '')
    year = session.get('year_entered', '')
    
    # Fill form and get CAPTCHA (async task will set captcha_b64 when done)
    asyncio.create_task(fill_party_details_and_captcha_with_disposition(session_id, party_name, year, disposition))
    
    return {
        'conversation_id': conversation_id,
        'response': f"Loading CAPTCHA for {disposition} cases...",
        'search_session_id': session_id
    }


async def handle_captcha_input(conversation_id: str, session_id: str, session: dict, user_msg: str):
    """Handle CAPTCHA input from user"""
    try:
        page = session['page']
        results = await submit_form_and_scrape(page, user_msg)
        
        session['status'] = 'completed'
        session['results'] = results
        
        # Format results for display
        formatted = format_case_results(results)
        
        # NOTE: Do NOT cleanup browser resources here - keep browser alive for View Case feature
        # Browser will be cleaned up by session expiry or when user starts a new search
        print(f"[INFO] Browser session kept alive for View Case feature")
        
        return {
            'conversation_id': conversation_id,
            'response': formatted,
            'results': results,
            'search_session_id': session_id
        }
    except Exception as e:
        error_msg = str(e)
        if 'captcha' in error_msg.lower() or 'invalid' in error_msg.lower():
            return {
                'conversation_id': conversation_id,
                'response': "Invalid CAPTCHA. Please try again with the correct text:",
                'search_session_id': session_id
            }
        else:
            session['status'] = 'error'
            session['error'] = error_msg
            return {
                'conversation_id': conversation_id,
                'response': f"An error occurred: {error_msg}",
                'search_session_id': session_id
            }


@app.get("/chat/status/{conversation_id}")
async def get_chat_status(conversation_id: str):
    """Get the status of a conversation's active search"""
    conversation = CONVERSATIONS.get(conversation_id)
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    search_session_id = conversation.get('current_search_session')
    
    if not search_session_id:
        return {'status': 'no_active_search'}
    
    session = SESSIONS.get(search_session_id)
    
    if not session:
        return {'status': 'session_expired'}
    
    status = session.get('status')
    
    result = {
        'status': status,
        'search_session_id': search_session_id
    }
    
    # Include dropdown options for multi-step selection
    if status == 'awaiting_state':
        options = session.get('state_options', [])
        result['options'] = options
        result['options_message'] = format_options_message(options, 'State')
        result['selected'] = {'state': session.get('selected_state')}
    elif status == 'awaiting_district':
        options = session.get('district_options', [])
        result['options'] = options
        result['options_message'] = format_options_message(options, 'District')
        result['selected'] = {
            'state': session.get('selected_state'),
            'district': session.get('selected_district')
        }
    elif status == 'awaiting_court_complex':
        options = session.get('court_complex_options', [])
        result['options'] = options
        result['options_message'] = format_options_message(options, 'Court Complex', allow_skip=True)
        result['selected'] = {
            'state': session.get('selected_state'),
            'district': session.get('selected_district'),
            'court_complex': session.get('selected_court_complex')
        }
    elif status == 'awaiting_establishment':
        options = session.get('establishment_options', [])
        result['options'] = options
        result['options_message'] = format_options_message(options, 'Court Establishment', allow_skip=False)
        result['selected'] = {
            'state': session.get('selected_state'),
            'district': session.get('selected_district'),
            'court_complex': session.get('selected_court_complex'),
            'establishment': session.get('selected_establishment')
        }
    elif status == 'awaiting_party_details':
        result['selected'] = {
            'state': session.get('selected_state'),
            'district': session.get('selected_district'),
            'court_complex': session.get('selected_court_complex'),
            'establishment': session.get('selected_establishment')
        }
    elif status == 'awaiting_year':
        result['selected'] = {
            'state': session.get('selected_state'),
            'district': session.get('selected_district'),
            'court_complex': session.get('selected_court_complex'),
            'establishment': session.get('selected_establishment')
        }
        result['party_name'] = session.get('party_name_entered')
    elif status == 'awaiting_disposition':
        # Check if CAPTCHA is loading (transitioning to awaiting_captcha)
        if session.get('captcha_loading'):
            result['status'] = 'loading_captcha'
            result['message'] = 'Loading CAPTCHA, please wait...'
        else:
            result['selected'] = {
                'state': session.get('selected_state'),
                'district': session.get('selected_district'),
                'court_complex': session.get('selected_court_complex'),
                'establishment': session.get('selected_establishment')
            }
            result['party_name'] = session.get('party_name_entered')
            result['year'] = session.get('year_entered')
            result['options'] = [
                {'value': 'pending', 'text': 'Pending'},
                {'value': 'disposed', 'text': 'Disposed'},
                {'value': 'both', 'text': 'Both'}
            ]
            result['options_type'] = 'disposition'
    elif status == 'awaiting_captcha':
        result['captcha_b64'] = session.get('captcha_b64')
        result['party_name'] = session.get('party_name')  # For pre-filling
        result['selected'] = {
            'state': session.get('selected_state'),
            'district': session.get('selected_district'),
            'court_complex': session.get('selected_court_complex'),
            'establishment': session.get('selected_establishment'),
            'party_name': session.get('party_name'),
            'year': session.get('case_year')
        }
    elif status == 'completed':
        result['results'] = session.get('results')
        result['formatted_results'] = format_case_results(session.get('results', {}))
        # Add session timeout warning
        case_view_start = session.get('case_view_start', time.time())
        time_remaining = max(0, CASE_VIEW_TIMEOUT - (time.time() - case_view_start))
        result['case_view_warning'] = f"You can view cases for the next {int(time_remaining // 60)} minutes. After that, the session will expire."
        if time_remaining <= 0:
            result['session_expired'] = True
    elif status == 'viewing_case':
        result['message'] = 'Loading case details...'
    elif status == 'viewing_case_completed':
        result['case_details'] = session.get('case_details', {})
    elif status == 'error':
        result['error'] = session.get('error')
    
    return result


class ViewCaseRequest(BaseModel):
    conversation_id: str
    case_index: int


@app.post("/chat/view-case")
async def view_case(body: ViewCaseRequest):
    """View details of a specific case from search results"""
    conversation_id = body.conversation_id
    case_index = body.case_index
    
    conversation = CONVERSATIONS.get(conversation_id)
    if not conversation:
        return {'status': 'error', 'error': 'Conversation not found'}
    
    search_session_id = conversation.get('current_search_session')
    if not search_session_id:
        return {'status': 'error', 'error': 'No active search session'}
    
    session = SESSIONS.get(search_session_id)
    if not session:
        return {'status': 'error', 'error': 'Search session expired'}
    
    # Check if browser page is still available
    page = session.get('page')
    if not page:
        return {'status': 'error', 'error': 'Browser session expired. Please search again.'}
    
    # Update status and start loading case details
    session['status'] = 'viewing_case'
    
    # Run the case view in background
    asyncio.create_task(click_view_and_extract_details(session, case_index))
    
    return {'status': 'loading', 'message': 'Loading case details...'}


async def click_view_and_extract_details(session: dict, case_index: int):
    """Click the View button for a case and extract detailed information"""
    try:
        page = session.get('page')
        if not page:
            session['status'] = 'error'
            session['error'] = 'Browser session expired'
            return
        
        print(f"[DEBUG] Clicking View button for case index {case_index}")
        
        # Find all View buttons/links in the results table
        view_buttons = await page.query_selector_all('a:has-text("View"), input[value="View"], button:has-text("View")')
        print(f"[DEBUG] Found {len(view_buttons)} View buttons")
        
        if case_index >= len(view_buttons):
            session['status'] = 'error'
            session['error'] = f'Case {case_index + 1} not found. Only {len(view_buttons)} cases available.'
            return
        
        # Click the View button for the selected case using multiple strategies
        click_success = False
        
        # Strategy 1: Scroll and force click
        try:
            view_button = view_buttons[case_index]
            await view_button.scroll_into_view_if_needed()
            await asyncio.sleep(0.3)
            await view_button.click(timeout=5000, force=True)
            print(f"[DEBUG] Clicked View button for case {case_index + 1} using force click")
            click_success = True
        except Exception as click_err:
            print(f"[DEBUG] Force click failed: {click_err}")
        
        # Strategy 2: JavaScript click on the element
        if not click_success:
            try:
                await page.evaluate(f"""
                    const buttons = document.querySelectorAll('a[href*="view"], input[value="View"], button');
                    const viewBtns = Array.from(buttons).filter(b => 
                        b.textContent?.toLowerCase().includes('view') || 
                        b.value?.toLowerCase() === 'view'
                    );
                    if (viewBtns[{case_index}]) {{
                        viewBtns[{case_index}].click();
                    }}
                """)
                print(f"[DEBUG] Clicked View button for case {case_index + 1} using JS click")
                click_success = True
            except Exception as js_err:
                print(f"[DEBUG] JS click failed: {js_err}")
        
        # Strategy 3: Find View link by href and navigate
        if not click_success:
            try:
                view_links = await page.query_selector_all('a[href*="cino="], a[href*="view"]')
                if view_links and case_index < len(view_links):
                    href = await view_links[case_index].get_attribute('href')
                    if href:
                        if not href.startswith('http'):
                            href = f"https://services.ecourts.gov.in{href}"
                        await page.goto(href, wait_until='domcontentloaded', timeout=15000)
                        print(f"[DEBUG] Navigated to View link for case {case_index + 1}")
                        click_success = True
            except Exception as nav_err:
                print(f"[DEBUG] Navigation failed: {nav_err}")
        
        if not click_success:
            session['status'] = 'error'
            session['error'] = 'Could not click View button. Please try again.'
            return
        
        # Wait for page to load (could be popup or same page)
        await asyncio.sleep(2)
        
        # Check for popup window
        popup_page = None
        try:
            pages = page.context.pages
            if len(pages) > 1:
                popup_page = pages[-1]  # Get the newest page (popup)
                print(f"[DEBUG] Found popup window, waiting for load...")
                await popup_page.wait_for_load_state('domcontentloaded', timeout=15000)
        except Exception as e:
            print(f"[DEBUG] No popup or error: {e}")
        
        # Use popup if available, otherwise use main page
        detail_page = popup_page if popup_page else page
        
        # Wait for content
        await asyncio.sleep(2)
        
        # Scrape case details from the detail page
        case_details = await scrape_case_details(detail_page)
        
        session['case_details'] = case_details
        session['status'] = 'viewing_case_completed'
        print(f"[DEBUG] Case details extracted: {len(case_details)} fields")
        
    except Exception as e:
        print(f"[ERROR] Error viewing case: {e}")
        import traceback
        traceback.print_exc()
        session['status'] = 'error'
        session['error'] = str(e)


async def scrape_case_details(page) -> dict:
    """Scrape detailed case information from the case detail page.
    
    Based on eCourts DOM structure, case details appear in div#partynametab with:
    - table.case_details_table: Case Type, Filing Number/Date, Registration Number/Date, CNR Number
    - table.case_status_table: First Hearing Date, Next Hearing Date, Case Stage, Court Number and Judge
    - table.Petitioner_Advocate_table: Petitioner and Advocate
    - table.Respondent_Advocate_table: Respondent and Advocate
    - table.acts_table: Under Act(s), Under Section(s)
    - table#historyheading: Case History
    - Interim Orders table
    - Case Transfer Details table
    """
    details = {}
    
    try:
        # Wait for case details panel to load
        await page.wait_for_timeout(2000)
        
        # Wait for the case details container
        try:
            await page.wait_for_selector('div#partynametab, div#CSpartyName, .case_details_table', timeout=10000)
            print("[DEBUG] Found case details container")
        except:
            print("[DEBUG] Case details container not found, trying alternative selectors")
        
        # Take screenshot for debugging
        try:
            screenshot_bytes = await page.screenshot(full_page=True)
            print(f"[DEBUG] Case detail screenshot: {len(screenshot_bytes)} bytes")
        except Exception:
            pass
        
        # Extract case details using JavaScript for reliability
        case_data = await page.evaluate("""
            () => {
                const details = {};
                
                // Helper to get text content
                const getText = (el) => el ? el.innerText.trim() : '';
                
                // 1. Case Details Table (case_details_table)
                const caseDetailsTable = document.querySelector('table.case_details_table, .case_details_table');
                if (caseDetailsTable) {
                    const rows = caseDetailsTable.querySelectorAll('tr');
                    rows.forEach(row => {
                        const cells = row.querySelectorAll('td');
                        if (cells.length >= 2) {
                            const label = getText(cells[0]).toLowerCase();
                            const value = getText(cells[1]);
                            if (label.includes('case type')) details.case_type = value;
                            else if (label.includes('filing number')) details.filing_number = value;
                            else if (label.includes('filing date')) details.filing_date = getText(cells[3]) || value;
                            else if (label.includes('registration number')) details.registration_number = value;
                            else if (label.includes('registration date')) details.registration_date = getText(cells[3]) || value;
                            else if (label.includes('cnr number')) details.cnr_number = value;
                        }
                        // Handle 4-column rows (Filing Number | value | Filing Date | value)
                        if (cells.length >= 4) {
                            const label1 = getText(cells[0]).toLowerCase();
                            const label2 = getText(cells[2]).toLowerCase();
                            if (label1.includes('filing number')) details.filing_number = getText(cells[1]);
                            if (label2.includes('filing date')) details.filing_date = getText(cells[3]);
                            if (label1.includes('registration number')) details.registration_number = getText(cells[1]);
                            if (label2.includes('registration date')) details.registration_date = getText(cells[3]);
                        }
                    });
                }
                
                // 2. Case Status Table (case_status_table)
                const caseStatusTable = document.querySelector('table.case_status_table, .case_status_table');
                if (caseStatusTable) {
                    const rows = caseStatusTable.querySelectorAll('tr');
                    rows.forEach(row => {
                        const cells = row.querySelectorAll('td');
                        if (cells.length >= 2) {
                            const label = getText(cells[0]).toLowerCase();
                            const value = getText(cells[1]);
                            if (label.includes('first hearing')) details.first_hearing_date = value;
                            else if (label.includes('next hearing')) details.next_hearing_date = value;
                            else if (label.includes('case stage')) details.case_stage = value;
                            else if (label.includes('court number')) details.court_number_and_judge = value;
                        }
                    });
                }
                
                // 3. Petitioner and Advocate
                const petitionerSection = document.querySelector('table.Petitioner_Advocate_table, .table-bordered:has(td:contains("Petitioner"))');
                const petitionerHeading = document.querySelector('h3:contains("Petitioner and Advocate"), h2:contains("Petitioner")');
                if (petitionerHeading) {
                    let nextTable = petitionerHeading.nextElementSibling;
                    while (nextTable && nextTable.tagName !== 'TABLE') {
                        nextTable = nextTable.nextElementSibling;
                    }
                    if (nextTable) {
                        const rows = nextTable.querySelectorAll('tr');
                        const petitioners = [];
                        rows.forEach(row => {
                            const text = getText(row);
                            if (text && !text.toLowerCase().includes('petitioner and advocate')) {
                                petitioners.push(text);
                            }
                        });
                        if (petitioners.length > 0) details.petitioner_and_advocate = petitioners.join('\\n');
                    }
                }
                
                // 4. Respondent and Advocate
                const respondentHeading = document.querySelector('h3:contains("Respondent and Advocate"), h2:contains("Respondent")');
                if (respondentHeading) {
                    let nextTable = respondentHeading.nextElementSibling;
                    while (nextTable && nextTable.tagName !== 'TABLE') {
                        nextTable = nextTable.nextElementSibling;
                    }
                    if (nextTable) {
                        const rows = nextTable.querySelectorAll('tr');
                        const respondents = [];
                        rows.forEach(row => {
                            const text = getText(row);
                            if (text && !text.toLowerCase().includes('respondent and advocate')) {
                                respondents.push(text);
                            }
                        });
                        if (respondents.length > 0) details.respondent_and_advocate = respondents.join('\\n');
                    }
                }
                
                // 5. Acts Table
                const actsTable = document.querySelector('table.acts_table, .acts_table');
                if (actsTable) {
                    const rows = actsTable.querySelectorAll('tbody tr');
                    const acts = [];
                    rows.forEach(row => {
                        const cells = row.querySelectorAll('td');
                        if (cells.length >= 2) {
                            acts.push({
                                act: getText(cells[0]),
                                section: getText(cells[1])
                            });
                        }
                    });
                    if (acts.length > 0) details.acts = acts;
                }
                
                // 6. Case History Table
                const historyTable = document.querySelector('table#historyheading, table.history_table, table[width="100%"]');
                if (historyTable) {
                    const rows = historyTable.querySelectorAll('tbody tr');
                    const history = [];
                    rows.forEach(row => {
                        const cells = row.querySelectorAll('td');
                        if (cells.length >= 4) {
                            history.push({
                                judge: getText(cells[0]),
                                business_on_date: getText(cells[1]),
                                hearing_date: getText(cells[2]),
                                purpose: getText(cells[3])
                            });
                        }
                    });
                    if (history.length > 0) details.case_history = history;
                }
                
                // 7. Interim Orders Table
                const ordersHeading = Array.from(document.querySelectorAll('h3, h2')).find(h => h.textContent.includes('Interim Orders'));
                if (ordersHeading) {
                    let ordersTable = ordersHeading.nextElementSibling;
                    while (ordersTable && ordersTable.tagName !== 'TABLE') {
                        ordersTable = ordersTable.nextElementSibling;
                    }
                    if (ordersTable) {
                        const rows = ordersTable.querySelectorAll('tbody tr');
                        const orders = [];
                        rows.forEach(row => {
                            const cells = row.querySelectorAll('td');
                            if (cells.length >= 3) {
                                orders.push({
                                    order_number: getText(cells[0]),
                                    order_date: getText(cells[1]),
                                    order_details: getText(cells[2])
                                });
                            }
                        });
                        if (orders.length > 0) details.interim_orders = orders;
                    }
                }
                
                // 8. Case Transfer Details
                const transferHeading = Array.from(document.querySelectorAll('h3, h2, td')).find(h => h.textContent.includes('Case Transfer'));
                if (transferHeading) {
                    let transferTable = transferHeading.closest('table') || transferHeading.nextElementSibling;
                    while (transferTable && transferTable.tagName !== 'TABLE') {
                        transferTable = transferTable.nextElementSibling;
                    }
                    if (transferTable) {
                        const rows = transferTable.querySelectorAll('tbody tr');
                        const transfers = [];
                        rows.forEach(row => {
                            const cells = row.querySelectorAll('td');
                            if (cells.length >= 4) {
                                transfers.push({
                                    registration_number: getText(cells[0]),
                                    transfer_date: getText(cells[1]),
                                    from_court: getText(cells[2]),
                                    to_court: getText(cells[3])
                                });
                            }
                        });
                        if (transfers.length > 0) details.case_transfers = transfers;
                    }
                }
                
                // Fallback: Get court/establishment from header
                const courtHeader = document.querySelector('h2.text-center, h4.text-center');
                if (courtHeader) {
                    details.court_name = getText(courtHeader);
                }
                
                return details;
            }
        """)
        
        if case_data:
            details.update(case_data)
            print(f"[DEBUG] Extracted case data via JS: {list(case_data.keys())}")
        
        # Fallback: Parse with BeautifulSoup
        if not details or len(details) < 3:
            html_content = await page.content()
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Label mappings for BeautifulSoup parsing
            label_mappings = {
                'case type': 'case_type',
                'filing number': 'filing_number',
                'filing date': 'filing_date',
                'registration number': 'registration_number',
                'registration date': 'registration_date',
                'cnr number': 'cnr_number',
                'first hearing': 'first_hearing_date',
                'next hearing': 'next_hearing_date',
                'case stage': 'case_stage',
                'court number': 'court_number_and_judge',
            }
            
            # Find all tables and extract label-value pairs
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        label = cells[0].get_text(strip=True).lower().rstrip(':')
                        value = cells[1].get_text(strip=True)
                        
                        # Check if this label matches any of our mappings
                        for key_pattern, field_name in label_mappings.items():
                            if key_pattern in label:
                                if value and value not in ['', '-', 'NA', 'N/A']:
                                    if field_name not in details or not details[field_name]:
                                        details[field_name] = value
                                break
        
        print(f"[DEBUG] Extracted case details: {details}")
        
    except Exception as e:
        print(f"[ERROR] Error scraping case details: {e}")
        import traceback
        traceback.print_exc()
    
    return details


# ═══════════════════════════════════════════════════════════════════════════
# MULTI-MODE CASE-STATUS SEARCH — native Chakshi form backend (Phase 1)
# ---------------------------------------------------------------------------
# A parallel REST API (the /search/* namespace) that drives the eCourts
# "Case Status" page's seven tabs from a clean Chakshi UI. It reuses the proven
# primitives already in this file:
#   • scrape_dropdown_options / select_*_and_get_*  → the geographic cascade
#   • capture_captcha                               → user-solved captcha
#   • submit_form_and_scrape (via /submit-captcha)  → results
# The existing iframe + conversational /chat flow is untouched.
#
# Because each session keeps ONE live page, the location (state→district→
# court complex→establishment) is set incrementally as the dropdowns are
# fetched, so /search/submit only needs to: click the tab, fill mode fields,
# capture the captcha. /submit-captcha and /results then finish (both are
# already mode-agnostic).
# ═══════════════════════════════════════════════════════════════════════════

# Phase 1c — keep the Starter instance (512MB) from OOMing under many live
# Chromium sessions, and reap browsers left open by abandoned searches.
MAX_CONCURRENT_SEARCHES = int(os.getenv("MAX_CONCURRENT_SEARCHES", "3"))
SEARCH_IDLE_TIMEOUT = int(os.getenv("SEARCH_IDLE_TIMEOUT", "600"))  # 10 min idle

# Per-mode metadata: the visible tab text + which user inputs that tab needs.
# `dropdown` names the dependent picklist (fetched live from eCourts) if any.
SEARCH_MODES: Dict[str, Dict[str, Any]] = {
    "party_name":    {"tab": "Party Name",    "dropdown": None,            "fields": ["party_name", "case_year", "status"]},
    "case_number":   {"tab": "Case Number",   "dropdown": "case_types",    "fields": ["case_type", "case_number", "case_year", "status"]},
    "filing_number": {"tab": "Filing Number", "dropdown": None,            "fields": ["filing_number", "filing_year", "status"]},
    "advocate":      {"tab": "Advocate",      "dropdown": None,            "fields": ["advocate_name", "bar_reg_no", "case_year", "status"]},
    "fir":           {"tab": "FIR Number",    "dropdown": "police_stations","fields": ["police_station", "fir_number", "fir_year", "status"]},
    "act":           {"tab": "Act",           "dropdown": "acts",          "fields": ["act", "status"]},
    "case_type":     {"tab": "Case Type",     "dropdown": "case_types",    "fields": ["case_type", "case_year", "status"]},
}

# Defensive selector candidates for the mode-specific dropdowns (eCourts v6
# IDs vary by tab; we try several and fall back gracefully to []).
CASE_TYPE_SELECTORS = [
    'select#case_type', 'select[name="case_type"]', 'select#caseType',
    'select#case_type_2', 'select[name="case_type_2"]', 'select#casetype',
]
POLICE_STATION_SELECTORS = [
    'select#police_station', 'select[name="police_station"]',
    'select#fir_police_station', 'select#policestation', 'select[name="ps"]',
]
ACT_SELECTORS = [
    'select#actcode', 'select[name="actcode"]', 'select#act_type',
    'select[name="act_type"]', 'select#bear_act', 'select#act', 'select[name="act"]',
]


def _active_session_count() -> int:
    return sum(1 for s in SESSIONS.values() if s.get("browser") is not None)


async def _cleanup_idle_search_sessions() -> None:
    """Close browsers for sessions idle longer than SEARCH_IDLE_TIMEOUT."""
    now = time.time()
    stale = [sid for sid, s in SESSIONS.items()
             if s.get("browser") is not None
             and now - s.get("last_activity", s.get("created_at", now)) > SEARCH_IDLE_TIMEOUT]
    for sid in stale:
        s = SESSIONS.get(sid, {})
        try:
            if s.get("context"): await s["context"].close()
            if s.get("browser"): await s["browser"].close()
            if s.get("pw"): await s["pw"].stop()
        except Exception:
            pass
        SESSIONS.pop(sid, None)
        print(f"[search] reaped idle session {sid}")


def _touch(session: dict) -> None:
    session["last_activity"] = time.time()


def _require_session(session_id: str) -> dict:
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    if not session.get("page"):
        raise HTTPException(status_code=409, detail=f"Session not ready (status: {session.get('status')})")
    _touch(session)
    return session


async def _scrape_first(page: Page, selectors: List[str]):
    """Return (options, selector) for the first dropdown selector that yields options."""
    for sel in selectors:
        opts = await scrape_dropdown_options(page, sel)
        if opts:
            return opts, sel
    return [], None


# ---- generic tab / field helpers (defensive: real selectors → JS fallback) ----

async def _click_tab(page: Page, tab_text: str) -> bool:
    for sel in [f'a:has-text("{tab_text}")', f'li a:has-text("{tab_text}")',
                f'[data-toggle="tab"]:has-text("{tab_text}")', f'button:has-text("{tab_text}")']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                await page.wait_for_timeout(1200)
                return True
        except Exception:
            continue
    try:
        clicked = await page.evaluate(
            "(t) => { for (const e of document.querySelectorAll('a,button,li')) {"
            " if ((e.textContent||'').toLowerCase().trim().includes(t)) { e.click(); return true; } } return false; }",
            tab_text.lower())
        if clicked:
            await page.wait_for_timeout(1200)
            return True
    except Exception:
        pass
    print(f"[search] WARN: could not click tab '{tab_text}'")
    return False


async def _fill_input(page: Page, selectors: List[str], value, keyword: str = "") -> bool:
    if value is None or str(value).strip() == "":
        return True  # nothing to fill is not a failure
    value = str(value)
    for sel in selectors:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                await el.fill("")
                await el.type(value, delay=40)
                await page.keyboard.press("Tab")
                return True
        except Exception:
            continue
    if keyword:
        try:
            ok = await page.evaluate(
                "([kw, val]) => { for (const inp of document.querySelectorAll('input')) {"
                " const m = ((inp.id||'')+' '+(inp.name||'')+' '+(inp.placeholder||'')).toLowerCase();"
                " if (m.includes(kw)) { inp.focus(); inp.value = val;"
                " inp.dispatchEvent(new Event('input',{bubbles:true}));"
                " inp.dispatchEvent(new Event('change',{bubbles:true})); return true; } } return false; }",
                [keyword.lower(), value])
            return bool(ok)
        except Exception:
            pass
    print(f"[search] WARN: could not fill input ({keyword or selectors[0]})")
    return False


async def _select_dropdown(page: Page, selectors: List[str], value) -> bool:
    if not value:
        return True
    for sel in selectors:
        try:
            if await page.query_selector(sel):
                await page.select_option(sel, str(value))
                await page.wait_for_timeout(1000)
                return True
        except Exception:
            continue
    print(f"[search] WARN: could not select dropdown {selectors[0]} = {value}")
    return False


async def _select_status(page: Page, status: str) -> bool:
    status = (status or "both").lower()
    cands = {"pending": ["Pending", "P", "pending"],
             "disposed": ["Disposed", "D", "disposed"],
             "both": ["Both", "B", "both"]}.get(status, ["Both", "B", "both"])
    for v in cands:
        for sel in [f'input[type="radio"][value="{v}"]', f'input[type="radio"][value="{v.lower()}"]']:
            try:
                el = await page.query_selector(sel)
                if el:
                    await el.check()
                    return True
            except Exception:
                continue
    try:
        return bool(await page.evaluate(
            "(want) => { for (const r of document.querySelectorAll('input[type=radio]')) {"
            " let lbl=''; if (r.id){ const l=document.querySelector('label[for=\"'+r.id+'\"]'); if(l) lbl=l.textContent||''; }"
            " lbl=(lbl+' '+(r.value||'')+' '+(r.parentElement?r.parentElement.textContent:'')).toLowerCase();"
            " if (lbl.includes(want)) { r.checked=true; r.dispatchEvent(new Event('change',{bubbles:true})); return true; } } return false; }",
            status))
    except Exception:
        return False


# ---- per-mode tab fillers (location already set on the live page) ----

async def fill_tab_party_name(page: Page, p: Dict[str, Any]):
    await _click_tab(page, "Party Name")
    await _fill_input(page, ['input#pet_name', 'input[name="pet_name"]', 'input#petres_name',
                             'input[placeholder*="Petitioner" i]'], p.get("party_name"), keyword="pet")
    await _fill_input(page, ['input#rgyear', 'input[name="rgyear"]', 'input[placeholder*="Year" i]'],
                      p.get("case_year"), keyword="year")
    await _select_status(page, p.get("status"))


async def fill_tab_case_number(page: Page, p: Dict[str, Any]):
    await _click_tab(page, "Case Number")
    await _select_dropdown(page, CASE_TYPE_SELECTORS, p.get("case_type"))
    await _fill_input(page, ['input#case_no', 'input[name="case_no"]', 'input#caseno',
                             'input[placeholder*="Case Number" i]'], p.get("case_number"), keyword="case_no")
    await _fill_input(page, ['input#rgyear', 'input#case_year', 'input[name="case_year"]',
                             'input[name="rgyear"]'], p.get("case_year"), keyword="year")
    await _select_status(page, p.get("status"))


async def fill_tab_filing_number(page: Page, p: Dict[str, Any]):
    await _click_tab(page, "Filing Number")
    await _fill_input(page, ['input#filing_no', 'input[name="filing_no"]', 'input#filingno',
                             'input[placeholder*="Filing" i]'], p.get("filing_number"), keyword="filing")
    await _fill_input(page, ['input#filing_year', 'input[name="filing_year"]', 'input#fyear',
                             'input[placeholder*="Year" i]'], p.get("filing_year"), keyword="year")
    await _select_status(page, p.get("status"))


async def fill_tab_advocate(page: Page, p: Dict[str, Any]):
    await _click_tab(page, "Advocate")
    # eCourts offers Name OR Bar registration number — fill whichever was given.
    await _fill_input(page, ['input#advocate_name', 'input[name="advocate_name"]', 'input#adv_name',
                             'input[placeholder*="Advocate" i]'], p.get("advocate_name"), keyword="advocate")
    await _fill_input(page, ['input#bar_reg_no', 'input[name="bar_reg_no"]', 'input#barcode',
                             'input#bar_code', 'input[placeholder*="Bar" i]'], p.get("bar_reg_no"), keyword="bar")
    await _fill_input(page, ['input#rgyear', 'input[name="rgyear"]', 'input[placeholder*="Year" i]'],
                      p.get("case_year"), keyword="year")
    await _select_status(page, p.get("status"))


async def fill_tab_fir(page: Page, p: Dict[str, Any]):
    await _click_tab(page, "FIR Number")
    await _select_dropdown(page, POLICE_STATION_SELECTORS, p.get("police_station"))
    await _fill_input(page, ['input#fir_no', 'input[name="fir_no"]', 'input#firno',
                             'input[placeholder*="FIR" i]'], p.get("fir_number"), keyword="fir")
    await _fill_input(page, ['input#fir_year', 'input[name="fir_year"]', 'input#firyear',
                             'input[placeholder*="Year" i]'], p.get("fir_year"), keyword="year")
    await _select_status(page, p.get("status"))


async def fill_tab_act(page: Page, p: Dict[str, Any]):
    await _click_tab(page, "Act")
    await _select_dropdown(page, ACT_SELECTORS, p.get("act"))
    await _select_status(page, p.get("status"))


async def fill_tab_case_type(page: Page, p: Dict[str, Any]):
    await _click_tab(page, "Case Type")
    await _select_dropdown(page, CASE_TYPE_SELECTORS, p.get("case_type"))
    await _fill_input(page, ['input#rgyear', 'input#case_year', 'input[name="case_year"]',
                             'input[name="rgyear"]'], p.get("case_year"), keyword="year")
    await _select_status(page, p.get("status"))


TAB_FILLERS = {
    "party_name": fill_tab_party_name,
    "case_number": fill_tab_case_number,
    "filing_number": fill_tab_filing_number,
    "advocate": fill_tab_advocate,
    "fir": fill_tab_fir,
    "act": fill_tab_act,
    "case_type": fill_tab_case_type,
}


# ───────────────────────────── Pydantic bodies ─────────────────────────────

class SearchSubmit(BaseModel):
    session_id: str
    mode: str
    # mode-specific (all optional; validated per mode)
    party_name: Optional[str] = None
    case_type: Optional[str] = None
    case_number: Optional[str] = None
    case_year: Optional[str] = None
    filing_number: Optional[str] = None
    filing_year: Optional[str] = None
    advocate_name: Optional[str] = None
    bar_reg_no: Optional[str] = None
    police_station: Optional[str] = None
    fir_number: Optional[str] = None
    fir_year: Optional[str] = None
    act: Optional[str] = None
    status: Optional[str] = "both"


# ───────────────────────────── REST endpoints ─────────────────────────────

@app.post("/search/session")
async def search_session():
    """Open a Case Status session: launch a browser on the eCourts casestatus
    page and return a session_id + the list of states + the supported modes."""
    await cleanup_old_sessions()
    await _cleanup_idle_search_sessions()
    if _active_session_count() >= MAX_CONCURRENT_SEARCHES:
        raise HTTPException(status_code=429,
                            detail="Search is busy right now — please retry in a moment.")

    session_id = base64.urlsafe_b64encode(os.urandom(12)).decode().rstrip("=")
    SESSIONS[session_id] = {"status": "starting", "created_at": time.time(),
                            "last_activity": time.time(), "mode": "case_status"}
    await init_party_search_session(session_id)  # navigates to casestatus page, scrapes states

    session = SESSIONS.get(session_id, {})
    if session.get("status") == "error":
        raise HTTPException(status_code=502, detail=session.get("error", "Failed to reach eCourts"))

    return {
        "session_id": session_id,
        "states": session.get("state_options", []),
        "modes": [{"id": m, "label": cfg["tab"], "fields": cfg["fields"]} for m, cfg in SEARCH_MODES.items()],
    }


@app.get("/search/options/districts")
async def search_options_districts(session_id: str, state_value: str, state_text: str = ""):
    _require_session(session_id)
    await select_state_and_get_districts(session_id, state_value, state_text)
    s = SESSIONS[session_id]
    if s.get("status") == "error":
        raise HTTPException(status_code=502, detail=s.get("error", "eCourts error"))
    return {"districts": s.get("district_options", [])}


@app.get("/search/options/court-complexes")
async def search_options_court_complexes(session_id: str, district_value: str, district_text: str = ""):
    _require_session(session_id)
    await select_district_and_get_courts(session_id, district_value, district_text)
    s = SESSIONS[session_id]
    if s.get("status") == "error":
        raise HTTPException(status_code=502, detail=s.get("error", "eCourts error"))
    return {"court_complexes": s.get("court_complex_options", [])}


@app.get("/search/options/establishments")
async def search_options_establishments(session_id: str, court_value: str = "", court_text: str = ""):
    _require_session(session_id)
    await select_court_complex_and_get_establishments(session_id, court_value, court_text)
    s = SESSIONS[session_id]
    if s.get("status") == "error":
        raise HTTPException(status_code=502, detail=s.get("error", "eCourts error"))
    return {"establishments": s.get("establishment_options", [])}


@app.get("/search/options/mode-fields")
async def search_options_mode_fields(session_id: str, mode: str, est_value: str = "", est_text: str = ""):
    """Lock in the establishment, open the chosen tab, and return that tab's
    dependent picklist (case types / police stations / acts), if any."""
    session = _require_session(session_id)
    if mode not in SEARCH_MODES:
        raise HTTPException(status_code=400, detail=f"Unknown mode '{mode}'")
    await select_establishment_and_prepare_form(session_id, est_value, est_text)
    page = session["page"]
    await _click_tab(page, SEARCH_MODES[mode]["tab"])
    await page.wait_for_timeout(1200)

    out: Dict[str, Any] = {"mode": mode, "case_types": [], "police_stations": [], "acts": []}
    dd = SEARCH_MODES[mode]["dropdown"]
    if dd == "case_types":
        out["case_types"], _ = await _scrape_first(page, CASE_TYPE_SELECTORS)
    elif dd == "police_stations":
        out["police_stations"], _ = await _scrape_first(page, POLICE_STATION_SELECTORS)
    elif dd == "acts":
        out["acts"], _ = await _scrape_first(page, ACT_SELECTORS)
    return out


@app.post("/search/submit")
async def search_submit(body: SearchSubmit):
    """Fill the chosen tab with the user's inputs and capture the captcha.
    The client then calls POST /submit-captcha and GET /results (both reused)."""
    session = _require_session(body.session_id)
    if body.mode not in TAB_FILLERS:
        raise HTTPException(status_code=400, detail=f"Unknown mode '{body.mode}'")

    page = session["page"]
    try:
        await TAB_FILLERS[body.mode](page, body.dict())
        captcha_b64, selector_used = await capture_captcha(page)
        if not captcha_b64:
            raise HTTPException(status_code=502, detail="Could not capture captcha from eCourts")
        session.update({"status": "awaiting_captcha", "captcha_b64": captcha_b64,
                        "captcha_selector": selector_used})
        _touch(session)
        return {"status": "awaiting_captcha", "session_id": body.session_id, "captcha_b64": captcha_b64}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[search] submit error: {e}")
        session["status"] = "error"
        session["error"] = str(e)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=os.getenv("BACKEND_HOST", "127.0.0.1"),
        port=int(os.getenv("BACKEND_PORT", "8000"))
    )
