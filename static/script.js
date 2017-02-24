// Wrap our code in a self-executing anonymous function to isolate scope.
(function() {

  // Our Google map.
  var map;

  $(document).ready(function() {
    // Create the base Google Map.
    map = new google.maps.Map($('.map').get(0), {
          center: { lat: 1.3521, lng: 110.8193},
          zoom: 5
        });
  });
})();
