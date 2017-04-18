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
smoke.boot = function(eeMapId, eeToken, boundaries, totalPM, provincial, timeseries) {
  // Load external libraries.
  google.load('visualization', '1.0');
  google.load('jquery', '1');
  google.load('maps', '3', {
      other_params: 'key=AIzaSyA2nsOVX-475AWtyU0xVIIj9wZKPIzQinI&libraries=drawing',
      callback: function(){}
  });

  // Create the Trendy Lights app.
  google.setOnLoadCallback(function() {
    var mapType = smoke.App.getEeMapType(JSON.parse(eeMapId)[3], JSON.parse(eeToken)[3]);
    var app = new smoke.App(mapType, JSON.parse(boundaries));
    
    // set the timesereies values for the chart
    smoke.App.total_PM = JSON.parse(totalPM).toFixed(2);
    smoke.App.provincial = JSON.parse(provincial);
    smoke.App.timeseries = JSON.parse(timeseries);

    // save the map layers
    smoke.App.mapids = JSON.parse(eeMapId);
    smoke.App.tokens = JSON.parse(eeToken);

  });
};


///////////////////////////////////////////////////////////////////////////////
//                               The application.                            //
///////////////////////////////////////////////////////////////////////////////



/**
 * The main application.
 * This constructor renders the UI and sets up event handling.
 */
