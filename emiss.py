import ee

def getEmissions(scenario, year, metYear, logging, oilpalm, timber, peatlands, conservation):
    """Gets the dry matter emissions from GFED4 and converts to oc/bc using emission factors associated with GFED4"""

    ds_grid = ee.Image('projects/IndonesiaPolicyTool/dsGFEDgrid')
    print(ds_grid.projection().nominalScale().getInfo())
    print("SCENARIO", scenario)
    peatmask = getPeatlands()
    print(peatmask.projection().nominalScale().getInfo())
    if logging:
        loggingmask = getLogging()
    if oilpalm:
        oilpalmmask = getOilPalm()
    if timber:
        timbermask = getTimber()
    if conservation:
        conservationmask = getConservation().reproject(crs=ds_grid.projection(), scale=ds_grid.projection().nominalScale()).eq(1)
        print(conservationmask.projection().nominalScale().getInfo())

    # get emissions based on transitions or from GFED 
    print("YEAR == ", year)
    if scenario=='GFED4':
        # gfed in kg DM
        #monthly_dm = ee.ImageCollection('users/tl2581/gfedv4s').filter(ee.Filter.rangeContains('system:index', 'DM_'+str(year)+'01', 'DM_'+str(year)+'12'))
        monthly_dm = ee.ImageCollection('users/karenyu/gfed4').filterDate(str(year) + '-01-1', str(year) + '-12-31').sort('system:time_start', True)
    else:
        monthly_dm = getDownscaled(year, metYear, peatmask)

    #monthly_dm = ee.ImageCollection('users/tl2581/gfedv4s').filterDate('2008-01-01', '2009-01-01').sort('system:time_start', True) 

    # map comes from IAV file
    #monthly_dm = (emissions * map)   # Gg to Tg 

    # mask out emissions
    def mask_emissions(ems):
        # first mask out data from regions that are turned off
        if logging:
            maskedEmissions = ems.updateMask(loggingmask)
        else:
            maskedEmissions = ems
        if oilpalm:
            maskedEmissions = maskedEmissions.updateMask(oilpalmmask)
        if timber:
            maskedEmissions = maskedEmissions.updateMask(timbermask)
        if peatlands:
            maskedEmissions = maskedEmissions.updateMask(peatmask)
        if conservation:
            maskedEmissions = maskedEmissions.updateMask(conservationmask)
        return maskedEmissions

    # function to compute oc and bc emissions from dm
    def get_oc_bc(dm_emissions):
        
        land_types = ['PET', 'DEF', 'AGRI', 'SAV', 'TEMP', 'PLT']

        #bands = ['b5', 'b4', 'b6', 'b1', 'b3', 'b2']
        bands = ['b1', 'b2', 'b3', 'b4', 'b5', 'b6']
        
        oc_ef = [2.62, 9.6, 9.6, 4.71, 6.02, 2.3]
        bc_ef = [0.37, 0.5, 0.5, 0.52, 0.04, 0.75]
        
        total_oc = ee.Image(0).rename(['b1'])
        total_bc = ee.Image(0).rename(['b1'])

        for land_type in range(0, len(land_types)): 
            oc_scale = oc_ef[land_type] #* 6.022e-23 * 12.0  # g OC/kg DM
            bc_scale = bc_ef[land_type] #* 6.022e-23 * 12.0  # g BC/kg DM

            band_number = bands[land_type]

            oc_fine = maskedEmissions.select(band_number).multiply(ee.Image(oc_scale))  # g OC
            bc_fine = maskedEmissions.select(band_number).multiply(ee.Image(bc_scale))  # g BC

            # interpolate to current grid (is this necessary in earth engine?)
            # sum up the total for each type
            total_oc = total_oc.add(oc_fine)
            total_bc = total_bc.add(bc_fine)

        # split into GEOS-Chem hydrophobic and hydrophilic fractions
        ocpo = total_oc.multiply(ee.Image(0.5 * 2.1 ))  # g OA
        ocpi = total_oc.multiply(ee.Image(0.5 * 2.1 ))  # g OA
        bcpo = total_bc.multiply(ee.Image(0.8 ))        # g BC
        bcpi = total_bc.multiply(ee.Image(0.2 ))        # g BC

        emissions_philic = ocpi.add(bcpi).multiply(ee.Image(1.0e-3))  # to kg OC/BC
        emissions_phobic = ocpo.add(bcpo).multiply(ee.Image(1.0e-3))

        return emissions_philic.addBands(emissions_phobic, ['b1']).rename(['b1', 'b2'])


    def convert_transition_emissions(oc_bc_emissions):
        # need to unmask to make mask values zero
        oc_bc_emissions = oc_bc_emissions.unmask()

        # split into GEOS-Chem hydrophobic and hydrophilic fractions
        ocpo = oc_bc_emissions.select('oc').multiply(ee.Image(0.5 * 2.1 ))  # g OA
        ocpi = oc_bc_emissions.select('oc').multiply(ee.Image(0.5 * 2.1 ))  # g OA
        bcpo = oc_bc_emissions.select('bc').multiply(ee.Image(0.8))        # g BC
        bcpi = oc_bc_emissions.select('bc').multiply(ee.Image(0.2))        # g BC

        emissions_philic = ocpi.add(bcpi).multiply(ee.Image(1.0e-3)).rename(['b1'])
        emissions_phobic = ocpo.add(bcpo).multiply(ee.Image(1.0e-3)).rename(['b1'])


        return emissions_philic.addBands(emissions_phobic, ['b1']).rename(['b1', 'b2'])


    if scenario=='GFED4':
        emissions_masked = monthly_dm.map(mask_emissions)
        emissions = emissions_masked.map(get_oc_bc)
    else:
        emissions_masked = monthly_dm.map(mask_emissions)
        emissions = emissions_masked.map(convert_transition_emissions)

    # compute total emissions
    def sum_collection(image, first):
        return ee.Image(first).add(ee.Image(image))

    #total_emissions = monthly_dm.sum().reproject(crs=ds_grid.projection(), scale=ds_grid.projection().nominalScale()).multiply(ee.Image.pixelArea()).reduceRegion(reducer=ee.Reducer.sum().unweighted(), geometry=ee.Geometry.Rectangle([90,-20,150,10]), scale=ee.Image(emissions_masked.first()).projection().nominalScale(), maxPixels=1e9)
    total_emissions = ee.Image(emissions_masked.iterate(sum_collection, ee.Image(0))).reproject(crs=ds_grid.projection(), scale=ds_grid.projection().nominalScale()).multiply(ee.Image.pixelArea()).reduceRegion(reducer=ee.Reducer.sum().unweighted(), geometry=ee.Geometry.Rectangle([90,-20,150,10]), crs=ds_grid.projection(), scale=ds_grid.projection().nominalScale(), maxPixels=1e9)
    print('total emissions: {}'.format(total_emissions.getInfo()))

    return emissions, total_emissions


def getDownscaled(emissyear, metyear, peatmask):
    """Scales the transition emissions from the appropriate 5-year chunk by the IAV of the meteorological year"""

    # read in IAV based on metYear
    #IAV = ee.Image('users/karenyu/dm_fractional_'+str(metyear))

    print(emissyear)
    # find closest year for land-use scenarios
    if emissyear >= 2025:
        start_landcover = ee.Image('projects/IndonesiaPolicyTool/marHanS_future/future_LULC_MarHanS_2025')
        end_landcover = ee.Image('projects/IndonesiaPolicyTool/marHanS_future/future_LULC_MarHanS_2030')
    elif emissyear >= 2020:
        start_landcover = ee.Image('projects/IndonesiaPolicyTool/marHanS_future/future_LULC_MarHanS_2020')
        end_landcover = ee.Image('projects/IndonesiaPolicyTool/marHanS_future/future_LULC_MarHanS_2025')
    elif emissyear >= 2015: 
        start_landcover = ee.Image('projects/IndonesiaPolicyTool/marHanS_future/future_LULC_MarHanS_2015')
        end_landcover = ee.Image('projects/IndonesiaPolicyTool/marHanS_future/future_LULC_MarHanS_2020')
    elif emissyear >= 2010: 
        start_landcover = ee.Image('projects/IndonesiaPolicyTool/marHanS_future/future_LULC_MarHanS_2010')
        end_landcover = ee.Image('projects/IndonesiaPolicyTool/marHanS_future/future_LULC_MarHanS_2015')
    elif emissyear >= 2005:
        start_landcover = ee.Image('projects/IndonesiaPolicyTool/marHanS2005')
        end_landcover = ee.Image('projects/IndonesiaPolicyTool/marHanS2010')

    # get the transition emissions
    transition_emissions = getTransition(start_landcover, end_landcover, peatmask, year=(metyear-2005) )

    print(ee.Image(transition_emissions.first()).bandNames().getInfo())

    # scale transition emissions based on IAV
    def scale_IAV(emissions):
        return emissions.multiply(IAV)

    scaled_emissions = transition_emissions #.map(scale_IAV)

    
    return scaled_emissions

