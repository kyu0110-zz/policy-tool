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
    mapid = getSensitivity('Malaysia', 2009)
    #mapid = GetMainMapId()
    print(mapid)
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
            content = getSensitivity(receptor, metYear)
        else:
            content = json.dumps({'error': 'Unrecognized receptor site: ' + receptor})

        print(content)

        ## Make new map 
        template_values = {
            'eeMapId': content['mapid'],
            'eeToken': content['token']
        }
        print template_values
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


def GetMainMapId():
  """Returns the MapID for the population density for mean over entire dataset."""
  collection = ee.ImageCollection(IMAGE_COLLECTION_ID).select('population-density')

  reference = collection.filterDate('2000-01-01', '2017-01-01').sort('system:time_start', False)
  #year = reference.first()

    #mean = reference.mean()

  return reference.getMapId({
      'min': '0',
      'max': '500',
      'bands': 'population-density',
      'format': 'png',
      'palette': 'FFFFFF, 220066',
      })


def getSensitivity(receptor, year):
    """Returns adjoint sensitivity."""
    img = ee.Image('users/karenyu/'+receptor+'/'+str(year)+'0101_hydrophilic').select('b1')

    return img.getMapId({
        'min': '0',
        'max': '0.001',
        'bands': 'b1',
        'format': 'png',
        'palette': 'FFFFFF, 220066',
        })


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


def compute_exposure(emissions_philic, emissions_phobic, sensitivity):
    """Computes the PM2.5 exposure given emissions and sensitivity"""

    for d in range(0,num_days):
        # if last day
        if d == num_days - 1:
            prev_sensitivity_philic = 0 #read data
            prev_sensitivity_phobic = 0 #read data
            daily_sensitivity_philic = prev_sensitivity_philic
            daily_sensitivity_phobic = prev_sensitivity_phobic
        else:
            prev_sensitivity_philic = 0#read data
            prev_sensitiity_phobic = 0#read data
            pres_sensitivity_philic = 0#read data
            pres_sensitivity_phobic = 0#read data
            daily_sensitivity_philic = prev_sensitivity_philic - pres_sensitivity_philic
            daily_sensitivity_phobic = prev_sensitivity_phobic - pres_sensitivity_phobic

        # calculate daily contribution as sensitivity * emissions
        cost_function[:,:,n] = cost_function[:,:,n] + daily_sensitivity_philic * emissions_philic
        cost_function[:,:,n] = cost_function[:,:,n] + daily_sensitivity_phobic * emissions_phobic

    # sum up daily for monthly
    return np.sum(cost_function, axis=2)





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
SENS_YEAR = 2009

AVERAGE_EXP = 1

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
