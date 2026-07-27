import os
import requests
from datetime import datetime
import zoneinfo
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict
from groq import Groq
from notion_client import Client

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
# Notion Integration
# ---------------------------------------------------------
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

notion = Client(auth=NOTION_TOKEN) if NOTION_TOKEN else None

def eintrag_erstellen(titel: str):
    """Erstellt einen neuen Eintrag in deiner Notion-Datenbank unter 'Titan'."""
    if not notion or not NOTION_DATABASE_ID:
        return "Sir, Notion ist auf Render nicht konfiguriert."
    
    try:
        notion.pages.create(
            parent={"database_id": NOTION_DATABASE_ID},
            properties={
                "Titan": {
                    "title": [
                        {"text": {"content": titel}}
                    ]
                }
            }
        )
        return f"Sir, der Eintrag '{titel}' wurde erfolgreich in Notion erstellt."
    except Exception as e:
        return f"Sir, Fehler beim Erstellen des Eintrags: {str(e)}"

def eintraege_auslesen():
    """Liest die neuesten Einträge aus deiner Notion-Datenbank aus."""
    if not notion or not NOTION_DATABASE_ID:
        return "Sir, Notion ist auf Render nicht konfiguriert."
    
    try:
        response = notion.databases.query(database_id=NOTION_DATABASE_ID)
        results = response.get("results", [])
        
        if not results:
            return "Sir, es wurden keine Einträge in Notion gefunden."
        
        eintraege = []
        for page in results:
            props = page.get("properties", {})
            titan_prop = props.get("Titan", {})
            if titan_prop.get("type") == "title":
                title_list = titan_prop.get("title", [])
                if title_list:
                    eintraege.append(title_list[0].get("plain_text", ""))
        
        if not eintraege:
            return "Sir, es wurden keine Einträge in Notion gefunden."

        liste_text = ", ".join(eintraege)
        return f"Sir, folgende Einträge befinden sich in Notion: {liste_text}."
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

    # 2. Erweiterte Schlüsselwörter für Notion (Notizen & To-Do-Liste)
    keywords_notion_read = [
        "welche notizen", "notion auslesen", "notizen anzeigen", "was steht in notion", 
        "meine aufgaben", "to-do-liste", "todo liste", "to do liste", "welche aufgaben", 
        "was steht auf meiner liste", "was steht auf der liste"
    ]
    keywords_notion_write = [
        "erstelle notiz", "notier", "in notion eintragen", "notiz hinzufügen", "neuer eintrag",
        "schreibe auf die to-do-liste", "auf die liste setzen", "auf die to-do-liste", 
        "auf meine liste", "erstelle die notiz"
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
                # Falls z. B. gesagt wurde "schreibe Essen machen auf die To-Do-Liste"
                if "auf die" in titel:
                    titel = titel.split("auf die")[0].strip()
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
        "Du bist TITAN, ein hochintelligenter, höflicher Sprachassistent. "
        "Platziere die Anrede 'Sir' AUSNAHMSLOS AN DEN ANFANG deiner Antwort (z. B. 'Sir, es ist...'). "
        "Antworte EXTREM KURZ, HOEFLICH UND DIREKT IN EINEM EINZIGEN SATZ. "
        "Sag niemals 'Ich habe keine genauen Informationen' oder 'Empfehle Wetterberichte'. "
        "Behandle die Systemdaten als absolute Tatsache.\n\n"
        f"Systemdaten:\n"
        f"- Uhrzeit/Datum: {datum_uhrzeit_str}\n"
        f"- Wetter am Standort: {weather_info}\n\n"
        "BEISPIELE FÜR DIE ANTWORT:\n"
        "Frage: Wie ist das Wetter?\n"
        "Antwort: Sir, aktuell sind es 15,4 °C bei einer Windgeschwindigkeit von 8,8 km/h.\n\n"
        "Frage: Wie spät ist es?\n"
        "Antwort: Sir, es ist Montag, 10:11 Uhr.\n"
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