def getTransition(initialLandcover, finalLandcover, peatmask, year):
    """ Returns emissions due to land cover transitions at 1 km resolution in kg DM per grid cell"""
    
    ds_grid = ee.Image('projects/IndonesiaPolicyTool/dsGFEDgrid')
    
    # get masks for the different islands
    islands = ee.Image('projects/IndonesiaPolicyTool/island_boundary_null').reproject(crs=ds_grid.projection(), scale=ds_grid.projection().nominalScale())

    suma_mask = islands.eq(ee.Image(2)).reproject(crs=ds_grid.projection(), scale=ds_grid.projection().nominalScale())
    kali_mask = islands.eq(ee.Image(3)).reproject(crs=ds_grid.projection(), scale=ds_grid.projection().nominalScale())
    #indo_mask = islands.eq(ee.Image(1)).add(islands.gt(ee.Image(3))).gt(0).reproject(crs=ds_grid.projection(), scale=ds_grid.projection().nominalScale())
    indo_mask = ee.Image('users/karenyu/indonesia').reproject(crs=ds_grid.projection(), scale=ds_grid.projection().nominalScale())
    # print area
    print("Area: {}".format(indo_mask.multiply(ee.Image.pixelArea()).reduceRegion(geometry=ee.Geometry.Rectangle([90,-20,150,10]), crs=ds_grid.projection(), scale=ds_grid.projection().nominalScale(), reducer=ee.Reducer.sum(), maxPixels=1e9).getInfo()))

    initial_masks = []
    final_masks = []

    # area of grid cell (m^2) and g to kg
    scaling_factor = 1.0e-3

    reverse_peatmask = peatmask.subtract(ee.Image(1)).multiply(ee.Image(-1))
    # order: DG, IN, NF, PL
    for i in range(1,5):
        initial_masks.append(initialLandcover.eq(ee.Image(i)))
        final_masks.append(finalLandcover.eq(ee.Image(i)))

#       in2in    in2dg     in2nf   in2pl  dg2dg    dg2nf   dg2pl   nf2nf   pl2pl
    initial_index = [1, 1, 1, 1, 0, 0, 0, 2, 3]
    final_index   = [1, 0, 2, 3, 0, 2, 3, 2, 3]
    gfed_index    = [3, 3, 3, 3, 3, 3, 3, 0, 0]

    #        SAVA  BORF TEMF DEFO  PEAT AGRI
    oc_ef = [2.62, 9.6, 9.6, 4.71, 6.02, 2.3]
    bc_ef = [0.37, 0.5, 0.5, 0.52, 0.04, 0.75]

    emissions_all_months = ee.List([])

    for month in range(0,12):
        kali_nonpeat_rates = KALI_NONPEAT[month+12*year]
        kali_peat_rates = KALI_PEAT[month+12*year]
        suma_nonpeat_rates = SUMA_NONPEAT[month+12*year]
        suma_peat_rates = SUMA_PEAT[month+12*year]
        indo_nonpeat_rates = INDO_NONPEAT[month+12*year] #INDO_NONPEAT[month]
        #indo_peat_rates = INDO_PEAT[month+12*year] #INDO_PEAT[month]
        #accumulate emissions    926.625433
        kali_nonpeat_oc = initial_masks[1].multiply(final_masks[1]).multiply(ee.Image(kali_nonpeat_rates[0] * scaling_factor * oc_ef[3]).updateMask(peatmask)).updateMask(kali_mask).reproject(crs=ds_grid.projection(), scale=ds_grid.projection().nominalScale())
        kali_nonpeat_bc = initial_masks[1].multiply(final_masks[1]).multiply(ee.Image(kali_nonpeat_rates[0] * scaling_factor * bc_ef[3]).updateMask(peatmask)).updateMask(kali_mask).reproject(crs=ds_grid.projection(), scale=ds_grid.projection().nominalScale())
        kali_peat_oc = initial_masks[1].multiply(final_masks[1]).multiply(ee.Image(kali_peat_rates[0] * scaling_factor * oc_ef[4]).updateMask(reverse_peatmask)).updateMask(kali_mask).reproject(crs=ds_grid.projection(), scale=ds_grid.projection().nominalScale())
        kali_peat_bc = initial_masks[1].multiply(final_masks[1]).multiply(ee.Image(kali_peat_rates[0] * scaling_factor * bc_ef[4]).updateMask(reverse_peatmask)).updateMask(kali_mask).reproject(crs=ds_grid.projection(), scale=ds_grid.projection().nominalScale())
        suma_nonpeat_oc = initial_masks[1].multiply(final_masks[1]).multiply(ee.Image(suma_nonpeat_rates[0] * scaling_factor * oc_ef[3]).updateMask(peatmask)).updateMask(suma_mask).reproject(crs=ds_grid.projection(), scale=ds_grid.projection().nominalScale())
        suma_nonpeat_bc = initial_masks[1].multiply(final_masks[1]).multiply(ee.Image(suma_nonpeat_rates[0] * scaling_factor * bc_ef[3]).updateMask(peatmask)).updateMask(suma_mask).reproject(crs=ds_grid.projection(), scale=ds_grid.projection().nominalScale())
        suma_peat_oc = initial_masks[1].multiply(final_masks[1]).multiply(ee.Image(suma_peat_rates[0] * scaling_factor * oc_ef[4]).updateMask(reverse_peatmask)).updateMask(suma_mask).reproject(crs=ds_grid.projection(), scale=ds_grid.projection().nominalScale())
        suma_peat_bc = initial_masks[1].multiply(final_masks[1]).multiply(ee.Image(suma_peat_rates[0] * scaling_factor * bc_ef[4]).updateMask(reverse_peatmask)).updateMask(suma_mask).reproject(crs=ds_grid.projection(), scale=ds_grid.projection().nominalScale())
        indo_nonpeat_oc = initial_masks[1].multiply(final_masks[1]).multiply(ee.Image(indo_nonpeat_rates[0] * scaling_factor * oc_ef[3])).updateMask(indo_mask).reproject(crs=ds_grid.projection(), scale=ds_grid.projection().nominalScale())
        indo_nonpeat_bc = initial_masks[1].multiply(final_masks[1]).multiply(ee.Image(indo_nonpeat_rates[0] * scaling_factor * bc_ef[3])).updateMask(indo_mask).reproject(crs=ds_grid.projection(), scale=ds_grid.projection().nominalScale())
        #indo_peat_oc = initial_masks[1].multiply(final_masks[1]).multiply(ee.Image(indo_peat_rates[0] * scaling_factor * oc_ef[4]).updateMask(reverse_peatmask)).updateMask(indo_mask).reproject(crs=ds_grid.projection(), scale=ds_grid.projection().nominalScale())
        #indo_peat_bc = initial_masks[1].multiply(final_masks[1]).multiply(ee.Image(indo_peat_rates[0] * scaling_factor * bc_ef[4]).updateMask(reverse_peatmask)).updateMask(indo_mask).reproject(crs=ds_grid.projection(), scale=ds_grid.projection().nominalScale())
        for transition_index in range(1, 9):
            kali_nonpeat_oc = kali_nonpeat_oc.add(initial_masks[initial_index[transition_index]].multiply(final_masks[final_index[transition_index]]).multiply(ee.Image(kali_nonpeat_rates[transition_index] * scaling_factor * oc_ef[gfed_index[transition_index]])))
            kali_nonpeat_bc = kali_nonpeat_bc.add(initial_masks[initial_index[transition_index]].multiply(final_masks[final_index[transition_index]]).multiply(ee.Image(kali_nonpeat_rates[transition_index] * scaling_factor * bc_ef[gfed_index[transition_index]])))
            kali_peat_oc = kali_peat_oc.add(initial_masks[initial_index[transition_index]].multiply(final_masks[final_index[transition_index]]).multiply(ee.Image(kali_peat_rates[transition_index] * scaling_factor * oc_ef[4])))
            kali_peat_bc = kali_peat_bc.add(initial_masks[initial_index[transition_index]].multiply(final_masks[final_index[transition_index]]).multiply(ee.Image(kali_peat_rates[transition_index] * scaling_factor * bc_ef[4])))
            suma_nonpeat_oc = suma_nonpeat_oc.add(initial_masks[initial_index[transition_index]].multiply(final_masks[final_index[transition_index]]).multiply(ee.Image(suma_nonpeat_rates[transition_index] * scaling_factor * oc_ef[gfed_index[transition_index]])))
            suma_nonpeat_bc = suma_nonpeat_bc.add(initial_masks[initial_index[transition_index]].multiply(final_masks[final_index[transition_index]]).multiply(ee.Image(suma_nonpeat_rates[transition_index] * scaling_factor * bc_ef[gfed_index[transition_index]])))
            suma_peat_oc = suma_peat_oc.add(initial_masks[initial_index[transition_index]].multiply(final_masks[final_index[transition_index]]).multiply(ee.Image(suma_peat_rates[transition_index] * scaling_factor * oc_ef[4])))
            suma_peat_bc = suma_peat_bc.add(initial_masks[initial_index[transition_index]].multiply(final_masks[final_index[transition_index]]).multiply(ee.Image(suma_peat_rates[transition_index] * scaling_factor * bc_ef[4])))
            indo_nonpeat_oc = indo_nonpeat_oc.add(initial_masks[initial_index[transition_index]].multiply(final_masks[final_index[transition_index]]).multiply(ee.Image(indo_nonpeat_rates[transition_index] * scaling_factor * oc_ef[gfed_index[transition_index]])))
            indo_nonpeat_bc = indo_nonpeat_bc.add(initial_masks[initial_index[transition_index]].multiply(final_masks[final_index[transition_index]]).multiply(ee.Image(indo_nonpeat_rates[transition_index] * scaling_factor * bc_ef[gfed_index[transition_index]])))
            #indo_peat_oc = indo_peat_oc.add(initial_masks[initial_index[transition_index]].multiply(final_masks[final_index[transition_index]]).multiply(ee.Image(indo_peat_rates[transition_index] * scaling_factor * oc_ef[4])))
            #indo_peat_bc = indo_peat_bc.add(initial_masks[initial_index[transition_index]].multiply(final_masks[final_index[transition_index]]).multiply(ee.Image(indo_peat_rates[transition_index] * scaling_factor * bc_ef[4])))

        # add to collection
        oc = kali_peat_oc.unmask().add(kali_nonpeat_oc.unmask()).add(indo_nonpeat_oc.unmask()).add(suma_peat_oc.unmask()).add(suma_nonpeat_oc.unmask()).reproject(crs=ds_grid.projection(), scale=ds_grid.projection().nominalScale())
        #oc = kali_peat_oc.unmask().add(kali_nonpeat_oc.unmask()).add(indo_peat_oc.unmask()).add(indo_nonpeat_oc.unmask()).add(suma_peat_oc.unmask()).add(suma_nonpeat_oc.unmask()).reproject(crs=ds_grid.projection(), scale=ds_grid.projection().nominalScale())
        bc = kali_peat_bc.unmask().add(kali_nonpeat_bc.unmask()).add(indo_nonpeat_bc.unmask()).add(suma_peat_bc.unmask()).add(suma_nonpeat_bc.unmask()).reproject(crs=ds_grid.projection(), scale=ds_grid.projection().nominalScale())
        #bc = kali_peat_bc.unmask().add(kali_nonpeat_bc.unmask()).add(indo_peat_bc.unmask()).add(indo_nonpeat_bc.unmask()).add(suma_peat_bc.unmask()).add(suma_nonpeat_bc.unmask()).reproject(crs=ds_grid.projection(), scale=ds_grid.projection().nominalScale())
        emissions_all_months = emissions_all_months.add(oc.addBands(bc).rename(['oc', 'bc']))

    return ee.ImageCollection(emissions_all_months)


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
    #ft = ee.FeatureCollection('projects/IndonesiaPolicyTool/IDN_peat')
    #ds_grid = ee.Image('projects/IndonesiaPolicyTool/dsGFEDgrid')
    #mask = ft.reduceToImage(properties=ee.List(['id']), reducer=ee.Reducer.max()).reproject(crs=ds_grid.projection(), scale=ds_grid.projection().nominalScale()).gt(0).expression("(b('max') > 0) ? 1: 0")
    #region = ee.Geometry.Rectangle([90,-20,150,10]);

    #mask = ee.Image('users/karenyu/peatlands')
    mask = ee.Image('projects/IndonesiaPolicyTool/peatlands')
    return mask#.reproject(crs=ds_grid.projection(), scale=ds_grid.projection().nominalScale()).subtract(ee.Image(1)).multiply(ee.Image(-1))

