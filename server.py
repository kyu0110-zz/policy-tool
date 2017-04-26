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

from google.appengine.api import memcache 

###############################################################################
#                             Web request handlers.                           #
###############################################################################


class MainHandler(webapp2.RequestHandler):
  """A servlet to handle requests to load the main web page."""

  def get(self, path=''):
    """Returns the main web page, populated with EE map."""

    mapIds, tokens, exposure, totalPM, provtotal, mort = GetMapData('Malaysia', 2008, 2008, False, False, False, False, False)

    print(mapIds)

    print(provtotal)
    # Compute the totals for different provinces.

    template_values = {
        'eeMapId': json.dumps(mapIds),
        'eeToken': json.dumps(tokens),
        'boundaries': json.dumps(REGION_IDS),
        'totalPM' : totalPM['b1'],
        'provincial': json.dumps(provtotal),
        'timeseries': json.dumps(exposure),
        'deaths': json.dumps(mort)
    }
    template = JINJA2_ENVIRONMENT.get_template('index.html')
    self.response.out.write(template.render(template_values))


class DetailsHandler(webapp2.RequestHandler):
    """A servlet to handle requests from UI."""

    def get(self):
        receptor = self.request.get('receptor')
        metYear = self.request.get('metYear')
        emissYear = self.request.get('emissYear')
        logging = self.request.get('logging')
        oilpalm = self.request.get('oilpalm')
        timber = self.request.get('timber')
        peatlands = self.request.get('peatlands')
        conservation = self.request.get('conservation')

        print 'Receptor = ' + receptor
        print 'Met year = ' + metYear
        print 'Emissions year = ' + emissYear
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
            mapIds, tokens, exposure, totalPM, provtotal, mort = GetMapData(receptor, metYear, emissYear, logging_bool, oilpalm_bool, timber_bool, peatlands_bool, conservation_bool)
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
            'deaths': json.dumps(mort)
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

def GetMapData(receptor, metYear, emissYear, logging, oilpalm, timber, peatlands, conservation ):
    """Returns two lists with mapids and tokens of the different map layers"""
    # a list of ids for different layers
    mapIds = []
    tokens = []

    # first layer is land cover
    landcover_mapids, landcover_tokens = getLandcoverData()
    mapIds.append(landcover_mapids)
    tokens.append(landcover_tokens)

    # second layer is emissions
    emissions = getEmissions(emissYear, metYear, logging, oilpalm, timber, peatlands, conservation)
    mapid = GetMapId(emissions.mean().select('b1'), maxVal=5e3, maskValue=1e-3, color='FFFFFF, AA0000')
    mapIds.append([mapid['mapid']])
    tokens.append([mapid['token']])

    # third layer is sensitivities and pm
    sensitivities = getSensitivity(receptor, metYear)
    meansens = sensitivities.filterDate(str(metYear)+'-07-01', str(metYear)+'-11-30').mean().set('system:footprint', ee.Image(sensitivities.first()).get('system:footprint'))
    mapid = GetMapId(meansens.select('b1'), maxVal=0.02, maskValue=0.0005)
    mapIds.append([mapid['mapid']])
    tokens.append([mapid['token']])
    
    # fourth layer is PM
    pm = getMonthlyPM(sensitivities, emissions)

    # get pm exposure for every image
    exposure = getExposureTimeSeries(pm)

    # we only want map for Jul - Nov
    summer_pm = pm.filterDate(str(metYear)+'-07-01', str(metYear)+'-11-30')

    totPM = summer_pm.mean().set('system:footprint', ee.Image(pm.first()).get('system:footprint'))
    mapid = GetMapId(totPM, maxVal=1e-2)
    mapIds[2].append(mapid['mapid'])
    tokens[2].append(mapid['token'])
    
    ## Compute the total Jun - Nov mean exposure at receptor
    proj = ee.Image(pm.first()).select('b1').projection()
    totalPM = computeTotal(totPM, proj)

    # get provincial totals
    prov = getProvinceBoundaries()
    provtotal = computeRegionalTotal(totPM, prov, proj)

    # fourth layer is health impacts
    pop_img = getPopulationDensity('2010')
    mapid = GetMapId(pop_img, maxVal=500, color='FFFFFF, 600020')
    mapIds.append([mapid['mapid']])
    tokens.append([mapid['token']])

    baseline_mortality = getBaselineMortality()
    mapid = GetMapId(baseline_mortality, maxVal=5, color='FFFFFF, 600020')
    mapIds[3].append(mapid['mapid'])
    tokens[3].append(mapid['token'])

    attributable_mortality = getAttributableMortality(baseline_mortality, receptor, totalPM['b1'])

    return mapIds, tokens, exposure, totalPM, provtotal, attributable_mortality


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


