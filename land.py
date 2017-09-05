import ee

def getLandcoverData():
    present = ee.Image('users/karenyu/marHanS2005_sin')
    BAU2010 = ee.Image('users/karenyu/marHanS2010_sin')
    BAU2015 = ee.Image('users/karenyu/future_LULC_MarHan2')
    BAU2020 = ee.Image('users/karenyu/future_LULC_MarHan3')
    BAU2025 = ee.Image('users/karenyu/future_LULC_MarHan4')
    BAU2030 = ee.Image('users/karenyu/future_LULC_MarHan5')

    sld_ramp = '<RasterSymbolizer>' + \
          '<ColorMap type="intervals" extended="false" >' + \
                '<ColorMapEntry color="#666666" quantity="1" label="Degraded"/>' + \
                '<ColorMapEntry color="#000000" quantity="2" label="Intact"/>' + \
                '<ColorMapEntry color="#fdb751" quantity="3" label="Non-Forest"/>' + \
                '<ColorMapEntry color="#ff0000" quantity="4" label="Plantation"/>' + \
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