def getConservation():
    """Get boundaries for conservation areas"""
    #fc = ee.FeatureCollection('1mY-MLMGjNqxCqZiY9ek5AVQMdNhLq_Fjh_2fHnkf')
    mask = ee.Image('users/karenyu/conservation')

    return mask


# Data for land cover emissions
#       in2in             in2dg          in2nf        in2pl         dg2dg          dg2nf        dg2pl         nf2nf         pl2pl
INDO_NONPEAT = [
[0,0,0,0,0.0108498781348414,1.22855432024582,0,0.0969077465426447,0.0210241957859082],
[0.000723701363987965,0.0284534225830103,0,0,0.00867827581122596,0.47989611965725,0,0.0921306087226664,0.0174264754413678],
[0.000666518889608638,0.018114532669687,0,0,0.0274206570399425,1.6996759393692,0,0.16631655430539,0.141762521061446],
[0,0,0,0,0.000496525828898452,0,0,0.203926233797778,0.0600478867712037],
[0,0,0,0,0.00333222867631222,0,0,0.624106033420603,0.0468502908752454],
[0,0,0,0,0.0150392474444058,0,0,0.845334559913058,0.0771936297073229],
[0,0,0,0,0.0422939332170886,0,0,3.50065470598447,0.973875011533476],
[0.000834070911636963,0,0,0,0.212243915309719,0,0,4.8246173250123,1.52725496687132],
[0.101051511955853,0.0462472961087345,0,0,1.8114270379808,5.69899908815996,0,20.358064211498,9.87110642553906],
[0.00785046028122776,0.510569502208876,1.59025006660042,0,0.266666346724007,3.10243888676,5.03480435011535,3.27062732633809,1.6976133176157],
[0.0136222458683832,0.385594695095371,0.19317496225903,0,0.0378062066672267,0.0659272568730764,0.830994647262596,0.496832839089551,0.23209327370423],
[0,0,0,0,0.00170915824281408,0,0,0.0299015073285745,0.0174555018174103],
[0,0,15.2115164386224,0,0.0161236523736697,1.3611447059969,0,0.0368311944582608,0.050714969633715],
[0,0,0,0,0.0139324796479899,1.03370882014546,0,0.132623030561815,0.0261915588586713],
[0.000407000711675733,0,0,0,0.0236570027947281,0,0,0.281538672132072,0.06008535076898],
[0,0,0,0,0.00700317830872144,0,0,0.301178968999451,0.0928122142809423],
[0,0.0161826630045952,4.45902258232995,0,0.0147957705608856,0.201614749056692,8.32384095156759,0.422046130884118,0.112396727915912],
[0,0.0313629051064516,0,0,0.00986689796890629,0,0,0.861582135784466,0.215952309093998],
[0.0156596827406229,0,2.76855014587262,15.7321792353524,0.0662068440376179,5.71805448889954,44.2220056621059,4.39364135390085,1.37089095376722],
[0.014632972103403,0.22108267941396,34.8778921243185,60.6905101936224,0.592178022106464,59.4589753714698,55.1121512413239,9.4144629519319,3.83095091863135],
[0.03402547616476,0.099848195739937,4.07603142814126,52.5318887028186,1.80695931880759,36.4239300594058,8.10319011612701,19.7075873914226,11.5734379630736],
[0.198057022316264,0.397862566191772,236.01773488623,1019.44453047616,5.06942587912486,192.000186522132,201.625858629478,45.3558141859141,25.1646124185204],
[0.177219079249518,0.557656115693491,123.691136986205,0,2.50718888623825,59.8715822651971,44.0142895115659,20.6632509413109,13.9987295703776],
[0.10913626242875,0.0238260502266346,111.069619024392,112.337059068535,0.767798210863137,5.70858959813158,4.02674871713065,2.5516630256553,2.23382548163888],
[0,0,32.2179143129917,0,0.010444299351535,2.77154799628534,0,0.294629100824958,0.179954599354442],
[0,0.0397285594946049,90.1166608052484,74.7389016386779,0.0235995851616688,0,0,0.160613207014141,0.0533146514606468],
[0.00260845371071478,0,0,0,0.0230947997899837,6.896828131633,56.7978720550698,0.213406126905056,0.0293168104150939],
[0,0.119701420989606,116.405868575485,41.1033203817621,0.0121924505613819,0.486508017251342,13.8104552484914,0.254560366304468,0.021193264340459],
[0.0027283948344111,0,0,0,0.0100552569468707,0,0,0.510241761791043,0.114148022306262],
[0,0.073040605783933,0,0,0.0205135671598086,0,0,0.414744096470137,0.0741087711225583],
[0.0066552006884346,0,0,0,0.0302971917706908,0,0,1.30529534299931,0.267210427008031],
[0,0,0,0,0.0111035625246172,0.991414492455567,0,4.19777401029126,0.552283587634392],
[0.0125863946347922,0.614007827329739,78.2966117394763,488.44714919349,1.041474629677,472.967593925566,50.7894388612154,12.1903875755245,6.53492862109577],
[0.0459856812203424,0.0427752622771001,24.4940530538744,0,0.807911581114611,254.689103282231,0,5.1407457590271,3.91764368547524],
[0.00743514101916365,0.0855043135813262,0,0,0.505284547554073,127.721733545945,0,1.57166789969527,1.28641871985085],
[0,0,108.221880744508,0,0.0706391622026469,44.8624264236177,0,0.277289757992151,0.300956252326116],
[0.0103084619225405,0,0,0,0.0734991619189764,6.44616529879541,0,0.314695651971283,0.128076726336055],
[0,0,0,0,0.0184965006644053,7.78103615879575,0,0.193629694582409,0.0860828406054982],
[0.000482921197261336,0,0,0,0.0191163691792595,24.8507632337511,0,0.401569289468616,0.123931003422785],
[0,0,0,0,0.00536017321648426,1.04586049604152,0,0.490577290422949,0.048850277761665],
[0.00695677660317761,0,0,0,0.0287628731509632,0.860038361645764,0,1.72998772214873,0.117471938811663],
[0.00043866379174562,0,0,0,0.0384234422843498,0,0,1.6820790955001,0.149658431485781],
[0,0,0,0,0.0433539355391127,1.52540986375965,0,4.39803858429639,0.721254195970358],
[0.00177929960994301,0,30.0824174816315,0,0.174649260214039,0,0,4.74624970562113,1.30195788344916],
[0.000521162076665977,0,8.4669343872937,0,0.326784443348714,32.4184255364675,0,8.38241334929496,2.58282986606577],
[0,0,0,0,0.138467912968838,16.0796655071735,0,2.63918136047879,1.71822126159008],
[0,0.320848005336437,0,0,0.0379236851210525,36.6219396421734,0,0.953426376132423,0.687440130311727],
[0,0,0,0,0.00612943569187199,0,0,0.270771518931653,0.0302306550850119],
[0.00514434494195859,0,0,0,0.00500238645069039,0,0,0.281836208239256,0.0795033167723869],
[0,0,0,0,0.00897109831718712,0.0458707418500243,0,0.102440156372849,0.0537130248513961],
[0,0.0521633483018458,0,0,0.0100299095653368,0.0546112977865122,0,0.554502742010138,0.0509109473561587],
[0.00114911474420365,0,0,0,0.0320756098055167,0,0,0.604592438128332,0.080542340520436],
[0,0,0,0,0.0259846117415257,0.511396604096604,0,0.600802872734922,0.0852359307827915],
[0.003746347769517,0,0,0,0.0414341244728417,0.607548458615974,0,1.45982737205361,0.220894494531161],
[0.00345758545231901,0,0,0,0.0462807327841658,21.8874843571319,0,3.73057293221245,0.526294572881275],
[0.0177860131332623,0,0,0,0.44090391398771,41.1626988038614,0,8.28162437694126,3.34629678760875],
[0.273012577837704,0.774363765075521,0,0,2.56360130207843,68.3491884737734,0,16.9852682234479,14.0260185436816],
[0.144087385709086,0.215264492626347,22.2575449610936,0,1.60096373004931,45.5833985775256,0,8.47439583226179,9.70020540037772],
[0.0602011784228519,0.153959692567452,11.6158741315313,0,0.70718221419696,187.832261875061,0,3.73911587050949,3.96496427924926],
[0.0013173166119335,0.114976839545752,0,0,0.0849965663442992,4.7565591914883,0,0.851941728462868,0.240604772711852]
        ]