def getLandcoverData():
    present = ee.Image('users/karenyu/marHanGfw2005_6classes')
    BAU2010 = ee.Image('users/karenyu/future_LULC_MarHanGFW1')
    BAU2015 = ee.Image('users/karenyu/future_LULC_MarHanGFW2')
    BAU2020 = ee.Image('users/karenyu/future_LULC_MarHanGFW3')
    BAU2025 = ee.Image('users/karenyu/future_LULC_MarHanGFW4')
    BAU2030 = ee.Image('users/karenyu/future_LULC_MarHanGFW5')

    sld_ramp = '<RasterSymbolizer>' + \
          '<ColorMap type="intervals" extended="false" >' + \
                '<ColorMapEntry color="#666666" quantity="1" label="Degraded"/>' + \
                '<ColorMapEntry color="#000000" quantity="2" label="Intact"/>' + \
                '<ColorMapEntry color="#fdb751" quantity="3" label="Non-Forest"/>' + \
                '<ColorMapEntry color="#ff0000" quantity="4" label="Tree Plantation Mosaic"/>' + \
                '<ColorMapEntry color="#800080" quantity="5" label="Old Established Plantations"/>' + \
                '<ColorMapEntry color="#EED2EE" quantity="6" label="New Established Plantations"/>' + \
            '</ColorMap>' + \
        '</RasterSymbolizer>'

    vizParams = { 'min': '0', 'max': '255', 'format': 'png' }

    image = present.updateMask(present).sldStyle(sld_ramp)
    presentMapID = image.getMapId(vizParams)

    image = BAU2010.updateMask(BAU2010).sldStyle(sld_ramp)
    BAU2010MapID = image.getMapId(vizParams)

    image = BAU2015.updateMask(BAU2015).sldStyle(sld_ramp)
    BAU2015MapID = image.getMapId(vizParams) 

    image = BAU2020.updateMask(BAU2020).sldStyle(sld_ramp)
    BAU2020MapID = image.getMapId(vizParams) 

    image = BAU2025.updateMask(BAU2025).sldStyle(sld_ramp)
    BAU2025MapID = image.getMapId(vizParams) 

    image = BAU2030.updateMask(BAU2030).sldStyle(sld_ramp)
    BAU2030MapID = image.getMapId(vizParams)  
   
    mapids = [presentMapID['mapid'], BAU2010MapID['mapid'], BAU2015MapID['mapid'], BAU2020MapID['mapid'], BAU2025MapID['mapid'], BAU2030MapID['mapid']]
    tokens = [presentMapID['token'], BAU2010MapID['token'], BAU2015MapID['token'], BAU2020MapID['token'], BAU2025MapID['token'], BAU2030MapID['token']]
    return mapids, tokens


