import os
import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict

app = FastAPI()

# Erlaube Zugriff von der Frontend-Webseite
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

# Funktion um das Wetter kostenlos über Open-Meteo abzufragen
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
    return {"status": "Titan Backend läuft!"}

@app.post("/api/chat")
async def chat(req: ChatRequest):
    user_msg = req.message.lower()
    
    # 1. Prüfen, ob nach dem Wetter gefragt wurde und GPS aktiv ist
    weather_info = ""
    if "wetter" in user_msg or "regen" in user_msg:
        if req.locationAllowed and req.coords:
            lat = req.coords.get("lat")
            lon = req.coords.get("lon")
            weather_info = f" [System-Info Wetter: {get_weather(lat, lon)}]"
        else:
            weather_info = " [System-Info: GPS-Standort ist deaktiviert]."

    # 2. Antwort logik (Wird an KI weitergeleitet)
    reply = f"Hallo Sir, ich habe Ihre Nachricht erhalten: '{req.message}'.{weather_info}"
    
    return {"reply": reply}
