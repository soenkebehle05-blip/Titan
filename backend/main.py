import os
import re
import requests
from datetime import datetime, timedelta
import zoneinfo
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import Optional, Dict
from groq import Groq
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str
    pin: Optional[str] = None
    locationAllowed: Optional[bool] = False
    coords: Optional[Dict[str, float]] = None

# ---------------------------------------------------------
# Google OAuth Configuration
# ---------------------------------------------------------
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
USER_CREDENTIALS = None

SCOPES = ['https://www.googleapis.com/auth/calendar']

def get_google_flow(request: Request):
    redirect_uri = str(request.url_for('auth_callback'))
    if redirect_uri.startswith("http://"):
        redirect_uri = redirect_uri.replace("http://", "https://")
        
    client_config = {
        "web": {
            "client_id": GOOGLE_CLIENT_ID,
            "project_id": "titan-assistant",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_secret": GOOGLE_CLIENT_SECRET
        }
    }
    return Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=redirect_uri
    )

@app.get("/auth/google")
async def auth_google(request: Request):
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return {"error": "Google Credentials sind auf Render nicht gesetzt."}
    flow = get_google_flow(request)
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    return RedirectResponse(authorization_url)

@app.get("/auth/callback", name="auth_callback")
async def auth_callback(request: Request, code: str):
    global USER_CREDENTIALS
    flow = get_google_flow(request)
    flow.fetch_token(code=code)
    credentials = flow.credentials
    USER_CREDENTIALS = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }
    return RedirectResponse(url="/")


# ---------------------------------------------------------
# Google Kalender Hilfsfunktionen
# ---------------------------------------------------------
def get_calendar_service():
    if not USER_CREDENTIALS:
        return None
    creds = Credentials(**USER_CREDENTIALS)
    return build('calendar', 'v3', credentials=creds)

def kalender_termine_abrufen():
    service = get_calendar_service()
    if not service:
        return "Sir, Sie sind noch nicht mit Google Kalender verbunden. Bitte melden Sie sich zuerst über Google an."
    
    tz = zoneinfo.ZoneInfo("Europe/Berlin")
    now = datetime.now(tz)
    start_of_day = now.replace(hour=0, minute=0, second=0).isoformat()
    end_of_day = (now + timedelta(days=1)).replace(hour=23, minute=59, second=59).isoformat()

    try:
        events_result = service.events().list(
            calendarId='primary', timeMin=start_of_day, timeMax=end_of_day,
            singleEvents=True, orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])

        if not events:
            return "Sir, Sie haben für heute keine anstehenden Termine im Kalender."

        termine = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            summary = event.get('summary', 'Unbenannter Termin')
            if 'T' in start:
                zeit_str = datetime.fromisoformat(start).strftime('%H:%M Uhr')
                termine.append(f"'{summary}' um {zeit_str}")
            else:
                termine.append(f"'{summary}' (Ganztägig)")

        return f"Sir, Ihre heutigen Termine lauten: {', '.join(termine)}."
    except Exception as e:
        return f"Sir, Fehler beim Abrufen des Kalenders: {str(e)}"

def kalender_termin_eintragen(summary: str, stunden_offset: int = 24):
    service = get_calendar_service()
    if not service:
        return "Sir, bitte verbinden Sie zuerst Ihren Google Kalender."

    tz = zoneinfo.ZoneInfo("Europe/Berlin")
    start_time = datetime.now(tz) + timedelta(hours=stunden_offset)
    end_time = start_time + timedelta(hours=1)

    event = {
        'summary': summary,
        'start': {'dateTime': start_time.isoformat()},
        'end': {'dateTime': end_time.isoformat()},
    }

    try:
        service.events().insert(calendarId='primary', body=event).execute()
        datum_str = start_time.strftime('%d.%m. um %H:%M Uhr')
        return f"Sir, der Termin '{summary}' wurde für den {datum_str} in Ihren Google Kalender eingetragen."
    except Exception as e:
        return f"Sir, Fehler beim Speichern des Termins: {str(e)}"


# ---------------------------------------------------------
# Notion Integration
# ---------------------------------------------------------
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

def extract_notion_id(raw_id: Optional[str]) -> str:
    if not raw_id:
        return ""
    cleaned = raw_id.strip('\'" ')
    match = re.search(r'([a-f0-9]{8}-?[a-f0-9]{4}-?[a-f0-9]{4}-?[a-f0-9]{4}-?[a-f0-9]{12})', cleaned, re.IGNORECASE)
    if match:
        uuid_str = match.group(1).replace("-", "")
        return f"{uuid_str[:8]}-{uuid_str[8:12]}-{uuid_str[12:16]}-{uuid_str[16:20]}-{uuid_str[20:]}"
    return raw_id

def get_notion_headers():
    token = NOTION_TOKEN.strip() if NOTION_TOKEN else ""
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

