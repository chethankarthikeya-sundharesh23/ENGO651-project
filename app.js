let isRegisterMode = false;

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
function generateWaypoints(startLat, startLon, endLat, endLon) {

    const midLat = (startLat + endLat) / 2;
    const midLon = (startLon + endLon) / 2;

    const offset = 0.05; // ~5 km deviation

    return [
        [midLat + offset, midLon],     // north deviation
        [midLat - offset, midLon],     // south
        [midLat, midLon + offset],     // east
        [midLat, midLon - offset]      // west
    ];
}

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
// Get route from OSRM and compute route risk
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

    if (routes.length < 2) {

        const waypoints = generateWaypoints(startLat, startLon, endLat, endLon)
            .slice(0, 2); // only try 2 waypoint routes

        for (let wp of waypoints) {

            const wpRoute = await getRouteViaWaypoint(
                startLat,
                startLon,
                wp[0],
                wp[1],
                endLat,
                endLon
            );

            if (wpRoute) {
                routes.push(wpRoute);
            }
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
    }
    console.log("Unique routes after filtering:", uniqueRoutes.length);
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
        const combinedScore = riskData.avg_score * 10 + (baseDuration / 60);
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

    <p style="margin-top:10px; padding:10px; background:#2a2a2a; border-radius:8px;">
        <strong>AI Explanation:</strong><br>
        ${data.ai_explanation}
    </p>

    ${terrainWarning ? `<p style="color:red;"><strong>⚠ ${terrainWarning}</strong></p>` : ""}

    <p><strong>Estimated Travel Time:</strong> ${minutes} mins</p>
    <p><strong>Estimated Arrival:</strong> ${arrivalTime}</p>

    <p>${data.reasons.find(r => r.includes("temperature"))}</p>
    <p>${data.reasons.find(r => r.includes("weather"))}</p>
    <p>${data.reasons.find(r => r.includes("road condition"))}</p>
    <p>${data.reasons.find(r => r.includes("wind"))}</p>
    <p>${data.reasons.find(r => r.includes("road slope"))}</p>
    `;

    panel.style.display = "block";
}