#       in2in             in2dg          in2nf        in2pl         dg2dg          dg2nf        dg2pl         nf2nf         pl2pl
INDO_PEAT = [
[0,0,0,0,23.8670360668649,92.3827366554702,14.7702326433228,311.414614765992,54.9622657913549],
[0,0,0,0,67.2641076223561,147.723134867761,183.20034774587,523.114123086286,162.462703935537],
[0,1.96494332699923,0,0,28.0031253168687,171.334184629627,53.5928709096323,439.016694904908,62.6176045469844],
[0,0,0,0,1.44342749966081,6.08463533358866,1.58771778982382,19.4346055994983,2.27670414122539],
[0,0,0,0,0.0979515563614474,5.88487270078673,0.529553966348275,14.0162212348648,0.708019420278442],
[0,0,0,0,2.10181106620135,53.6792630477818,0.736434527775246,262.754142284337,8.60833362702959],
[0,0,0,0,2.23216804265124,37.6717739271777,0.773230678624197,72.6728843675703,10.5907868515206],
[0,0,0,0,38.8260136407024,585.252844112274,32.3543234358163,919.196172946995,82.4772905036023],
[0,0,0,0,39.6571704648135,71.5230676717296,1.5494967661016,489.507797474714,176.527621025794],
[0,0,0,0,1.99766580267307,2.91283000180805,3.84125606677836,17.282396567388,10.6590432129787],
[0,0,0,0,0.0174969304278157,0.0993583128614679,0.411440642428998,0.309733558781582,0.0629163687964067],
[0,0,0,0,0.0100825331327301,0.447105282749952,0.776019821937161,0.60825389096061,0.0443273160626854],
[0,0,0,0,0.306216790416655,9.43601731182056,5.06180676814222,11.4158918894454,0.692449797291723],
[0,0,0,0,1.09093227676467,19.3429554755391,2.88866875229204,28.3336319460971,2.71498056439787],
[0,0.171520815697716,0,0,5.81764924319898,104.623465043981,16.1455417253062,56.1419672490074,11.4889404093333],
[0,0,0,0,0.0660006007921737,3.75998933247166,0.333361714629344,2.59940271337565,0.306518206719038],
[0,0,0,0,0.3413090218932,16.4738007696443,4.91286743914283,18.1208104860368,0.672300726317515],
[0,0,0,0,0.570859422552345,22.9735614166934,4.66562112196273,8.59141973370807,1.1806053618147],
[0,0,0,0,12.7017647283927,489.75027588554,42.5827258393373,252.406759492149,28.9236714390206],
[0,1.15820298533004,579.711523172439,0,77.5110221850843,875.214585318231,377.736626912491,1003.82902841113,286.371657777981],
[0.168529161387246,0,0,0,77.5031723595165,567.039008655115,598.293259008238,1413.81445404943,1337.94102207127],
[0,0,0,0,162.321797115432,1257.80203109507,606.655227618472,1427.88333594959,1737.7989863468],
[0,0,0,0,22.2397002701113,201.394108165376,6.47003587543486,98.7115040424649,105.019796805969],
[0,0,0,0,0.197995027810691,0.297832919084553,0.125138458611184,1.78253080528272,0.86693085234329],
[0,0,0,0,0.222923365980897,5.13425940089017,0.203067751635525,1.35781097182106,0.573380731452868],
[0,0,0,0,2.52943779350056,145.564060078722,32.8593052264058,47.1815062632411,18.2158571605059],
[0,0,0,0,1.22946705521957,117.482048565994,19.281686864361,21.9008692238754,10.2842996310946],
[0,0,0,0,0.354330447397412,18.0646627035298,20.125512341282,2.71741669120836,0.914613791254021],
[0,0,0,0,0.18866931662371,7.34857109549986,0.423377738210897,1.24220555276814,0.426986870350645],
[0,0.0478920527871059,198.086377414808,0,0.40573613499294,14.3902036861908,1.31099903502535,1.39842649624408,0.504474560698703],
[0,0,0,0,1.12229365088256,61.2014648009195,2.02068509660208,16.289882579228,2.37217889657222],
[0,0,64.8187691877834,0,4.70588849470696,77.0833568959159,4.96263869608985,25.8586022645505,10.1618286240365],
[0,0,0,0,4.15891956871774,54.9775864434201,0.249781492848221,95.6933004792504,40.5416126870126],
[0,0,0,0,2.78913817192601,37.1625692961837,0.380095614474158,19.2128217123483,15.2044777800525],
[0,0,0,0,0.0744712393923458,1.71237431746084,0.132630885279819,0.190967786553777,0.430068260764278],
[0,0,0,0,0,0.767664931966382,0.0486328066904822,0.596901294994933,0.357103791531336],
[0,0,0,0,0.9132852083891,20.3691361766511,0.321940080242562,4.71244903092318,2.18268597936098],
[0,0,334.970545150121,0,1.99409946266867,27.6944712907169,11.2072788832914,23.193349708262,6.01804627108865],
[0,0,0,0,0.0433800642994144,0.44200158710854,0,0.521112618791589,0.162743773292768],
[0,0,0,0,0.028412756546955,0.51551049187627,2.75871900820502,0.754889833821711,0.315863896098328],
[0,0.261115552012543,48.0489627056877,0,7.02190820216502,125.690215053382,21.6519429979393,14.4859073205552,12.359665018205],
[0,0,0,0,0.879038668787939,31.503718664042,15.7183717454963,4.43809523690569,4.24813240584689],
[0,0,21.2589964841028,0,1.23667517493491,29.6049430386443,20.9055025078791,29.4217591019819,6.30917147013855],
[0,121.785316650512,8708.90001432863,0,12.4550196813049,380.383127507905,29.5062240206663,37.8672902547754,25.3838770965065],
[0.0562822133458923,1.02632024378071,89.8779536597949,0,0.707849256842813,5.12988558551016,1.12490361571696,15.1682010575454,4.01288722398543],
[0,0,0,0,0.119151414595996,2.20003283947541,0.418445240250941,1.08295881137526,0.997246417700801],
[0,0,0,0,0.142432600199364,3.75460039121704,0,0.30474458415069,0.397245437899327],
[0,0,0,0,0.139033286512088,6.31614225528952,0,0.550393810889457,0.351352667440837],
[0,1.81108692975402,467.31472318235,0,4.59072279261821,89.0087475106968,3.7193815300382,73.7178611193649,16.8234298002061],
[0.186593869491055,1.99105987743062,37.6224340325068,0,6.90844615932732,66.3393081442403,28.9204616499899,38.1740572005324,9.92204636936513],
[0,0,0,0,0.0759814828557231,0.468293582820688,0.461018813471652,0.0943197976631189,0.352623677917389],
[0,0.567426062977756,44.4605551238034,0,0.410429678316362,15.7230551076944,2.76578510552782,0.249801860460742,1.06530035037552],
[0,0.237361742725757,14.9856036112105,0,2.8491632777029,131.090936913721,22.1279018472772,40.9357904540189,5.92624633677451],
[0,64.1194680291188,4754.9572963346,659.20423484312,11.124091720895,275.778753667843,35.0271156766769,86.6351548717039,16.4458599078633],
[0.47039867660324,108.800552014029,15480.5856338665,63.1121894186458,30.2991874716429,629.637009083804,74.379986891198,297.729144672351,66.4743070619919],
[0.364048810189914,42.0460801030249,15957.1367876977,525.002781069699,86.1942162838367,1081.75328089742,78.5417650960616,478.564686708423,254.967246300124],
[0,0,0,0,243.092871300575,1839.95743611188,165.847468640285,1768.03707814613,1406.04625714769],
[0,0.522881148061311,91.5805527169861,18.8542504469889,3.84111141698323,50.9415085070728,15.5921509966331,25.9875449682194,39.2549380325232],
[0,0,0,0,0.497848461324704,5.43029140755172,1.79355776274143,1.88649495039738,3.36110032088928],
[0,0,0,0,0.142335759582442,1.27578325505979,1.43758162553096,0.402922029718645,0.166389277884753]
        ]
       