smoke.App = function(mapType, boundaries) {
  // Create and display the map.
  this.map = this.createMap(mapType);

  // Draw boundaries
  this.addBoundaries(boundaries);

  // Add legend
  this.addLegend();

  // Register a click handler to show a panel when user clicks a source region
  this.map.data.addListener('mouseover', this.handlePolygonHover.bind(this));
  this.map.data.addListener('mouseout', this.handlePolygonOut.bind(this));

  // Draw hidden details panel
  $('.detailstab').click(this.handlePanelExpand.bind(this));

  // Shows chart with total PM from different regions.
  //this.map.data.addListener('click', this.handlePolygonClick.bind(this));

  // Register a click handler to hide panel
  $('.panel .close').click(this.hidePanel.bind(this));

  // Adds tab for scenario panel
  $('.scenariotab').click(this.handleScenarioExpand.bind(this));
  $('.scenarioUI .close').click(this.hideScenario.bind(this));

  // Changes receptor or year based on UI
  $('#get').click(this.newScenario.bind(this));

  // layer UI: landcover toggle
  $('#landcover').click(this.handleLayerClick.bind(this, "LANDCOVER"));

  // layer UI: emissions toggle
  $('#emissions').click(this.handleLayerClick.bind(this, "EMISSIONS"));

  // layer UI: GEOS-Chem toggle
  $('#geoschem').click(this.handleLayerClick.bind(this, "GEOSCHEM"));
  $('#sensitivity').click(this.handleLayerSwitchClick.bind(this, "GEOSCHEM"));
  $('#PM').click(this.handleLayerSwitchClick.bind(this, "GEOSCHEM"));

  // layer UI: population density toggle
  $('#population').click(this.handleLayerClick.bind(this, "POPULATION"));

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
 * Add boundaries to map
 */
smoke.App.prototype.addBoundaries = function(regions) {
  regions.forEach((function(region) {
    //this.map.data.addGeoJson(region);
    this.map.data.loadGeoJson('static/regions/' + region + '.json');
  }).bind(this));
  this.map.data.setStyle(function(feature) {
      return {
          'strokeWeight': 5,
          'fillOpacity': 0.0,
          'fillColor': 'red',
          'strokeColor': 'red',
          'strokeOpacity': 0.0
      };
  });
};


/** 
 * Handles a click on a source region. 
 */
smoke.App.prototype.handlePolygonHover = function(event) {
    var feature = event.feature;

    // Highlight region
    this.map.data.overrideStyle(feature, {
        strokeOpacity: 0.6
    });
};

/** 
 * Handles a click on a source region. 
 */
smoke.App.prototype.handlePolygonOut = function(event) {
    this.map.data.revertStyle();
};

/**
 * Handles a click
 */
smoke.App.prototype.handlePolygonClick = function(event) {
    this.clear();
    var feature = event.feature;

    // Highlight the polygon and show the chart
    this.map.data.overrideStyle(feature, {
        strokeOpacity: 0.6,
    });

    $('.panel').show();
    this.drawChart();
    //var title = feature.getProperty('title');
    //$('.panel').show();
    //$('.panel .title').show().text(title);

    // Load and show details about region
    //var id = feature.getPRoperty('id');

};

/** 
 * Draws panel in hidden state
 */
smoke.App.prototype.handlePanelExpand = function(event) {
    $('.detailstab').hide();
    $('.panel').show();
    $('.panel .title').show().text('Total PM = ' + smoke.App.total_PM + ' ug/m^3');
    this.drawTimeSeries();
    this.drawSourcePie();
}

/** 
 * Draws panel in hidden state
 */
smoke.App.prototype.handleScenarioExpand = function(event) {
    $('.scenariotab').hide();
    $('.scenarioUI').show();
}

/** 
 * Draws panel in hidden state
 */
smoke.App.prototype.hideScenario = function(event) {
    $('.scenarioUI').hide();
    $('.scenariotab').show();
}

/** 
 * Adds a chart to map showing total PM at receptor site
 * and contribution from various regions.
 */
smoke.App.prototype.drawSourcePie = function() {
  // Add chart that shows contribution from each region
    console.info(smoke.App.provincial)
    var summaryData = google.visualization.arrayToDataTable(smoke.App.provincial, true);
       
    var wrapper = new google.visualization.ChartWrapper({
      chartType: 'PieChart',
      dataTable: summaryData,
      options: {
        title: 'Contribution from each province'
      }
    });

  var chartEl = $('.sourcePie').get(0);
    wrapper.setContainerId(chartEl);
    wrapper.draw();
};

/** 
 * Adds a chart to map showing total PM at receptor site
 * and contribution from various regions.
 */
smoke.App.prototype.drawTimeSeries = function() {
  // Add chart that shows contribution from each region
    var summaryData = google.visualization.arrayToDataTable(smoke.App.timeseries, true);
    summaryData.insertColumn(0, 'string');
    summaryData.setValue(0, 0, 'Jan');
    summaryData.setValue(1, 0, 'Feb');
    summaryData.setValue(2, 0, 'Mar');
    summaryData.setValue(3, 0, 'Apr');
    summaryData.setValue(4, 0, 'May');
    summaryData.setValue(5, 0, 'Jun');
    summaryData.setValue(6, 0, 'Jul');
    summaryData.setValue(7, 0, 'Aug');
    summaryData.setValue(8, 0, 'Sep');
    summaryData.setValue(9, 0, 'Oct');
    summaryData.setValue(10, 0, 'Nov');
    summaryData.setValue(11, 0, 'Dec');
       
    summaryData.removeColumn(1); 

    var wrapper = new google.visualization.ChartWrapper({
      chartType: 'LineChart',
      dataTable: summaryData,
      options: {
        title: 'Population weighted exposure',
        legend: { position: 'none'}
      }
    });

  var chartEl = $('.receptorTimeSeries').get(0);
    wrapper.setContainerId(chartEl);
    wrapper.draw();
};

/**
 * Hides panel
 */
smoke.App.prototype.hidePanel = function() { 
    $('.panel').hide();
    $('.detailstab').show();
};


/** 
 * Clears panel
 */
smoke.App.prototype.clear = function() {
   $('.panel').hide();
};

smoke.App.prototype.newScenario = function() {
    map = this.map;

    $.getJSON(
      '/details',
      {
         receptor: $('#receptor').val(),
         metYear: $('#metYear').val(),
         emissYear: $('#emissYear').val(),
         logging: $('#logging').is(':checked'),
         oilpalm: $('#oilpalm').is(':checked'),
         timber: $('#timber').is(':checked'),
         peatlands: $('#peatlands').is(':checked'),
         conservation: $('#conservation').is(':checked')
      },
      function(data) {
        // Get new maptype
        var mapType = smoke.App.getEeMapType(JSON.parse(data.eeMapId)[3], JSON.parse(data.eeToken)[3]);
        console.info(data.eeMapId);
        console.info(data.totalPM);

        // Set other map values
        smoke.App.mapids = JSON.parse(data.eeMapId);
        smoke.App.tokens = JSON.parse(data.eeToken);

        // Set total PM equal to extracted value
        smoke.App.total_PM = data.totalPM.toFixed(2);
        smoke.App.provincial = JSON.parse(data.provincial);
        smoke.App.timeseries = JSON.parse(data.timeseries);

        // Overlap new map
        mapType.setOpacity(0.4);
    
        // clear old map layers
        map.overlayMapTypes.clear();
    
        // draw new map layer    
        map.overlayMapTypes.push(mapType);

        // Redraw charts
        $('.panel').hide();
        $('.detailstab').show(); 
    });
};

smoke.App.prototype.handleLayerClick = function(layername) {
    // get index of layer in layers array
    var ind = smoke.App.layers.indexOf(layername);
    console.info(smoke.App.layers);

    // if layer is already in array
    if (ind > -1) {
        this.removeLayer(ind);
        smoke.App.layers.splice(ind, 1);
    } else {  // layer not in array
        this.addLayer(layername);
        smoke.App.layers.push(layername);
    };
};

smoke.App.prototype.addLayer = function(layername) {
    if (layername == "LANDCOVER") {
        id_index = 0;
        var opacity = 0.8;
    } else if (layername == "EMISSIONS") {
        id_index = 1;
        var opacity = 0.4;
    } else if (layername == "GEOSCHEM") {
        if ($('#sensitivity').is(':checked')) {
            id_index = 2;
        } else {
            id_index = 3;
        }
        var opacity = 0.4;
    } else if (layername == "POPULATION") {
        id_index = 4;
        var opacity = 0.4;
    };

    var mapType = smoke.App.getEeMapType(smoke.App.mapids[id_index], smoke.App.tokens[id_index]);
    mapType.setOpacity(opacity);
    this.map.overlayMapTypes.push(mapType);
};

smoke.App.prototype.removeLayer = function(ind) {
    this.map.overlayMapTypes.removeAt(ind);
};

smoke.App.prototype.handleLayerSwitchClick = function(layername) {
    // remove old layer
    var ind = smoke.App.layers.indexOf(layername);
    console.info(ind);
    console.info(smoke.App.layers);

    // remove old layer only if layer is present, otherwise do nothing
    if (ind > -1) {
        this.removeLayer(ind);
        smoke.App.layers.splice(ind, 1);

        // add new layer
        this.addLayer(layername);
        smoke.App.layers.push(layername);
    };

};

smoke.App.prototype.addLegend = function() {
    var legend = document.getElementById('legend');
    var styles = {
        intact: {name: 'Intact', palette: '#000000'}, 
        degraded: {name: 'Degraded', palette: '#666666'}, 
        nonforest: {name: 'Non-forest', palette: '#fdb751'}, 
        plantation: {name: 'Tree plantation mosaic', palette: '#ff0000'}, 
        established: {name: 'Established plantations', palette: '#800080'}
    };
    for (var landtype in styles) {
          var type = styles[landtype];
          var name = type.name;
          var palette = type.palette;
          var div = document.createElement('div');
          div.innerHTML = '<div style="width:10px; height:10px; float:left; background-color:' + palette + '"></div>' + name
          legend.appendChild(div);
    };
    this.map.controls[google.maps.ControlPosition.LEFT_BOTTOM].push(legend);
};

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

    
/** @type {string} The Earth Engine API URL. */
smoke.App.EE_URL = 'https://earthengine.googleapis.com';


/** @type {number} The default zoom level for the map. */
smoke.App.DEFAULT_ZOOM = 5;


/** @type {Object} The default center of the map. */
smoke.App.DEFAULT_CENTER = {lng: 110.82, lat: 3.35};


smoke.App.total_PM = 0.0;
smoke.App.provincial;
smoke.App.timeseries = 0.0;
smoke.App.mapids;
smoke.App.tokens;
smoke.App.layers = ["GEOSCHEM"];

smoke.App.POPULATION = false;
smoke.App.GEOSCHEM = true;
smoke.App.EMISSIONS = false;
smoke.App.LANDCOVER = false;

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
