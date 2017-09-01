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
    transition_emissions = getTransition(start_landcover, end_landcover, peatmask)

    print(ee.Image(transition_emissions.first()).bandNames().getInfo())

    # scale transition emissions based on IAV
    def scale_IAV(emissions):
        return emissions.multiply(IAV)

    scaled_emissions = transition_emissions.map(scale_IAV)

    return scaled_emissions

def getTransition(initialLandcover, finalLandcover, peatmask):
    """ Returns emissions due to land cover transitions at 1 km resolution in kg DM per grid cell"""
    # get masks for the different islands
    islands = ee.Image('users/karenyu/boundaries_islands_1km')
    suma_mask = islands.eq(ee.Image(2))
    kali_mask = islands.eq(ee.Image(3))
    indo_mask = suma_mask.add(kali_mask).lt(ee.Image(1))

    initial_masks = []
    final_masks = []

    # area of grid cell (m^2) and g to kg
    scaling_factor = 926.625433 * 926.625433 * 1.0e-3

    reverse_peatmask = peatmask.subtract(ee.Image(1)).multiply(ee.Image(-1))
    # order: DG, IN, NF, TM, OPL, NPL
    for i in range(1,7):
        initial_masks.append(initialLandcover.eq(ee.Image(i)))
        final_masks.append(finalLandcover.eq(ee.Image(i)))

    #in2in,in2dg,in2nf,in2tm,in2opl,in2npl,dg2dg,dg2nf,dg2tm,dg2opl,dg2npl,nf2nf,tm2tm,tm2nf,opl2opl,opl2nf,npl2npl
    initial_index = [1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 2, 3, 3, 4, 4, 5]
    final_index   = [1, 0, 2, 3, 4, 5, 0, 2, 3, 4, 5, 2, 3, 2, 4, 2, 5]
    gfed_index    = [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 3, 3, 3, 5, 5, 5]

    oc_ef = [2.62, 9.6, 9.6, 4.71, 6.02, 2.3]
    bc_ef = [0.37, 0.5, 0.5, 0.52, 0.04, 0.75]

    emissions_all_months = ee.List([])

    for month in range(0,12):
        kali_nonpeat_rates = KALI_NONPEAT[month]
        kali_peat_rates = KALI_PEAT[month]
        suma_nonpeat_rates = SUMA_NONPEAT[month]
        suma_peat_rates = SUMA_PEAT[month]
        indo_nonpeat_rates = SUMA_NONPEAT[month] #INDO_NONPEAT[month]
        indo_peat_rates = SUMA_PEAT[month] #INDO_PEAT[month]
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
        for transition_index in range(1, 16):
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


