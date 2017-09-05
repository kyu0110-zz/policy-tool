import ee

def getEmissions(scenario, year, metYear, logging, oilpalm, timber, peatlands, conservation):
    """Gets the dry matter emissions from GFED4 and converts to oc/bc using emission factors associated with GFED4"""

    print("SCENARIO", scenario)
    peatmask = getPeatlands()
    if logging:
        loggingmask = getLogging()
    if oilpalm:
        oilpalmmask = getOilPalm()
    if timber:
        timbermask = getTimber()
    if conservation:
        conservationmask = getConservation()

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
        #oc_ef = [2.157739E+23, 2.157739E+23, 2.082954E+23, 1.612156E+23, 1.885199E+23, 1.885199E+23]
        #bc_ef = [2.835829E+22, 2.835829E+22, 2.113069E+22, 2.313836E+22, 2.574832E+22, 2.574832E+22]

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
        ocpo = total_oc.multiply(ee.Image(0.5))# * 2.1 ))  # g OA
        ocpi = total_oc.multiply(ee.Image(0.5))# * 2.1 ))  # g OA
        bcpo = total_bc.multiply(ee.Image(0.8 ))        # g BC
        bcpi = total_bc.multiply(ee.Image(0.2 ))        # g BC

        emissions_philic = ocpi.add(bcpi).multiply(ee.Image(1.0e-3))  # to kg OC/BC
        emissions_phobic = ocpo.add(bcpo).multiply(ee.Image(1.0e-3))

        return emissions_philic.addBands(emissions_phobic, ['b1']).rename(['b1', 'b2'])


    def convert_transition_emissions(oc_bc_emissions):
        # first mask out data from regions that are turned off
        if logging:
            maskedEmissions = oc_bc_emissions.updateMask(loggingmask)
        else:
            maskedEmissions = oc_bc_emissions
        if oilpalm:
            maskedEmissions = maskedEmissions.updateMask(oilpalmmask)
        if timber:
            maskedEmissions = maskedEmissions.updateMask(timbermask)
        if peatlands:
            maskedEmissions = maskedEmissions.updateMask(peatmask)
        if conservation:
            maskedEmissions = maskedEmissions.updateMask(conservationmask)

        # split into GEOS-Chem hydrophobic and hydrophilic fractions
        ocpo = oc_bc_emissions.select('oc').multiply(ee.Image(0.5))# * 2.1 ))  # g OA
        ocpi = oc_bc_emissions.select('oc').multiply(ee.Image(0.5))# * 2.1 ))  # g OA
        bcpo = oc_bc_emissions.select('bc').multiply(ee.Image(0.8))        # g BC
        bcpi = oc_bc_emissions.select('bc').multiply(ee.Image(0.2))        # g BC

        emissions_philic = ocpi.add(bcpi).multiply(ee.Image(1.0e-3)).rename(['b1'])
        emissions_phobic = ocpo.add(bcpo).multiply(ee.Image(1.0e-3)).rename(['b1'])


        return emissions_philic.addBands(emissions_phobic, ['b1']).rename(['b1', 'b2'])


    if scenario=='GFED4':
        emissions = monthly_dm.map(get_oc_bc)
    else:
        emissions = monthly_dm.map(convert_transition_emissions)

    return emissions


def getDownscaled(emissyear, metyear, peatmask):
    """Scales the transition emissions from the appropriate 5-year chunk by the IAV of the meteorological year"""

    # read in IAV based on metYear
    IAV = ee.Image('users/karenyu/dm_fractional_'+str(metyear))

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
    elif emissyear > 2005:
        start_landcover = ee.Image('users/karenyu/marHanS2005_sin')
        end_landcover = ee.Image('users/karenyu/marHanS2010_sin')

    # get the transition emissions
    transition_emissions = getTransition(start_landcover, end_landcover, peatmask, year=(emissyear-2005)%5 )

    print(ee.Image(transition_emissions.first()).bandNames().getInfo())

    # scale transition emissions based on IAV
    def scale_IAV(emissions):
        return emissions.multiply(IAV)

    scaled_emissions = transition_emissions #.map(scale_IAV)

    return scaled_emissions

def getTransition(initialLandcover, finalLandcover, peatmask, year):
    """ Returns emissions due to land cover transitions at 1 km resolution in kg DM per grid cell"""
    # get masks for the different islands
    islands = ee.Image('users/karenyu/indo_boundaries_sin')
    suma_mask = islands.eq(ee.Image(2))
    kali_mask = islands.eq(ee.Image(3))
    indo_mask = suma_mask.add(kali_mask).lt(ee.Image(1))

    initial_masks = []
    final_masks = []

    # area of grid cell (m^2) and g to kg
    scaling_factor = 926.625433 * 926.625433 * 1.0e-3

    reverse_peatmask = peatmask.subtract(ee.Image(1)).multiply(ee.Image(-1))
    # order: DG, IN, NF, TM, OPL, NPL
    for i in range(1,5):
        initial_masks.append(initialLandcover.eq(ee.Image(i)))
        final_masks.append(finalLandcover.eq(ee.Image(i)))

