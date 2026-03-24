from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import requests
import os
import math

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request model
class Query(BaseModel):
    query: str
    lat: float
    lon: float


# -----------------------------
# Gemini AI
# -----------------------------
def extract_destination(query):
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        print("Gemini API key missing")
        return query

    prompt = f"""
    Extract the destination location from this navigation request.
    Return ONLY the place name.

    Examples:
    Input: Take me to the airport
    Output: Calgary International Airport

    Input: Find Tim Hortons
    Output: Tim Hortons

    Request: {query}
    """

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }

    try:
        res = requests.post(url, params={"key": api_key}, json=payload)

        print("🔍 Gemini status:", res.status_code)
        print("🔍 Gemini response:", res.text)

        if res.status_code == 200:
            data = res.json()

            if "candidates" in data:
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
            else:
                print("No candidates in response")
                return query

        else:
            print("Gemini API error:", res.text)
            return query

    except Exception as e:
        print("Gemini exception:", e)
        return query


# -----------------------------
# Distance
# -----------------------------
def distance(lat1, lon1, lat2, lon2):
    R = 6371  # km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = math.sin(dlat/2)**2 + \
        math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * \
        math.sin(dlon/2)**2

    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


# -----------------------------
# Route (OpenRouteService)
# -----------------------------
def get_route(start, end):
    url = "https://api.openrouteservice.org/v2/directions/driving-car"

    headers = {
        "Authorization": os.getenv("ORS_API_KEY"),
        "Content-Type": "application/json"
    }

    body = {
        "coordinates": [
            [start["lon"], start["lat"]],
            [end["lon"], end["lat"]]
        ],
        "alternative_routes": {
            "target_count": 3,
            "weight_factor": 1.4
        }
    }

    res = requests.post(url, json=body, headers=headers)
    return res.json()


# -----------------------------
# Weather
# -----------------------------
def get_weather(lat, lon):
    url = "https://api.openweathermap.org/data/2.5/weather"

    params = {
        "lat": lat,
        "lon": lon,
        "appid": os.getenv("WEATHER_API_KEY"),
        "units": "metric"
    }

    res = requests.get(url, params=params)
    return res.json()


# -----------------------------
# MAIN ENDPOINT
# -----------------------------
@app.post("/ai-query")
def ai_query(q: Query):

    user_lat = q.lat
    user_lon = q.lon

    destination = extract_destination(q.query) + ", Calgary"
    print(destination)
    # Get 5 candidates
    url = "https://nominatim.openstreetmap.org/search"
    headers = {"User-Agent": "ENGO651-project"}
    # Try Calgary bounded search FIRST
    params = {
        "q": destination,
        "format": "json",
        "limit": 5,
        "viewbox": "-114.3,51.3,-113.7,50.9",
        "bounded": 1
    }

    res = requests.get(url, params=params, headers=headers)
    data = res.json()

    # 🔥 FALLBACK if nothing found
    if not data:
        print(f"⚠️ No Calgary results, trying global search... {extract_destination(q.query)}")

        params = {
            "q": extract_destination(q.query),  # NO ", Calgary"
            "format": "json",
            "limit": 5
        }

        res = requests.get(url, params=params, headers=headers)
        data = res.json()

    if not data:
        return {"error": "Location not found"}

    # Choose closest
    best = None
    best_dist = float("inf")

    for place in data:
        lat = float(place["lat"])
        lon = float(place["lon"])

        d = distance(user_lat, user_lon, lat, lon)

        if d < best_dist:
            best_dist = d
            best = place

    dest_lat = float(best["lat"])
    dest_lon = float(best["lon"])

    # Route
    route_data = get_route(
        {"lat": user_lat, "lon": user_lon},
        {"lat": dest_lat, "lon": dest_lon}
    )

    weather = get_weather(dest_lat, dest_lon)

    routes = route_data.get("routes", [])

    best_route = None
    best_score = float("inf")

    for r in routes:
        distance_km = r["summary"]["distance"] / 1000
        duration_min = r["summary"]["duration"] / 60

        safety = compute_safety(weather)

        # COST FUNCTION (THIS IS YOUR CORE IDEA)
        cost = (distance_km * 0.6) + (duration_min * 0.3) + ((1 - safety) * 10)

        if cost < best_score:
            best_score = cost
            best_route = r

    return {
        "destination": best["display_name"],
        "lat": dest_lat,
        "lon": dest_lon,
        "route": best_route,
        "weather": weather,
        "safety_score": safety
    }

def compute_safety(weather):
    score = 1.0

    # Snow penalty
    if "snow" in str(weather).lower():
        score -= 0.4

    # Wind penalty
    if weather.get("wind", {}).get("speed", 0) > 10:
        score -= 0.2

    # Extreme cold penalty
    if weather.get("main", {}).get("temp", 0) < -15:
        score -= 0.2

    return max(score, 0.1)