#       in2in        in2dg        in2nf        in2pl         dg2dg          dg2nf        dg2pl         nf2nf         pl2pl
KALI_NONPEAT = [
[0,0,0,0,0.141898395770196,5.04137937066207,0,8.43633142092599,0.929263023452826],
[0,0,0,0,0.243136385289838,6.75179617841169,0,4.80809423480058,0.533540733361768],
[0,0,0,0,0.163535291617904,17.9619683545011,0,14.2369306182066,1.16238776939075],
[0,0,0,0,0.0061003704611507,0.437702073509896,0,0.220618305791912,0.0383000513537196],
[0,0,0,0,0.00419868683304416,0.557994690766836,0,0.335847064733673,0.0461618287808865],
[0,0,0,0,0.00380437309967666,0.23750730136304,0.878131839053386,1.42692523611751,0.223658747290698],
[0.00048812800946021,0,0,0,0.0370704404462311,4.02106896990643,0.135407476927308,2.99117784028273,1.10414667028501],
[0.0217950512816821,0.075668688499598,0,0,0.961712980653188,5.43320830304711,0.782294109558142,52.938523503534,6.50505979854233],
[0.0134675500619511,0.176134005663868,0,0,3.39288697189553,21.5084764722804,113.114151110409,165.459281281018,24.4042233043091],
[0,0,0,0,0.222288401033585,3.97079894893773,1.50689990292372,3.34257083863134,1.14159535094577],
[0,0,0,0,0.0146334396140677,0.241544555477277,0,0.124870626181157,0.0672749853829141],
[0,0,0,0,0,0.0190337912283179,0.226851932703073,0.052296539607846,0.0165990107881163],
[0,0,0,0,0.0189501489571428,2.72374327564718,5.72052541774091,0.739234098080591,0.265773020555465],
[0,0,0,0,0.000751582541533638,0.656762185373764,1.19211771265402,0.113298457079295,0.11918256513585],
[0,0,0,0,0.00400268495288158,2.53751207485317,13.1615936958364,0.314640930273736,0.276541053683804],
[0,0,0,0,0.0121301012680546,0.774440065083017,3.13809336910649,0.348025543915819,0.0819726655147324],
[0,0,0,0,0.00458392009912198,1.18961966743519,1.90837443092229,1.61378824073801,0.0666380322601847],
[0,0,0,0,0.0115073753942004,1.42047933619463,0.642525842121486,0.202744742030538,0.0781698674160583],
[0.00124754031345457,0,0,0,0.46616006498106,54.0840898947675,971.620853797119,16.6979714228122,7.46682612459072],
[0.201120989375111,2.35123973731279,0,0,17.9703908349688,367.547697179878,1216.59628609166,196.895478424134,99.491204307053],
[0.159606112367788,0.9361322812181,319.456798037224,0,20.523022843723,409.859858419373,646.171463159044,609.08222478095,195.641801327091],
[0.0227209514575995,6.72350882219362,31.0659200464728,0,22.7028024047767,466.973633160424,868.093378389013,466.74272628081,180.880278613975],
[0.00222531507291861,0.020976058788183,0,0,2.88890575533954,45.4938859289326,30.520111474812,14.0256143314826,15.7203039818291],
[0,0,0,0,0.0364691516528197,2.8164517718684,5.45211647241814,1.07014219455144,0.480802329022784],
[0,0,0,0,0.0175342321069389,2.68625781592241,0,0.151539092349077,0.126937563322665],
[0,0,0,0,0.0355933714784958,51.0893560586212,77.2674314920651,2.91458166277248,0.169819144672647],
[0,0,0,0,0.0211431210757555,17.3936021819163,8.58699972730376,1.13444905462082,0.188171827640688],
[0,0,0,0,0.0514172344420786,18.7076542309554,12.140124729372,0.873642643549419,0.286869163972301],
[0,0,0,0,0.0179294102229564,6.2607092380834,8.15715703207007,0.996151024873974,0.122791268531709],
[0,0,0,0,0.0188763991640117,4.62431405542575,10.5874894947598,0.419912135276066,0.115905799171654],
[0,0,0,0,0.0834307329295962,15.9644031511164,4.09055639859679,0.397106303039652,0.296254857696596],
[0.0241679002595746,0.0907764603094821,0,0,1.71488943190185,14.3548850013393,22.6225198138113,5.69261552259598,4.62291499505739],
[0.0314872792560485,0.107537119519053,0,0,3.8755675688935,39.9419573505136,1.39806525994032,17.1688848575286,10.0957923594863],
[0,0,0,0,2.41133443105714,32.5533994813153,6.95696843842552,5.94692684960439,4.80625317434818],
[0,0,0,0,0.116115724442259,1.62949967965776,0,0.925525504873541,0.369669557709035],
[0,0,0,0,0.00489542081317865,0.301987083625561,0,0.242017899539541,0.0672801905708212],
[0,0,0,0,0.0644978487957514,4.64709756311862,0,0.608608521977493,0.368036323216884],
[0,0,0,0,0.0182688587346885,5.6259431747717,0,0.586320857714679,0.12230956629636],
[0,0,0,0,0.00754223845257115,0.604040574737115,0,0.640785903918461,0.0264820833533872],
[0,0,0,0,0.00729464515687185,0.675205915733631,1.39496870391927,1.05452700262177,0.0713917322833523],
[0,0,0,0,0.0979291418054794,53.7305487738603,0.980948204583571,1.31849114125819,0.427650258793701],
[0,0,0,0,0.0825361081416504,10.3495917872069,0,1.44588306166675,0.776600272123579],
[0,0,0,0,0.034204128722632,11.655541544471,0,1.59053802548526,0.406299704727385],
[0.0111433310088932,0.437337154364124,0,0,0.371336244468295,7.24309405015358,4.06753232684012,2.14450178672301,1.48465221147588],
[0.0197659202820391,0.0754666438372122,0,0,1.60472755820661,3.5614927572157,0.167686036247238,3.17630797153937,4.16291834253167],
[0.0315434878795527,0,0,0,0.635278277485274,9.62612828193102,1.7142505285494,0.537233898435375,0.944115330104383],
[0,0,0,0,0.0536291773245414,6.2325809219733,0,0.201854684210138,0.166476252048662],
[0,0,0,0,0.0189660247388035,0,0,0.163343902483098,0.0388901760857501],
[0,0,0,0,0.00705875183156401,0.738735032285369,0,0.532083558015053,0.06043675721098],
[0,0,0,0,0.0107783181783702,0.424578050880922,0,0.353150741674759,0.101635993170785],
[0.0113217886275355,0,0,0,0.0580731343175588,9.8931102769011,0,0.695190628827643,0.0453352438973346],
[0,0,0,0,0.0319423755713694,18.0568788751163,0,1.18163158196641,0.189464918700653],
[0,0,0,0,0.0597546246022599,13.8143810032527,0,1.97725309786706,0.290901022094608],
[0,0,0,0,0.851894800488644,53.6730186667157,0,2.15912491130462,2.07423089189103],
[0.00146995720057281,0,0,0,2.37069785795754,113.496321644761,5.32023672481965,29.2315603020836,9.87770691097881],
[0.205664727612888,1.31762502904669,676.510609918428,0,13.016260316238,182.440645716603,0.898400390153746,109.179978504,49.3470946459444],
[0.356900956816167,4.31510345254784,3300.14328799671,0,28.0518169558918,541.017607261504,101.700921621849,691.500291336522,159.97157646753],
[0,0,0,0,1.592091854963,68.6871281138071,0,6.79863143146074,7.76714667562518],
[0,0,0,0,0.231589855873243,5.79023943680366,0,0.432189247162947,0.676276844685908],
[0,0,0,0,0.015194694888262,1.49169524765403,0,0.0380094377470179,0.108054091996207]
    ] 