#       in2in    in2dg     in2nf   in2pl  dg2dg    dg2nf   dg2pl   nf2nf   pl2pl
    initial_index = [1, 1, 1, 1, 0, 0, 0, 2, 3]
    final_index   = [1, 0, 2, 3, 0, 2, 3, 2, 3]
    gfed_index    = [1, 1, 1, 1, 1, 1, 1, 3, 3]

    oc_ef = [2.62, 9.6, 9.6, 4.71, 6.02, 2.3]
    bc_ef = [0.37, 0.5, 0.5, 0.52, 0.04, 0.75]

    emissions_all_months = ee.List([])

    for month in range(0,12):
        kali_nonpeat_rates = KALI_NONPEAT[month+12*year]
        kali_peat_rates = KALI_PEAT[month+12*year]
        suma_nonpeat_rates = SUMA_NONPEAT[month+12*year]
        suma_peat_rates = SUMA_PEAT[month+12*year]
        indo_nonpeat_rates = INDO_NONPEAT[month+12*year] #INDO_NONPEAT[month]
        indo_peat_rates = INDO_PEAT[month+12*year] #INDO_PEAT[month]
        #accumulate emissions    926.625433
        kali_nonpeat_oc = initial_masks[1].multiply(final_masks[1]).multiply(ee.Image(kali_nonpeat_rates[0] * scaling_factor * oc_ef[1]).updateMask(kali_mask).updateMask(peatmask))
        kali_nonpeat_bc = initial_masks[1].multiply(final_masks[1]).multiply(ee.Image(kali_nonpeat_rates[0] * scaling_factor * bc_ef[1]).updateMask(kali_mask).updateMask(peatmask))
        kali_peat_oc = initial_masks[1].multiply(final_masks[1]).multiply(ee.Image(kali_peat_rates[0] * scaling_factor * oc_ef[1]).updateMask(kali_mask).updateMask(reverse_peatmask))
        kali_peat_bc = initial_masks[1].multiply(final_masks[1]).multiply(ee.Image(kali_peat_rates[0] * scaling_factor * bc_ef[1]).updateMask(kali_mask).updateMask(reverse_peatmask))
        suma_nonpeat_oc = initial_masks[1].multiply(final_masks[1]).multiply(ee.Image(suma_nonpeat_rates[0] * scaling_factor * oc_ef[1]).updateMask(suma_mask).updateMask(peatmask))
        suma_nonpeat_bc = initial_masks[1].multiply(final_masks[1]).multiply(ee.Image(suma_nonpeat_rates[0] * scaling_factor * bc_ef[1]).updateMask(suma_mask).updateMask(peatmask))
        suma_peat_oc = initial_masks[1].multiply(final_masks[1]).multiply(ee.Image(suma_peat_rates[0] * scaling_factor * oc_ef[1]).updateMask(suma_mask).updateMask(reverse_peatmask))
        suma_peat_bc = initial_masks[1].multiply(final_masks[1]).multiply(ee.Image(suma_peat_rates[0] * scaling_factor * bc_ef[1]).updateMask(suma_mask).updateMask(reverse_peatmask))
        indo_nonpeat_oc = initial_masks[1].multiply(final_masks[1]).multiply(ee.Image(indo_nonpeat_rates[0] * scaling_factor * oc_ef[1]).updateMask(indo_mask).updateMask(peatmask))
        indo_nonpeat_bc = initial_masks[1].multiply(final_masks[1]).multiply(ee.Image(indo_nonpeat_rates[0] * scaling_factor * bc_ef[1]).updateMask(indo_mask).updateMask(peatmask))
        indo_peat_oc = initial_masks[1].multiply(final_masks[1]).multiply(ee.Image(indo_peat_rates[0] * scaling_factor * oc_ef[1]).updateMask(indo_mask).updateMask(reverse_peatmask))
        indo_peat_bc = initial_masks[1].multiply(final_masks[1]).multiply(ee.Image(indo_peat_rates[0] * scaling_factor * bc_ef[1]).updateMask(indo_mask).updateMask(reverse_peatmask))
        for transition_index in range(1, 9):
            kali_nonpeat_oc = kali_nonpeat_oc.add(initial_masks[initial_index[transition_index]].multiply(final_masks[final_index[transition_index]]).multiply(ee.Image(kali_nonpeat_rates[transition_index] * scaling_factor * oc_ef[gfed_index[transition_index]])))
            kali_nonpeat_bc = kali_nonpeat_bc.add(initial_masks[initial_index[transition_index]].multiply(final_masks[final_index[transition_index]]).multiply(ee.Image(kali_nonpeat_rates[transition_index] * scaling_factor * bc_ef[gfed_index[transition_index]])))
            kali_peat_oc = kali_peat_oc.add(initial_masks[initial_index[transition_index]].multiply(final_masks[final_index[transition_index]]).multiply(ee.Image(kali_peat_rates[transition_index] * scaling_factor * oc_ef[gfed_index[transition_index]])))
            kali_peat_bc = kali_peat_bc.add(initial_masks[initial_index[transition_index]].multiply(final_masks[final_index[transition_index]]).multiply(ee.Image(kali_peat_rates[transition_index] * scaling_factor * bc_ef[gfed_index[transition_index]])))
            suma_nonpeat_oc = suma_nonpeat_oc.add(initial_masks[initial_index[transition_index]].multiply(final_masks[final_index[transition_index]]).multiply(ee.Image(suma_nonpeat_rates[transition_index] * scaling_factor * oc_ef[gfed_index[transition_index]])))
            suma_nonpeat_bc = suma_nonpeat_bc.add(initial_masks[initial_index[transition_index]].multiply(final_masks[final_index[transition_index]]).multiply(ee.Image(suma_nonpeat_rates[transition_index] * scaling_factor * bc_ef[gfed_index[transition_index]])))
            suma_peat_oc = suma_peat_oc.add(initial_masks[initial_index[transition_index]].multiply(final_masks[final_index[transition_index]]).multiply(ee.Image(suma_peat_rates[transition_index] * scaling_factor * oc_ef[gfed_index[transition_index]])))
            suma_peat_bc = suma_peat_bc.add(initial_masks[initial_index[transition_index]].multiply(final_masks[final_index[transition_index]]).multiply(ee.Image(suma_peat_rates[transition_index] * scaling_factor * bc_ef[gfed_index[transition_index]])))
            indo_nonpeat_oc = indo_nonpeat_oc.add(initial_masks[initial_index[transition_index]].multiply(final_masks[final_index[transition_index]]).multiply(ee.Image(indo_nonpeat_rates[transition_index] * scaling_factor * oc_ef[gfed_index[transition_index]])))
            indo_nonpeat_bc = indo_nonpeat_bc.add(initial_masks[initial_index[transition_index]].multiply(final_masks[final_index[transition_index]]).multiply(ee.Image(indo_nonpeat_rates[transition_index] * scaling_factor * bc_ef[gfed_index[transition_index]])))
            indo_peat_oc = indo_peat_oc.add(initial_masks[initial_index[transition_index]].multiply(final_masks[final_index[transition_index]]).multiply(ee.Image(indo_peat_rates[transition_index] * scaling_factor * oc_ef[gfed_index[transition_index]])))
            indo_peat_bc = indo_peat_bc.add(initial_masks[initial_index[transition_index]].multiply(final_masks[final_index[transition_index]]).multiply(ee.Image(indo_peat_rates[transition_index] * scaling_factor * bc_ef[gfed_index[transition_index]])))

        # add to collection
        oc = kali_peat_oc.unmask().add(kali_nonpeat_oc.unmask()).add(indo_peat_oc.unmask()).add(indo_nonpeat_oc.unmask()).add(suma_peat_oc.unmask()).add(suma_nonpeat_oc.unmask())
        bc = kali_peat_bc.unmask().add(kali_nonpeat_bc.unmask()).add(indo_peat_bc.unmask()).add(indo_nonpeat_bc.unmask()).add(suma_peat_bc.unmask()).add(suma_nonpeat_bc.unmask())
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

    mask = ee.Image('users/karenyu/peatlands')
    return mask

def getConservation():
    """Get boundaries for conservation areas"""
    #fc = ee.FeatureCollection('1mY-MLMGjNqxCqZiY9ek5AVQMdNhLq_Fjh_2fHnkf')
    mask = ee.Image('users/karenyu/conservation')

    return mask


