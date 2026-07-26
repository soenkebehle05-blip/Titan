import os
import requests
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
    user_msg = req.message
    
    weather_info = ""
    if ("wetter" in user_msg.lower() or "regen" in user_msg.lower() or "temperatur" in user_msg.lower()):
        if req.locationAllowed and req.coords:
            lat = req.coords.get("lat")
            lon = req.coords.get("lon")
            weather_info = f"\nSystem-Zusatzinfo zum Wetter am Standort: {get_weather(lat, lon)}"
        else:
            weather_info = "\nSystem-Zusatzinfo: GPS ist deaktiviert."

    system_instruction = (
        "Du bist TITAN, ein hochintelligenter, höflicher KI-Sprachassistent. "
        "Du sprichst den Nutzer immer höflich mit 'Sir' an. "
        "Halte deine Antworten kurz, prägnant und perfekt für die Sprachausgabe."
    )

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return {"reply": "Sir, der GROQ_API_KEY fehlt noch auf Render."}

    try:
        client = Groq(api_key=api_key)
        
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": f"{system_instruction}\n{weather_info}"},
                {"role": "user", "content": user_msg}
            ],
            model="llama-3.3-70b-versatile",
        )
        reply = chat_completion.choices[0].message.content
    except Exception as e:
        reply = f"Sir, es gab einen Fehler: {str(e)}"

    return {"reply": reply}