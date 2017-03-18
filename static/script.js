/**
 * @fileoverview Runs the Trendy Lights application. The code is executed in the
 * user's browser. It communicates with the App Engine backend, renders output
 * to the screen, and handles user interactions.
 */


smoke = {};  // Our namespace.


/**
 * Starts the Trendy Lights application. The main entry point for the app.
 * @param {string} eeMapId The Earth Engine map ID.
 * @param {string} eeToken The Earth Engine map token.
 * @param {string} serializedPolygonIds A serialized array of the IDs of the
 *     polygons to show on the map. For example: "['poland', 'moldova']".
 */
smoke.boot = function(eeMapId, eeToken) {
  // Load external libraries.
  google.load('visualization', '1.0');
  google.load('jquery', '1');
  google.load('maps', '3', {
      other_params: 'key=AIzaSyA2nsOVX-475AWtyU0xVIIj9wZKPIzQinI&libraries=drawing',
      callback: function(){}
  });

  // Create the Trendy Lights app.
  google.setOnLoadCallback(function() {
    var mapType = smoke.App.getEeMapType(eeMapId, eeToken);
    var app = new smoke.App(mapType);
  });
};


///////////////////////////////////////////////////////////////////////////////
//                               The application.                            //
///////////////////////////////////////////////////////////////////////////////



/**
 * The main application.
 * This constructor renders the UI and sets up event handling.
 */
smoke.App = function(mapType, eeMapId, eeToken) {
  // Create and display the map.
  this.map = this.createMap(mapType);

  // Shows chart with total PM from different regions.
  this.drawChart();

  // Changes receptor or year based on UI
  this.getReceptor(this.map); 


  // Register a click handler 
  //var controlUI = 
  // add menu to the map
  //this.addUI(this.map);

};


/**
 * Creates a Google Map with default receptor and PM contribution
 * overlaid.  
  */
smoke.App.prototype.createMap = function(mapType) {
  var mapOptions = {
    backgroundColor: '#FFFFFF',
    center: smoke.App.DEFAULT_CENTER,
    disableDefaultUI: true, 
    zoom: smoke.App.DEFAULT_ZOOM
  };
  var mapEl = $('.map').get(0);
  var map = new google.maps.Map(mapEl, mapOptions);

  map.setOptions({styles: smoke.App.BLACK_BASE_MAP_STYLES});
  mapType.setOpacity(0.4);
  map.overlayMapTypes.push(mapType);
  return map;
};


/** 
 * Adds a chart to map showing total PM at receptor site
 * and contribution from various regions.
 */
smoke.App.prototype.addChart = function(){
  
}


/** 
 * Adds a menu to the left side
 */
smoke.App.prototype.addUI = function(map) {
    var drawingManager = new google.maps.drawing.DrawingManager({
    drawingMode: google.maps.drawing.OverlayType.RECTANGLE,
    drawingControl: true
  });
  drawingManager.setMap(map);

   var rectangle = null;

   google.maps.event.addListener(
           drawingManager, 'overlaycomplete', function(event) {
               rectangle = event.overlay;
               drawingManager.setOptions({drawingMode: null});
           });

};

///////////////////////////////////////////////////////////////////////////////
//                        Static helpers and constants.                      //
///////////////////////////////////////////////////////////////////////////////


/**
 * Generates a Google Maps map type (or layer) for the passed-in EE map id. See:
 * https://developers.google.com/maps/documentation/javascript/maptypes#ImageMapTypes
 * @param {string} eeMapId The Earth Engine map ID.
 * @param {string} eeToken The Earth Engine map token.
 * @return {google.maps.ImageMapType} A Google Maps ImageMapType object for the
 *     EE map with the given ID and token.
 */
smoke.App.getEeMapType = function(eeMapId, eeToken) {
  var eeMapOptions = {
    getTileUrl: function(tile, zoom) {
      var url = smoke.App.EE_URL + '/map/';
      url += [eeMapId, zoom, tile.x, tile.y].join('/');
      url += '?token=' + eeToken;
      return url;
    },
    tileSize: new google.maps.Size(256, 256)
  };
  return new google.maps.ImageMapType(eeMapOptions);
};

smoke.App.prototype.drawChart = function() {
  // Add chart that shows contribution from each region
    var summaryData = google.visualization.arrayToDataTable([
               ['Province', 'Contribution'],
               ['Jambi', 10],
               ['South Sumatra', 4],
               ['West Kalimantan', 6],
               ['Central Kalimantan', 2],
               ['Other',  1]
    ]);
        
    var wrapper = new google.visualization.ChartWrapper({
      chartType: 'PieChart',
      dataTable: summaryData,
      options: {
        title: 'Contribution from each province'
      }
    });

  var chartEl = $('.chart').get(0);
    wrapper.setContainerId(chartEl);
    wrapper.draw();
};

    
smoke.App.prototype.getReceptor = function(map) {
  $('#get').click(function() {
    $.getJSON(
      '/details',
      {
         receptor: $('#receptor').val(),
         metYear: $('#metYear').val(),
         emissYear: $('#emissYear').val()
      },
      function(data) {
        // clear old map layers
        map.overlayMapTypes.clear();

        // Get new maptype
        var mapType = smoke.App.getEeMapType(data.eeMapId, data.eeToken);
      
        console.info(data.eeMapId);
        console.info(data.totalPM);

        // Overlap new map
        mapType.setOpacity(0.3);
        map.overlayMapTypes.push(mapType);


    });
  });
};

/** @type {string} The Earth Engine API URL. */
smoke.App.EE_URL = 'https://earthengine.googleapis.com';


/** @type {number} The default zoom level for the map. */
smoke.App.DEFAULT_ZOOM = 5;


/** @type {Object} The default center of the map. */
smoke.App.DEFAULT_CENTER = {lng: 110.82, lat: 3.35};


/**
 * @type {Array} An array of Google Map styles. See:
 *     https://developers.google.com/maps/documentation/javascript/styling
 */
smoke.App.BLACK_BASE_MAP_STYLES = [
  {stylers: [{lightness: 0}]},
  { 
      featureType: 'road',
      stylers: [{visibility: 'off'}]
  },
  {
      featureType: 'landscape',
      elementType: 'geometry.fill', 
      stylers: [{color: '#FFFFFF'}]
  },
  {
      featureType: 'poi.park',
      elementType: 'geometry.fill',
      stylers: [{color: '#FFFFFF'}]
  }
];