#!/usr/bin/env python
""" Web server

Code runs on Google App Engine. Sends requests to GAE when page loads and 
based on user clicks. Info from GAE is then passed to browser to be executed by
javascript. Uses Jinja2 templating engine to pass info to browser. 
"""

import json
import os

import config
import ee               # earth engine API
import jinja2           # templating engine
import webapp2

from google.appengine.api import memcache 


###############################################################################
#                             Web request handlers.                           #
###############################################################################


class MainHandler(webapp2.RequestHandler):
  """A servlet to handle requests to load the main web page."""

  def get(self, path=''):
    """Returns the main web page, populated with EE map."""

    mapIds, tokens, exposure, totalPM = GetMapData('Malaysia', 2008, 2008)

    print(mapIds)

    # Compute the totals for different provinces.

    template_values = {
        'eeMapId': json.dumps(mapIds),
        'eeToken': json.dumps(tokens),
        'boundaries': json.dumps(REGION_IDS),
        'totalPM' : totalPM['b1'],
        'timeseries': json.dumps(exposure)
    }
    template = JINJA2_ENVIRONMENT.get_template('index.html')
    self.response.out.write(template.render(template_values))


class DetailsHandler(webapp2.RequestHandler):
    """A servlet to handle requests from UI."""

    def get(self):
        receptor = self.request.get('receptor')
        metYear = self.request.get('metYear')
        emissYear = self.request.get('emissYear')

        print 'Receptor = ' + receptor
        print 'Met year = ' + metYear
        print 'Emissions year = ' + emissYear
        if receptor in RECEPTORS:
            mapIds, tokens, exposure, totalPM = GetMapData(receptor, metYear, emissYear)
        else:
            mapIds  = json.dumps({'error': 'Unrecognized receptor site: ' + receptor})
            tokens = json.dumps({'error': 'Unrecognized receptor site: ' + receptor})

        ## Make new map 
        template_values = {
            'eeMapId': json.dumps(mapIds),
            'eeToken': json.dumps(tokens),
            'totalPM': totalPM['b1'],
            'timeseries': json.dumps(exposure)

        }
        self.response.out.write(json.dumps(template_values))
        #self.response.headers['Content-Type'] = 'application/json'
        #self.response.out.write(content)

        #if self.request.get('rectangle'):
        #    coords = [float(i) for i in self.request.get('rectangle').split(',')]
        #    geometry = ee.FeatureCollection([ee.Feature(
        #        ee.Geometry.Rectangle(coords=coords), {'system:index': '0'}
        #    )])
        #label = ui.Button('Click me!')
        #slider = ui.Slider()

# Define webapp2 routing from URL paths to web request handlers. See:
# http://webapp-improved.appspot.com/tutorials/quickstart.html
app = webapp2.WSGIApplication([
    ('/', MainHandler),
    ('/details', DetailsHandler)
], debug=True)


        
###############################################################################
#                                   Helpers.                                  #
###############################################################################

def GetMapData(receptor, metYear, emissYear):
    """Returns two lists with mapids and tokens of the different map layers"""
    # a list of ids for different layers
    mapIds = []
    tokens = []

    # first layer is land cover
    landcover_img = getLandcoverData()
    mapIds.append(landcover_img['mapid'])
    tokens.append(landcover_img['token'])

    # second layer is emissions
    emissions = getEmissions(emissYear)
    mapid = GetMapId(emissions.mean(), maxVal=5e5, maskValue=1, color='FFFFFF, AA0000')
    mapIds.append(mapid['mapid'])
    tokens.append(mapid['token'])

    # third layer is sensitivities
    sensitivities = getSensitivity(receptor, metYear)
    meansens = sensitivities.mean().set('system:footprint', ee.Image(sensitivities.first()).get('system:footprint'))
    mapid = GetMapId(meansens, maxVal=0.02, maskValue=0.0005)
    mapIds.append(mapid['mapid'])
    tokens.append(mapid['token'])
    
    # fourth layer is PM
    pm = getMonthlyPM(sensitivities, emissions)

    # get pm exposure for every image
    exposure = getExposureTimeSeries(pm)

    # we only want map for Jun - Nov
    summer_pm = pm.filterDate(str(metYear)+'-06-01', str(metYear)+'-11-30')

    totPM = summer_pm.mean().set('system:footprint', ee.Image(pm.first()).get('system:footprint'))
    mapid = GetMapId(totPM, maxVal=1e-5)
    mapIds.append(mapid['mapid'])
    tokens.append(mapid['token'])
    
    ## Compute the total Jun - Nov mean exposure at receptor
    proj = ee.Image(pm.first()).select('b1').projection()
    totalPM = computeTotal(totPM, proj)

    # fifth layer is population
    pop_img = getPopulationDensity('2010')
    mapIds.append(pop_img['mapid'])
    tokens.append(pop_img['token'])

    return mapIds, tokens, exposure, totalPM


