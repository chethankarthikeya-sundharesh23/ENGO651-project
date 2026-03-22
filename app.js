var userLat, userLon;
var map = L.map('map').setView([51.0447, -114.0719], 12);

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: 'OpenStreetMap'
}).addTo(map);


// get user location
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

async function sendQuery(){

    const query = document.getElementById("queryInput").value;

    const response = await fetch("http://localhost:8000/ai-query",{
        method:"POST",
        headers:{
        "Content-Type":"application/json"
    },
    body: JSON.stringify({
        query: query
    })
    });

    const data = await response.json();

    const lat = data.lat;
    const lon = data.lon;

    map.setView([lat,lon],14);

    L.marker([lat,lon])
    .addTo(map)
    .bindPopup("Destination")
    .openPopup();

    getRoute(userLat,userLon,lat,lon);

}

async function getRoute(startLat, startLon, endLat, endLon){

    const url = `https://router.project-osrm.org/route/v1/driving/${startLon},${startLat};${endLon},${endLat}?overview=full&geometries=geojson`;

    const response = await fetch(url);
    const data = await response.json();

    const route = data.routes[0].geometry;

    // draw route on map
    L.geoJSON(route, {
        color: 'blue',
        weight: 5
    }).addTo(map);
}