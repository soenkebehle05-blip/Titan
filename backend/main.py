import os
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
    
    # 1. Deutsche Zeit & Datum ermitteln
    wochentage = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    tz = zoneinfo.ZoneInfo("Europe/Berlin")
    jetzt = datetime.now(tz)
    aktueller_tag = wochentage[jetzt.weekday()]
    datum_uhrzeit_str = f"{aktueller_tag}, {jetzt.strftime('%d.%m.%Y')}, {jetzt.strftime('%H:%M')} Uhr"

    # 2. Live-Wetterdaten abrufen
    weather_info = "Keine GPS-Daten."
    keywords_wetter = ["wetter", "regen", "temperatur", "grad", "sonne", "kalt", "warm"]
    if any(kw in user_msg.lower() for kw in keywords_wetter):
        if req.locationAllowed and req.coords:
            lat = req.coords.get("lat")
            lon = req.coords.get("lon")
            weather_info = get_weather(lat, lon)
        else:
            weather_info = "Der Nutzer hat seinen GPS-Standort in der App deaktiviert."

    # 3. Extrem kurzer und direkter System-Prompt
    system_instruction = (
        "Du bist TITAN, ein extrem effizienter Assistent. "
        "ANTWORTE IMMER EXTREM KURZ, KNAPP UND DIREKT IN EINEM EINZIGEN KURZEN SATZ. "
        "Verzichte komplett auf Begrüßungen, Floskeln, Erklärungen oder Disclaimer über 'Echtzeitdaten'. "
        "Nutze folgende Systemdaten als absolute Wahrheit:\n"
        f"- Datum/Uhrzeit: {datum_uhrzeit_str}\n"
        f"- Aktuelles Wetter am Standort: {weather_info}\n\n"
        "Wenn der Nutzer nach dem Wetter fragt, nenne direkt die Temperatur und Bedingungen ohne Umschweife."
    )

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return {"reply": "GROQ_API_KEY fehlt auf Render."}

    try:
        client = Groq(api_key=api_key)
        
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_msg}
            ],
            model="llama-3.3-70b-versatile",
            max_tokens=100  # Zwingt die KI zu sehr kurzen Antworten
        )
        reply = chat_completion.choices[0].message.content
    except Exception as e:
        reply = f"Fehler: {str(e)}"

    return {"reply": reply}