def eintrag_erstellen(titel: str):
    if not NOTION_TOKEN or not NOTION_DATABASE_ID:
        return "Sir, Notion ist auf Render nicht konfiguriert."
    
    clean_id = extract_notion_id(NOTION_DATABASE_ID)
    url_block = f"https://api.notion.com/v1/blocks/{clean_id}/children"
    payload = {
        "children": [{
            "object": "block",
            "type": "to_do",
            "to_do": {"rich_text": [{"type": "text", "text": {"content": titel}}], "checked": False}
        }]
    }
    try:
        res = requests.patch(url_block, json=payload, headers=get_notion_headers(), timeout=10)
        if res.status_code == 200:
            return f"Sir, '{titel}' wurde auf Ihre Liste geschrieben."
        return f"Sir, Fehler beim Eintragen in Notion: {res.text}"
    except Exception as e:
        return f"Sir, Fehler bei Notion: {str(e)}"

def eintraege_auslesen():
    if not NOTION_TOKEN or not NOTION_DATABASE_ID:
        return "Sir, Notion ist nicht konfiguriert."
    clean_id = extract_notion_id(NOTION_DATABASE_ID)
    url_block = f"https://api.notion.com/v1/blocks/{clean_id}/children"
    try:
        res = requests.get(url_block, headers=get_notion_headers(), timeout=10)
        results = res.json().get("results", [])
        eintraege = []
        for block in results:
            b_type = block.get("type")
            if b_type in ["to_do", "bulleted_list_item", "paragraph"]:
                texts = block.get(b_type, {}).get("rich_text", [])
                if texts:
                    text_content = texts[0].get("plain_text", "").strip()
                    if text_content:
                        eintraege.append(text_content)
        if not eintraege:
            return "Sir, es wurden noch keine Notizen auf Ihrer Liste gefunden."
        return f"Sir, folgende Einträge befinden sich auf Ihrer Liste: {', '.join(eintraege)}."
    except Exception as e:
        return f"Sir, Fehler beim Auslesen von Notion: {str(e)}"


# ---------------------------------------------------------
# Wetter Funktion
# ---------------------------------------------------------
def get_weather(lat: float, lon: float):
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        res = requests.get(url, timeout=5).json()
        temp = res["current_weather"]["temperature"]
        wind = res["current_weather"]["windspeed"]
        return f"{temp}°C, Windgeschwindigkeit {wind} km/h"
    except Exception:
        return "Keine Wetterdaten verfügbar"


@app.get("/")
def home():
    return {"status": "Titan Backend läuft!"}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    user_msg = req.message
    user_msg_lower = user_msg.lower()
    
    # 1. Deutsche Zeit & Datum ermitteln
    wochentage = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    tz = zoneinfo.ZoneInfo("Europe/Berlin")
    jetzt = datetime.now(tz)
    datum_uhrzeit_str = f"{wochentage[jetzt.weekday()]}, {jetzt.strftime('%d.%m.%Y')}, {jetzt.strftime('%H:%M')} Uhr"

    # 2. Kalender Schlüsselwörter
    if any(kw in user_msg_lower for kw in ["welche termine", "kalender auslesen", "welche kalender", "termine heute", "was steht im kalender"]):
        return {"reply": kalender_termine_abrufen()}
    
    if any(kw in user_msg_lower for kw in ["termin eintragen", "trage termin", "neuer termin", "termin erstellen"]):
        titel = user_msg_lower.replace("termin eintragen", "").replace("trage termin", "").strip()
        return {"reply": kalender_termin_eintragen(titel if titel else "Wichtiger Termin")}

    # 3. Notion Schlüsselwörter
    if any(kw in user_msg_lower for kw in ["welche notizen", "notion auslesen", "to-do-liste", "was steht auf meiner liste", "liste vorlesen"]):
        return {"reply": eintraege_auslesen()}

    if any(kw in user_msg_lower for kw in ["schreibe auf die", "auf meine liste", "neuer eintrag", "schreib"]):
        titel = user_msg
        for kw in ["schreibe auf die liste", "auf meine liste", "schreib"]:
            if kw in user_msg_lower:
                titel = user_msg_lower.split(kw)[-1].strip(" :")
                break
        return {"reply": eintrag_erstellen(titel if titel else user_msg)}

    # 4. KI-System-Prompt
    system_instruction = (
        "Du bist TITAN, ein hochintelligenter Sprachassistent. "
        "Platziere die Anrede 'Sir' AUSNAHMSLOS AN DEN ANFANG deiner Antwort. "
        "Antworte EXTREM KURZ UND DIREKT IN EINEM EINZIGEN SATZ. "
        "Nenne Uhrzeit, Datum oder Wetter NUR, wenn der Nutzer explizit danach fragt.\n\n"
        f"Hintergrund-Informationen (NUR bei expliziter Nachfrage nennen):\n"
        f"- Uhrzeit/Datum: {datum_uhrzeit_str}\n"
    )

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return {"reply": "Sir, GROQ_API_KEY fehlt auf Render."}

    try:
        client = Groq(api_key=api_key)
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_msg}
            ],
            model="llama-3.3-70b-versatile",
            max_tokens=70
        )
        reply = chat_completion.choices[0].message.content
    except Exception as e:
        reply = f"Sir, es gab einen Fehler: {str(e)}"

    return {"reply": reply}