# Data for land cover emissions
#       in2in             in2dg          in2nf        in2pl         dg2dg          dg2nf        dg2pl         nf2nf         pl2pl
INDO_NONPEAT = [
        [0,               0,             0,           0,            0.126468664,   8.095330537, 3.074121942,  0.8981308992, 0.5437315408], #0501
        [0.0002142532906, 0.01882082839, 0,           0,            0.419107835,   13.68455636, 4.992601463,  1.224905343,  1.327373486],  #0502
        [0.0006371033727, 0.02098192195, 0,           0,            0.5610106261,  12.9715665,  2.888307422,  1.79579604,   1.967945064],  #0503
        [0,               0,             0,           0,            0.04371785951, 1.944288923, 0.7675191809, 0.5696320405, 0.2433009629], #0504
        [0.000465907284,  0,             0,           0,            0.03907231567, 1.433473195, 0.3826001204, 1.280888517,  0.2475396002], #0505
        [0.0002946935754, 0,             0.4866126084, 0,           0.2190509472,  12.62933679, 4.091800655,  3.547408225,  2.048807514],  #0506
        [0.01626062269,   0,             0,           0,            0.1616643924,  9.52988979,  3.356835988,  4.648076757,  1.999061892],  #0507
        [0.06010067786,   0.1169658276,  0,      0.2084429595,      1.218613913,   54.55897637, 23.51157724,  18.38159061,  9.595124633],  #0508
        [0.03057529972,   0.1295910034,  0,      0.7309380706,      2.825866211,   20.00165241, 11.20656716,  37.67886144,  17.79334733],  #0509
        [0.004303910525,  0.1597591627,  0,       1.892081162,      0.2499328084,  2.398389415, 1.347623951,  2.56613575,   1.210392739],  #0510
        [0.01156696154,   0.1555434558,  0,           0,            0.02601621523, 0.2881683998,0.1869554559, 0.3154801618, 0.1296531209], #0511
        [0,               0,             0,           0,            0.007465686211,0.3577478048,0.141733953,  0.06251310179,0.02990244852],#0512
        [0.0006057657525, 0,             0,        1.831084046,     0.09590987963, 6.679941938, 1.788662735,  0.2817922135, 0.2917503357], #0601
        [0,               0,             0,           0,            0.04139274314, 2.768780376, 1.209159568,  0.2800514078, 0.199078356],  #0602
        [0.0002688951948, 0.01161171833, 0,           0,            0.07669710716, 4.706531409, 2.20000783,   0.4156842674, 0.3701568538], #0603
        [0,               0,             0,           0,            0.01269038387, 0.906101222, 0.5277469272, 0.2900381297, 0.1212965326], #0604
        [0,               0,    1.439852414,          0.5185850996, 0.03271482866, 1.538278822, 0.5003646529, 0.5761327888, 0.1839548517], #0605
        [0.0002289815299, 0,             0,           0,            0.07392567287, 9.468284472, 2.031344345,  0.8833662405, 0.4560847896], #0606 
        [0.01152033845,   0.05456938876, 2.754367238, 0.7123384017, 1.493670968,   140.2101506, 41.79583121,  11.83852237,  7.478854875],  #0607
        [0.1156109857,    0.9710091859,  51.08467439, 8.476463172,  8.94710079,    296.8050981, 150.4007659,  61.23636967,  61.39827184],  #0608
        [0.07381120421,   0.135965197,   10.63624374, 1.450272464,  13.61954826,   203.6360122, 134.377815,   149.3050091,  144.6995524],  #0609
        [0.10147939,      1.176988747,   172.4601344, 10.24024945,  16.22324207,   325.9246929, 170.6029373,  128.5442044,  146.3158223],  #0610
        [0.09631870388,   0.1390829623,  83.44298137, 2.175507604,  3.154565115,   24.21330009, 16.54773763,  20.75617836,  17.65354362],  #0611
        [0.04977861735,   0,             77.75572501, 2.459015139,  0.4597587705,  1.822143369, 1.067463501,  1.759145707,  0.8901386385],  #0612
        [0,               0,             25.0581161047431,0,0.0717128875373262,2.10617855881496,0.448007581672363,0.271208660077717,0.247028802548807],
        [0.0065708533664452,0.0244116062368389,53.6120543556178,2.99222707533947,0.172587455049592,43.6673608419059,7.34628964063392,0.564848299858828,0.67868248403088],
        [0.00271940148872365,0,0,0,0.102957863409372,18.3085566005758,3.45216731671468,0.399462915529398,0.403745501261559],
        [0,0.0754356622714885,73.0124382738264,4.58058885387527,0.0937778237917119,16.8477605957563,1.87329103725705,0.29884299337516,0.189734576182922],
        [0.00116925228787315,0,0,0,0.0228754349369444,3.22323024960873,1.18920005473688,0.518335232018755,0.202071636962712],
        [0.000109801651054241,0,36.5076665107108,0,0.0378383127569034,2.98872476809825,1.12999718171297,0.426879895421266,0.200160042693292],
        [0.00496302245400627,0.0814803286258948,0,0,0.28945276436865,27.9668173427171,7.2128984391177,2.7180644596883,1.27214293491172],
        [0.00888808938442338,0.0556151868550316,8.56403593032662,0.621157203429698,0.72435986406719,25.740729476508,9.03603194855621,5.65300985548002,5.63872992221301],
        [0.0165021777737508,0.428758140909768,45.9999483033953,7.66352510245057,2.36061189380357,51.2109575005853,27.8066772815666,23.7918976214963,16.1858982905269],
        [0.0427816627789966,0.215552242005351,4.66475847983198,0.647742614641478,1.28595127079115,28.0074057333779,13.5171910940949,5.32003674154107,4.84246809701633],
        [0.00344269198095622,0.0638965873941728,0,1.001541854182,0.358078699704191,3.97697764628239,5.47012770385998,1.11447982288956,0.693842313366061],
        [0.00214018442474024,0,45.0699295125889,9.10947964646415,0.0572825565027349,1.88771473906934,1.10783485564791,0.202256349282455,0.140831709181671],
        [0.00663320374448012,0,0,0,0.0657585093858398,5.55957171616481,1.32799229307798,0.288930366127094,0.270132764652573],
        [0.000837628674551008,0,0,0,0.0839887609160862,5.82487085713106,1.42678641364716,0.264071287098785,0.26219306155179],
        [0,0,0,0,0.0252249186719389,1.07576426748209,0.271612807169687,0.353215720044263,0.0890193678773371],
        [0,0,0,0,0.0126678045325273,0.688565729499123,0.229321092265401,0.598133827158904,0.103131697301536],
        [0.0400792698758897,0.0509839701140626,0,1.33812893588462,0.534321682188373,57.4090761927245,16.9809799092405,1.83949136856549,1.42387232664019],
        [0.00028226774538045,0,0,0,0.187464053383936,26.3801346444412,5.5035177851645,1.8164334898192,0.702129008137505],
        [0.000974389198508815,0.0219731149593941,2.58959800485401,0.295238603262341,0.46576741681144,27.2291229987364,8.91780972809038,9.30346824491763,2.65804737379426],
        [0.0338267925964012,0.396581309468274,140.049965520327,15.002168271158,1.44199799282261,92.2406430031774,33.2381232643113,5.76822224674708,4.29957492078814],
        [0.00819702428740284,0.0764675614899853,5.55726008038335,0.159112815330318,0.810020174845782,11.551780020724,6.07869850786907,6.45076985545509,3.49798494950208],
        [0.00476448546052839,0,0,0,0.306652541616711,4.61862395369509,1.72779207018786,1.70023638424854,1.08944682237372],
        [0.018407742121313,0.0814345684554234,9.57759068343622,0,0.0916406268661044,5.32737762290701,2.11460509118248,0.699262892889512,0.340465047341252],
        [0,0,0,0,0.0177003103038301,1.97423491926442,0.434432428993856,0.212685458160114,0.0795643479926637],
        [0,0.0627904145474762,17.8056588465717,6.7623483241394,0.192150179041589,35.8128704137066,5.13306575247179,0.580409431382856,0.53085267611242],
        [0.000782590700475081,0,0,2.55005989617642,0.157439706811093,10.9779349113912,4.23625584206838,0.39488509505132,0.476394716553414],
        [0,0.032052285181568,0,0,0.0207876986792137,3.84308287179817,0.484394148257528,0.465773447740933,0.122128965798133],
        [0.00402072088737975,0,1.4211030185278,0,0.0714957437176223,20.2674158719046,1.83839613087055,1.26148396740856,0.404709617937457],
        [0.0129004394186573,0.166639768457731,0,0.732270164180161,0.810914444507611,103.947852868187,21.7789215709401,1.70290381907173,1.1873316629337],
        [0.0235216367578336,0.00333039977866643,52.1973581430224,7.56179571871965,1.19717795333237,103.302187548577,20.5574492736373,3.11250654894779,2.26392547448579],
        [0.0119217300197482,0.327714618481511,349.340075983684,61.6239512286683,2.09392860127273,152.954374396254,52.5509558361387,15.8349025155426,10.2122809740522],
        [0.0682416497688895,0.369131788586172,516.995458783299,42.2709199634209,7.05843473403051,176.965915212205,87.8920053652098,28.2048912020477,29.6796685475175],
        [0.26074489980889,1.18320840498468,123.539114873043,24.7567694532329,14.4413720570869,331.740607602814,125.397369630147,131.366169280896,125.190362959438],
        [0.095641005257619,0.0594185391575845,32.1090919624179,0.141372851559407,1.60292173750736,41.4195715463661,14.4825918843626,6.74015213826783,6.8178018074921],
        [0.0309689830760065,0,9.03447441642539,3.0073764377212,0.533465491027819,10.4652226384753,4.44637287582397,2.28918652574057,1.76322926929396],
        [0.000847655988466698,0.1208747510124,0,0,0.0534923225971646,0.695626644628736,0.166182996694984,0.469940791666896,0.149053247194794]
    ]