#       in2in        in2dg        in2nf        in2pl         dg2dg          dg2nf          dg2pl          nf2nf          pl2pl
KALI_PEAT = [
[0,0,0,0,1.14567262211807,2.96531346083011,27.3307190064749,14.4520457623341,1.6454184297017],
[0,0,0,0,0.845743245095655,1.24155950362149,8.84240076494358,6.45035490974219,1.4905195824053],
[0,0,0,0,1.89756831608281,6.86708412035096,0,12.1728200224356,2.25556831108417],
[0,0,0,0,0.00342246092062386,0.0703900040577518,0,0.674621900565412,0.226343970577692],
[0,0,0,0,0.0054051426109136,0.00374671366578473,0.0388971716675158,7.4786259909714,0.366897104697019],
[0,0,0,0,0.0632144761419324,0.280879643270617,0,2.49881005284716,0.384164185246744],
[0,0,0,0,0.868056984751492,18.4856687098073,0,46.8369097587178,7.71368779888645],
[0,0,0,0,23.0766461199999,123.574494674767,0,269.725658137902,68.9553241069449],
[0,0,0,0,61.4223430453099,117.287899720042,0.130115170963729,879.187013617661,345.097807895228],
[0,0,0,0,3.11629309058904,6.17705027887684,33.0079248130038,31.761155548493,20.9193962107074],
[0,0,0,0,0.0178294576611451,0.156587087571791,0,0.277858529875381,0.0780000134529697],
[0,0,0,0,0,0,0,0,0],
[0,0,0,0,0.27968994360766,2.55191643462887,0,3.36400201722975,0.294793071717045],
[0,0,0,0,0.0174550793636596,0.199828180623469,6.45720927759445,0.591720128520843,0.248915509058177],
[0,0,0,0,0.55174084679505,10.6509174402706,20.0288624679866,2.89213011310205,0.947897131054468],
[0,0,0,0,0.0288959679382822,1.97353374517034,0.434767248060358,0.709298659086709,0.21503955284739],
[0,0,0,0,0.0467238200265344,1.60737662035448,12.5411478393468,1.49954002205318,0.21846448339775],
[0,0,0,0,0.0436368496429981,2.86850432547072,5.19778219231072,1.05509272407184,0.108254824943917],
[0,0,0,0,7.89872391199494,229.282771439861,293.236523486825,121.758495008586,30.6887565936191],
[0,0,0,0,72.4739999824835,794.130137018201,3391.35384253323,804.403302744312,404.534197452817],
[0.372113344183554,0,0,0,112.001701235109,1044.03888458148,5780.90100179906,2001.13824191351,1384.8811406524],
[0,0,0,0,242.028379640407,2861.9229519777,5530.6678137471,1583.24639551779,1846.16668537432],
[0,0,0,0,34.7525395449066,477.454815670077,62.5660585091058,111.833561078427,135.352162691085],
[0,0,0,0,0.302736747175432,0.507677341759706,1.21010459199045,2.88539899094043,0.979481761053562],
[0,0,0,0,0.0347033271222512,0.41953125504413,0,0.573686748034933,0.30795194937688],
[0,0,0,0,0.0477344177755645,83.9919043637239,156.154372295063,1.70570787248891,1.07649179939151],
[0,0,0,0,0.532228705031314,14.7641870106331,3.49604567071315,2.63633570623859,0.682220630231911],
[0,0,0,0,0.0382562183768374,38.2002612824561,8.36963589454525,1.04998165942004,0.608740321794993],
[0,0,0,0,0.1398903099726,4.259437381185,1.13040670497625,1.11602461507471,0.282797810120647],
[0,0,0,0,0.0443117479690747,1.88343713687678,1.74132235350525,0.360193551321105,0.0554036235793021],
[0,0,0,0,0.270094718561042,32.4898593792362,13.374639832241,15.7175657091611,1.12276140571385],
[0,0,0,0,4.68552138362742,125.98330998095,33.8137475836472,17.5149384166869,12.5136987377463],
[0,0,0,0,5.20428196987758,56.3299421882362,0,166.454022015819,61.1084454472506],
[0,0,0,0,2.77666320517699,50.1961738708367,2.42964691162571,31.4711254120297,20.1691399034211],
[0,0,0,0,0.0117641159727573,3.05112398668812,0,0.35386557170745,0.538014636077614],
[0,0,0,0,0,0.364237847416648,0,0.15302423139806,0.138565863473429],
[0,0,0,0,0.88471014077344,28.4401760177689,3.11320095972862,2.34577179326497,2.178300903267],
[0,0,0,0,0.0401049124473993,1.30288805524927,0,0,0.356254079694831],
[0,0,0,0,0.00412810198253858,0.612862168027897,0,0,0.106908268681099],
[0,0,0,0,0.0322416977149276,0.141876624699185,6.62654483761649,0.668329605380592,0.195750409049841],
[0,0,0,0,5.97589781363554,152.879884031221,31.1190720599306,3.86144120214939,13.0168012221352],
[0,0,0,0,0.432833238711999,58.0046790071701,34.2416705913142,1.04534090595404,3.39094621043624],
[0,0,0,0,0.13811135446945,7.98748185813757,0,2.44963792706405,0.934474860297936],
[0,0,0,0,1.63697379820702,42.8637047490675,0,4.94763122590811,2.87110001755147],
[0.124271446281445,0,0,0,0.83565308349831,8.75670813225785,1.01414056838525,25.8707133214879,6.47054295508041],
[0,0,0,0,0.150529158473235,1.82657701835727,0,1.72614014875709,1.72703459092226],
[0,0,0,0,0.145649101114342,3.87960078466344,0,0.157889734212817,0.333958630135967],
[0,0,0,0,0.0156066080897113,0.226392999334849,0,0,0.0953752400849899],
[0,0,0,0,0.0128163056910158,0,0,0.273831867235351,0.132129557029719],
[0,0,0,0,0.126441258077987,2.08956489756764,0,0.372501793234691,0.304473661195705],
[0,0,0,0,0.0403221251275634,0.176893276209182,0,0,0.164902754957128],
[0,0,0,0,0.11214796389799,22.4230989445465,0.290005995189384,0.259316943165782,0.266318349390898],
[0,0,0,0,0.495678452787675,163.008782876094,0,8.14844880990313,3.17122534164465],
[0,0,0,0,2.60769280040512,98.0736584873872,33.2714456907619,7.94568998636526,11.6125572985197],
[0,0,0,0,26.4655711878859,896.566452323318,81.0721489484593,179.213203880557,91.4674140769384],
[0.803821837661292,0,0,0,118.765812408311,2287.18945321392,230.786615195148,650.673897266211,405.669625302512],
[0,0,0,0,361.156713430694,4330.5907501266,66.5118509791295,2833.00938227805,2190.33400955188],
[0,0,0,0,5.2742832159808,94.6653193117802,115.479947527323,41.5069775016981,46.6104069598718],
[0,0,0,0,0.440116215727287,3.51420027332468,0,3.07183681594776,5.87979624376134],
[0,0,0,0,0.0822036706950086,1.59514410269574,0,0.290388548235962,0.120313172273648]
    ]