def getEmissions(year, metYear, logging, oilpalm, timber, peatlands, conservation):
    """Gets the dry matter emissions from GFED and converts to oc/bc"""

    # get either current emissions or future emissions based on year
    if year < 2010:
        monthly_dm = ee.ImageCollection('users/tl2581/gfedv4s').filter(ee.Filter.rangeContains('system:index', 'DM_'+str(year)+'01', 'DM_'+str(year)+'12'))
    else:
        monthly_dm = getFutureEmissions(year, metYear)

    #monthly_dm = ee.ImageCollection('users/tl2581/gfedv4s').filterDate('2008-01-01', '2009-01-01').sort('system:time_start', True) 

    if logging:
        loggingmask = getLogging()
    if oilpalm:
        oilpalmmask = getOilPalm()
    if timber:
        timbermask = getTimber()
    if peatlands:
        peatmask = getPeatlands()
    if conservation:
        conservationmask = getConservation()
    

    # map comes from IAV file
    #monthly_dm = (emissions * map)   # Gg to Tg 

    # function to compute oc and bc emissions from dm
    def get_oc_bc(dm_emissions):
   
        # first mask out data from regions that are turned off
        if logging:
            maskedEmissions = dm_emissions.updateMask(loggingmask)
        else:
            maskedEmissions = dm_emissions

        if oilpalm:
            maskedEmissions = maskedEmissions.updateMask(oilpalmmask)
        if timber:
            maskedEmissions = maskedEmissions.updateMask(timbermask)
        if peatlands:
            maskedEmissions = maskedEmissions.updateMask(peatmask)
        if conservation:
            maskedEmissions = maskedEmissions.updateMask(conservationmask)

        land_types = ['PET', 'DEF', 'AGRI', 'SAV', 'TEMP', 'PLT']
        oc_ef = [2.157739E+23, 2.157739E+23, 2.082954E+23, 1.612156E+23, 1.885199E+23, 1.885199E+23]
        bc_ef = [2.835829E+22, 2.835829E+22, 2.113069E+22, 2.313836E+22, 2.574832E+22, 2.574832E+22]

        total_oc = ee.Image(0).rename(['b1'])
        total_bc = ee.Image(0).rename(['b1'])

        for land_type in range(0, len(land_types)): 
            oc_scale = oc_ef[land_type] * 6.022e-23 * 12  # g OC
            bc_scale = bc_ef[land_type] * 6.022e-23 * 12  # g BC

            oc_fine = maskedEmissions.multiply(ee.Image(oc_scale))
            bc_fine = maskedEmissions.multiply(ee.Image(bc_scale))

            # interpolate to current grid (is this necessary in earth engine?)

            # sum up the total for each type
            total_oc = total_oc.add(oc_fine)
            total_bc = total_bc.add(bc_fine)

        # split into GEOS-Chem hydrophobic and hydrophilic fractions, convert g to kg
        ocpo = total_oc.multiply(ee.Image(0.5 * 1.0e-3 * 2.1))
        ocpi = total_oc.multiply(ee.Image(0.5 * 1.0e-3 * 2.1))
        bcpo = total_bc.multiply(ee.Image(0.8 * 1.0e-3))
        bcpi = total_bc.multiply(ee.Image(0.2 * 1.0e-3))

        # compute daily averages from the monthly total
        emissions_philic = ocpi.add(bcpi).multiply(ee.Image(1.0/(30.0 * 6.0)))
        emissions_phobic = ocpo.add(bcpo).multiply(ee.Image(1.0/(30.0 * 6.0)))

        return emissions_philic.addBands(emissions_phobic, ['b1']).rename(['b1', 'b2'])

    emissions = monthly_dm.map(get_oc_bc)

    return emissions


def getFutureEmissions(emissyear, metyear):
    """Scales the transition emissions from the appropriate 5-year chunk by the IAV of the meteorological year"""

    # read in IAV based on metYear
    IAV = ee.Image(1)

    # find closest year for land-use scenarios
    if emissyear > 2025:
        start_landcover = ee.Image('users/karenyu/future_LULC_MarHanGFW4')
        end_landcover = ee.Image('users/karenyu/future_LULC_MarHanGFW5')
    elif emissyear > 2020:
        start_landcover = ee.Image('users/karenyu/future_LULC_MarHanGFW3')
        end_landcover = ee.Image('users/karenyu/future_LULC_MarHanGFW4')
    elif emissyear > 2015: 
        start_landcover = ee.Image('users/karenyu/future_LULC_MarHanGFW2')
        end_landcover = ee.Image('users/karenyu/future_LULC_MarHanGFW3')
    elif emissyear > 2010: 
        start_landcover = ee.Image('users/karenyu/future_LULC_MarHanGFW1')
        end_landcover = ee.Image('users/karenyu/future_LULC_MarHanGFW2')
    elif emissyear == 2010:
        start_landcover = ee.Image('users/karenyu/marHanGfw2005_6classes')
        end_landcover = ee.Image('users/karenyu/future_LULC_MarHanGFW1')

    # get the transition emissions
    transition_emissions = getTransitionEmissions(start_landcover, end_landcover)

    print(ee.Image(transition_emissions.first()).bandNames().getInfo())

    # scale transition emissions based on IAV
    def scale_IAV(emissions):
        return emissions.multiply(IAV)

    scaled_emissions = transition_emissions.map(scale_IAV)

    return scaled_emissions