#       in2in             in2dg          in2nf        in2pl         dg2dg          dg2nf        dg2pl         nf2nf         pl2pl
INDO_PEAT = [
        [0,               0,             0,           0,            18.2132396973583,109.61453371701, 54.0868107669118,408.726572762009,90.6551893996921], #0501
        [0,               0,             0,           0,            56.6391537628736,231.340246787279,272.152085454495,677.638725149537,238.379371677876], #0502
        [0,            0.82294531181905, 0,           0,            28.0010129434829,215.234572765821,130.019960522975,494.130383507705,109.923763745767], #0503
        [0,               0,             0,           0,            1.30248196436994,10.9804429445114,12.1656111726976,12.146844302034, 3.73878268953857], #0504
        [0,               0,             0,           0,            0.23931155771026,8.02618983166835,1.75753116806299,16.7409158856217,1.53351732614104], #0505
        [0,               0,             0,           0,            5.07504764459719,91.1807201861616,20.9054967551746,274.185372437051,22.7490282675401], #0506
        [0,               0,             0,           0,            1.99519103273836,52.0494560657791,8.29982161872361,79.4865275046815,15.7384149899228], #0507
        [0.0102557891461718,0,           0,           0,            47.0622922241102,875.703899304423,326.268194388286,721.117214689971,150.201128396664], #0508
        [0.0242309784734087,0,           0,           0,            37.8746889219643,79.8033869189937,52.4439998117259,428.251077416467,189.900830840733], #0509
        [0,               0,             0,           0,            2.109967449675,  4.2330362076155, 2.40370086832141,21.167902049338, 12.944654384054],  #0510
        [0,               0,             0,           0,          0.0106847527797957,0.100848494446217,0.0907540056389329,0.153789908618314,0.0975839796383151], #0511
        [0,               0,             0,           0,      0.00729115363532433,0.542284654738693,0.652824922968682,0.698599334480409,0.105070778480429], #0512
        [0,               0,             0,           0,            0.179876528379909,19.2665865435827,4.77307958706703,8.11667132346641,1.49187036098544], #0601
        [0,               0,             0,           0,            0.997730526273808,24.3162864994941,8.07642193998495,28.5485584050548,5.7112247944742],  #0602
        [0,           0.0528988348504998,0,           0,            4.57797657618547,117.452767502042,46.7772477333189,58.8583816176369,21.5642227076084],  #0603
        [0,               0,             0,           0,            0.055185079865127,4.67566915356915,1.09948589323259,2.15859942864273,0.556066249011236],#0604
        [0,      0.0572879499544666, 0.661976085879814,0,           0.485084451505118,26.8372891996102,6.07258566551129,12.2431450947935,2.57749277703421], #0605
        [0,               0,             0,           0,            0.658779340565469,26.6415252292529,6.16963753630122,9.33328196690188,2.67756189090157], #0606
        [0,               0,             0,           0,            14.6928555578135,549.083006358126,137.889934566665,194.021345731735,50.5811206828798],  #0607
        [0,        0.617005528444354,495.099354261432,16.5099634830248,69.3939002421175,1116.2155764971,319.154212202503,952.073734626241,308.344999171801],#0608
        [0.0571439562882872,0,           7.0267304698577,0,         68.0492193672383,749.910641140283,451.489777810784,1269.19447194687,1509.94968535963],  #0609
        [0.0106443238680452,0.55485955657371,104.404773628935,0,    144.237025550819,1402.94281413795,739.518441987653,1688.84397977856,1996.95787964984],  #0610
        [0,               0,             0,           0,            17.5108271358224,203.726429492907,113.408364968052,127.541925714991,105.05527459579],   #0611
        [0.107368019862205,0,            0,           0,            0.0790389424280789,0.147806262131709,0,            2.3558288667481, 1.28020078169953],  #0612
        [0,0,0,0,0.0723358711757417,3.74058430074513,3.32034744617522,2.94994889069608,0.854916739361423],
        [0,0,0,0,1.88023914839571,147.23510302598,50.8341363566053,54.8901134100529,26.7483350386843],
        [0,0,129.183170363608,0,4.18123196392851,100.512302852668,20.118675876144,34.3723938081242,13.4778448864661],
        [0,0,0,0,0.23594731069286,3.84134433208557,9.27871366102974,3.61708572596368,0.993276985784852],
        [0,0,0,0,0.13448788586231,7.31661919818908,1.4628823740864,1.14822706982749,0.704229531059278],
        [0,0.0221556239184754,60.3197124644604,0,0.325491298925383,12.5758155672551,8.90636955498683,2.05732614264823,0.6433846337841],
        [0,0,0,0,0.769203291649227,46.1686452762059,18.3697527016483,10.2432201901668,3.64204551913712],
        [0,0,120.132503989566,0,3.39929949041422,69.2503411521096,19.1020097239623,28.9559742951198,11.8167724292755],
        [0.0301198030203287,0,0,0,4.00607836817226,61.8868134966581,13.7082843507254,42.607212948104,35.0269654945277],
        [0,0,0,0,2.39397628547353,25.4534039714512,24.9613804944817,7.59396823065581,15.180020622492],
        [0,0,0,0,0.0605253707366589,1.67924420587859,1.3592340665268,1.04670573843244,0.237300131923187],
        [0,0,0,0,0.0324784631690791,1.28401029331149,0.0636568148038252,1.27786800624976,0.408975822445238],
        [0,0,191.687280486297,0,0.825900399319296,21.3241791985479,4.66456607090096,5.16325797634719,2.79650515450632],
        [0,0,38.8182667561978,47.3033742065435,1.53666496090126,28.8963274183433,20.4808216935557,28.6758201011314,9.48143701557189],
        [0,0,0,0,0.0666775219662703,0.335075282492559,0.146802551869162,0.123690888373475,0.382872685183522],
        [0,0,0,0,0.0643826593471904,0.604693739638036,0.334723263605005,0.815891500262122,0.319638376140879],
        [0,0.120796199648963,20.0068857188295,7.82123200020578,5.30938846433477,135.776603382269,41.8678786378746,9.93818166149538,17.3677459624522],
        [0,0,0,0,0.751666537252937,23.9052857338367,15.0383099194456,6.31553425226405,5.83765875006331],
        [0,0,0,0,1.52176853651092,29.1751070000777,21.6701836969315,24.0205100428164,10.1505836763036],
        [0,54.5623090050643,7702.81083108426,420.613917769436,11.3756633410766,373.466880962715,145.844515250343,43.5658791568793,35.8374478143038],
        [0,0.474792037822518,78.6374908194956,3.03455313149265,0.376357871453878,9.83765394047907,3.00789113800857,2.6440353926796,3.06893009343823],
        [0,0,0,0,0.0676644076753401,2.26036599704742,0.908886098739516,0.405666752988492,0.76852030945324],
        [0,0,0,0,0.147447146126464,3.67235470715147,1.1499030564214,0.521782542329858,0.413243255168546],
        [0,0,140.313911968139,0,0.130752409288448,4.64297189001867,1.70364931353427,0.68030118087127,0.469784712797238],
        [0,0.360788272742241,104.964745606418,2.97785651489446,4.19377084101113,67.6495727734464,41.8929594334404,86.1421670002539,24.2284888435449],
        [0.0649057256334133,2.22528024413936,0,0,6.01183954925856,63.5978723837795,49.3516101556429,43.4554498452634,16.7347289165415],
        [0,0,0,0,0.059926851897974,0.343868544826821,0.757903026402775,0.114628534305607,0.455712412540724],
        [0,0.262500304784759,25.0435650361494,0,0.600649686035159,12.5773517168707,4.7689512481246,0.603336857408626,1.17653423456],
        [0,0.0319207297514729,2.74917493236751,0.511466337566799,3.79371827217201,150.68080966399,30.9915049025727,35.9172396226052,8.87142962524767],
        [0,33.9092587395492,2375.93740276305,319.237652533544,12.4275044385301,255.722296008847,101.974227654024,85.2565600256038,27.1414878061632],
        [0.113526281214821,50.2585896529415,10046.5224568511,574.694010733039,24.764272410371,736.583049702649,261.766376685603,203.157617578176,63.0895256852022],
        [0.0286368062605177,23.5026146561504,6934.25705052477,916.444787758586,66.6539365261531,1131.48603645134,342.458034886585,497.643413075423,287.052740958333],
        [0.101537031970425,0,0,0,206.256434150225,1864.12787787629,615.432516951555,1510.04916903109,1343.83006572323],
        [0,0.483786239872376,40.0635783310917,7.45357141066961,4.12242336953539,31.119406648712,22.4191127441765,23.2723816013088,44.0354453826243],
        [0,0,0,0,0.394843414190704,8.71985299215791,5.28431651015326,1.68959483917285,3.58464834093651],
        [0,0,0,0,0.103485852719142,1.69037562044916,0.899809467963256,0.412576052205806,0.25463013506765]
    ]
       

