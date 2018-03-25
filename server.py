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
import math

import emiss
import health
import land

from google.appengine.api import memcache 

###############################################################################
#                             Web request handlers.                           #
###############################################################################


class MainHandler(webapp2.RequestHandler):
  """A servlet to handle requests to load the main web page."""

  def get(self, path=''):
    """Returns the main web page, populated with EE map."""

    mapIds, tokens, exposure, totalPM, provtotal, mort, totalE = GetMapData('Miriam', 'Singapore', 2006, 2006, False, False, False, False, False)

    print(totalE['bc'])

    print(provtotal)
    # Compute the totals for different provinces.

    template_values = {
        'eeMapId': json.dumps(mapIds),
        'eeToken': json.dumps(tokens),
        'boundaries': json.dumps(REGION_IDS),
        'totalPM' : totalPM['b1'],
        'provincial': json.dumps(provtotal),
        'timeseries': json.dumps(exposure),
        'endeaths': json.dumps(mort[0]),
        'lndeaths': json.dumps(mort[1]),
        'pndeaths': json.dumps(mort[2]),
        'a14deaths': json.dumps(mort[3]),
        'adultdeaths': json.dumps(mort[4]),
        'totalE': json.dumps(totalE)
    }
    template = JINJA2_ENVIRONMENT.get_template('index.html')
    self.response.out.write(template.render(template_values))


class ExportHandler(webapp2.RequestHandler):
    """A servlet to handle requests for image exports."""
    
    def DoPost(self):
        """Kicks off export of an image for the specified year and region.
        HTTP Parameters:
        coordinates: The coordinates of the polygon to export.
        filename: The final filename of the file to create in the user's Drive.
        client_id: The ID of the client (for the Channel API).
        year: The year of the image, in "YYYY" format.
        """

        # Kick off an export runner to start and monitor the EE export task.
        # Note: The work "task" is used by both Earth Engine and App Engine to refer
        # to two different things. "TaskQueue" is an async App Engine service.
        taskqueue.add(url='/details', params={
            'scenario': self.request.get('scenario'),
            'receptor': self.request.get('receptor'),
            'metYear': self.request.get('metYear'),
            'emissYear': self.request.get('emissYear'),
            'logging': self.request.get('logging'),
            'oilpalm': self.request.get('oilpalm'),
            'timber': self.request.get('timber'),
            'peatlands': self.request.get('peatlands'),
            'conservation': self.request.get('conservation')}
            )

class DetailsHandler(webapp2.RequestHandler):
    """A servlet to handle requests from UI."""

    def get(self):
        scenario = self.request.get('scenario')
        receptor = self.request.get('receptor')
        metYear = int(self.request.get('metYear'))
        emissYear = int(self.request.get('emissYear'))
        logging = self.request.get('logging')
        oilpalm = self.request.get('oilpalm')
        timber = self.request.get('timber')
        peatlands = self.request.get('peatlands')
        conservation = self.request.get('conservation')

        print('scenario', scenario)

        print 'Receptor = ' + receptor
        print 'Met year = ' + str(metYear)
        print 'Emissions year = ' + str(emissYear)
        print 'logging = ' + logging
        print 'oil palm = ' + oilpalm
        print 'timber = ' + timber
        print 'peatlands = ' + peatlands 
        print 'conservation = ' + conservation

        # convert to boolean
        if logging == 'true':
            logging_bool = True 
        else:
            logging_bool = False

        if oilpalm == 'true':
            oilpalm_bool = True 
        else:
            oilpalm_bool = False

        if timber == 'true':
            timber_bool = True 
        else:
            timber_bool = False

        if peatlands == 'true':
            peatlands_bool = True 
        else:
            peatlands_bool = False 

        if conservation == 'true':
            conservation_bool = True 
        else:
            conservation_bool = False

        print(logging_bool)

        if receptor in RECEPTORS:

            mapIds, tokens, exposure, totalPM, provtotal, mort, totalE = GetMapData(scenario, receptor, metYear, emissYear, logging_bool, oilpalm_bool, timber_bool, peatlands_bool, conservation_bool)
        else:
            mapIds  = json.dumps({'error': 'Unrecognized receptor site: ' + receptor})
            tokens = json.dumps({'error': 'Unrecognized receptor site: ' + receptor})

        ## Make new map 
        template_values = {
            'eeMapId': json.dumps(mapIds),
            'eeToken': json.dumps(tokens),
            'totalPM': totalPM['b1'],
            'provincial': json.dumps(provtotal),
            'timeseries': json.dumps(exposure),
            'endeaths': json.dumps(mort[0]),
            'lndeaths': json.dumps(mort[1]),
            'pndeaths': json.dumps(mort[2]),
            'a14deaths': json.dumps(mort[3]),
            'adultdeaths': json.dumps(mort[4]),
            'totalE': json.dumps(totalE)
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
    ('/details', DetailsHandler),
    ('/export', ExportHandler)
], debug=True)

        
###############################################################################
#                                   Helpers.                                  #
###############################################################################

