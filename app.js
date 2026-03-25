// Store user location globally
var userLat, userLon;
// Initialize map centered on Calgary
var map = L.map('map').setView([51.0447, -114.0719], 12);

// Add OpenStreetMap basemap
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: 'OpenStreetMap'
}).addTo(map);

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

        const route = routes[i].geometry;

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
                risk: riskData
            };
        }
    }

    // 🟢 Draw BEST route
    if (bestRoute) {

        L.geoJSON(bestRoute.geometry, {
            color: 'blue',
            weight: 6
        }).addTo(map);

        showRiskPanel(bestRoute.risk);

        console.log("Safest route selected");
    }
}
// Display risk results in UI panel
function showRiskPanel(data) {
    const panel = document.getElementById("riskPanel");
    panel.innerHTML = `
    <h3>Route Risk: ${data.risk_level}</h3>
    <p><strong>Score:</strong> ${data.avg_score}</p>
    <p>${data.reasons.find(r => r.includes("temperature"))}</p>
    <p>${data.reasons.find(r => r.includes("weather"))}</p>
    <p>${data.reasons.find(r => r.includes("wind"))}</p>
    <p>${data.reasons.find(r => r.includes("road slope"))}</p>
    `;

    panel.style.display = "block";
}