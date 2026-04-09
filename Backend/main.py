from fastapi import FastAPI
from pydantic import BaseModel
import json
from shapely.geometry import Point, LineString
from fastapi.middleware.cors import CORSMiddleware
import math
import requests
import os
import rasterio

with open("Calgey_Traffic_Incidents_20260310.geojson", "r", encoding="utf-8") as f:
    incidents_data = json.load(f)
incident_points = []
for feature in incidents_data["features"]:
    lon, lat = feature["geometry"]["coordinates"]
    incident_points.append(Point(lon, lat))
# --------------------------------------------------
# Open DEM raster used for elevation and slope analysis
# --------------------------------------------------
dem = rasterio.open("dem.tif")
app = FastAPI()
# --------------------------------------------------
# Return elevation value from DEM at a given latitude/longitude
# --------------------------------------------------
def get_elevation(lat, lon):
    """
    Retrieve elevation from the DEM raster at a given latitude and longitude.

    Args:
        lat (float): Latitude of the location.
        lon (float): Longitude of the location.

    Returns:
        float: Elevation value in meters.
    """
    row, col = dem.index(lon, lat)
    elevation = dem.read(1)[row, col]
    return float(elevation)
# --------------------------------------------------
# Calculate terrain slope from the DEM
# Uses neighboring raster cells to estimate x/y slope
# Slope = sqrt(dx² + dy²)
# --------------------------------------------------
def get_slope(lat, lon):
    """
    Estimate terrain slope at a given location using DEM raster data.

    The slope is computed using elevation differences between neighboring cells
    in the x (east-west) and y (north-south) directions.

    Args:
        lat (float): Latitude of the location.
        lon (float): Longitude of the location.

    Returns:
        float: Slope value (unitless gradient). Returns 0 if computation fails.
    """

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
# --------------------------------------------------
# Load WeatherAPI key from environment variables
# --------------------------------------------------
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
print("Loaded Weather API key:", WEATHER_API_KEY)
# --------------------------------------------------
# Request current weather conditions from WeatherAPI
# Returns:
#   temperature (°C)
#   wind speed (km/h)
#   simplified weather code
# --------------------------------------------------
def get_weather(lat, lon):
    """
   Fetch current weather data from WeatherAPI for a given location.

   Args:
       lat (float): Latitude of the location.
       lon (float): Longitude of the location.

   Returns:
       tuple:
           temp (float): Temperature in Celsius.
           wind (float): Wind speed in km/h.
           weather_code (int): Simplified weather condition code.
   """
    url = "https://api.weatherapi.com/v1/current.json"

    params = {
        "key": WEATHER_API_KEY,
        "q": f"{lat},{lon}"
    }

    try:
        response = requests.get(url, params=params, timeout=20)

        print("WeatherAPI status:", response.status_code)
        print("WeatherAPI text:", response.text[:200])

        if response.status_code != 200:
            return 0, 0, 0

        data = response.json()

        current = data.get("current", {})

        temp = current.get("temp_c", 0)
        wind = current.get("wind_kph", 0)

        condition_text = current.get("condition", {}).get("text", "").lower()

        # convert to your existing weather codes
        if "snow" in condition_text:
            weather_code = 71
        elif "rain" in condition_text:
            weather_code = 61
        elif "clear" in condition_text or "sunny" in condition_text:
            weather_code = 0
        else:
            weather_code = 3

        return temp, wind, weather_code

    except Exception as e:
        print("WeatherAPI error:", e)
        return 0, 0, 0
# --------------------------------------------------
# Request nearby road condition information from Alberta 511
# Looks for incidents within 5 km of the input location
# --------------------------------------------------
def get_road_condition(lat, lon):
    """
    Retrieve nearby road condition information from Alberta 511 API.

    Searches for traffic incidents within a 5 km radius of the given location.

    Args:
        lat (float): Latitude of the location.
        lon (float): Longitude of the location.

    Returns:
        str: Description of road condition (e.g., "Clear Road", "Snow", "Closed"),
             or "No Data" if unavailable.
    """

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
# --------------------------------------------------
# Convert numeric weather codes into simple labels
# Example: Snow, Rain, Clear, Cloudy
# --------------------------------------------------
def interpret_weather(code):
    """
   Convert numeric weather codes into human-readable categories.

   Args:
       code (int): Weather condition code.

   Returns:
       str: Weather type ("Snow", "Rain", "Clear", "Cloudy", or "Unknown").
   """

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
    """
    Compute a driving risk score based on environmental and road factors.

    Factors considered:
        - Temperature
        - Weather type
        - Wind speed
        - Terrain slope
        - Road conditions

    Args:
        temp (float): Temperature in Celsius.
        wind (float): Wind speed in km/h.
        slope (float): Terrain slope.
        condition (str): Road condition description.
        weather_type (str): Interpreted weather type.

    Returns:
        tuple:
            score (int): Numerical risk score.
            level (str): Risk level ("LOW", "MEDIUM", "HIGH").
            reasons (list): List of contributing risk factors.
    """

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
# --------------------------------------------------
# Enable frontend requests from localhost
# Required so the JavaScript frontend can access the API
# --------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def generate_ai_explanation(risk_level, reasons):
    """
    Generate a short natural-language explanation of driving risk using Gemini API.

    Args:
        risk_level (str): Overall risk level ("LOW", "MEDIUM", "HIGH").
        reasons (list): List of contributing factors.

    Returns:
        str: AI-generated explanation (max ~50 words).
    """

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