def GetMapData(scenario, receptor, metYear, emissYear, logging, oilpalm, timber, peatlands, conservation ):
    """Returns two lists with mapids and tokens of the different map layers"""
    # a list of ids for different layers
    mapIds = []
    tokens = []

    # first layer is land cover
    landcover_mapids, landcover_tokens = land.getLandcoverData()
    mapIds.append(landcover_mapids)
    tokens.append(landcover_tokens)

    # second layer is emissions
    emissions, total_emissions = emiss.getEmissions(scenario, emissYear, metYear, logging, oilpalm, timber, peatlands, conservation)

    if scenario == 'GFED4': 
        scale = 1e9 * 2.592e-6 
    else:
        scale = 1e9 * 2.592e-6 

    print(ee.Image(emissions.first()).bandNames().getInfo())
    emissions_display = ee.Image(ee.ImageCollection(emissions.toList(1, 8)).first()).add(ee.Image(ee.ImageCollection(emissions.toList(1,9)).first())) 
    mapid = GetMapId(emissions_display.select('b1').add(emissions_display.select('b2')).multiply(scale), maxVal=10, maskValue=1e-6, color='FFFFFF, FFFF00, FFC100, FF7700, DE2700, 761200')

    mapIds.append([mapid['mapid']])
    tokens.append([mapid['token']])

    # third layer is sensitivities and pm
    sensitivities = getSensitivity(receptor, metYear)
    meansens = sensitivities.filterDate(str(metYear)+'-07-01', str(metYear)+'-11-01').mean().set('system:footprint', ee.Image(sensitivities.first()).get('system:footprint'))
    print(ee.Image(meansens).bandNames().getInfo())
    mapid = GetMapId(ee.Image(meansens).select('b1').add(meansens.select('b2')).multiply(SCALE_FACTOR*1e3*30*31), maxVal=0.10, maskValue=0.001, color='FFFFFF, FE9CFF, FF00B4, CC00FF, 5F00E5, 0003AE')
    mapIds.append([mapid['mapid']])
    tokens.append([mapid['token']])
    
    # fourth layer is PM
    pm = getMonthlyPM(sensitivities, emissions)

    # get pm exposure for every image
    exposure = getExposureTimeSeries(pm)

    # we only want map for Sept + Oct
    summer_pm = pm.filterDate(str(metYear)+'-07-01', str(metYear)+'-11-01')

    totPM = summer_pm.mean().divide(ee.Image.pixelArea()).multiply(ee.Image(55.5*74*1000*1000)).set('system:footprint', ee.Image(pm.first()).get('system:footprint'))
    annualPM = pm.mean().set('system:footprint', ee.Image(pm.first()).get('system:footprint'))
    mapid = GetMapId(totPM, maxVal=0.05, color='FFFFFF, FE9CFF, FF00B4, CC00FF, 5F00E5, 0003AE')
    mapIds[2].append(mapid['mapid'])
    tokens[2].append(mapid['token'])
    
    ## Compute the total Jun - Nov mean exposure at receptor
    proj = ee.Image(pm.first()).select('b1').projection()
    totalPM = computeTotal(totPM, proj)
    annual_PM = computeTotal(annualPM, proj)

    # get provincial totals
    prov = getProvinceBoundaries()
    provtotal = computeRegionalTotal(totPM, prov, proj)

    # fourth layer is health impacts
    pop_img = getPopulationDensity('2010')
    mapid = GetMapId(pop_img, maxVal=1000, color='FFFFFF, a5ffd8, 3cff00, 30ce00, 218b00, 124000')
    mapIds.append([mapid['mapid']])
    tokens.append([mapid['token']])

    baseline_mortality = getBaselineMortality()
    mapid = GetMapId(baseline_mortality, maxVal=1e-2, color='FFFFFF, a5ffd8, 3cff00, 30ce00, 218b00, 124000')
    mapIds[3].append(mapid['mapid'])
    tokens[3].append(mapid['token'])

    print('annual pm {}'.format(annual_PM['b1']))

    earlyneonatal_mortality = health.getAttributableMortality(receptor, annual_PM['b1'], 'earlyneonatal')
    lateneonatal_mortality = health.getAttributableMortality(receptor, annual_PM['b1'], 'lateneonatal')
    postneonatal_mortality = health.getAttributableMortality(receptor, annual_PM['b1'], 'postneonatal')
    age14_mortality = health.getAttributableMortality(receptor, annual_PM['b1'], '1-4')
    adult_mortality = health.getAttributableMortality(receptor, annual_PM['b1'], 'adult')

    attributable_mortality = [earlyneonatal_mortality, lateneonatal_mortality, postneonatal_mortality, age14_mortality, adult_mortality]
    return mapIds, tokens, exposure, totalPM, provtotal, attributable_mortality, total_emissions.getInfo() #ee.Feature(None, {'bc': total_emissions.get('bc')}).getInfo()['properties']