#       in2in        in2dg        in2nf        in2pl         dg2dg          dg2nf        dg2pl         nf2nf         pl2pl
KALI_NONPEAT = [
        [0,         0,            0,           0,            0.331708585832679,7.6547494012543,4.90830888303383,5.2747832367022,1.09206173767653],
        [0,         0,            0,           0,            0.215073067939497,7.27663960152063,5.96496494755527,3.0454389192096,0.489897584902251],
        [0,         0,            0,           0,            0.618224416352075,13.3588143009681,3.93728446862657,8.34821441354794,1.74280515998342],
        [0,         0,            0,           0,            0.00363645498250971,0.426874660909499,0.106709575381463,0.251657803229281,0.0471600052034655],
        [0,         0,            0,           0,            0.00156198148849879,0.186261830532257,0.224519072156636,0.252165819427254,0.0732781885814704],
        [0,         0,            0,           0,            0.00806597300551262,0.523273411752145,0.113354304431444,1.27700046413552,0.239561251335556],
        [0.000259197884551638,0,  0,           0,            0.0815766185150368,3.02282212976471,2.32133233657131,3.39449754250721,1.249469287783],
        [0.012710008761238,0.10384294420103,0, 0.929722996233893,1.36738692567232,9.46563880663533,9.88021023302174,52.5046276193902,9.68732044350943],
        [0.0108767860071335,0.193267820425399, 0, 0,         4.65574590121618,25.3526638001514,17.554232836271,203.984189274514,41.4084243557172],
        [0,         0,            0,           0,            0.32526194585202,3.82057498646759,1.81602951747791,4.77565554075695,1.51285625208343],
        [0,         0,            0,           0,            0.0129745918531377,0.122556863837429,0.069501387339188,0.11010777207204,0.0713953451474321],
        [0,         0,            0,           0,            0,             0.0540968338986586,0,0.0380673506682151,0.0142825880375858],
        [0,         0,            0,           0,            0.0440875639605659,2.68052259061789,1.16085391769174,0.492624733910028,0.263238658023815],
        [0,         0,            0,           0,            0.000858712717207488,0.291604086145761,0.451402109006026,0.0559426800025092,0.129771295600874],
        [0,         0,            0,           0,            0.0149261768891761,2.13641400566909,0.919352545116908,0.317444793259908,0.289998615305396],
        [0,         0,            0,           0,            0.0245496244668265,0.65958492764525,0.269614143692581,0.202708273609225,0.100717626318109],
        [0,         0,            0,           0,            0.011368003414185,1.12191676090153,0.222490835738234,0.833799053253443,0.0949154171637785],
        [0,         0,            0,           0,            0.0142007641564605,0.668892896873828,0.281469459033298,0.143941789393492,0.0868427141131412],
        [0.00161208069670569,0,   0,           0,            1.40965284596381,69.447749177361,50.2623472577231,32.105365546414,9.34546822399754],
        [0.148441205635251,1.81658695653405, 0, 27.7450525154948,21.8646799124013,346.891934877,227.317221360751,228.475712221591,111.981392981732],
        [0.144272759808098,0.487763658583927,  58.0557515095229,0,38.3481482298139,348.835741563301,277.246118103814,668.922643669564,260.533533564823],
        [0.00122992400422333,4.18295496292328, 40.0744927980014,11.6164023194436,42.456470198678,544.221724780914,343.623415669019,500.406473346507,278.538486731046],
        [0,         0,           10.6188447957345,0,         5.27847894236326,38.7737350056544,29.8700291906377,15.6514858297297,22.7540153000422],
        [0,         0,           0,            0,            0.0313534696235369,1.90939068631276,0.80006511710685,0.856752212837657,0.527136108760286],
        [0,0,0,0,0.0389925031160059,2.11283206236656,0.358544316682982,0.119920870737888,0.123470033075423],
        [0,0,0,0,0.0332120786114234,57.1802426893722,11.0456274795087,0.553089554734944,0.452510334245007],
        [0,0,0,0,0.103569541658204,17.8652090396758,3.63307273747715,0.718729878702682,0.281013414092415],
        [0,0,0,0,0.269191353518451,30.9923046880638,3.39651974757785,0.517090677322787,0.397228867960352],
        [0,0,0,0,0.0311584234562878,5.27633449900432,2.20649702286802,0.586654763673802,0.15863451817111],
        [0,0,0,0,0.0352387207385936,3.93600194272133,1.10230954044011,0.215813786003933,0.125978748612581],
        [0,0,0,0,0.099051530710332,24.4208243552369,4.79442683703099,3.91080266977585,0.399874408943448],
        [0.0231375657340265,0.0816188821283256,0.858267328055342,0,1.62816179713991,34.6416140257195,11.5599210351187,6.44486109631061,4.94393173110926],
        [0.0246239698193139,0.182468839964764,0,0,3.61539293722958,41.3165488379061,27.2476254127336,49.8288656804531,12.8872518305114],
        [0.0117556256120776,0,0,0,2.33285722462834,32.5485401468867,15.364165943367,9.68552099326974,6.08357704968931],
        [0,0,0,0,0.114057040882937,1.59651035110171,0.779660623935748,0.848559897007637,0.368991251342332],
        [0,0,0,0,0.00477068037764872,0,0.259384121243233,0.257799265255562,0.0531219487353313],
        [0,0,0,0,0.0950442223112262,8.73664539875666,0.945676318025546,0.688931642686549,0.437298187694055],
        [0,0,0,0,0.0374363344703509,4.75115880096065,1.03799155123562,0.412840032679119,0.166183338757104],
        [0,0,0,0,0.0128982522905629,0.811360966485745,0,0.415759439530748,0.0224920614940538],
        [0,0,0,0,0.0155427917394885,0.871172893132008,0.136331693748036,0.779122992286394,0.0902191713942462],
        [0,0,0,0,0.258144762016976,76.6084330503361,10.5824174562185,1.41904203846375,0.866932529200418],
        [0,0,0,0,0.0949012738705574,27.3240802071186,2.31300083307507,0.887737276899099,0.749825044276841],
        [0,0,0,0,0.0493165680402037,9.42498939975933,1.43696749115335,1.03395814358232,0.510388703764657],
        [0.0118016061370957,0.305015202901854,0,0,0.530192445170036,11.8992194197953,5.84516305530259,2.20001837441661,1.50675276193076],
        [0.0264302876794978,0.0544118927132689,0,0,1.37460007965815,3.48721399665192,5.84854127232822,9.65507034763892,4.16210599546483],
        [0.0157901851428615,0,0,0,0.574604387343879,6.13870943594222,1.92350003769148,0.861243085099393,1.08203764988578],
        [0,0,0,0,0.0685237235066538,6.65358532744053,0.732987923636929,0.196555810208452,0.148917667752853],
        [0,0,0,0,0.0249656739317816,0,0,0.0495614271341359,0.0731622887850579],
        [0,0,0,0,0.00953367285991816,0.71906174881166,0,0.238462684112445,0.0646632230458932],
        [0,0,0,0,0.0193805681533865,0.390925183421787,0.200293517334457,0.263588381140757,0.102132140051266],
        [0,0,0,0,0.0360630264160153,5.57255555894379,0.356041403778089,0.486482283891656,0.0906814140847393],
        [0,0,0,0,0.0590214487405442,23.2674011532134,0.909080015970814,0.786235661168982,0.187038204962713],
        [0,0,0,0,0.229220277211867,19.0908300559576,3.94704647901161,2.45815264010977,0.61014532655704],
        [0,0,0,0,1.07191031891307,50.7930693355916,14.5920359705874,3.07937525658389,2.8382716570187],
        [0.00169691769985076,0,0,0.0997917255887856,3.16081762370568,140.34705043862,50.4119393384723,60.0330454807202,16.6427668870048],
        [0.195340016794302,1.37471559543758,73.8152110435356,15.2173574834603,17.8951150000818,233.191868973288,117.613731677691,118.821420293578,65.7043668887283],
        [0.279546599699191,2.77158122019759,876.076607642251,70.6729487168584,42.6185462405203,619.341487989074,277.125523437496,851.391895271105,316.587611926378],
        [0,0,0,0,2.05547746660841,66.0004005401633,24.5951012261866,11.3866096924081,8.86922388123376],
        [0,0,0,0,0.233396482945797,4.98211086799232,1.36249465520963,1.58108862261266,0.82599248012883],
        [0,0,0,0,0.0183327340360962,1.0998122764632,0.118546290765401,0.0595904095477636,0.106953962846184]
    ] 


