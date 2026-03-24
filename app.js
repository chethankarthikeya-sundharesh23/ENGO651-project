var map = L.map('map').setView([51.0447, -114.0719], 12);

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: 'OpenStreetMap'
}).addTo(map);

let userLat = null;
let userLon = null;
let routeLayer = null;


// -----------------------------
// Decode polyline
// -----------------------------
function decodePolyline(encoded) {
    let points = [];
    let index = 0, len = encoded.length;
    let lat = 0, lng = 0;

    while (index < len) {
        let b, shift = 0, result = 0;
        do {
            b = encoded.charCodeAt(index++) - 63;
            result |= (b & 0x1f) << shift;
            shift += 5;
        } while (b >= 0x20);

        let dlat = ((result & 1) ? ~(result >> 1) : (result >> 1));
        lat += dlat;

        shift = 0;
        result = 0;

        do {
            b = encoded.charCodeAt(index++) - 63;
            result |= (b & 0x1f) << shift;
            shift += 5;
        } while (b >= 0x20);

        let dlng = ((result & 1) ? ~(result >> 1) : (result >> 1));
        lng += dlng;

        points.push([lat / 1e5, lng / 1e5]);
    }

    return points;
}


// -----------------------------
// Get user location
// -----------------------------
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


// -----------------------------
// Send query
// -----------------------------
async function sendQuery(){

    console.log("Button clicked");

    const query = document.getElementById("queryInput").value;

    if (!query) {
        alert("Enter a destination");
        return;
    }

    if (userLat === null || userLon === null){
        alert("Location not loaded yet");
        return;
    }

    try {
        const response = await fetch("http://localhost:8000/ai-query", {
            method:"POST",
            headers:{
                "Content-Type":"application/json"
            },
            body: JSON.stringify({
                query: query,
                lat: userLat,
                lon: userLon
            })
        });

        const data = await response.json();

        console.log("Backend data:", data);

        if (data.error) {
            alert(data.error);
            return;
        }

        const lat = data.lat;
        const lon = data.lon;

        map.setView([lat, lon], 14);

        L.marker([lat, lon])
            .addTo(map)
            .bindPopup("Destination")
            .openPopup();

        // Draw route
        if (data.route) {

            let latlngs = [];

            // Case 1: encoded polyline (string)
            if (typeof data.route.geometry === "string") {

                latlngs = decodePolyline(data.route.geometry);

            }
            // Case 2: GeoJSON coordinates
            else if (data.route.geometry && data.route.geometry.coordinates) {

                latlngs = data.route.geometry.coordinates.map(c => [c[1], c[0]]);

            }
            else {
                console.log("Unknown geometry format:", data.route);
                alert("Route format not supported");
                return;
            }

            // clear old route
            if (routeLayer) {
                map.removeLayer(routeLayer);
            }

            // draw route
            routeLayer = L.polyline(latlngs, {color: 'blue'}).addTo(map);

            console.log("Route drawn successfully");

        } else {
            console.log(" No route found", data);
        }

        console.log("FULL ROUTE:", data.route);

        //  Weather
        if (data.weather && data.weather.weather){
            const condition = data.weather.weather[0].description;
            const temp = data.weather.main.temp;

            alert(`Weather:\n${condition}, ${temp}°C`);
        }

        // Safety
        if (data.safety_score !== undefined){
            alert(`Safety Score: ${data.safety_score.toFixed(2)}`);
        }

    } catch (err) {
        console.error("Error:", err);
        alert("Something went wrong");
    }
}