def GetMapId(image, maxVal=0.1, maskValue=0.000000000001, color='FFFFFF, 220066'):
    """Returns the MapID for a given image."""
    mask = image.gt(ee.Image(maskValue)).int()
    maskedImage = image.updateMask(mask)

    return maskedImage.getMapId({
        'min': '0',
        'max': str(maxVal),
        'format': 'png',
        'palette': color,
        })

def getSensitivity(receptor, year, monthly=True):
    """Gets sensitivity for a particular receptor and meteorological year."""
    if monthly:
        sensitivities = ee.ImageCollection('projects/IndonesiaPolicyTool/'+receptor+'_monthly_sensitivities').filterDate(str(year)+'-01-01', str(year)+'-12-31').sort('system:time_start', True) # sort in ascending order
        def divide_by_days(image):
            ndays = ee.Number(image.get('ndays'))
            date = image.get('system:time_start')
            footprint = image.get('system:footprint')
            newimage = image.multiply(ee.Image(ee.Number(1.0).divide(ndays).divide(ndays))).set('system:time_start', date).set('system:footprint', footprint)
            return ee.Image(newimage)

        return ee.ImageCollection(sensitivities.map(divide_by_days));
    else:
        sensitivities = ee.ImageCollection('projects/IndonesiaPolicyTool/'+receptor+'_sensitivities').filterDate(str(year)+'-01-01', str(year)+'-12-31')
        return sensitivities


