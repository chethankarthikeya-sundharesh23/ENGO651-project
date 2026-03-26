// Store user location globally
var userLat, userLon;
// Initialize map centered on Calgary
var map = L.map('map').setView([51.0447, -114.0719], 12);

// Add OpenStreetMap basemap
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: 'OpenStreetMap'
}).addTo(map);

let demLayer;
let layerControl;

// fetch dem bounds
async function loadDEMLayer() {

    const response = await fetch("http://localhost:8000/dem-bounds");
    const bounds = await response.json();

    const rectangleBounds = [
        [bounds.min_lat, bounds.min_lon],
        [bounds.max_lat, bounds.max_lon]
    ];

    demLayer = L.rectangle(rectangleBounds, {
        color: "red",
        weight: 2,
        fillOpacity: 0.1
    });

    // create control AFTER layer exists
    const overlayMaps = {
        "DEM Coverage": demLayer
    };

    layerControl = L.control.layers(null, overlayMaps).addTo(map);
}

// call it
loadDEMLayer();

// Get user location
if (navigator.geolocation) {

    navigator.geolocation.getCurrentPosition(function(position){

        userLat = position.coords.latitude;
        userLon = position.coords.longitude;

        map.setView([userLat, userLon], 14);

        L.marker([userLat, userLon])
        .addTo(map)
        .bindPopup("You are here")
        .openPopup();

    });

}

// Send user query to backend 
async function sendQuery(){

    const query = document.getElementById("queryInput").value;
    // Call backend API to process query
    const response = await fetch("http://localhost:8000/ai-query",{
        method:"POST",
        headers:{
        "Content-Type":"application/json"
    },
    body: JSON.stringify({
        query: query
    })
    });
    // Get response data (destination + weather + risk info)
    const data = await response.json();
    if (data.error) {
        alert(data.error);
        console.log("Backend error:", data.error);
        return;
    }
    // Extract destination coordinates
    const lat = data.lat;
    const lon = data.lon;
    // Move map to destination
    map.setView([lat,lon],14);
    // Add destination marker
    L.marker([lat,lon])
    .addTo(map)
    .bindPopup("Destination")
    .openPopup();
    // Call routing function
    getRoute(userLat,userLon,lat,lon);
}
// Get route from OSRM and compute route risk
async function getRoute(startLat, startLon, endLat, endLon){

    const url = `https://router.project-osrm.org/route/v1/driving/${startLon},${startLat};${endLon},${endLat}?overview=full&geometries=geojson&alternatives=true`;

    const response = await fetch(url);
    const data = await response.json();
    console.log("OSRM full response:", data);
    console.log("Number of routes:", data.routes.length);

    const routes = data.routes;

    let bestRoute = null;
    let bestRisk = Infinity;

    // clear old layers
    map.eachLayer(layer => {
        if (layer instanceof L.Polyline) {
            map.removeLayer(layer);
        }
    });

    for (let i = 0; i < routes.length; i++) {

        const routeObj = routes[i];
        const route = routeObj.geometry;

        const baseDuration = routeObj.duration;

        // draw ALL routes (gray first)
        L.geoJSON(route, {
            color: 'gray',
            weight: 3,
            opacity: 0.5
        }).addTo(map);

        // sample points
        const coords = route.coordinates;
        const sampled = coords.filter((_, idx) => idx % 20 === 0);

        // send to backend
        const riskResponse = await fetch("http://localhost:8000/route-risk", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                route: sampled
            })
        });

        const riskData = await riskResponse.json();

        console.log(`Route ${i} risk:`, riskData);

        // find best (LOWEST score)
        if (riskData.avg_score < bestRisk) {
            bestRisk = riskData.avg_score;
            bestRoute = {
                geometry: route,
                risk: riskData,
                duration: baseDuration
            };
        }
    }

    // Draw BEST route
    if (bestRoute) {

        L.geoJSON(bestRoute.geometry, {
            color: 'blue',
            weight: 6
        }).addTo(map);

        showRiskPanel(bestRoute.risk, bestRoute.duration);

        console.log("Safest route selected");
    }
}
function adjustDuration(baseSeconds, riskScore) {

    let factor = 1;

    if (riskScore >= 10) {
        factor = 1.5; // very slow
    } else if (riskScore >= 5) {
        factor = 1.25; // moderate delay
    } else {
        factor = 1.1; // slight delay
    }

    return baseSeconds * factor;
}
// Display risk results in UI panel
function showRiskPanel(data, durationSeconds) {

    const panel = document.getElementById("riskPanel");

    const adjustedSeconds = adjustDuration(durationSeconds, data.avg_score);

    const minutes = Math.round(adjustedSeconds / 60);

    const arrival = new Date(Date.now() + adjustedSeconds * 1000);
    const arrivalTime = arrival.toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit'
    });

    const terrainWarning = data.reasons.find(r =>
        r.includes("limited terrain data")
    );

    panel.innerHTML = `
    <h3>Route Risk: ${data.risk_level}</h3>

    <p><strong>Score:</strong> ${data.avg_score}</p>

    ${terrainWarning ? `<p style="color:red;"><strong>⚠ ${terrainWarning}</strong></p>` : ""}

    <p><strong>Estimated Travel Time:</strong> ${minutes} mins</p>
    <p><strong>Estimated Arrival:</strong> ${arrivalTime}</p>

    <p>${data.reasons.find(r => r.includes("temperature"))}</p>
    <p>${data.reasons.find(r => r.includes("weather"))}</p>
    <p>${data.reasons.find(r => r.includes("wind"))}</p>
    <p>${data.reasons.find(r => r.includes("road slope"))}</p>
    `;

    panel.style.display = "block";
}