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
    pm = getSensitivity('Malaysia', 2008)
    mapid = GetMapId(pm)

    # Compute the totals for different provinces. 

    template_values = {
        'eeMapId': mapid['mapid'],
        'eeToken': mapid['token']
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
            pm = getSensitivity(receptor, metYear)
            content = GetMapId(pm)
        else:
            content = json.dumps({'error': 'Unrecognized receptor site: ' + receptor})

        print(content)

        ## Compute the total 
        totalPM = computeTotal(pm)

        ## Make new map 
        template_values = {
            'eeMapId': content['mapid'],
            'eeToken': content['token'],
            'totalPM': totalPM['b1']

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


def getSensitivity(receptor, year):
    """Returns adjoint sensitivity."""
    sensitivities = ee.ImageCollection('users/karenyu/'+receptor+'_sensitivities').sort('system:time_start', False).toList(31)

    # get emissions
    emiss = ee.Image('users/karenyu/placeholder_emissions')

    # iterate over sensitivity files
    sensitivity = ee.Image(sensitivities.get(0))
    pm_philic = ee.Image(0).select([0], ['b1'])
    pm_phobic = ee.Image(0).select([0], ['b2'])
    for i in range(1,31):
        next_sensitivity = ee.Image(sensitivities.get(i))
        daily_sensitivity_philic = sensitivity.select('b1').subtract(next_sensitivity.select('b1'))
        daily_sensitivity_phobic = sensitivity.select('b2').subtract(next_sensitivity.select('b2'))
        pm_philic = pm_philic.add(daily_sensitivity_philic.multiply(emiss.select('b1')))
        pm_phobic = pm_phobic.add(daily_sensitivity_phobic.multiply(emiss.select('b2')))

    # multiply emissions
    pm = pm_philic.add(pm_phobic)

    return pm



def computeTotal(image):
    """Computes total over a specific region"""
    totalValue = image.reduceRegion(reducer=ee.Reducer.sum(), maxPixels=1e9)

    return ee.Feature(None, {'b1': totalValue.get('b1')}).getInfo()['properties']

def getPopulationDensity(year):
    img = ee.Image(IMAGE_COLLECTION_ID + '/' + year).select('population-density')

    return reference.getMapId({
        'min': '0',
        'max': '500',
        'bands': 'population-density',
        'format': 'png',
        'palette': 'FFFFFF, 220066',
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

# The ImageCollection of the night-time lights dataset. See:
# https://earthengine.google.org/#detail/NOAA%2FDMSP-OLS%2FNIGHTTIME_LIGHTS
IMAGE_COLLECTION_ID = 'users/karenyu/philic'
#IMAGE_COLLECTION_ID = 'CIESIN/GPWv4/unwpp-adjusted-population-density'


# Receptor sites
RECEPTORS = ['Singapore', 'Malaysia', 'Indonesia', 'Population_weighted_SEAsia']
DEFAULT_RECEPTOR = 'Population_weighted_SEAsia'

# CHOOSE YEAR
SENS_YEAR = 2008

AVERAGE_EXP = 1

SCALE_FACTOR = 1.0 / (24.0 * 24.0 * 3.0)

###############################################################################
#                               Initialization.                               #
###############################################################################


# Use our App Engine service account's credentials.
EE_CREDENTIALS = ee.ServiceAccountCredentials(
    config.EE_ACCOUNT, config.EE_PRIVATE_KEY_FILE)

# Create the Jinja templating system we use to dynamically generate HTML. See:
# http://jinja.pocoo.org/docs/dev/
JINJA2_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    autoescape=True,
    extensions=['jinja2.ext.autoescape'])

# Initialize the EE API.
ee.Initialize(EE_CREDENTIALS)