#       in2in        in2dg        in2nf        in2pl         dg2dg          dg2nf          dg2pl          nf2nf          pl2pl
KALI_PEAT = [
        [0,          0   ,        0   ,        0   ,         0.433665158001377,0,          1.38972605328482,22.2061519491548,2.01817333149979],
        [0,          0   ,        0   ,        0   ,         0.112891156449748,1.21382666233261,1.32999137031361,15.2450263876597,1.82408922806392],
        [0,          0   ,        0   ,        0   ,         0.127598948027437,0.0987751272055991,0,      9.48381896983098,2.17477877979208],
        [0,          0   ,        0   ,        0   ,         0.00362049486677976,0,        0.159628673426899,2.45429082882845,0.125386277210032],
        [0,          0   ,        0   ,        0   ,         0.000227069219684983,0,       0.0436031040592018,22.8712989544282,0.881792025627216],
        [0,          0   ,        0   ,        0   ,         0.0535954755375268,0.0963310697319351,0.140704347947672,2.37048058838684,0.343352925878885],
        [0,          0   ,        0   ,        0   ,         0.814162057515152,19.6284388597542,2.75767007160008,130.396295127392,13.9199765460984],
        [0,          0   ,        0   ,        0   ,         25.8184335056146,84.0274149610757,157.447598679046,488.008582931273,134.288321339896],
        [0,          0   ,        0   ,        0   ,         84.9685461396138,150.921419195029,137.772357978589,1627.44350031085,562.353796003517],
        [0,          0   ,        0   ,        0   ,         4.7658069601906,10.1076911315244,7.5031498379854,83.856031279843,38.8033233290556],
        [0,          0   ,        0   ,        0   ,         0.00840238451448946,0.13393321888802,0,      0.161133568246952,0.141488096998992],
        [0,          0   ,        0   ,        0   ,         0,0,0,0,0],
        [0,          0   ,        0   ,        0   ,         0.143113238806654,4.63206749661364,0.561717672568723,5.79442711720859,0.603043219111233],
        [0,          0   ,        0   ,        0   ,         0.0335522608309769,0.599349138444922,0.376704586658762,1.28265771916258,0.435044192268563],
        [0,          0   ,        0   ,        0   ,         0.206367987975356,17.8181317841393,12.3679497616779,5.92782108513566,2.21099808554703],
        [0,          0   ,        0   ,        0   ,         0.0254643217013386,2.83711306018628,0.761776060064733,0.352861094483959,0.217460627438674],
        [0,          0   ,        0   ,        0   ,         0,             1.28696292874153,0.661192281515994,1.3299370902779,0.590931714798763],
        [0,          0   ,        0   ,        0   ,         0.0158700386942943,2.64184289458993,0.881851106462896,1.3179999657664,0.38424648057064],
        [0,          0   ,        0   ,        0   ,         8.38525277835691,261.571931351463,69.1354433626341,131.567861576733,43.5264266433777],
        [0,          0   ,        0   ,        0   ,         87.8270818110879,1173.50791892699,539.748375140782,1202.42844057038,543.562333877084],
        [0,          0   ,        0   ,        0   ,         140.753222761897,1573.40038516807,1474.12688529181,2897.37609463108,1941.17873144483],
        [0,          0   ,        0   ,        0   ,         310.089336243454,3427.5662101529,2647.61208676785,3005.41510950626,2671.98523515487],
        [0,          0   ,        0   ,        0   ,         39.2901098422425,515.132072616247,422.563895914028,277.253837010487,193.960584413242],
        [0,          0   ,        0   ,        0   ,         0.0616806676253939,0.300274470650153,0,      7.848734758087,1.62145910430889],
        [0,0,0,0,0,0,0.274800407668905,1.46020764525838,0.643117271674052],
        [0,0,0,0,0.162099835710594,63.2633816379855,4.46858724936124,10.2290448803395,2.6847685370921],
        [0,0,0,0,0.0710666272986206,6.2407222832204,1.06133773708072,3.80695550419322,1.52249504795561],
        [0,0,0,0,0,4.30180001133144,2.10464173478639,0.736595144491012,0.0332799794353341],
        [0,0,0,0,0.0356058366496388,2.53016036536082,0.228529556268072,1.78336888896235,0.810037735015771],
        [0,0,0,0,0,0.616179936743747,0.0630558308465809,0,0.155560392914003],
        [0,0,0,0,0.220648316015382,11.8315740114303,6.57301243906203,1.59967477702075,2.61772477097229],
        [0,0,0,0,3.49252691107105,126.719350669255,38.1909422683363,22.9082977981213,18.5932955780407],
        [0,0,0,0,4.70233964593438,70.2204423847213,12.870611551572,133.598407508535,74.4658171570316],
        [0,0,0,0,2.68329981900472,36.8599553874876,51.3309051133081,20.7771315979156,25.1816412628752],
        [0,0,0,0,0,2.17470743488959,3.34419395971846,2.47904388661548,0.230460251923631],
        [0,0,0,0,0.038000247178471,0.459957152514711,0,1.25608453787942,0.106496735203622],
        [0,0,0,0,0.59422988848948,29.8640637193459,11.8206107138692,4.26428821990986,3.9814052957441],
        [0,0,0,0,0,0.301657252524547,0.261398495607598,0,0.0421971405225927],
        [0,0,0,0,0,0.314131085167569,0,0,0.208173353444344],
        [0,0,0,0,0.0495546128433606,0.293787294029423,0,0.66474764524014,0.141969600022685],
        [0,0,0,0,6.46384551094527,157.419916883411,65.1876044389537,4.91898334528949,21.0212073223991],
        [0,0,0,0,0.832421875186718,47.5333295517862,17.2959804139352,2.86533799836937,5.98689707357843],
        [0,0,0,0,0.122331908939082,10.6435195631203,4.26858815097965,1.8209975162873,0.956837158583232],
        [0,0,0,0,0.874931950187703,39.5578575816762,5.18484028989048,5.49418384341466,3.82161765968895],
        [0,0,0,0,0.46702879950337,21.0716118431833,7.4602926621836,7.07043375372034,6.12350542317532],
        [0,0,0,0,0.0513588773865247,2.65066545254047,2.06026029361803,1.05267221574073,1.7250868458043],
        [0,0,0,0,0.130746229741557,3.34592060164487,1.7957574295175,0.442819616887461,0.495508819670432],
        [0,0,0,0,0,0.373622982855499,0,0,0.0415546222127236],
        [0,0,0,0,0,0,0,0,0.226261330237217],
        [0,0,0,0,0.116052206419069,3.62836482279123,0.656448658598883,0.803611478931444,0.51940338431784],
        [0,0,0,0,0.0310254361014222,0.278425115656573,0,0,0.286846463701906],
        [0,0,0,0,0.154634679916504,16.4297284022971,6.83572987404819,0.188102927695676,0.13969648817601],
        [0,0,0,0,0.560283518080917,171.706396634718,9.86579060553685,5.43793334046377,4.11967535657951],
        [0,0,0,0,3.04314535355857,99.9479380935053,34.1325788304043,11.4240928676479,13.1375806936383],
        [0,0,0,0,26.9079695781241,1013.37662266574,331.3622309986,115.532201534053,106.350731906137],
        [0,0,0,0,134.506667254343,2588.49498998673,1034.26969520823,1380.61934766772,664.38136905297],
        [0,0,0,0,437.137678275364,4576.98081013026,2132.40987551677,4457.59364658826,2909.58237511504],
        [0,0,0,0,7.94710419466333,55.1341866412844,60.1750326081521,58.9327600419763,71.5895018995678],
        [0,0,0,0,0.444743594141601,11.0649647942,11.1414851924409,4.04775302024288,8.63294402602239],
        [0,0,0,0,0.00269936475650061,2.39951643689886,1.08648829640043,0.241048104611297,0.257299784371592]
    ]


