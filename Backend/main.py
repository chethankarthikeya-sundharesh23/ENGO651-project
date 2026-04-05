from fastapi import FastAPI
from pydantic import BaseModel
import json
from shapely.geometry import Point, LineString
from fastapi.middleware.cors import CORSMiddleware
import requests
import os
import rasterio

with open("Calgey_Traffic_Incidents_20260310.geojson", "r", encoding="utf-8") as f:
    incidents_data = json.load(f)

incident_points = []

for feature in incidents_data["features"]:
    lon, lat = feature["geometry"]["coordinates"]
    incident_points.append(Point(lon, lat))

dem = rasterio.open("dem.tif")
app = FastAPI()
def get_elevation(lat, lon):
    row, col = dem.index(lon, lat)
    elevation = dem.read(1)[row, col]
    return float(elevation)

import math

def get_slope(lat, lon):

    row, col = dem.index(lon, lat)
    data = dem.read(1)

    try:
        center = data[row, col]
        right = data[row, col + 1]
        down = data[row + 1, col]

        # approximate meters per degree
        meters_per_degree = 111320  # ~111 km

        cellsize_deg = dem.res[0]
        cellsize_m = cellsize_deg * meters_per_degree

        dx = (right - center) / cellsize_m
        dy = (down - center) / cellsize_m

        slope = math.sqrt(dx**2 + dy**2)

        print("Correct slope:", slope)

        return float(slope)

    except Exception as e:
        print("Slope error:", e)
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

    current = data.get("current_weather")

    if not current:
        return 0, 0, 0   # fallback

    temp = current.get("temperature", 0)
    wind = current.get("windspeed", 0)
    weather_code = current.get("weathercode", 0)
    return temp, wind, weather_code

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

def interpret_weather(code):

    if code is None:
        return "Unknown"

    if code in [71, 73, 75, 77, 85, 86]:
        return "Snow"
    elif code in [61, 63, 65]:
        return "Rain"
    elif code == 0:
        return "Clear"
    else:
        return "Cloudy"

def calculate_risk(temp, wind, slope, condition, weather_type):

    score = 0
    reasons = []

    # --- include base info ---
    reasons.append(f"weather: {weather_type}")
    reasons.append(f"road condition: {condition}")

    # temperature
    if temp < 0:
        score += 2
        reasons.append("freezing temperature")
    elif temp < 3:
        score += 1
        reasons.append("near freezing")
    else:
        reasons.append("above freezing temperature")

    # weather type
    if weather_type == "Snow":
        score += 2
        reasons.append("snowfall")
    elif weather_type == "Rain" and temp <= 0:
        score += 2
        reasons.append("freezing rain")

    # wind
    if wind > 30:
        score += 1
        reasons.append("strong wind")
    else:
        reasons.append("moderate wind")

    # slope
    if slope > 0.15:
        score += 2
        reasons.append("steep slope")
    elif slope > 0.05:
        score += 1
        reasons.append("moderate slope")
    else:
        reasons.append("flat terrain")

    # Alberta 511
    cond = condition.lower()

    if "snow" in cond:
        score += 2
        reasons.append("snow-covered road")
    elif "ice" in cond:
        score += 3
        reasons.append("icy road")
    elif "closed" in cond:
        score += 3
        reasons.append("road closed")

    # final level
    if score >= 5:
        level = "HIGH"
    elif score >= 3:
        level = "MEDIUM"
    else:
        level = "LOW"

    return score, level, reasons
