var map = L.map('map').setView([51.0447, -114.0719], 12);

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: 'OpenStreetMap'
}).addTo(map);


// get user location
if (navigator.geolocation) {

    navigator.geolocation.getCurrentPosition(function(position){

        var lat = position.coords.latitude;
        var lon = position.coords.longitude;

        map.setView([lat, lon], 14);

        L.marker([lat, lon])
        .addTo(map)
        .bindPopup("You are here")
        .openPopup();

    });

}