#       in2in        in2dg        in2nf        in2pl         dg2dg          dg2nf        dg2pl         nf2nf         pl2pl
SUMA_NONPEAT = [
[0,0,0,0,0.120703121608,14.9794332176265,0.357981103148019,0.43723505740209,0.359823210220344],
[0,0,0,0,0.810591206444419,31.4737046987557,5.74766573729406,2.59315449634913,2.47304128594596],
[0,0,0,0,0.931292355589687,14.9866598513115,0.057757635467517,0.960422461343263,3.23494817461169],
[0,0,0,0,0.22596426849281,1.83375081870666,0.527378203324721,1.06829702315233,0.537444443157773],
[0,0,0,0,0.345238062313016,1.14262095922809,2.80900400993976,4.37927976530373,0.416088192680782],
[0.00245593575158044,0,2.37504709155438,0,0.81192269099827,24.3843436157067,4.53309249088541,16.3485141240355,4.07968491195245],
[0,0.946156217313942,0,0,0.686862520684546,6.50961356252627,1.07714046618582,10.3211150987106,3.50891116216009],
[0.542664698579784,1.05664826328643,0,0,5.13374802559292,60.8864589637822,56.7932983755022,39.6944465976326,13.5989638072589],
[0.0351889347442764,0.099438648947489,0,0,0.663645876487579,15.360206468849,4.63384632278107,9.23479834156471,5.21571487358116],
[0,0.187715972980448,0,0,0.0752502989355917,0.784737579178057,0.289631541503268,0.506078293872877,0.386174588006619],
[0,0,0,0,0.0179186053632778,0.147296841144939,0.377613157050411,0.11284850200482,0.0588839447406469],
[0,0,0,0,0.0489415924642539,0.619361810058844,0.156835399333086,0.183465744538299,0.065509636377591],
[0,0,0,0,0.536810274894718,9.49927191083573,0.859859166946478,1.21196907925658,0.497125069638954],
[0,0,0,0,0.195687888069405,4.19735948777709,2.54564148274341,0.738720172309781,0.321245082715491],
[5.83515895558356e-05,0,0,0,0.246364442513415,9.56505104368369,2.17317724527496,1.42922636231535,0.530456193000527],
[0,0,0,0,0.0175753886695615,1.54744324427056,0.130125183613203,0.395685398601459,0.148012322988075],
[0,0,0,0,0.0897492225353858,3.31154946673539,1.32121985347194,0.555650292114737,0.280690860715202],
[0.00190830059637943,0.0231992721099628,0,0,0.454365162961465,19.9931068338013,5.62486761678987,1.9089337413248,0.952991820039366],
[0.00442423624411427,0.187755840453666,0,0,7.75472150501697,253.150189234536,40.5280489519708,30.756485119843,10.1589709030434],
[0.463553685873932,1.35322048411538,0,0,13.3452372960748,298.915366192499,56.9953657134319,118.975425593682,72.969279703497],
[0.118429973251961,0,0,0,6.84618657230987,45.2594428593525,12.5235464064996,269.949325002518,160.646086676175],
[0.024514953394494,0,0,0,4.78652667393901,61.8992098606132,37.139128874535,175.832360297881,135.761400540647],
[0.0214422953249877,0.0735841893000734,0,0,0.225468747446211,0.522156951047226,0.0297091586824667,22.7766452263133,15.9064716933043],
[0,0,0,0,0.00910948883948564,0.0787915699619255,0,0.298762741928729,0.143134937108137],
[0,0,0,0,0.291355718551979,2.45405482315874,0,0.434456671760483,0.413009890016342],
[0.0672475800543507,0,0,0,0.795353037352241,24.5475437691346,6.05398376530089,1.0641577091758,0.982149668908215],
[0.0234479285115962,0,0,0,0.297752945316091,23.234303234689,0.5779478194572,0.690015562492367,0.638371262676717],
[0,0,0,0,0.0817501243797677,1.06566030460466,0,0.342323341857608,0.173048704605972],
[0,0,0,0,0.0656970887020114,0.915495237654975,0,0.80886270479305,0.295748554918371],
[0,0,0,0,0.106867405169221,3.40265786529096,0.261255841537114,0.592786364641101,0.430754093015225],
[0.0235039611966004,1.51483887547148,0,0,1.39250157099278,31.5755442733584,1.96669258278429,8.4962771883729,2.59939157025547],
[0.0234440103073512,0.0590078710505272,0,0,1.47572485137853,23.0954254934635,8.10891937980938,9.35985004911814,11.033463462544],
[0.0216034528366366,0.371005224222489,0,0,3.64720018979135,34.6534909554203,3.98594109885395,52.6397807023267,29.1369412340724],
[0,0.994789712371869,0,0,0.460437354618292,7.18667775384967,0.455833348312687,4.98450501460632,5.02257984726353],
[0.0423714706181032,1.74510340631858,0,0,0.185321424484753,2.42924051886728,1.92044427865477,0.455582375759733,0.464886649849658],
[0.0178360028231508,0,0,0,0.00806114867403704,1.29722072653162,0,0.113691303834068,0.143772957177751],
[0,0,0,0,0.077379599119594,1.16555100689788,0,0.165694628343919,0.218116133498342],
[0.0224757396287047,0,0,0,0.332135122705947,8.42418968231316,0.291447407608845,0.610470970277343,0.405475151500196],
[0,0,0,0,0.0451371480073834,0.117207443723212,0,0.186760381218415,0.120277919619735],
[0,0,0,0,0.044512527005587,0.111059416135458,0,0.687708201891567,0.187402666272971],
[0.226799838700096,0.176643374647474,0,0,2.70715297722257,74.8256812705946,10.9082595592717,3.48331674750995,3.18466851002963],
[0,0,0,0,0.926645856705905,42.7996295613443,0.424393870634883,3.07658570573257,1.05985608027721],
[0.00812042564855084,0.205187118799444,6.31962376664306,0,2.38481972873317,82.0761400437818,3.35902367567046,31.202979346896,5.48564611844452],
[0.202947802261494,0.730067949340245,177.646453845561,0,7.14294167226558,288.911926609381,19.9299375840378,11.1821824625579,8.59957988265024],
[0.0120310175176854,0,0,0,1.44457559765225,24.8583800807699,3.41858994191493,2.2309385747159,3.64614252117216],
[0,0,0,0,0.166213395000063,2.62049179406717,0.37489369419325,0.47014376728668,0.647561867538631],
[0.132276933781286,0,0,0,0.312613484738457,2.83936516661604,11.0244096757687,0.357618628626187,0.281479316407635],
[0,0,0,0,0.0554778022576765,4.78516427048498,0,0.251989840434891,0.0866408753847286],
[0,0.107152387161781,73.9141426155772,0,1.02793928485911,67.7957579561563,0.786064266835947,1.14990747989259,0.721087593070703],
[0.00652200331441643,0.479580677817881,0,0,0.999530881813634,26.3630413678979,5.06598445820932,1.62395394783625,0.900883170072705],
[0,0,0,0,0.0323549260314406,2.03779884775054,3.29719928780189,0.300582489314887,0.210579693777916],
[0.016327182478265,0,0,0,0.281144802913357,23.3966587623149,0,3.72849302533968,0.78514589614252],
[0.308111738999638,0.85091183086093,3.81082959214817,0,4.76967186776014,307.224738364964,50.8149535203278,5.31439234000853,1.72526067316471],
[0.218199073242027,0.148099958177258,322.754748378957,0,4.82091848001994,187.393740479224,16.0959279847774,9.61392390907155,3.3116664413481],
[0.116527067519473,0.992666744035188,911.961856671343,0,6.91923238972445,232.202914602036,55.7855255052644,25.5173255608938,12.0141962845166],
[0.030580103494392,0.0413568786369661,759.253894815995,0,7.76847760867569,168.07673383771,22.1226262228166,37.4343858802541,23.8413897961632],
[0.0589479059282674,0,0,0,1.618245991526,6.73391695097645,1.71225729812729,89.4616180146209,61.4596496103959],
[0.0105980250409623,0,7.29608734391017,0,0.323352740958419,14.4361641455001,6.64925320690155,5.60719194703266,1.90466645052374],
[0,0,0,0,0.163362960586318,7.24044741758639,1.32674547705792,0.393860435097785,0.260732098663845],
[0,0.526587511800424,0,0,0,0,0,0.0570860293949095,0.0322533253279867]
    ]


