import os
import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict
from google import genai

app = FastAPI()

# CORS-Einstellungen für Zugriff über die Webseite
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

# Wetter-Funktion (kostenlos via Open-Meteo)
def get_weather(lat: float, lon: float):
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        res = requests.get(url).json()
        temp = res["current_weather"]["temperature"]
        wind = res["current_weather"]["windspeed"]
        return f"Aktuelle Temperatur: {temp}°C, Windgeschwindigkeit: {wind} km/h."
    except Exception:
        return "Wetterdaten konnten nicht abgerufen werden."

@app.get("/")
def home():
    return {"status": "Titan Backend mit Gemini läuft!"}

@app.post("/api/chat")
async def chat(req: ChatRequest):
    user_msg = req.message
    
    # 1. Wetterdaten ermitteln, falls Standort freigegeben ist
    weather_info = ""
    if ("wetter" in user_msg.lower() or "regen" in user_msg.lower() or "temperatur" in user_msg.lower()):
        if req.locationAllowed and req.coords:
            lat = req.coords.get("lat")
            lon = req.coords.get("lon")
            weather_info = f"\nSystem-Zusatzinfo zum aktuellen Wetter am Standort des Nutzers: {get_weather(lat, lon)}"
        else:
            weather_info = "\nSystem-Zusatzinfo: Der Nutzer hat den GPS-Standort deaktiviert."

    # 2. System-Prompt für Titan definieren
    system_instruction = (
        "Du bist TITAN, ein hochintelligenter, höflicher und effizienter KI-Sprachassistent. "
        "Du sprichst den Nutzer immer höflich mit 'Sir' an (oder passe es je nach Tonfall an). "
        "Halte deine Antworten eher kurz, prägnant und ideal für die Sprachausgabe geeignet."
    )

    # 3. Gemini API aufrufen
    api_key = os.environ.get("GEMINI_API_KEY")
    
    if not api_key:
        return {"reply": "Sir, der GEMINI_API_KEY ist im Server bisher nicht hinterlegt. Bitte tragen Sie ihn auf Render.com unter Environment Variables ein."}

    try:
        client = genai.Client(api_key=api_key)
        prompt = f"{system_instruction}\n{weather_info}\n\nNutzer-Nachricht: {user_msg}"
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        reply = response.text
    except Exception as e:
        reply = f"Sir, es gab einen Fehler bei der Kommunikation mit Gemini: {str(e)}"

    return {"reply": reply}