#"in2in","in2dg","in2nf","in2tm","in2opl","in2npl","dg2dg","dg2nf","dg2tm","dg2opl","dg2npl","nf2nf","tm2tm","tm2nf","opl2opl","opl2nf","npl2npl"
INDO_PEAT = [[0,0.438321304252059,182.398956821875,59.2909628210567,0,0,23.0189812038843,211.804765216489,131.8012232323,84.7220995246637,70.8434326552986,458.896413216703,91.1479538619174,270.374515362733,161.763128741764,79.8521110547242,146.536006764221],
[0.162585370086986,3.52108036891983,179.607503974971,0,0,0,70.7256286192177,479.439079709886,301.019793978838,332.116889050951,402.964042158723,846.761778022073,220.993880464687,519.101495420234,250.646352793328,199.892267778254,557.41551916623],
[0,0.9680366049645,93.031133943468,0,0,0,43.17941018499,413.493557607337,206.175745136278,201.02896868897,169.97367018949,486.881981352112,101.824538542969,439.280208807738,126.91567892806,237.241278914272,207.531757735263],
[0,0.399379118627397,24.0537477765632,0,0,0,1.56843635810501,33.8901593576995,17.0710353751424,40.8729104453277,14.5763746623608,19.9079405697714,3.06547669558851,11.5733914184614,2.6346681495102,28.7046047902401,25.2692815995271],
[0,0.184986950753729,41.5656052089791,0,0,0,11.3597655487288,306.614250705849,110.602523086127,96.5230355066224,73.8435951124947,68.1238390829658,15.9205578987621,105.728047993697,26.8505752372802,99.0672964810061,62.7950900895712],
[0,21.5690821973926,1673.91980533454,0,0,161.237570777062,19.3571007027526,430.881690417898,228.76834510262,161.629821144424,95.7300443947756,277.909365451558,35.92637580838,254.272508811741,48.8893978098755,77.1540044050316,98.631343861475],
[0.239474723913053,43.0038442803903,3673.60655670989,0,0,0,46.9625537093158,1095.69902068704,521.150691898367,383.045450046775,249.287079095655,418.877282956499,103.321003910122,485.863140249186,123.908174097427,449.168044086696,110.765119081642],
[0.0751092621553771,76.4338481238148,13746.4210011414,0,0,0,198.120131617304,2748.49633538361,1413.25904003234,1167.93513453589,750.536512780639,1932.78075267674,739.395165135508,1837.084940906,705.831650178009,1991.89488606297,452.291731245507],
[0.146816775062368,0.758835279637426,116.280156275259,0,0,0,301.061723706603,2219.06403031645,1466.68755075359,782.03334598877,708.127575611243,2782.80639378215,2845.34342534639,3479.35844099063,3570.93500964657,5557.25889160933,3796.55008607729],
[0.0353031753681968,1.25915710718032,62.9188338287598,0,0,0,162.935892920269,1689.90852751379,1268.24489619076,231.705903847648,321.301844557863,1391.69941966371,1747.9915433367,2225.35771495378,2213.44023670671,2873.72286532194,2772.55898414706],
[0.157989404958238,0,0,0,0,0,19.5281149215842,192.176476392519,229.749680132859,11.9859454374504,20.0678621394233,119.195801509028,119.166481826605,125.957874587173,125.476408382077,65.095437893916,37.2982526757788],
[0,0,102.047391252957,0,0,0,0.2649497721819,9.16630564995589,5.46236593422238,2.68305668452843,3.49680678074707,5.09230169812204,1.83470647240317,4.19548685192016,1.28716001821828,6.01216120802981,3.55160842844629]]
       

#"in2in","in2dg","in2nf","in2tm","in2opl","in2npl","dg2dg","dg2nf","dg2tm","dg2opl","dg2npl","nf2nf","tm2tm","tm2nf","opl2opl","opl2nf","npl2npl"
KALI_NONPEAT = [[0,0,0,0,0,0,0.499833142345155,19.6521010554361,1.42138859253777,8.74242737070232,50.6152374379234,7.44267661332771,0.674315801171735,1.65367925217955,2.82348683817091,5.32744497732793,18.8514737386981],
[0,0,0,0,0,0,0.328833131370847,59.9259072258124,1.20017327228948,13.817496550965,109.762428617414,4.31621733527446,0.453234089273986,1.29625400982371,2.23573943861356,8.68712207243014,9.72457758530684],
[0,0,0,0,0,0,0.840093197614931,39.0183490193031,5.75932228447008,7.95760277246585,30.9544652561659,12.600764764967,0.684675358990892,2.76322232454052,2.51183243230672,11.6682747077566,14.6254619378375],
[0,0,0,0,0,0,0.243693530725475,54.8869285709127,1.90688359669088,18.2487141039165,20.5088273571821,1.83651417137009,0.412034632797484,2.34884430849096,1.15410861729504,4.29545083580706,1.73189976166659],
[0,0,0,0,0,0,0.521457707403484,79.362767181563,5.88880331400736,24.0744501434151,50.9150206564899,5.18905341268493,1.29420613698995,6.60134168331411,1.57627543011166,6.77475140137536,2.93149527782036],
[0,0,0,0,0,0,1.14039975444272,73.675767586296,15.5933672235762,35.1201203805742,15.0871489207529,6.11794007554816,3.42419989776983,6.76825072486941,5.82730847121024,13.90066751118,2.78492788793107],
[0.00523396549688887,0.00161445305109198,0,0.0973448944905581,0,0,6.10084327329287,230.468442746598,64.8506922545553,91.2048785811454,468.644543616617,95.2997652290192,23.6528256348884,52.4870231810514,44.5193048430993,76.6323915889455,54.1749162003461],
[0.387347730881175,2.82835827979988,105.780570159026,25.1665432255009,0,0,41.2070823246995,570.43108861248,263.589266199369,332.71181686187,1098.15246808975,403.873954095883,189.872963070728,274.266778722965,286.03109491647,327.056413481879,154.467056474453],
[0.458341536556404,9.50936710409971,637.871593675149,57.6030937987012,0,0,95.6839295670922,977.229764263643,528.297309690771,729.873826314512,1018.2946567159,1645.70940465181,583.071758442524,677.430667180768,1058.28115165537,1312.51930021735,337.494860482164],
[0.0154019798866009,3.03452738544069,81.4220292153248,36.67916792038,0,0,50.6781261037017,660.296865592891,429.487633251228,338.832800482275,601.338042581944,498.699473096316,282.848290053378,242.440942522474,397.661019438262,729.625457499195,132.796580425422],
[0,0,44.89336623361,0,0,0,5.94575723847544,39.5035809265802,30.9026245986674,30.9410896887216,21.2261560933116,18.7530721813877,23.724782362438,20.117978724466,40.6162245877635,30.272091834842,11.9646887661852],
[0,0,0,0,0,0,0.0765152998095878,3.03082615196282,0.665311382867261,1.04549263491471,4.99239063467271,0.937244163464245,0.461423153183224,0.918957847881739,1.1374324257627,4.00288780383141,2.11677872025537]]


