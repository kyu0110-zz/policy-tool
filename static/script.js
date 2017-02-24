// Initialize the Google Map and add our custom layer overlay.
var initialize = function(mapId, token) {
  var myLatLng = new google.maps.LatLng(1.3521, 113.8193);
  var mapOptions = {
    center: myLatLng,
    zoom: 5,
    maxZoom: 10,
    streetViewControl: false
  };

  // Create the base Google Map.
  var map = new google.maps.Map(
      document.getElementById('map'), mapOptions);
};