#       in2in        in2dg        in2nf        in2pl         dg2dg          dg2nf        dg2pl         nf2nf         pl2pl
SUMA_NONPEAT = [
        [0,          0,           0,           0,            0.141407318660674,10.1929944736626,2.45547296377941,0.934985845619184,0.571133152598292],
        [0.00179835516790388,0.0077570040354415,0,0,         2.34908063123527,25.2427722671811,6.39229117738353,3.4219138978516,3.2490425533639],
        [0.00534758714693163,0,   0,           0,            2.45000531701715,15.031248167097,3.13179240644172,3.00229534533409,3.8636657754395],
        [0,          0,           0,           0,            0.279665720151973,4.41850460682842,1.92661914728248,1.67928877452138,0.583004265029243],
        [0.0039106366564806,0,    0,           0,            0.244475332655683,3.43130373817633,0.761135085710914,3.46224167820493,0.56898713776611],
        [0.00247353827297001,0,   3.450752779704,0,          1.36013834648593,31.7418245612809,10.8010196259883,12.0032328662344,5.38158082969737],
        [0.135828607718478,0,     0,           0,            0.55949106093953,20.3993340358765,6.26923274000322,8.33051716406681,3.58237472811291],
        [0.463074374886174,0.519779809985713,0,0,            4.55458191180253,127.251060944897,50.8265426648063,39.1483353701879,16.9493174557764],
        [0.0392316678612583,0.0705437063490065,0,0,          0.592275305402192,13.8975885278644,7.50631777978354,10.4416530303888,4.94021344950983],
        [0,          0.0984791954508626,0,     0,            0.0669334398221191,0.4643362546202,0.659727266059102,0.494747277287429,0.36430014946926],
        [0,          0,           0,           0,            0.010934429109709,0.444609811509436,0.103345284967913,0.128840125139796,0.0580552621050258],
        [0,          0,           0,           0,            0.0387697294382907,0.846050649108185,0.378698143592637,0.14085532214185,0.0643624304590081],
        [0.00508455188128589,0,   0,           0,            0.522310600794883,13.2689793755988,2.97130591067213,0.817392823806553,0.548109254965777],
        [0,          0,           0,           0,            0.231678302639577,6.64872612430634,2.67823798840798,0.770043800516603,0.411247560003204],
        [5.87698151050795e-05,0.0673516409513571,0,0,        0.380015229598215,9.13490947818588,4.808914577692,0.892594190905769,0.710504129352543],
        [0,          0,           0,           0,            0.0270543440324998,1.43645552423209,0.507549253156265,0.309581858170427,0.163186765211477],
        [0,          0,           0,           0,            0.157859322309269,2.39137625519869,1.01292787835861,0.830236579128025,0.328347994709381],
        [0.00192197803158633,0,   0,           0,            0.43032918776983,23.3866483423599,5.07099691595651,1.36106473259746,0.988462484866845],
        [0.00803561410397135,0.316519723772878,0,3.2937486067904,6.87647781580497,264.648978407524,51.5501379397385,22.0034084423079,11.6854344382509],
        [0.478627105582356,1.43596152907508,214.804845057869,3.64429077901145,13.9231701405149,288.255805534767,131.456505426783,120.769306310384,72.3440248228347],
        [0.103233788034995,0,     0,           0,            7.84520137640244,40.3871169807798,24.950671985298,243.915989275326,173.05999037237],
        [0.00927181405833486,0,   0,           0,            5.68484337511404,63.7771815662117,26.8110953664273,178.901045144458,147.899579323291],
        [0.017230075566154,0,     0,           0,            0.20719664438176,0.921259357118464,0.47447055883394,21.9607641388703,17.9084989653675],
        [0,          0,           0,           0,            0.00736784195821156,0.0199456088104428,0.0403924026320432,0.291990829485471,0.151751797289217],
        [0,          0,           0,           0,0.268844071077208,2.07844623940891,0.780015805849315,0.4028995625386,0.423224266689714],
        [0.0551530764257196,0,0,0,1.02506806382762,34.8997055610991,6.59220765413034,1.58174533601927,1.45413352465748],
        [0.0228255524473728,0,0,0,0.409928824441063,22.0156123107501,4.57246837852213,0.743214993282379,0.836905784794069],
        [0,          0,           0,           0,0.0459119483248436,1.0220039198005,1.01203375367137,0.304837337091907,0.173093317737471],
        [0,          0,           0,           0,0.0559984058558339,1.14898565420969,0.61110042422207,0.555589025715904,0.323364887981095],
        [0,          0,           258.88957566153,0,0.124182040654193,2.35833913478862,1.68955044050451,0.647124886230977,0.362426831846759],
        [0.0234694263266502,0.472611691193602,0,0,1.61683857183852,38.8135422416062,13.5777017023276,6.06633250648761,2.90919893855203],
        [0.00250000273090415,0.197882260176447,59.8725421776434,2.87214007924533,1.5720909984157,19.1670726338367,10.6982938804292,8.80424666709205,10.9025918937145],
        [0.00208075500204519,0,   0,9.12163773985048,3.7271752842323,43.0491581937766,17.3368770513999,43.1234385195802,28.0985556039952],
        [0.0628818112846509,0,    0,0,0.728870871294307,5.76143485147551,2.72645944382068,4.75549123721225,4.87028118718439],
        [0.0213375806324759,0.370620427520743,0,4.6309830821488,0.178307325491882,1.52204843926888,1.96255736326937,0.463028562242261,0.432394926840285],
        [0.0179638394832559,0,    0,0,0.0214315687413044,1.32549109595079,0.48090930539661,0.141249215825792,0.116181974606238],
        [0,          0,           0,           0,0.0999266705292918,1.16922563487136,1.09317248408569,0.129419709105159,0.245254385418144],
        [0.00703071514878116,0,   0,           0,0.361190468606128,8.5434521313796,2.60496287699425,0.349796230825334,0.520305236722686],
        [0,          0,           0,           0,0.037494993907342,0.0651491914477951,0.165485506996433,0.205373689337888,0.128298669029704],
        [0,          0,           0,           0,0.035123387771369,0.255398868119229,0.45415805267561,0.661105536818306,0.174726078324473],
        [0.304286296216522,0.295723160985307,0,6.18731253011556,2.98505627663824,43.8296498179163,32.9240418255324,2.41928858520817,3.08927008482439],
        [0,          0,           0,           0,1.01609049027764,30.5759537752629,11.7331239172082,2.53219422619062,1.15566259030692],
        [0.00817862748363623,0.127451020349105,18.3638121163922,1.36514012988687,2.85147528977154,56.7799078999401,22.096743538269,25.4496255189834,6.2606638158568],
        [0.245694562992258,1.8342720901193,885.186388908613,63.5189901099303,7.87168363666116,220.913011859589,82.0104030112259,10.3855444308341,9.32073781260244],
        [0.00162700333364594,0.360401502306528,0,0,1.27464604238809,23.4586245986306,7.57318629417306,2.31315670725068,3.4790533342293],
        [0,          0,           0,           0,0.157699746444911,2.50711697500425,0.76206302842731,0.453039652238217,0.609004524317967],
        [0.133225007258153,0,0,0,0.255181841616749,3.03615585788832,2.54521352841406,0.554858847847886,0.209912349144958],
        [0,          0,           0,           0,0.0491204533689714,5.072501498027,1.16075753845709,0.325101157436117,0.0957167091286781],
        [0,          0.36420427495182,126.266614761875,31.2681098187996,1.23904718232655,91.0115919229815,13.70645235587,1.67451827857502,1.32564716948011],
        [0.00656874873114239,0,0,11.7911040745315,0.960253910056034,27.6777045326332,11.0858719957425,1.25208000611901,1.19772351707277],
        [0,          0,           0,           0,0.0464429371358843,2.34116854335685,0.859756274710369,0.315761713120273,0.195335724291196],
        [0.0275418840994594,0,10.07757527669,0,0.301562588086092,20.5201871130749,3.83122082257345,3.4369923760502,0.868205244398444],
        [0.108281052932321,0.966563391668618,0,3.3859101621373,4.91144272965974,241.198964824949,53.5804279487025,4.43005912704067,2.6759830210702],
        [0.162768494370217,0.0193173726504353,370.151072140843,34.9646376712406,5.78697199727968,196.733019165525,37.6338202324473,7.39062982980459,3.70274394550908],
        [0.0777460176993899,1.90084849535316,2477.30169241161,284.836688996567,7.5270870125462,200.890852233541,79.9186615973122,27.0794823962855,13.6708337549583],
        [0.0207552207730293,0.0406880357856573,3592.39498126961,179.679275850895,9.95404590890601,133.631074201309,94.8999517388812,38.6514617902645,23.7850169817447],
        [0.0478046866710185,0.051116996225046,0,4.30274670276174,1.73500933072569,7.66149727517309,6.01463807437345,95.0193534459292,67.2262558183509],
        [0,          0,           30.6050425338013,0,0.47987781096326,13.1010807636789,4.01460301680675,2.25327975446985,2.09981034778272],
        [0,          0,           0,           0,0.155933610140554,5.56659142443517,1.6832184331266,0.317428448129245,0.298018825306679],
        [0,          0.518071275663763,0,      0,0.000869396832206842,0,0.00768351354724426,0.0354265267842358,0.0374964752432613]
    ]