# Allow frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# -----------------------------
# Gemini explanation function
# -----------------------------
def generate_ai_explanation(risk_level, reasons):

    api_key = os.getenv("GEMINI_API_KEY")

    prompt = f"""
    Create one short driving-risk explanation under 50 words.

    Risk level: {risk_level}
    Reasons: {', '.join(reasons)}

    Requirements:
    - Maximum 50 words
    - Mention the most important reasons
    - Sound natural and helpful
    - Return only the explanation sentence
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
            return result["candidates"][0]["content"]["parts"][0]["text"].strip()

        else:
            print("Gemini explanation error:", response.text)

    except Exception as e:
        print("AI explanation error:", e)

    return f"{risk_level} risk because of current weather and road conditions."

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
    place = extract_destination(q.query)
    destination = place + ", Calgary"

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

    if not data:
        print("Trying without Calgary restriction...")
        params = {
            "q": place,
            "format": "json",
            "limit": 5
        }
        response = requests.get(url, params=params, headers=headers)
        data = response.json()

    if len(data) == 0:
        print("Location not found")
        return {"error": "Location not found"}

    lat = float(data[0]["lat"])
    lon = float(data[0]["lon"])
    temp, wind, weather_code = get_weather(lat, lon)
    weather_type = interpret_weather(weather_code)
    slope = get_slope(lat, lon)
    condition = get_road_condition(lat, lon)
    risk_score, risk_level, reasons = calculate_risk(
    temp, wind, slope, condition, weather_type
    )
    return {
    "destination": destination,
    "lat": lat,
    "lon": lon,
    "weather_type": weather_type,
    "temperature": temp,
    "wind": wind,
    "slope": slope,
    "condition": condition,
    "risk_score": risk_score,
    "risk_level": risk_level,
    "reasons": reasons
    }

class RouteRiskRequest(BaseModel):
    route: list
    risk_score: float | None = None

@app.post("/route-risk")
def route_risk(req: RouteRiskRequest):

    if not req.route:
        return {"error": "No route points"}

    missing_dem_points = 0
    total_points = len(req.route)

    # =========================
    # GLOBAL factors 
    # =========================
    first_point = req.route[0]
    lon, lat = first_point

    temp, wind, weather_code = get_weather(lat, lon)
    weather_type = interpret_weather(weather_code)

    global_score = 0
    global_reasons = []

    # temperature
    if temp < 0:
        global_score += 2
        global_reasons.append(f"temperature: {temp}°C (freezing)")
    elif temp < 3:
        global_score += 1
        global_reasons.append(f"temperature: {temp}°C (near freezing)")
    else:
        global_reasons.append(f"temperature: {temp}°C (above freezing)")

    # weather
    if weather_type == "Snow":
        global_score += 2
        global_reasons.append("snowfall")
    elif weather_type == "Rain" and temp <= 0:
        global_score += 2
        global_reasons.append("freezing rain")
    else:
        global_reasons.append(f"weather: {weather_type}")

    # wind
    if wind > 30:
        global_score += 1
        global_reasons.append("strong wind")
    else:
        global_reasons.append("moderate wind")

    # =========================
    # LOCAL factors (along route)
    # =========================
    local_score = 0

    # slope counters
    steep_count = 0
    moderate_count = 0
    flat_count = 0
    road_conditions = []
    for point in req.route:

        lon, lat = point

        if not is_within_dem(lat, lon):
            missing_dem_points += 1

        slope = get_slope(lat, lon)
        condition = get_road_condition(lat, lon)
        if condition not in ["Clear Road", "No Data"] and condition not in road_conditions:
            road_conditions.append(condition)
        # slope classification
        if slope > 0.15:
            local_score += 2
            steep_count += 1
        elif slope > 0.05:
            local_score += 1
            moderate_count += 1
        else:
            flat_count += 1

        # road condition
        cond = condition.lower()

        if "snow" in cond:
            local_score += 2
        elif "ice" in cond:
            local_score += 3
        elif "closed" in cond:
            local_score += 3

    # historical accident density along route
    incident_count = count_incidents_near_route(req.route, threshold=0.0001)
    route_length_km = calculate_route_length_km(req.route)
    if route_length_km > 0:
        accidents_per_km = incident_count / route_length_km
    else:
        accidents_per_km = 0

    if accidents_per_km >= 50:
        local_score += 2
        accident_reason = (
            f"historical accident density: {accidents_per_km:.1f} accidents/km (high)"
        )
    elif accidents_per_km >= 30:
        local_score += 1
        accident_reason = (
            f"historical accident density: {accidents_per_km:.1f} accidents/km (moderate)"
        )
    else:
        accident_reason = (
            f"historical accident density: {accidents_per_km:.1f} accidents/km (low)"
        )
        

    # =========================
    # Combine scores
    # =========================
    total_score = global_score + local_score

    # =========================
    # Risk level
    # =========================
    if total_score >= 10:
        final_level = "HIGH"
    elif total_score >= 5:
        final_level = "MEDIUM"
    else:
        final_level = "LOW"

    # =========================
    # Clean slope summary
    # =========================
    slope_summary = f"road slope: {moderate_count} moderate, {flat_count} flat"

    # include steep if exists
    if steep_count > 0:
        slope_summary = f"road slope: {steep_count} steep, {moderate_count} moderate, {flat_count} flat"

    # =========================
    #  Final reasons
    # =========================
    reasons = global_reasons.copy()
    if road_conditions:
        reasons.append(f"road condition: {road_conditions[0]}")
    else:
        reasons.append("road condition: Clear Road")
    reasons.append(slope_summary)
    reasons.append(accident_reason)
    coverage = 1 - (missing_dem_points / total_points)

    if coverage < 0.8:  # threshold (you can tweak)
        reasons.append("limited terrain data on this route")
    ai_explanation = generate_ai_explanation(final_level, reasons)
    incident_count = count_incidents_near_route(req.route)
    return {
        "avg_score": total_score,
        "risk_level": final_level,
        "reasons": reasons,
        "ai_explanation": ai_explanation,
        "incident_count": incident_count,
        "accidents_per_km": round(accidents_per_km, 2)
    }
    
@app.get("/dem-bounds")
def dem_bounds():

    bounds = dem.bounds

    return {
        "min_lat": bounds.bottom,
        "max_lat": bounds.top,
        "min_lon": bounds.left,
        "max_lon": bounds.right
    }
def is_within_dem(lat, lon):
    bounds = dem.bounds

    return (
        bounds.bottom <= lat <= bounds.top and
        bounds.left <= lon <= bounds.right
    )

class RouteQuery(BaseModel):
    startLat: float
    startLon: float
    endLat: float
    endLon: float
    wpLat: float | None = None
    wpLon: float | None = None


@app.post("/osrm-route")
def osrm_route(q: RouteQuery):

    # build coordinate string
    if q.wpLat is not None and q.wpLon is not None:
        coords = (
            f"{q.startLon},{q.startLat};"
            f"{q.wpLon},{q.wpLat};"
            f"{q.endLon},{q.endLat}"
        )
    else:
        coords = (
            f"{q.startLon},{q.startLat};"
            f"{q.endLon},{q.endLat}"
        )

    # lighter request to reduce 504 timeout
    url = (
        f"https://router.project-osrm.org/route/v1/driving/{coords}"
        f"?overview=full&geometries=geojson&alternatives=true"
    )

    try:
        response = requests.get(url, timeout=15)

        print("OSRM status:", response.status_code)

        if response.status_code != 200:
            print(response.text[:300])
            return {"routes": []}

        return response.json()

    except Exception as e:
        print("OSRM exception:", e)
        return {"routes": []}


def calculate_route_length_km(route_coords):
    total_km = 0

    for i in range(1, len(route_coords)):
        lon1, lat1 = route_coords[i - 1]
        lon2, lat2 = route_coords[i]

        R = 6371

        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)

        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(dlon / 2) ** 2
        )

        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        total_km += R * c

    return total_km


def count_incidents_near_route(route_coords, threshold=0.0001):
    """
    threshold ≈ 10 m in lat/lon degrees
    """

    line = LineString(route_coords)

    count = 0

    for pt in incident_points:
        if line.distance(pt) < threshold:
            count += 1

    return count