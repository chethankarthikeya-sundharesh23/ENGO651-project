let isRegisterMode = false;
// --------------------------------------------------
// Login / Registration Mode Toggle
// Switches between login and register interface
// --------------------------------------------------
function toggleMode() {

    isRegisterMode = !isRegisterMode;

    document.getElementById("formTitle").innerText =
        isRegisterMode ? "Register" : "Login";

    document.querySelector("#loginBox button").innerText =
        isRegisterMode ? "Register" : "Login";

    document.getElementById("toggleText").innerHTML =
        isRegisterMode
        ? `Already have an account? <a href="#" onclick="toggleMode()">Login</a>`
        : `Don't have an account? <a href="#" onclick="toggleMode()">Register</a>`;
}
// --------------------------------------------------
// Handle user login or account registration
// User credentials are stored locally in browser storage
// --------------------------------------------------
function login() {

    const username = document.getElementById("username").value;
    const password = document.getElementById("password").value;

    if (!username || !password) {
        alert("Please enter username and password");
        return;
    }

    // get saved users
    let users = JSON.parse(localStorage.getItem("users")) || {};

    if (isRegisterMode) {

        if (users[username]) {
            alert("Username already exists");
            return;
        }

        users[username] = password;
        localStorage.setItem("users", JSON.stringify(users));

        alert("Registration successful! Please log in.");
        toggleMode();

        document.getElementById("password").value = "";
        return;
    }

    // login mode
    if (users[username] && users[username] === password) {

    document.getElementById("loginBox").style.display = "none";
    document.getElementById("mainContent").style.display = "block";

    setTimeout(() => {
        map.invalidateSize();
    }, 100);
    }
}

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

// --------------------------------------------------
// Request DEM coverage bounds from backend
// and display them as a rectangle on the map
// --------------------------------------------------
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
        .bindPopup("You are here", {offset: [-50, 0]})
        .openPopup();
        });
}

// --------------------------------------------------
// Send the natural language query to the backend
// Backend returns destination coordinates and risk info
// --------------------------------------------------
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