def GetMapId(image, maxVal=0.1, maskValue=0.000000000001, color='FFFFFF, 220066'):
    """Returns the MapID for a given image."""
    mask = image.gt(ee.Image(maskValue)).int()
    maskedImage = image.updateMask(mask)

    return maskedImage.getMapId({
        'min': '0',
        'max': str(maxVal),
        'bands': 'b1',
        'format': 'png',
        'palette': color,
        })


def changeLayers():
    """Updates layers based on input from UI"""
    return 0


def getLandcoverData():
    gfcImage = ee.Image('UMD/hansen/global_forest_change_2015').select('treecover2000');
    mask = gfcImage.gt(ee.Image(0.001)).int() 
    maskedImage = gfcImage.updateMask(mask);
    
    return maskedImage.getMapId({
        'min': '0',
        'max': '100', 
        'bands': 'treecover2000',
        'format': 'png',
        'palette': 'FFFFFF, 00AA00'
        })

def getEmissions(year):
    """Gets the dry matter emissions from GFED and converts to oc/bc"""

    monthly_dm = ee.ImageCollection('users/tl2581/gfedv4s').filter(ee.Filter.rangeContains('system:index', 'DM_'+str(year)+'01', 'DM_'+str(year)+'12'))
    #monthly_dm = ee.ImageCollection('users/tl2581/gfedv4s').filterDate('2008-01-01', '2009-01-01').sort('system:time_start', True) 

    # map comes from IAV file
    #monthly_dm = (emissions * map)   # Gg to Tg 

    # function to compute oc and bc emissions from dm
    def get_oc_bc(dm_emissions):
    
        land_types = ['PET', 'DEF', 'AGRI', 'SAV', 'TEMP', 'PLT']
        oc_ef = [2.157739E+23, 2.157739E+23, 2.082954E+23, 1.612156E+23, 1.885199E+23, 1.885199E+23]
        bc_ef = [2.835829E+22, 2.835829E+22, 2.113069E+22, 2.313836E+22, 2.574832E+22, 2.574832E+22]

        total_oc = ee.Image(0).rename(['b1'])
        total_bc = ee.Image(0).rename(['b1'])

        for land_type in range(0, len(land_types)): 
            oc_scale = oc_ef[land_type] * 6.022e-23 * 12  # g OC
            bc_scale = bc_ef[land_type] * 6.022e-23 * 12  # g BC

            oc_fine = dm_emissions.multiply(ee.Image(oc_scale))
            bc_fine = dm_emissions.multiply(ee.Image(bc_scale))

            # interpolate to current grid (is this necessary in earth engine?)

            # sum up the total for each type
            total_oc = total_oc.add(oc_fine)
            total_bc = total_bc.add(bc_fine)

        # split into GEOS-Chem hydrophobic and hydrophilic fractions, convert g to kg
        ocpo = total_oc.multiply(ee.Image(0.5 * 1.0e3 * 2.1 * 10e-9))
        ocpi = total_oc.multiply(ee.Image(0.5 * 1.0e3 * 2.1 * 10e-9))
        bcpo = total_bc.multiply(ee.Image(0.8 * 1.0e3 * 10e-9))
        bcpi = total_bc.multiply(ee.Image(0.2 * 1.0e3 * 10e-9))

        # compute daily averages from the monthly total
        emissions_philic = ocpi.add(bcpi).multiply(ee.Image(1.0/(31.0 * 6.0)))
        emissions_phobic = ocpo.add(bcpo).multiply(ee.Image(1.0/(31.0 * 6.0)))

        return emissions_philic.addBands(emissions_phobic, ['b1']).rename(['b1', 'b2'])

    emissions = monthly_dm.map(get_oc_bc)

    return emissions



def getSensitivity(receptor, year, monthly=True):
    """Gets sensitivity for a particular receptor and meteorological year."""
    if monthly:
        sensitivities = ee.ImageCollection('users/karenyu/'+receptor+'_monthly_sensitivities').filterDate(str(year)+'-01-01', str(year)+'-12-31').sort('system:time_start', True) # sort in ascending order
    else:
        sensitivities = ee.ImageCollection('users/karenyu/'+receptor+'_sensitivities').filterDate(str(year)+'-01-01', str(year)+'-12-31')
    return sensitivities


def getDailyPM(sensitivities):
    """Returns daily PM."""

    # get emissions
    emiss = ee.Image('users/karenyu/placeholder_emissions')

    def computeDailySensitivity(sensitivity, prev_sensitivities):
        # first sum up all previous sensitivities, then subtract from current value
        daily_sensitivity = sensitivity.subtract(ee.ImageCollection(ee.List(prev_sensitivities)).sum())

        # append to list
        return ee.List(prev_sensitivities).add(daily_sensitivity)

    def computePM(sensitivity, pm_values):
        pm_philic = sensitivity.select('b1').multiply(emiss.select('b1'))
        pm_phobic = sensitivity.select('b2').multiply(emiss.select('b2'))
        return ee.List(pm_values).add(pm_philic.add(pm_phobic))

    all_pm = ee.List([])

    # iterate over sensitivity files, month by month then day by day
    for month in range(1,5):
        monthly_sensitivities = sensitivities.filterDate(str(year) + '-' + str(month).zfill(2) + '-01', str(year) + '-' + str(month+1).zfill(2) + '-01').sort('system:time_start', False)

        first = ee.List([ee.Image(monthly_sensitivities.first())])
        #first = ee.List([ee.Image(0).select([0], ['b1']).addBands(ee.Image(0).select([0], ['b2']))])
        daily_sensitivities = ee.ImageCollection(ee.List(ee.ImageCollection(monthly_sensitivities.toList(30, 1)).iterate(computeDailySensitivity, first)))

        first = ee.List([])
        daily_pm = daily_sensitivities.iterate(computePM, first)

        all_pm = all_pm.cat(ee.List(daily_pm))

    return ee.ImageCollection(all_pm)



