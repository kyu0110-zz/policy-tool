import math

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