// --------------------------------------------------
// Generate several waypoint candidates around the midpoint
// Used to force OSRM to create alternative routes
// --------------------------------------------------
function generateWaypoints(startLat, startLon, endLat, endLon) {

    const midLat = (startLat + endLat) / 2;
    const midLon = (startLon + endLon) / 2;

    const offset = 0.03; // ~3 km deviation

    return [
        [midLat + offset, midLon],     // north deviation
        [midLat - offset, midLon],     // south
        [midLat, midLon + offset],     // east
        [midLat, midLon - offset]      // west
    ];
}
// --------------------------------------------------
// Request a route that passes through a waypoint
// --------------------------------------------------
async function getRouteViaWaypoint(startLat, startLon, wpLat, wpLon, endLat, endLon) {

    const response = await fetch("http://localhost:8000/osrm-route", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            startLat,
            startLon,
            wpLat,
            wpLon,
            endLat,
            endLon
        })
    });

    const data = await response.json();

    if (!data.routes || data.routes.length === 0) return null;

    return data.routes[0];
}
// --------------------------------------------------
// Compare two routes to determine if they are similar
// Prevents duplicate alternative routes from being shown
// --------------------------------------------------
function isSimilarRoute(routeA, routeB) {

    const a = routeA.geometry.coordinates;
    const b = routeB.geometry.coordinates;

    if (!a || !b) return false;

    const minLen = Math.min(a.length, b.length);

    let similarCount = 0;

    for (let i = 0; i < minLen; i += 10) {
        const dx = Math.abs(a[i][0] - b[i][0]);
        const dy = Math.abs(a[i][1] - b[i][1]);

        if (dx < 0.001 && dy < 0.001) {
            similarCount++;
        }
    }

    return (similarCount / (minLen / 10)) > 0.7;
}
// --------------------------------------------------
// Main routing function
// 1. Request routes from backend
// 2. Generate extra alternatives if needed
// 3. Calculate risk for each route
// 4. Select and display the safest route
// --------------------------------------------------
async function getRoute(startLat, startLon, endLat, endLon){

    const response = await fetch("http://localhost:8000/osrm-route", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            startLat,
            startLon,
            endLat,
            endLon
        })
    });
    const data = await response.json();
    console.log("OSRM full response:", data);

    let routes = data.routes || [];

    // Try extra waypoint routes until we have at least 3 unique routes
    const waypoints = generateWaypoints(startLat, startLon, endLat, endLon);

    for (let wp of waypoints) {

        // stop if we already have enough routes before filtering
        if (routes.length >= 3) break;

        const wpRoute = await getRouteViaWaypoint(
            startLat,
            startLon,
            wp[0],
            wp[1],
            endLat,
            endLon
        );

        if (!wpRoute) continue;

        // avoid adding obviously identical routes
        let duplicate = false;

        for (let r of routes) {
            if (isSimilarRoute(wpRoute, r)) {
                duplicate = true;
                break;
            }
        }

        if (!duplicate) {
            routes.push(wpRoute);
        }
    }

    if (routes.length === 0) {
        alert("Could not get route from OSRM right now. Please try again.");
        return;
    }

    console.log("Total routes before filtering:", routes.length);

    const uniqueRoutes = [];

    for (let r of routes) {

        let duplicate = false;

        for (let u of uniqueRoutes) {
            if (isSimilarRoute(r, u)) {
                duplicate = true;
                break;
            }
        }

        if (!duplicate) {
            uniqueRoutes.push(r);
        }

        // stop once we have 3 unique routes
        if (uniqueRoutes.length >= 3) break;
    }

    console.log("Unique routes after filtering:", uniqueRoutes.length);

    if (uniqueRoutes.length < 3) {
        console.warn("Only", uniqueRoutes.length, "unique routes found");
    }
    
    let bestRoute = null;
    let bestRisk = Infinity;

    // clear old layers
    map.eachLayer(layer => {
        if (layer instanceof L.Polyline) {
            map.removeLayer(layer);
        }
    });

    for (let i = 0; i < uniqueRoutes.length; i++) {

        const routeObj = uniqueRoutes[i];
        const route = routeObj.geometry;

        const baseDuration = routeObj.duration;

        // draw ALL routes (gray first)
        L.geoJSON(route, {
            color: 'red',
            weight: 3,
            opacity: 0.6
        }).addTo(map);

        // Sample every 20th coordinate along the route
        const coords = route.coordinates;
        const sampled = coords.filter((_, idx) => idx % 20 === 0);

        // send to backend
        const riskResponse = await fetch("http://localhost:8000/route-risk", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                route: sampled,
                risk_score: 0
            })
        });

        const riskData = await riskResponse.json();

        console.log(`Route ${i + 1}: risk=${riskData.avg_score}, density=${riskData.accidents_per_km} accidents/km`);

        // find best (LOWEST score)
        const combinedScore = Math.round(riskData.avg_score * 10 + (baseDuration / 60));
        console.log(`Route ${i}:`);
        console.log("  Duration (min):", Math.round(baseDuration / 60));
        console.log("  Risk score:", riskData.avg_score);
        console.log("  Combined score:", combinedScore);
        if (combinedScore < bestRisk) {
            bestRisk = combinedScore;
            bestRoute = {
                geometry: route,
                risk: riskData,
                duration: baseDuration
            };
        }
    }

    // Draw BEST route
    if (bestRoute) {

    const explanationResponse = await fetch("http://localhost:8000/generate-explanation", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            risk_level: bestRoute.risk.risk_level,
            reasons: bestRoute.risk.reasons
        })
    });

    const explanationData = await explanationResponse.json();

    bestRoute.risk.ai_explanation = explanationData.ai_explanation;

    L.geoJSON(bestRoute.geometry, {
        color: 'blue',
        weight: 6
    }).addTo(map);

    showRiskPanel(bestRoute.risk, bestRoute.duration);

    console.log("Safest route selected");
    }
}
// --------------------------------------------------
// Adjust estimated travel time based on risk score
// Higher-risk routes are assumed to take longer
// --------------------------------------------------
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
// --------------------------------------------------
// Display route risk information in the side panel
// Includes score, AI explanation, weather, slope,
// road conditions, and estimated arrival time
// --------------------------------------------------
function showRiskPanel(data, durationSeconds) {

    const panel = document.getElementById("riskPanel");
    const content = document.getElementById("riskPanelContent");
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

    content.innerHTML = `
    <h3 style="margin-top:0; color:#356dff;">Route Risk: ${data.risk_level}</h3>

    <p><strong>Score:</strong> ${data.avg_score}</p>

    <div style="margin-top:12px; padding:12px; background:#f3f6ff; border-radius:12px; border-left:4px solid #356dff;">
        <strong>AI Explanation:</strong><br>
        ${data.ai_explanation}
    </div>

    ${terrainWarning ? `<p style="color:#d93025;"><strong>⚠ ${terrainWarning}</strong></p>` : ""}

    <p><strong>Estimated Travel Time:</strong> ${minutes} mins</p>
    <p><strong>Estimated Arrival:</strong> ${arrivalTime}</p>

    <p>🌡️ ${data.reasons.find(r => r.includes("temperature"))}</p>
    <p>☁️ ${data.reasons.find(r => r.includes("weather"))}</p>
    <p>🛣️ ${data.reasons.find(r => r.includes("road condition"))}</p>
    <p>💨 ${data.reasons.find(r => r.includes("wind"))}</p>
    <p>⛰️ ${data.reasons.find(r => r.includes("road slope"))}</p>
    <p>⚠️ ${data.reasons.find(r => r.includes("historical accident density"))}</p>
    `;

    
    panel.style.display = "block";
    panel.classList.remove("collapsed");
    document.getElementById("riskPanelContent").style.display = "block";
    document.getElementById("toggleRiskPanel").innerText = "−";
}
// --------------------------------------------------
// Collapse or expand the risk information panel
// --------------------------------------------------
function toggleRiskPanel() {
    const panel = document.getElementById("riskPanel");
    const content = document.getElementById("riskPanelContent");
    const button = document.getElementById("toggleRiskPanel");

    panel.classList.toggle("collapsed");

    if (panel.classList.contains("collapsed")) {
        content.style.display = "none";
        button.innerText = "+";
    } else {
        content.style.display = "block";
        button.innerText = "−";
    }
}