#"in2in","in2dg","in2nf","in2tm","in2opl","in2npl","dg2dg","dg2nf","dg2tm","dg2opl","dg2npl","nf2nf","tm2tm","tm2nf","opl2opl","opl2nf","npl2npl"
KALI_PEAT = [[0,0,0,0,0,0,1.22605819240138,32.5496087386543,8.45503788609138,21.5912985147715,49.1687891900904,22.8604164948083,4.50953944817885,10.17263951806,5.12376205741975,20.0798241323016,113.239584113085],
[0,0,0,0,0,0,0.454638658126531,75.0689004314931,1.33342826200517,2.00115676337084,59.5349949502489,23.8784012895206,2.81072488180051,3.34941565036672,0.752546148428862,48.2246801383751,91.8659883040562],
[0,0,0,0,0,0,0.559923974489373,20.0157306189996,9.77121703882802,2.44835560938036,42.1506090406253,14.6371559878492,5.33919698984751,5.21311310017184,5.99176128753387,15.7844081928898,44.8494965227082],
[0,0,0,0,0,0,0.269587707071081,16.3803639662323,3.08771828645297,6.45234432389878,18.9702897723118,3.91545748692972,0.294784865632936,0.523247799782479,0.26048604656465,6.06906347784001,14.9108921799321],
[0,0,0,0,0,0,10.0552637620498,357.270320181861,91.2923009730349,150.46511017161,100.92243014647,32.3793803016318,15.4834785657426,68.182326234223,32.9172758487785,63.1139958305387,77.8325211488573],
[0,0,0,0,0,0,4.10163095830223,131.43534921922,52.7147957386189,49.3514778521815,80.6249812376419,18.1537768679758,18.6954287285481,56.7544483490127,20.7417112177813,29.0625862757907,7.93986161625957],
[0,0,0,0,0,0,39.2618826647374,967.964268522629,306.908885326986,540.09716219747,632.442514129056,345.696948522152,110.258860447908,278.360154846275,297.770361726297,781.924550282774,277.305861355777],
[0,0,0,0,0,0,258.472822247919,2975.12415687361,1772.50603437832,1702.55625282477,2849.15032205183,2556.68318467648,1261.09986992832,2390.02130657346,1584.44388320497,2170.60879983128,1430.90930611627],
[0,0,0,0,0,0,639.731025180393,5452.14523354669,3747.92879791892,2160.63037278847,4541.07317185728,7668.89644234707,5402.73365975468,6468.29271704774,9010.98543781962,8010.261923047,1955.35117374015],
[0,0,0,0,0,0,339.540808044206,4228.6472219015,3191.86055778128,822.761893568302,2274.77785801803,2638.90906701693,2659.47347727357,2828.14132298702,2657.690882653,2380.07237780248,1023.89021294566],
[0,0,0,0,0,0,42.9301626120522,488.151844418927,590.53853017929,34.1668516798243,149.626149614416,284.570598233045,183.823010751764,313.249381047384,345.35867419271,171.640938279272,62.4152544481653],
[0,0,0,0,0,0,0.141185105884332,4.53428922967468,0.932474738576116,0,0,7.703016974642,1.91716996144268,3.42459378035968,0.0984087155191177,0.992650034279607,0]]


