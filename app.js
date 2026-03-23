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
    // Request route from OSRM API
    const url = `https://router.project-osrm.org/route/v1/driving/${startLon},${startLat};${endLon},${endLat}?overview=full&geometries=geojson`;
    const response = await fetch(url);
    const data = await response.json();
    // Extract route geometry
    const route = data.routes[0].geometry;
    // Draw route on map
    L.geoJSON(route, {
        color: 'blue',
        weight: 5
    }).addTo(map);

    // Sample route points
    const coords = route.coordinates;
    // Take every 20th point
    const sampled = coords.filter((_, i) => i % 20 === 0); // every 20th point
    // Send to backend for risk
    const riskResponse = await fetch("http://localhost:8000/route-risk", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            route: sampled
        })
    });
    // Receive route risk result
    const riskData = await riskResponse.json();
    console.log("Route Risk Data:", riskData);
    // Display risk information in panel
    showRiskPanel(riskData);
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