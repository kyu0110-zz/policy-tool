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
    pm = getMonthlyPM('Malaysia', 2008)

    # get pm exposure for every image
    exposure = getExposureTimeSeries(pm)

    totPM = pm.sum().set('system:footprint', ee.Image(pm.first()).get('system:footprint'))
    mapid = GetMapId(totPM)

    # Compute the totals for different provinces.

    template_values = {
        'eeMapId': mapid['mapid'],
        'eeToken': mapid['token'],
        'boundaries': json.dumps(REGION_IDS),
        'timeseries': json.dumps(exposure)
    }
    template = JINJA2_ENVIRONMENT.get_template('index.html')
    self.response.out.write(template.render(template_values))


class LayerHandler(webapp2.RequestHandler):
    """A servlet to handle requests for different map layers."""

    def get(self):
        landcover = self.request.get('landcover')
        emissions = self.request.get('emissions')
        geoschem = self.request.get('geoschem')
        population = self.request.get('population')

        print('Landcover = ' + landcover)
        print('Emissions = ' + emissions)
        print('geoschem = ' + geoschem)
        print('population = ' + population)

        if landcover == 'true':
            # add landcover layer to map
            landcover_img = getLandcoverData()

        if emissions == 'true':
            # add emissions layer to map
            emissions_img = getEmissions()

        if geoschem == 'true':
            # add geoschem layer to map
            geoschem_img =getMonthlyPM('Malaysia', '2006')

        if population == 'true':
            # add population density layer to map
            pop_img = getPopulationDensity('2010')

        template_values = {
        'eeMapId': pop_img['mapid'],
        'eeToken': pop_img['token'],
        }
        self.response.out.write(json.dumps(template_values))


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
            pm = getMonthlyPM(receptor, metYear)
            exposure = getExposureTimeSeries(pm)
            totPM = pm.sum().set('system:footprint', ee.Image(pm.first()).get('system:footprint'))
            content = GetMapId(totPM)
        else:
            content = json.dumps({'error': 'Unrecognized receptor site: ' + receptor})

        print(content)

        ## Compute the total
        proj = ee.Image(pm.first()).select('b1').projection()
        totalPM = computeTotal(totPM, proj)

        ## Make new map 
        template_values = {
            'eeMapId': content['mapid'],
            'eeToken': content['token'],
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
    ('/layers', LayerHandler),
    ('/details', DetailsHandler)
], debug=True)


        
###############################################################################
#                                   Helpers.                                  #
###############################################################################


def GetMapId(image, maskValue=0.000000000001):
    """Returns the MapID for a given image."""
    mask = image.gt(ee.Image(maskValue)).int()
    maskedImage = image.updateMask(mask)

    return maskedImage.getMapId({
        'min': '0',
        'max': '0.01',
        'bands': 'b1',
        'format': 'png',
        'palette': 'FFFFFF, 220066',
        })


def changeLayers():
    """Updates layers based on input from UI"""
    return 0


def getLandcoverData():
    return 0

def getEmissions():
    return 0

def getDailyPM(receptor, year):
    """Returns daily PM."""
    sensitivities = ee.ImageCollection('users/karenyu/'+receptor+'_sensitivities').filterDate(str(year)+'-01-01', str(year)+'-12-31')

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



def getMonthlyPM(receptor, year):
    """Returns monthly PM"""
    sensitivities = ee.ImageCollection('users/karenyu/'+receptor+'_monthly_sensitivities').filterDate(str(year)+'-01-01', str(year)+'-12-31').sort('system:time_start', True) # sort in ascending order

    # get emissions
    emiss = ee.Image('users/karenyu/placeholder_emissions')

    first = ee.List([])

    def computePM(sensitivity, pm_values):
        pm_philic = sensitivity.select('b1').multiply(emiss.select('b1'))
        pm_phobic = sensitivity.select('b2').multiply(emiss.select('b2'))
        return ee.List(pm_values).add(pm_philic.add(pm_phobic).set('system:footprint', sensitivity.get('system:footprint')))

    # iterate over all files
    monthly_pm = sensitivities.iterate(computePM, first)

    return ee.ImageCollection(ee.List(monthly_pm))


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