def getDailyPM(sensitivities):
    """Returns daily PM."""

    # get emissions
    emiss = ee.Image(0)

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
    mask = ee.Image('projects/IndonesiaPolicyTool/logging_concessions')
    print(mask.projection().nominalScale().getInfo())

    print("sensitivities nominal scale")
    print(ee.Image(sensitivities.first()).projection().nominalScale().getInfo())
    print(ee.Image(emiss.first()).projection().nominalScale().getInfo())
   
    # aggregate emissions to coarser grid
    grid = ee.FeatureCollection('ft:10zDDmOTT43LmBdYb8p93Ki6BbdXjQDLzdi01aF43')

    prj = ee.Image(sensitivities.first()).projection()
    def aggregate_image(image):
        regridded = image.reduceRegions(collection=grid, reducer=ee.Reducer.mean().unweighted(), scale=image.projection().nominalScale())
        b1 = regridded.reduceToImage(properties=ee.List(['b1']), reducer=ee.Reducer.mean().unweighted()).rename(['b1']).reproject(crs=prj, scale=prj.nominalScale())
        b2 = regridded.reduceToImage(properties=ee.List(['b2']), reducer=ee.Reducer.mean().unweighted()).rename(['b2']).reproject(crs=prj, scale=prj.nominalScale())
        regridded_image = b1.addBands(b2)
        return regridded_image

    coarse_data = emiss.map(aggregate_image)
    print(ee.Image(coarse_data.first()).projection().nominalScale().getInfo())

    # compute total emissions
    def sum_collection(image, first):
        return ee.Image(first).add(ee.Image(image))

    total_emissions = ee.Image(emiss.iterate(sum_collection, ee.Image(0))).multiply(ee.Image.pixelArea()).reduceRegion(reducer=ee.Reducer.sum().unweighted(), geometry=ee.Geometry.Rectangle([90,-20,150,10]), scale=ee.Image(emiss.first()).projection().nominalScale(), maxPixels=1e9)
    print("fine total emissions: {}".format(total_emissions.getInfo()))
    
    total_emissions = ee.Image(coarse_data.iterate(sum_collection, ee.Image(0))).multiply(ee.Image.pixelArea()).reduceRegion(reducer=ee.Reducer.sum().unweighted(), geometry=ee.Geometry.Rectangle([90,-20,150,10]), scale=prj.nominalScale(), maxPixels=1e9)
    print("coarse total emissions: {}".format(total_emissions.getInfo()))
    combined_data = sensitivities.toList(12).zip(coarse_data.toList(12))

    def computePM(data):
        sensitivity = ee.Image(ee.List(data).get(0))
        emission = ee.Image(ee.List(data).get(1))
        pm_philic = sensitivity.select('b1').multiply(emission.select('b1')).multiply(ee.Image(SCALE_FACTOR)).multiply(ee.Image.pixelArea())
        pm_phobic = sensitivity.select('b2').multiply(emission.select('b2')).multiply(ee.Image(SCALE_FACTOR)).multiply(ee.Image.pixelArea())
        return pm_philic.add(pm_phobic).set('system:footprint', sensitivity.get('system:footprint')).set('system:time_start', sensitivity.get('system:time_start'))

    # iterate over all files
    monthly_pm = combined_data.map(computePM)

    return ee.ImageCollection(ee.List(monthly_pm))
    #return monthly_pm


def getExposureTimeSeries(imageCollection):
    """Computes the exposure at receptor site"""

    def sumRegion(image):
        PM_at_receptor = image.reduceRegion(reducer=ee.Reducer.sum().unweighted())
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
    totalValue = image.reduceRegion(reducer=ee.Reducer.sum().unweighted(), maxPixels=1e9, crs=projection)

    return ee.Feature(None, {'b1': totalValue.get('b1')}).getInfo()['properties']


def computeRegionalTotal(image, regions, projection):
    """Computes the provincial totals"""
    provincialTotals = image.reduceRegions(regions, reducer=ee.Reducer.sum().unweighted(), crs=projection)

    # remove unncessary info
    def strip(feature):
        return ee.Feature(None, {'province': ee.Feature(feature).get('NAME_1'), 
                'regional': ee.Feature(feature).get('sum')})

    stripped_totals = provincialTotals.map(strip).getInfo()
    
    # extract the totals and only return that
    def getVal(feature):
        return [feature['properties']['province'], feature['properties']['regional']]

    return map(getVal, stripped_totals['features'])
    #return ee.Dictionary(provincialTotals.iterate(getVal, ee.Dictionary({})))

def getProvinceBoundaries():
    """Get boundaries for the provinces"""
    #fc = ee.FeatureCollection('ft:1lhjVcyhalgraQMwtlvGdaGj26b9VlrJYZy8ju0WO')
    fc = ee.FeatureCollection('ft:19JY_hNX1c_zk7UVlt4LC8cj7Qv3wKqnKJHN84wWs')

    #def simplify(feature):
    #    return feature.simplify(1000)

    return fc
    #return fc.getInfo()

def getBaselineMortality():
    img = ee.Image('projects/IndonesiaPolicyTool/GPW2005').select('b13')
    return img


def getPopulationDensity(year):
    #img = ee.Image(POPULATION_DENSITY_COLLECTION_ID + '/' + year).select('population-density')
    img = ee.Image('projects/IndonesiaPolicyTool/GPW2005').select('b1')
    return img

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