#"in2in","in2dg","in2nf","in2tm","in2opl","in2npl","dg2dg","dg2nf","dg2tm","dg2opl","dg2npl","nf2nf","tm2tm","tm2nf","opl2opl","opl2nf","npl2npl"
SUMA_NONPEAT = [[0.00551548281114805,0.533019346946946,134.026451224914,10.8554839277357,0,0,2.56070497911274,114.873067895518,36.1012104707442,11.3734039697649,12.371043334406,6.02801446288948,2.87743443017295,16.8104815846962,1.9495464360285,13.5937944151857,4.36918880036574],
[0.0956587425263827,0.0142793515964156,0,14.1288994446699,0,0,5.52258186075396,146.731320850243,48.2670057664767,35.1260617833871,26.2547561468817,8.89664405175225,6.93706700497791,27.9718032827859,5.83065760944689,17.4790724311045,10.0544106971656],
[0.0307260154246492,0.067351640942768,0,0,0,0,3.82525181220973,57.023186128618,22.4259687122675,5.09788856079554,46.5439550106305,6.57993505647711,6.41359500929214,16.2673639060769,2.99905270775154,5.90162956421177,4.05396875642789],
[0.0312345632045627,0.00309375793154609,10.1765845803508,0,0,0,0.662258961259155,27.8452608757823,8.60168298484368,10.3233015664642,1.67438818416051,5.71860227295838,1.36710759947207,4.95899835719338,1.79617886628159,3.77737551433918,6.12370266513753],
[0.321068171643906,0.907658735278216,3.31590403853473,6.86187907146041,0,0,8.73130040456015,247.761892821191,40.8017342888647,247.389970881074,105.518835361345,12.8575410891439,4.5643611459388,16.5491537016426,7.49835463665761,49.6163540369094,11.2652951788568],
[0.18396607470244,0.0212047992337772,765.005989870225,0.273162808122411,0,0,8.61617294697926,231.072705543859,43.7648510466757,126.453563034805,117.845343103871,23.3036316152447,8.92757896411735,25.3191717177663,10.1754665179599,63.0166830478722,37.9197546584951],
[0.151926475442837,3.33672701045172,1209.36551051173,109.969242417761,0,0,19.7771819945208,513.019447383337,163.969272111968,185.481719958992,233.121783285321,89.600802973935,32.244051151039,95.4884832795162,33.9962044438778,167.949545210603,67.6774115071273],
[0.791548262921929,6.43448198768715,7919.8230659738,403.198678948882,0,0,38.921928740722,736.489767138369,309.983859815523,407.353498274518,335.802775913893,204.93560261704,117.251982570451,340.819935833842,105.698207374029,345.001236119785,179.977414304075],
[0.156717233481304,0.495495238947526,0,11.7518994036758,0,0,15.2382935152543,120.876926553246,60.351420338715,81.4872018709296,54.4261654414539,376.787467901039,271.606504750422,478.296148916636,251.190451133897,891.605248113975,154.811382303712],
[0.0131733934144928,0,16.7249289175971,0,0,0,6.56479018164913,60.1059563402921,43.4718781265233,15.0118309457991,41.3042293943948,181.529882232642,170.638751448755,170.966838920353,188.814757887561,373.177196370638,124.20890511445],
[0.162885695687283,0.677425417081589,0,8.62278823646067,0,0,0.865170839517604,11.0415127795914,5.06414786434635,9.2786394471199,6.86783988413804,22.2459091167544,16.5950542952933,13.2564623900451,22.4439936947571,64.5962513085615,35.9333415382961],
[0.0179638394832559,0.518071275663763,0,0,0,0,0.0895072337904743,5.69755377093188,1.11116486362894,2.27752237598001,1.50918291194403,0.735020802403515,0.352287789560921,1.30493905991263,0.41290286432818,1.27459394991437,0.891909160937646]]


