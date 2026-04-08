# Winter Road Risk Mapper

An AI-powered web mapping application that recommends safer winter driving routes in Calgary by combining weather, terrain slope, road conditions, and historical accident data. The system generates several possible routes, evaluates their risk, and highlights the safest option for the user.

## Project Structure

```text
ENGO651-project/
│
├── index.html
├── style.css
├── app.js
├── README.md
├── .gitignore
├── .gitattributes
│
└── Backend/
    ├── main.py
    ├── requirements.txt
    ├── dem.tif
    ├── Calgey_Traffic_Incidents_20260310.geojson
    └── __pycache__/
```

## Clone the Repository

```bash
git clone <your-github-repository-url>
cd ENGO651-project
```

## Install Dependencies

```bash
cd Backend
pip install -r requirements.txt
```

## Set API Keys (PowerShell)

```powershell
$env:WEATHER_API_KEY="your_weatherapi_key"
$env:GEMINI_API_KEY="your_gemini_api_key"
```

If you use Command Prompt instead of PowerShell:

```cmd
set WEATHER_API_KEY=your_weatherapi_key
set GEMINI_API_KEY=your_gemini_api_key
```

## Run the Backend

From the `Backend` folder:

```bash
python -m uvicorn main:app
```

You should see:

```text
Uvicorn running on http://127.0.0.1:8000
```

## Run the Frontend

Open a second terminal in the project root folder:

```bash
cd ENGO651-project
python -m http.server 5500
```

Then open this in your browser:

```text
http://127.0.0.1:5500
```

Or, if you use VS Code:

```text
Right click index.html → Open with Live Server
```

## API Endpoints

```text
POST /ai-query
POST /osrm-route
POST /route-risk
GET  /dem-bounds
```

## Example Usage

```text
Take me to the airport
Find Tim Hortons
Take me to University of Calgary
```

## Risk Level Thresholds

```text
0–4   = LOW
5–9   = MEDIUM
10+   = HIGH
```

## Slope Classification

```text
Slope <= 0.05      → Flat
0.05 < Slope <= 0.15 → Moderate
Slope > 0.15       → Steep
```

## Common Errors

If you see:

```text
Loaded Weather API key: None
```

your Weather API key was not set.

If you see:

```text
401 API key required
```

your WeatherAPI key is missing or invalid.

If you see:

```text
503 UNAVAILABLE
```

Gemini is temporarily overloaded. Wait a few minutes and try again.

## Author
Wei He  
Chethan Karthikeya Sundharesh