def getTransitionEmissions(initialLandcover, finalLandcover):
    initial_masks = []
    final_masks = []

    # order: DG, IN, NF, TM, OPL, NPL
    for i in range(1,7):
        initial_masks.append(initialLandcover.eq(ee.Image(i)))
        final_masks.append(finalLandcover.eq(ee.Image(i)))

    #in2in,in2dg,in2nf,in2tm,in2opl,in2npl,dg2dg,dg2nf,dg2tm,dg2opl,dg2npl,nf2nf,tm2tm,tm2nf,opl2opl,opl2nf,npl2npl
    initial_index = [1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 2, 3, 3, 4, 4, 5]
    final_index   = [1, 0, 2, 3, 4, 5, 0, 2, 3, 4, 5, 2, 3, 2, 4, 2, 5]

    emissions_all_months = ee.List([])

    for month in range(0,12):
        emiss_rates = INDO_NONPEAT[month]
        #accumulate emissions
        monthly_emissions = initial_masks[1].multiply(final_masks[1]).multiply(ee.Image(emiss_rates[0] * 926.625433 * 926.625433))
        for transition_index in range(1, 16):
            monthly_emissions = monthly_emissions.add(ee.Image(0))
            monthly_emissions = monthly_emissions.add(initial_masks[initial_index[transition_index]].multiply(final_masks[final_index[transition_index]]).multiply(ee.Image(emiss_rates[transition_index] * 926.625433 * 926.625433)))

        # add to collection
        emissions_all_months = emissions_all_months.add(monthly_emissions)

    return ee.ImageCollection(emissions_all_months)


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
        pm_philic = sensitivity.select('b1').multiply(emission.select('b1')).multiply(ee.Image(SCALE_FACTOR/30.0))
        pm_phobic = sensitivity.select('b2').multiply(emission.select('b2')).multiply(ee.Image(SCALE_FACTOR/30.0))
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


def computeRegionalTotal(image, regions, projection):
    """Computes the provincial totals"""
    provincialTotals = image.reduceRegions(regions, reducer=ee.Reducer.sum(), crs=projection)

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

def getLogging():
    """Get boundaries for logging concessions"""
    #fc = ee.FeatureCollection('ft:1QgJf-3Vso3hirAnBMknJmEwwZ9-2tHIT62RHqLxX')
    mask = ee.Image('users/karenyu/logging_concessions')

    return mask

def getOilPalm():
    """Get boundaries for oil palm concessions"""
    #fc = ee.FeatureCollection('1eKRxDmhsYm-uJ0h_knFqJd7iS-kMhjkpJDBG8URF')
    mask = ee.Image('users/karenyu/oilpalm')

    return mask

def getTimber():
    """Get boundaries for timber concessions"""
    #fc = ee.FeatureCollection('1SCflzzfReLipuUttF76z8Ln-1zjvHRn2pKjzt6om')
    #img = fc.reduceToImage(properties=ee.List(['objectid']), reducer=ee.Reducer.count())

    mask = ee.Image('users/karenyu/timber_concession')
    return mask

def getPeatlands():
    """Get boundaries for peatlands"""
    #fc = ee.FeatureCollection('1cSPErISE1fJURsPbeHrnaoCofSa6efRPbBX5bz8a')

    mask = ee.Image('users/karenyu/peatlands')
    return mask

def getConservation():
    """Get boundaries for conservation areas"""
    #fc = ee.FeatureCollection('1mY-MLMGjNqxCqZiY9ek5AVQMdNhLq_Fjh_2fHnkf')
    mask = ee.Image('users/karenyu/conservation')

    return mask


def getPopulationDensity(year):
    #img = ee.Image(POPULATION_DENSITY_COLLECTION_ID + '/' + year).select('population-density')
    img = ee.Image('users/karenyu/GPW2005').select('b1')
    return img


def getBaselineMortality():
    return ee.Image('users/karenyu/baseline_mortality')


def getAttributableMortality(baseline_mortality, receptor, exposure):
    CR_25, CR, CR_97 = concentrationResponse(exposure)
    if receptor == 'Indonesia': 
        mortality_rate = 0.0099759
        population = 257563815
    elif receptor == 'Malaysia':
        mortality_rate = 0.0078068 
        population = 30331007 
    elif receptor == 'Singapore':
        mortality_rate = 0.0076863
        population = 5603740 

    total_deaths_25 = mortality_rate * population * CR_25 
    total_deaths = mortality_rate * population * CR
    total_deaths_97 = mortality_rate * population * CR_97

    return [total_deaths_25, total_deaths, total_deaths_97]