#"in2in","in2dg","in2nf","in2tm","in2opl","in2npl","dg2dg","dg2nf","dg2tm","dg2opl","dg2npl","nf2nf","tm2tm","tm2nf","opl2opl","opl2nf","npl2npl"
SUMA_PEAT = [[0,0.966380744068204,250.804503460399,1600.95770295511,0,0,68.9417439309121,320.906371231239,211.565268575257,106.234030824466,73.9750269440131,629.176689562017,182.592476333465,381.029920425344,195.231815704049,102.892749534197,148.571260078578],
[2.23584516442036,7.76303646168188,246.966164922726,0,0,0,216.652684026718,725.56009067712,494.668040289043,444.604404470465,452.583332710578,1167.42906411204,450.299929825059,738.298767593071,304.034775247731,258.356118390314,584.515750379162],
[0,2.13426070217406,127.920837715291,0,0,0,131.858982088619,652.800387432031,333.124697086963,268.695661267359,188.44179242687,670.857637130214,203.630000562441,623.780215154525,152.754704738517,322.607055520676,217.013294688422],
[0,0.880523684521852,33.0746862404156,0,0,0,4.4407720613472,44.5932289857413,25.9450507207285,52.6017787873028,13.9415333513225,25.9731934698543,5.88023078658991,16.2733929137126,3.1420926682596,37.4300083329773,25.8839603376449],
[0,0.352939268157771,53.0291496232796,0,0,0,21.1523455606596,277.058137294494,124.646042403617,78.1421788457911,69.93119291668,83.3114769504059,19.4162228975744,122.231997227071,25.4644499976485,112.926344603641,61.9932374086009],
[0,47.5540328534844,2301.69422525506,0,0,177.364224690593,53.8452609355133,613.404423453679,343.022947943122,199.888863764353,97.9124530828873,379.588333610608,57.6293470296778,338.665177301003,54.9187898351048,95.6919763636293,103.901554515183],
[3.29321391694366,94.8119259327139,5051.32860635963,0,0,0,91.2021604449979,1176.7306417535,666.481215219508,329.529803503176,193.928043816782,465.966750544358,118.598896680164,576.28259765961,86.991574128652,320.8991960691,101.352699323121],
[0,168.296085505807,18885.2473909806,0,0,0,259.077734138494,2621.05701232289,1220.77219718946,985.762049699311,447.324747327503,1829.74914073709,449.834418870641,1621.34993501928,519.334596099638,1923.00538985383,396.802358579017],
[0,1.6730279706859,155.771962242616,0,0,0,59.566205674333,272.299459377686,76.0253334052241,312.273988571762,154.336212459604,1301.63275504831,1270.88513998003,2261.01547692718,2415.60123797054,4611.690983077,3905.17672781261],
[0,0.745498400073421,56.0055932694164,0,0,0,41.1310004141286,161.051752310745,96.181954982647,30.302537614022,39.0598671195718,1048.58661167964,1337.64650662325,1991.96633540288,2120.56177637703,3064.01209356565,2874.96868204765],
[0,0,0,0,0,0,1.19759120157943,13.8318059891697,9.5272585240884,4.42776268819743,1.34903119279798,69.0524291752461,85.892268239879,48.8891073048508,78.7643688629097,24.0249604310456,35.8974410164988],
[0,0,140.318485031805,0,0,0,0.584190179967298,11.9983800558757,8.29173590265185,3.59731296072892,4.00203216312867,4.14119679923384,1.41222718061573,4.55064402927999,1.54120263529369,7.94705023865037,3.75771460429369]]
