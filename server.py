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
    mapid = GetMainMapId()
    template_values = {
        'eeMapId': mapid['mapid'],
        'eeToken': mapid['token']
    }
    template = JINJA2_ENVIRONMENT.get_template('index.html')
    self.response.out.write(template.render(template_values))


# Define webapp2 routing from URL paths to web request handlers. See:
# http://webapp-improved.appspot.com/tutorials/quickstart.html
app = webapp2.WSGIApplication([
    ('/', MainHandler)
])


###############################################################################
#                                   Helpers.                                  #
###############################################################################


def GetMainMapId():
  """Returns the MapID for the night-time lights trend map."""
  collection = ee.ImageCollection(IMAGE_COLLECTION_ID).select('population-density')

  reference = collection.filterDate('2000-01-01', '2017-01-01').sort('system:time_start', False)
  mean = reference.mean()

  return mean.getMapId({
      'min': '0',
      'max': '500',
      'bands': 'population-density',
      'format': 'png',
      'palette': 'FFFFFF, 220066',
      })

###############################################################################
#                                   Constants.                                #
###############################################################################


# Memcache is used to avoid exceeding our EE quota. Entries in the cache expire
# 24 hours after they are added. See:
# https://cloud.google.com/appengine/docs/python/memcache/
MEMCACHE_EXPIRATION = 60 * 60 * 24

# The ImageCollection of the night-time lights dataset. See:
# https://earthengine.google.org/#detail/NOAA%2FDMSP-OLS%2FNIGHTTIME_LIGHTS
IMAGE_COLLECTION_ID = 'CIESIN/GPWv4/unwpp-adjusted-population-density'

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