def concentrationResponse(dExposure):
    def FullLin25CI(x):
        return ((0.0059 * 1.8) - (1.96 * 0.004)) * x

    def FullLin(x):
        return (0.0059 * 1.8) * x 

    def FullLin975CI(x):
        return ((0.0059 * 1.8) + (1.96 * 0.004)) * x

    def LinTo50(x):
        if x > 50:
            return FullLin(50)
        else:
            return FullLin(x) 

    def Lin50HalfLin(x):
        if x <= 50:
            return FullLin(x)
        else: 
            return (FullLin(x) + FullLin(50)) * 0.5

    def FullLog(x):
        return 1 - (1/math.exp(0.00575 * 1.8 * (x)))

    def FullLog225CI(x):
        return 1 - (1/math.exp(((0.0059 * 1.8) - (1.96 * 0.004)) * (x))) 

    def FullLog2(x):
        return 1 - (1/math.exp(0.0059 * 1.8 * (x)))

    def FullLog2975CI(x):
        return 1 - (1/math.exp(((0.0059 * 1.8) + (1.96 * 0.004)) * (x)))

    def Lin50Log(x):
        if x <= 50: 
            return FullLin(x)
        else:
            return FullLin(50) + FullLog(x) - FullLog(50)

    if dExposure <= 50:
        Lin50Log225CI = FullLin25CI(dExposure)
        Lin50Log2 = FullLin(dExposure)
        Lin50Log2975CI = FullLin975CI(dExposure)
    else:
        Lin50Log225CI = FullLin25CI(50) + FullLog225CI(dExposure) - FullLog225CI(50)
        Lin50Log2 = FullLin(50) + FullLog2(dExposure) - FullLog2(50)
        Lin50Log2975CI = FullLin975CI(50) + FullLog2975CI(dExposure) - FullLog2975CI(50)
    return Lin50Log225CI, Lin50Log2, Lin50Log2975CI


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

# Data for land cover emissions
#in2in,in2dg,in2nf,in2tm,in2opl,in2npl,dg2dg,dg2nf,dg2tm,dg2opl,dg2npl,nf2nf,tm2tm,tm2nf,opl2opl,opl2nf,npl2npl
INDO_NONPEAT = [[0.008197090042,0.09189487345,45.08259032,2.414848632,0,99.62405558,0.5851376497,56.89003923,13.23437324,9.474651961,30.48744721,3.025035159,1.288852821,9.643030397,2.091151198,8.660805616,10.17454118],
[0.01139663662,0.06239636031,56.45024628,3.143033855,57.85880118,32.14237698,0.9690808753,89.70646311,16.60274935,21.67981473,63.02774005,3.228240267,2.420661473,15.26761109,3.971457501,12.1041069,9.638991123],
[0.003903939588,0.04366400351,0,0,0,0,0.8714240293,44.09290443,9.970130629,7.420294069,39.73751491,4.212207518,2.386355319,9.647900184,2.610260354,9.367637215,8.261123163],
[0.003721238199,0.08461353334,73.67114817,0.6271246072,119.2253549,67.02342792,0.1896129203,39.70551525,3.695080593,14.11716819,11.60070125,2.786611068,0.6384868533,3.583137124,1.447893564,4.108222706,4.347909571],
[0.04269593381,0.1564843473,1.732841888,1.526454223,3.299481933,10.99779359,1.494500312,140.0227631,16.05544109,112.9297011,77.84635536,6.282340802,2.019456548,11.03557469,4.717004999,24.37953918,7.638316017],
[0.02731323219,0.003655800401,121.2735682,0.06076623004,0,0,1.678851633,130.4693188,21.34323882,70.09079297,67.74787327,9.938019986,4.125263717,15.89372733,7.695079308,33.55982871,22.79506765],
[0.0337372371,0.5756916391,197.8887014,24.48579226,0,0,4.965160689,325.5810477,81.45475691,128.4848211,340.3287642,45.25855048,18.34708554,68.78541069,35.60324901,116.1209016,63.48808218],
[0.2343221978,2.027323474,1303.542795,95.69052989,60.83012343,95.48372991,18.98220118,593.1907953,213.7176597,352.1231844,677.1915077,119.964009,95.72065985,274.8728212,163.9229257,331.4825874,166.6288735],
[0.402160571,3.147158609,144.2447899,29.82459307,20.24387878,248.9676516,35.71717497,571.8534967,251.9015785,461.8178704,500.6391082,341.2642587,270.5614806,492.0583825,527.578186,1126.198147,227.8575944],
[0.2643180172,1.218160114,222.2949219,12.76341971,118.7833439,194.5475882,20.24593458,382.5312947,207.0975685,216.2563633,315.3197157,144.7223586,152.1536701,181.4451014,250.2639547,577.1953486,126.38394],
[0.2468356043,0.3724324773,115.0425349,6.555582307,93.63776922,0,4.348996864,34.73644492,24.798789,44.72874265,39.04249045,24.28327564,19.46629308,18.71915917,28.13705289,49.09576491,26.59634286],
[0.01908487111,0.1311755492,120.6789472,0,77.89568727,493.5910992,0.5650428577,6.133650458,1.821382238,5.303140883,4.385465151,2.523862176,1.269228463,1.720818905,0.8537594324,3.510877517,1.550712832]]

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