#       in2in        in2dg        in2nf        in2pl         dg2dg          dg2nf        dg2pl         nf2nf         pl2pl
SUMA_PEAT = [
        [0,          0,           0,           0,           55.3656499654056,181.503418125979,73.9078329127183,567.141990498403,148.829597267745],
        [0,          0,           0,           0,           173.843907854137,382.269648535498,373.969555176022,947.700088683471,393.296410010351],
        [0,          1.81437337188111,0,       0,           85.8392106393286,356.32822735096,178.896694133443,691.613893703908,180.634667352977],
        [0,          0,           0,           0,           3.99635540377873,18.1817853836005,16.6801620694879,16.2375187563689,6.10764115665539],
        [0,          0,           0,           0,           0.734862223314401,13.2900340819469,2.40218016833702,15.6504761478884,2.04833026451743],
        [0,          0,           0,           0,           15.5143833784363,150.917294497498,28.7124808941142,384.763723816971,37.4385137049778],
        [0,          0,           0,           0,           5.02624203314829,73.3896039769466,10.4056026069191,66.7708253205091,18.4309128990277],
        [0,          0,           0,           0,           109.562031365515,1395.24303056699,391.009162060265,845.653753321041,175.117448383273],
        [0,          0,           0,           0,           1.22895037188102,33.7566004847528,21.4862611445241,40.4147534069068,6.5528388036819],
        [0,          0,           0,           0,           0.0127858040296933,0.420076462146427,0.547653017505863,0.754157917642552,0.258609402994366],
        [0,          0,           0,           0,           0.0179142735945905,0.079678272920005,0.124869993213881,0.11933861001497,0.0765247361783511],
        [0,          0,           0,           0,           0.0223985397186411,0.897933103345997,0.898233010510568,0.982420497592381,0.173791388474743],
        [0,          0,           0,           0,           0.340790912378154,28.8826501631455,6.36076369122433,9.42103571790308,2.12750682834883],
        [0,          0,           0,           0,           3.01972807113228,39.873010887218,10.9739364651703,39.7058126813159,9.20980088670703],
        [0,          0.116627722374566,0,      0,           13.7848945108368,182.866724125466,59.8127157876018,80.731782811972,34.4646382615466],
        [0,          0,           0,           0,           0.135137130060613,5.89263730687423,1.23262212152223,2.91419760292599,0.801390004785476],
        [0,          0,           0,           0,           1.41367464502618,43.5991214657193,8.11218987779248,16.7252489934005,3.86961846170615],
        [0,          0,           0,           0,           2.00234639489271,42.3917330142556,8.16456743466827,12.6717552761524,4.13554732451726],
        [0,          0,           0,           0,           33.7934260096328,738.673295535946,164.297278688296,227.45739720147,59.9314651441806],
        [0,          1.18130189346248,781.425055343171,44.3726488253614,94.4782378478152,1083.26629631715,240.611617150324,925.142826943412,213.813878153526],
        [0,          0,           0,           0,           18.713179207791,216.039461461641,79.0322511798691,786.386841569059,1440.30548838601],
        [0,          0,           0,           0,           23.7645222662435,88.6354606384621,43.7308310858755,1338.0811811254,1847.6413645613],
        [0,          0,           0,           0,           0.171803561926989,1.5263805877058,0.62254270405202,83.3995218866839,66.106981866223],
        [0,          0,           0,           0,           0,              0.0489959251912341,0,      0.507418899280414,0.926148015064045],
        [0,          0,          0,        0,        0.222216944622137,6.19378483264269,4.4674520913517,3.55519048426622,1.05635788836871],
        [0,          0,          0,        0,        5.55719121451193,202.555901598032,68.3000247280631,73.6717527366905,42.7814942868226],
        [0,          0,          206.69979657516,0,12.7488278345894,162.363359962679,27.2912738312594,47.0273812448227,21.4641973078117], 
        [0,          0,          0,        0,        0.724833884236963,3.55631605847071,11.9926591919358,4.83322598984605,1.62480628784031],
        [0,          0,          0,        0,        0.309148482719423,10.4657110097673,1.92875233914637,1.00126290034688,0.723911310072339],
        [0,          0.0488471998050982,96.5146795885456,0,0.999914437645502,20.4217738342635,12.2312348762174,2.89315960238288,0.979511247174768],
        [0,          0,          0,        0,        2.0649953877563,68.7346771487061,22.8577198949749,13.6474207802307,4.59923394254566],
        [0,          0,          192.218259288851,0,5.72566793415919,32.0596574991659,12.2362472831997,32.8398030969839,9.40246566019737],
        [0,          0,          0,        0,        5.84268202815148,56.6980889753676,14.1276840060587,12.9986337368801,17.2091494826056],
        [0,          0,          0,        0,        3.68612395111116,18.1178755111818,15.4654097146025,3.15585744336838,11.3611592375628],
        [0,          0,          0,        0,        0.185934899775326,1.36287364160267,0.640207072906382,0.177929117403907,0.267061886102514],
        [0,          0,          0,        0,        0.0266213485499997,1.82626471245176,0.0875865035004136,1.23023760478213,0.565477411886306],
        [0,          0,          306.709626114928,0, 1.67969552276801,15.8411351842337,2.01941972427886,5.6912164295659,2.43202687667804],
        [0,          0,          62.1112473035167,127.133897908359,4.72065915525863,47.6508591807582,28.0837721777564,40.3259952624721,15.6597183211901],
        [0,          0,          0,        0,        0.204834406021351,0.350049223374549,0.201988149466525,0.0724678559427216,0.343029297894592],
        [0,          0,          0,        0,        0.130855705242357,0.809754461946449,0.460551480462197,0.918700361326517,0.451419255581487],
        [0,          0.266323174723552,32.01205850998,21.0205662346642,7.5258838110777,122.202606896238,33.6308902376152,12.2837158203078,17.2848697178052],
        [0,          0,          0,        0,        1.18485606275041,8.5965582640686,14.3300491088602,7.89571722552944,6.39698745368949],
        [0,          0,          0,        0,        4.49243557102274,41.3706906505532,28.2464011622062,33.1529641725998,16.2529045216443],
        [0,          120.295236081137,12324.8982615973,1130.45396396136,33.7645284655026,592.611510885839,198.762998805888,59.3656305265961,57.1964599300968],
        [0,          1.04678891565976,125.824078398294,8.15575156081173,0.49284079474827,2.55309405100418,1.3947315385393,1.23215190491751,1.69555414810047],
        [0,          0,          0,        0,        0.111902288589217,2.01484117621562,0.492793254918799,0.121932093121109,0.255455293751091],
        [0,          0,          0,        0,        0.276373096655257,3.89962787219817,0.921696131004706,0.517446750433441,0.402943926067301],
        [0,          0,          224.509562498318,0, 0.401673477097847,7.4444264686665,2.34408031603837,0.95668832138428,0.737532601841382],
        [0,          0.795441234732297,167.949056392891,8.00337211669701,12.8382471748419,112.016429544299,57.6412415444829,121.13929457293,39.8573176999601],
        [0.892572023688356,4.90614523462686,0,0,     18.3078260676989,102.942184921599,67.6299221921797,60.8152101223323,27.3532376416602],
        [0,          0,          0,        0,        0.120349356244536,0.387885850553832,0.975876578203166,0.114524567604955,0.524738683443782],
        [0,          0.578742665243914,40.0710075772157,0,1.50259676344193,10.1155858367545,3.94088618902321,0.540363881691981,1.80710562915621],
        [0,          0.0703766352882755,4.39882298654266,1.3746315190933,10.8976394709979,137.568243939627,38.8751921327853,48.0967345993993,12.4156103374443],
        [0,          74.7608075939714,3801.62351213502,857.992221622313,33.9935418353409,358.278248514781,127.511688055742,115.779265255845,37.7133238180855],
        [1.56119327804822,110.806690876012,16074.9588531843,1544.56401714728,39.7341245577811,559.046407322729,238.294626451268,245.953197141911,46.4411260597082],
        [0,          51.8169525839381,11095.1722094221,2463.06315437073,22.8109701935106,186.132358907519,90.7920091745004,223.100681252251,112.334302561543],
        [0,          0,          0,        0,        42.7996630267955,102.986534320409,62.3843451349542,587.161001547811,638.154099770127],
        [0,          1.06661871536359,64.1038106419048,20.0324311462258,1.7481377851019,15.5870006744131,8.57470228717785,10.3144016505148,33.504157225736],
        [0,          0,          0,        0,        0.567513702896036,7.14327327226792,3.06309179292366,0.380134451093927,0.904410137680601],
        [0,          0,          0,        0,        0.309040225441127,1.23475413749881,0.809569468335827,0.390509799029834,0.262429101022705]
    ]
