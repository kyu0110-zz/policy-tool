import math

def getAttributableMortality(receptor, exposure, age):
    year = '2005'

    if age=='adult':
        CR_25, CR, CR_97 = concentrationResponse(exposure)
    else:
        CR_25, CR, CR_97 = concentrationResponseChild(exposure)

    #mortality_rate = {'2005': {'Indonesia': 0.0099759, 'Malaysia': 0.0078068, 'Singapore': 0.0076863}}
    #population = {'Indonesia': 257563815, 'Malaysia': 30331007, 'Singapore': 5603740}
   
    mortality_rate = {'earlyneonatal': {'2005': {'Indonesia': 2449.447916, 'Malaysia': 307.822903, 'Singapore': 138.625514},
            '2010': {'Indonesia': 1766.350721, 'Malaysia': 277.366607, 'Singapore': 136.436176},
            '2015': {'Indonsia': 1178.856507, 'Malaysia': 188.300136, 'Singapore': 108.775055}},
            'lateneonatal': {'2005': {'Indonesia': 855.656908, 'Malaysia': 81.248922, 'Singapore': 78.940460},
            '2010': {'Indonesia': 568.458840, 'Malaysia': 82.687460, 'Singapore': 67.082849},
            '2015': {'Indonesia': 370.369132, 'Malaysia': 69.624377, 'Singapore': 60.953660}}, 
            'postneonatal': {'2005': {'Indonesia': 515.194821, 'Malaysia': 47.331711, 'Singapore': 21.578431},
            '2010': {'Indonesia': 369.668706, 'Malaysia': 47.202972, 'Singapore': 17.500542},
            '2015': {'Indonesia': 226.980567, 'Malaysia': 34.900627, 'Singapore': 16.539159}},
            '1-4': {'2005': {'Indonesia': 37.127353, 'Malaysia': 5.014201, 'Singapore': 3.114068},
            '2010': {'Indonsia': 25.623974, 'Malaysia': 4.512403, 'Singapore': 2.762267},
            '2015': {'Indonesia': 15.716153, 'Malaysia': 3.141835, 'Singapore': 2.381157}},
            'adult': #{'2005': {'Indonesia': 11.69838019976476, 'Malaysia': 46.866452636527164, 'Singapore': 52.17024922961024},
                     {'2005': {'Indonesia': 0.0099759*100000.0, 'Malaysia': 0.0078068*100000.0, 'Singapore': 0.0076863*100000.0}, 
                '2010': {'Indonesia': 11.419532683191251, 'Malaysia': 47.8500684668024, 'Singapore': 52.324629794405304},
                '2015': {'Indonesia': 10.744837776788115, 'Malaysia': 49.84244480909222, 'Singapore': 58.83291894359718}}}

    population = {'earlyneonatal': {'2005': {'Indonesia': 9.263730e4, 'Malaysia': 8.895073e3, 'Singapore': 7.186277e2},
                '2010': {'Indonesia': 9.698937e4, 'Malaysia': 9.045705e3, 'Singapore': 7.280622e2},
                '2015': {'Indonesia': 9.620548e4, 'Malaysia': 9.752598e3, 'Singapore': 7.255022e2}},
                'lateneonatal': {'2005': {'Indonesia': 2.752874e5, 'Malaysia': 2.665513e4, 'Singapore': 2.153700e3}, 
                '2010': {'Indonesia': 2.886072e5, 'Malaysia': 2.707535e4, 'Singapore': 2.186420e3},
                '2015': {'Indonesia': 2.870570e5, 'Malaysia': 2.920269e4, 'Singapore': 2.175771e3}},
                'postneonatal':  {'2005': {'Indonesia': 4.347065e6, 'Malaysia': 4.303966e5, 'Singapore': 3.439537e4},
                '2010': {'Indonesia': 4.581694e6, 'Malaysia': 4.309730e5, 'Singapore': 3.579362e4},
                '2015': {'Indonesia': 4.598456e6, 'Malaysia': 4.650476e5, 'Singapore': 3.498836e4}},
                '1-4': {'2005': {'Indonesia': 1.792731e7, 'Malaysia': 1.973355e6, 'Singapore': 1.613114e5},
                '2010': {'Indonesia': 1.919759e7, 'Malaysia': 1.834883e6, 'Singapore': 1.557840e5}, 
                '2015': {'Indonesia': 1.981817e7, 'Malaysia': 1.937488e6, 'Singapore': 1.539489e5}},
                'adult': {'2005': {'Indonesia': 115498024.0, 'Malaysia': 12979736.0, 'Singapore': 2394994.0},
                '2010': {'Indonesia': 218774546.0, 'Malaysia': 25798490.0, 'Singapore': 3603053.0},
                '2015': {'Indonesia': 232821069.0, 'Malaysia': 27854334.0, 'Singapore': 3731829.0}}}

    total_deaths_25 = mortality_rate[age][year][receptor] * population[age][year][receptor] * CR_25 / 100000.0 
    total_deaths = mortality_rate[age][year][receptor] * population[age][year][receptor] * CR / 100000.0
    total_deaths_97 = mortality_rate[age][year][receptor] * population[age][year][receptor] * CR_97 / 100000.0 

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


def concentrationResponseChild(dExposure):
    def FullLin25CI(x):
        return 0.003 * x

    def FullLin(x):
        return 0.012 * x

    def FullLin975CI(x):
        return 0.03 * x

    def FullLog(x):
        return 1 - (1/math.exp(0.012 * x))

    def FullLog25CI(x):
        return 1 - (1/math.exp(0.003 * x )) 

    def FullLog975CI(x):
        return 1 - (1/math.exp(0.03 * x))

    if dExposure <= 50:
        Lin50Log25CI = FullLin25CI(dExposure)
        Lin50Log = FullLin(dExposure)
        Lin50Log975CI = FullLin975CI(dExposure)
    else:
        Lin50Log25CI = FullLin25CI(50) + FullLog25CI(dExposure) - FullLog25CI(50)
        Lin50Log = FullLin(50) + FullLog(dExposure) - FullLog(50)
        Lin50Log975CI = FullLin975CI(50) + FullLog975CI(dExposure) - FullLog975CI(50)
    return Lin50Log25CI, Lin50Log, Lin50Log975CI