#       in2in        in2dg        in2nf        in2pl         dg2dg          dg2nf        dg2pl         nf2nf         pl2pl
SUMA_PEAT = [
[0,0,0,0,63.9743113310572,157.103129949692,13.3215239191195,641.17572335183,109.375734691543],
[0,0,0,0,184.504414488364,253.746601315547,203.310546636453,1096.84170610007,326.745766054364],
[0,1.96494332699923,0,0,74.0841082253856,290.375586725843,59.7741968071433,913.004072662895,124.221167848375],
[0,0,0,0,3.98529425915448,10.4377502992021,1.77084291310235,40.2665678308601,4.36923614378273], 
[0,0,0,0,0.26131254920119,10.1416357934874,0.586145626773855,21.275872383307,1.05615794362632],
[0,0,0,0,5.7002991053978,92.329050211664,0.821373844163692,551.753820459179,17.0016578818352],
[0,0,0,0,4.64006833539366,51.5586902695285,0.862414010985492,101.362357444919,13.5270621110338],
[0,0,0,0,66.6264676022699,919.415955545056,36.0860253199621,1640.39857120152,96.2773768628549],
[0,0,0,0,1.23774330405105,38.3984503053421,1.71320623087855,56.7897928477496,4.49028058626804],
[0,0,0,0,0.0230883234832095,0.550185087840895,0.477213764040605,1.20450625085598,0.187655155094136],
[0,0,0,0,0.0169099603143175,0.0579360857980009,0.458895623943672,0.345129079852066,0.0475224835605797],
[0,0,0,0,0.0278800096221191,0.77072039834675,0.865524850141572,1.28368742474833,0.0895663568792758],
[0,0,0,0,0.353041425278311,14.4187343297233,5.64562839838988,20.3570865301753,1.09828553103713],
[0,0,0,0,2.98581176103041,33.1987643676318,2.47707833754147,59.1395467317476,5.2317676745652],
[0,0.171520815697716,0,0,15.1129205452133,172.640860563568,15.6976450056932,115.273073855696,22.2467919887329],
[0,0,0,0,0.131496922219656,5.05302713295854,0.321665743890904,4.69826254738128,0.399878394610718],
[0,0,0,0,0.861304655463137,27.2341289411056,4.03303237169954,36.5778456359475,1.13547147837616],
[0,0,0,0,1.5015016750999,37.525615766485,4.60424241710969,16.9601092884257,2.275012017038],
[0,0,0,0,21.1799918645792,678.276837329769,13.6726714904964,397.484695325822,27.1222819923706],
[0,1.15820298533004,579.711523172439,0,86.4022683676816,933.903565569876,30.150281491439,1225.28066993304,165.778749608615],
[0,0,0,0,16.6070911367568,221.786165659973,0.538615276399663,761.622684444589,1290.03543858356],
[0,0,0,0,21.6254056567367,96.7381893757353,38.7265833473136,1255.36093715572,1627.20237922145],
[0,0,0,0,0.152298237604158,1.58117546775493,0,84.1401589412164,74.0635544654676],
[0,0,0,0,0.0131071367110964,0.14594737954522,0,0.557854453826242,0.75206499522963],
[0,0,0,0,0.555165439705832,8.54678292228802,0.226489298770974,2.22853913858047,0.844268855815117],
[0,0,0,0,6.91008865788739,190.130029343721,18.638626651602,97.6799570999046,35.7077451883176],
[0,0,0,0,2.46021759991088,191.829308425334,21.1023803831621,43.2931071428797,20.0838743048661],
[0,0,0,0,0.912258061999976,3.49050240362979,21.4814184962383,4.56901444112749,1.22677846980124],
[0,0,0,0,0.274772998369188,9.58448823318902,0.341830017620852,1.38232276025253,0.574141612853581],
[0,0.0478920527871059,198.086377414808,0,1.04371489946315,23.4426100404722,1.2613661523737,2.55132885709322,0.96278199409169],
[0,0,0,0,2.62657737230562,81.9829448370302,0.711136023089811,16.925409966295,3.64729442095841],
[0,0,64.8187691877834,0,4.74184009296325,41.6895367357962,1.63499262093784,35.1237963574303,7.76158521839065],
[0,0,0,0,2.31366773442026,53.9987504117928,0.278590936795814,17.1172898509699,19.5517610706267],
[0,0,0,0,2.81115872216847,27.7288372115906,0.143703267948773,5.60062866407544,10.1377024282121],
[0,0,0,0,0.185160541384765,0.743386372837399,0.147928343917039,0.0100784765013991,0.31990164314418],
[0,0,0,0,0,1.05966573723187,0.0542420457993819,1.08980312116996,0.580136610243028],
[0,0,0,0,0.96372531975568,14.5273119085394,0,7.34051798982764,2.18716124775122],
[0,0,334.970545150121,0,5.44324975160413,46.7967176497805,12.4999105715383,48.948328651488,11.7962902703262],
[0,0,0,0,0.112666806757936,0.318332579430821,0,1.09978041334676,0.219727703214673],
[0,0,0,0,0.0216539897252481,0.785946945620909,2.31260944996328,0.851010354956596,0.438447878749686],
[0,0.261115552012543,48.0489627056877,0,8.86830385020664,106.01031367717,20.5600177277921,26.2838107973905,11.6890128291661],
[0,0,0,0,1.66667115624636,12.3223050781422,13.5819206668434,8.20556813117553,5.12294921692478],
[0,0,21.2589964841028,0,3.17583704124789,45.251676523454,23.3167135861274,59.3728623989194,11.7944149025522],
[0,121.785316650512,8708.90001432863,0,31.5508078856163,624.67992118581,32.9094301482918,74.4228174111066,48.3596972370582],
[0,1.02632024378071,89.8779536597949,0,0.482252616572759,2.50478889576423,1.13767886886794,3.28363149494924,1.50468240114196],
[0,0,0,0,0.0637640777438666,2.47034042335837,0.466708122166985,0.36874020952129,0.252447952818725],
[0,0,0,0,0.136754900095743,3.66412501922861,0,0.467819069528418,0.461833929463074],
[0,0,0,0,0.356903476321306,10.7239070155271,0,1.16157680895766,0.612595041508801],
[0,1.81108692975402,467.31472318235,0,12.6715475217949,153.43334105975,4.14836973283696,155.27354197992,33.8580369015068],
[0.341058268018476,1.99105987743062,37.6224340325068,0,18.8798992844432,112.843317132801,32.2561067746276,80.1506701427039,19.7374334251959],
[0,0,0,0,0.138926634876441,0.679209328054152,0.514192071081927,0.19905690693361,0.54420564701107],
[0,0.567426062977756,44.4605551238034,0,0.936950318485897,10.8735587040049,3.05133796491944,0.239235868148554,1.8807158224774],
[0,0.237361742725757,14.9856036112105,0,7.00348543942147,107.988777737288,24.6801027356526,77.3443862054014,8.73793263587261],
[0,64.1194680291188,4754.9572963346,659.20423484312,26.157060873225,404.40182554312,35.2296121686024,174.015612488556,21.3785739416618],
[0.859799726315099,108.800552014029,15480.5856338665,63.1121894186458,37.0662067098946,436.433291832148,73.6081223888346,429.334781543419,40.9671415303894],
[0,42.0460801030249,15957.1367876977,525.002781069699,28.6995164285554,209.257738349935,60.9820595100894,287.446579595498,101.165219008302],
[0,0,0,0,34.6890478867166,37.2353057297324,177.304698222733,585.442083760033,605.62726510244],
[0,0.522881148061311,91.5805527169861,18.8542504469889,1.3113065492843,19.2941837408137,4.07123388469904,8.75404212631724,31.7481817344671],
[0,0,0,0,0.599756213094353,6.81715950734931,2.00042417723543,0.570235972208493,0.790599830892157],
[0,0,0,0,0.248479664506278,1.04462965072496,1.60339025606065,0.527884464315228,0.213413077373596] ]