# --------------------------------------------------
# Use Gemini to extract a destination from natural language
# Example:
#   "Take me to the airport"
# becomes
#   "Calgary International Airport"
# --------------------------------------------------
def extract_destination(query):
    """
    Extract a destination place name from a natural language query using Gemini API.

    Example:
        "Take me to the airport" → "Calgary International Airport"

    Args:
        query (str): User input query.

    Returns:
        str: Extracted destination name.
    """

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



@app.post("/ai-query")
def ai_query(q: Query):
    """
    Process a natural language navigation query.

    Workflow:
        1. Extract destination using AI
        2. Geocode location using OpenStreetMap
        3. Fetch weather, slope, and road condition
        4. Compute risk score

    Args:
        q (Query): User query object.

    Returns:
        dict: Destination details, environmental data, and risk analysis.
    """

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

class ExplanationRequest(BaseModel):
    risk_level: str
    reasons: list[str]

@app.post("/generate-explanation")
def generate_explanation(req: ExplanationRequest):
    """
    Generate a short AI explanation for a given risk level and reasons.

    Args:
        req (ExplanationRequest): Contains risk level and contributing reasons.

    Returns:
        dict: AI-generated explanation text.
    """
    explanation = generate_ai_explanation(req.risk_level, req.reasons)
    return {"ai_explanation": explanation}

@app.post("/route-risk")
def route_risk(req: RouteRiskRequest):
    """
    Calculate overall driving risk for a route.

    Includes:
        - Global factors (weather, temperature, wind)
        - Local factors (slope, road conditions)
        - Historical accident density

    Args:
        req (RouteRiskRequest): Route coordinates.

    Returns:
        dict: Risk score, level, reasons, and accident statistics.
    """

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

    # --------------------------------------------------
    # Count how many sampled route points fall into each slope class
    # flat: slope <= 0.05
    # moderate: 0.05 - 0.15
    # steep: > 0.15
    # --------------------------------------------------
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

    # --------------------------------------------------
    # Compute historical accident density along the route
    # Accident density = incidents / route length
    # --------------------------------------------------
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

    # --------------------------------------------------
    # Create a readable summary of terrain conditions
    # Example:
    #   road slope: 1 steep, 2 moderate, 5 flat
    # --------------------------------------------------
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
    incident_count = count_incidents_near_route(req.route)
    return {
        "avg_score": total_score,
        "risk_level": final_level,
        "reasons": reasons,
        "incident_count": incident_count,
        "accidents_per_km": round(accidents_per_km, 2)
    }
# --------------------------------------------------
# Return the geographic bounds of the DEM raster
# Used by the frontend to draw the DEM coverage area
# --------------------------------------------------
@app.get("/dem-bounds")
def dem_bounds():
    """
    Return the geographic bounds of the DEM raster.

    Returns:
        dict: Minimum and maximum latitude and longitude of DEM coverage.
    """

    bounds = dem.bounds

    return {
        "min_lat": bounds.bottom,
        "max_lat": bounds.top,
        "min_lon": bounds.left,
        "max_lon": bounds.right
    }
# --------------------------------------------------
# Check whether a point falls inside the DEM coverage area
# --------------------------------------------------
def is_within_dem(lat, lon):
    """
    Check if a coordinate lies within the DEM coverage area.

    Args:
        lat (float): Latitude.
        lon (float): Longitude.

    Returns:
        bool: True if inside DEM bounds, False otherwise.
    """
    bounds = dem.bounds

    return (
        bounds.bottom <= lat <= bounds.top and
        bounds.left <= lon <= bounds.right
    )
# --------------------------------------------------
# Data model for requesting a route from OSRM
# --------------------------------------------------
class RouteQuery(BaseModel):
    startLat: float
    startLon: float
    endLat: float
    endLon: float
    wpLat: float | None = None
    wpLon: float | None = None

@app.post("/osrm-route")
def osrm_route(q: RouteQuery):
    """
    Fetch driving route(s) from OSRM between given points.

    Supports optional waypoint routing.

    Args:
        q (RouteQuery): Start, end, and optional waypoint coordinates.

    Returns:
        dict: OSRM routing response containing route geometries and details.
    """

    # Build coordinate string for OSRM request
    # If a waypoint exists, route goes:
    # start -> waypoint -> destination
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

    # Use public online OSRM server
    url = (
        f"https://router.project-osrm.org/route/v1/driving/"
        f"{coords}"
        f"?alternatives=true&steps=true&overview=full&geometries=geojson"
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
    """
    Compute total route length using the Haversine formula.

    Args:
        route_coords (list): List of [lon, lat] coordinate pairs.

    Returns:
        float: Total distance in kilometers.
    """
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
    Count how many historical traffic incidents are near a route.

    Args:
        route_coords (list): List of [lon, lat] coordinates defining the route.
        threshold (float): Maximum distance (in degrees) from route to count incidents.

    Returns:
        int: Number of nearby incidents.
    """
    line = LineString(route_coords)

    count = 0

    for pt in incident_points:
        if line.distance(pt) < threshold:
            count += 1

    return count