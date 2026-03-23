from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import requests
import os
import rasterio

dem = rasterio.open("dem.tif")
app = FastAPI()
def get_elevation(lat, lon):
    row, col = dem.index(lon, lat)
    elevation = dem.read(1)[row, col]
    return float(elevation)

def get_slope(lat, lon):

    row, col = dem.index(lon, lat)

    data = dem.read(1)

    try:
        center = data[row, col]
        right = data[row, col + 1]
        down = data[row + 1, col]

        dx = abs(right - center)
        dy = abs(down - center)

        slope = (dx + dy) / 2

        return float(slope)

    except:
        return 0
def get_weather(lat, lon):
    url = "https://api.open-meteo.com/v1/forecast"

    params = {
        "latitude": lat,
        "longitude": lon,
        "current_weather": True
    }

    response = requests.get(url, params=params)
    data = response.json()

    temp = data["current_weather"]["temperature"]
    wind = data["current_weather"]["windspeed"]

    return temp, wind

def get_road_condition(lat, lon):

    url = "https://services.arcgis.com/ArcGIS/rest/services/Traffic_Events/FeatureServer/0/query"

    params = {
        "where": "1=1",
        "outFields": "*",
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "distance": 5000,
        "units": "esriSRUnit_Meter",
        "f": "json"
    }

    try:
        response = requests.get(url, params=params)

        if response.status_code != 200:
            return "No Data"

        data = response.json()
        features = data.get("features", [])

        if not features:
            return "Clear Road"

        attr = features[0]["attributes"]

        return attr.get("DESCRIPTION", "Unknown")

    except Exception as e:
        print("511 ERROR:", e)
        return "No Data"

# Allow frontend access
origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request format from frontend
class Query(BaseModel):
    query: str


# -----------------------------
# Gemini AI function
# -----------------------------
def extract_destination(query):

    api_key = os.getenv("GEMINI_API_KEY")

    prompt = f"""
    Extract the destination location from this navigation request.
    Return ONLY the place name.

    Examples:

    Input: Take me to the airport
    Output: Calgary International Airport

    Input: I want to go to University of Calgary
    Output: University of Calgary

    Input: Find Tim Hortons
    Output: Tim Hortons

    Request: {query}
    """

    gemini_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }

    try:
        response = requests.post(
            gemini_url,
            params={"key": api_key},
            json=payload
        )

        if response.status_code == 200:
            result = response.json()
            destination = result["candidates"][0]["content"]["parts"][0]["text"]
            return destination.strip()

        else:
            print("Gemini error:", response.text)
            return query

    except Exception as e:
        print("Gemini exception:", e)
        return query


# -----------------------------
# AI Navigation Endpoint
# -----------------------------
@app.post("/ai-query")
def ai_query(q: Query):

    user_text = q.query

    # Use Gemini to extract location restricting to calgary for now
    destination = extract_destination(user_text) + ", Calgary"

    # OpenStreetMap geocoding
    url = "https://nominatim.openstreetmap.org/search"

    params = {
        "q": destination,
        "format": "json",
        "limit": 1,
        "viewbox": "-114.3,51.3,-113.7,50.9",  # Calgary bounding box
        "bounded": 1
    }

    headers = {
        "User-Agent": "ENGO651-project"
    }

    response = requests.get(url, params=params, headers=headers)
    data = response.json()

    if len(data) == 0:
        return {"error": "Location not found"}

    lat = float(data[0]["lat"])
    lon = float(data[0]["lon"])
    temp, wind = get_weather(lat, lon)
    slope = get_slope(lat, lon)
    condition = get_road_condition(lat, lon)
    return {
    "destination": destination,
    "lat": lat,
    "lon": lon,
    "temperature": temp,
    "wind": wind,
    "slope": slope,
    "condition": condition
    }

