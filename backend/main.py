import os
import re
import requests
from datetime import datetime
import zoneinfo
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict
from groq import Groq

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
# Notion Integration (Schreibt direkt auf die Seite "Titan")
# ---------------------------------------------------------
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

def extract_notion_id(raw_id: Optional[str]) -> str:
    """Isoliert die 32-stellige Notion UUID mit Bindestrichen."""
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
    
    # Fügt eine To-Do-Zeile direkt auf der Notion-Seite ein
    payload = {
        "children": [
            {
                "object": "block",
                "type": "to_do",
                "to_do": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {"content": titel}
                        }
                    ],
                    "checked": False
                }
            }
        ]
    }
    
    try:
        res = requests.patch(url_block, json=payload, headers=get_notion_headers(), timeout=10)
        if res.status_code == 200:
            return f"Sir, '{titel}' wurde auf Ihre Liste geschrieben."
        else:
            err_msg = res.json().get('message', res.text)
            return f"Sir, Fehler beim Eintragen in Notion: {err_msg}"
    except Exception as e:
        return f"Sir, Fehler bei der Verbindung zu Notion: {str(e)}"

def eintraege_auslesen():
    if not NOTION_TOKEN or not NOTION_DATABASE_ID:
        return "Sir, NOTION_TOKEN ist auf Render nicht konfiguriert."
    
    clean_id = extract_notion_id(NOTION_DATABASE_ID)
    url_block = f"https://api.notion.com/v1/blocks/{clean_id}/children"
    
    try:
        res = requests.get(url_block, headers=get_notion_headers(), timeout=10)
        if res.status_code != 200:
            err_msg = res.json().get('message', res.text)
            return f"Sir, Fehler beim Auslesen aus Notion: {err_msg}"
            
        results = res.json().get("results", [])
        if not results:
            return "Sir, es wurden noch keine Notizen auf Ihrer Liste gefunden."
        
        eintraege = []
        for block in results:
            b_type = block.get("type")
            # Liest To-Do-Blöcke und Bullet-Points aus
            if b_type in ["to_do", "bulleted_list_item", "paragraph"]:
                texts = block.get(b_type, {}).get("rich_text", [])
                if texts:
                    text_content = texts[0].get("plain_text", "").strip()
                    if text_content:
                        eintraege.append(text_content)
                            
        if not eintraege:
            return "Sir, es wurden noch keine Notizen auf Ihrer Liste gefunden."

        liste_text = ", ".join(eintraege)
        return f"Sir, folgende Einträge befinden sich auf Ihrer Liste: {liste_text}."
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
    aktueller_tag = wochentage[jetzt.weekday()]
    datum_uhrzeit_str = f"{aktueller_tag}, {jetzt.strftime('%d.%m.%Y')}, {jetzt.strftime('%H:%M')} Uhr"

    # 2. Schlüsselwörter für Notion
    keywords_notion_read = [
        "welche notizen", "notion auslesen", "notizen anzeigen", "was steht in notion", 
        "meine aufgaben", "to-do-liste", "todo liste", "to do liste", "welche aufgaben", 
        "was steht auf meiner liste", "was steht auf der liste", "was steht noch",
        "vorlesen", "lies mir", "lies meine", "liste vorlesen"
    ]
    keywords_notion_write = [
        "erstelle notiz", "notier", "in notion eintragen", "notiz hinzufügen", "neuer eintrag",
        "schreibe auf die to-do-liste", "auf die liste setzen", "auf die to-do-liste", 
        "auf meine liste", "erstelle die notiz", "eintrag erstellen", "schreib", "setze"
    ]

    # Auslesen
    if any(kw in user_msg_lower for kw in keywords_notion_read):
        return {"reply": eintraege_auslesen()}

    # Eintragen
    if any(kw in user_msg_lower for kw in keywords_notion_write):
        titel = user_msg
        for kw in keywords_notion_write:
            if kw in user_msg_lower:
                titel = user_msg_lower.split(kw)[-1].strip(" :")
                if "auf die" in titel:
                    titel = titel.split("auf die")[0].strip()
                if "auf meine" in titel:
                    titel = titel.split("auf meine")[0].strip()
                break
        return {"reply": eintrag_erstellen(titel if titel else user_msg)}

    # 3. Live-Wetterdaten abrufen
    weather_info = "Keine GPS-Daten vorhanden."
    keywords_wetter = ["wetter", "regen", "temperatur", "grad", "sonne", "kalt", "warm", "prognose", "vorhersage", "morgen"]
    if any(kw in user_msg_lower for kw in keywords_wetter):
        if req.locationAllowed and req.coords:
            lat = req.coords.get("lat")
            lon = req.coords.get("lon")
            weather_info = get_weather(lat, lon)
        else:
            weather_info = "GPS-Standort deaktiviert."

    # 4. System-Prompt für Titan
    system_instruction = (
        "Du bist TITAN, ein hochintelligenter Sprachassistent. "
        "Platziere die Anrede 'Sir' AUSNAHMSLOS AN DEN ANFANG deiner Antwort (z. B. 'Sir, es ist...'). "
        "Antworte EXTREM KURZ UND DIREKT IN EINEM EINZIGEN SATZ. "
        "Behandle die Systemdaten als absolute Tatsache.\n\n"
        f"Systemdaten:\n"
        f"- Uhrzeit/Datum: {datum_uhrzeit_str}\n"
        f"- Wetter am Standort: {weather_info}\n"
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