def getMonthlyPM(sensitivities, emiss):
    """Returns monthly PM"""

    # get emissions
    #emiss = ee.Image('users/karenyu/placeholder_emissions')

    combined_data = sensitivities.toList(12).zip(emiss.toList(12))

    def computePM(data):
        sensitivity = ee.Image(ee.List(data).get(0))
        emission = ee.Image(ee.List(data).get(1))
        pm_philic = sensitivity.select('b1').multiply(emission.select('b1')).multiply(ee.Image(SCALE_FACTOR/31.0))
        pm_phobic = sensitivity.select('b2').multiply(emission.select('b2')).multiply(ee.Image(SCALE_FACTOR/31.0))
        return pm_philic.add(pm_phobic).set('system:footprint', sensitivity.get('system:footprint')).set('system:time_start', sensitivity.get('system:time_start'))

    # iterate over all files
    monthly_pm = combined_data.map(computePM)

    return ee.ImageCollection(ee.List(monthly_pm))
    #return monthly_pm


def getExposureTimeSeries(imageCollection):
    """Computes the exposure at receptor site"""

    def sumRegion(image):
        PM_at_receptor = image.reduceRegion(reducer=ee.Reducer.sum())
        return ee.Feature(None, {'b1': PM_at_receptor.get('b1'),
                                 'index': image.get('system:index')})

    exposure = imageCollection.map(sumRegion).getInfo()

    # extract the values
    def extractSum(feature):
        return [feature['properties']['index'],
                feature['properties']['b1']]

    return map(extractSum, exposure['features'])



def computeTotal(image, projection):
    """Computes total over a specific region"""
    geom = ee.Geometry.Rectangle([-55, -20, 40, 20]);
    totalValue = image.reduceRegion(reducer=ee.Reducer.sum(), maxPixels=1e9, crs=projection)

    return ee.Feature(None, {'b1': totalValue.get('b1')}).getInfo()['properties']


def getProvinceBoundaries():
    """Get boundaries for the provinces"""
    fc = ee.FeatureCollection('ft:1lhjVcyhalgraQMwtlvGdaGj26b9VlrJYZy8ju0WO').first().geometry();
    return fc.getInfo()

def getPopulationDensity(year):
    img = ee.Image(POPULATION_DENSITY_COLLECTION_ID + '/' + year).select('population-density')

    return img.getMapId({
        'min': '0',
        'max': '500',
        'bands': 'population-density',
        'format': 'png',
        'palette': 'FFFFFF, 600020',
        })


def compute_IAV(emissions):
    """Get interannaual variability from GFED4 emissions."""

    return 0


###############################################################################
#                                   Constants.                                #
###############################################################################


# Memcache is used to avoid exceeding our EE quota. Entries in the cache expire
# 24 hours after they are added. See:
# https://cloud.google.com/appengine/docs/python/memcache/
MEMCACHE_EXPIRATION = 60 * 60 * 24

POPULATION_DENSITY_COLLECTION_ID = 'CIESIN/GPWv4/unwpp-adjusted-population-density'
LANDCOVER_COLLECTION_ID = ''

# Receptor sites
RECEPTORS = ['Singapore', 'Malaysia', 'Indonesia', 'Population_weighted_SEAsia']
DEFAULT_RECEPTOR = 'Population_weighted_SEAsia'

# CHOOSE YEAR
SENS_YEAR = 2008

AVERAGE_EXP = 1

SCALE_FACTOR = 1.0 / (24.0 * 24.0 * 3.0)

REGION_PATH = 'static/regions/'

###############################################################################
#                               Initialization.                               #
###############################################################################


# Use our App Engine service account's credentials.
EE_CREDENTIALS = ee.ServiceAccountCredentials(
    config.EE_ACCOUNT, config.EE_PRIVATE_KEY_FILE)

# Read region IDs from the file system
REGION_IDS = [name.replace('.json', '') for name in os.listdir(REGION_PATH)]

# Create the Jinja templating system we use to dynamically generate HTML. See:
# http://jinja.pocoo.org/docs/dev/
JINJA2_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    autoescape=True,
    extensions=['jinja2.ext.autoescape'])

# Initialize the EE API.
ee.Initialize(EE_CREDENTIALS)
