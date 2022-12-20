import pandas as pd
from datetime import datetime, timedelta
import numpy as np
import pyubx2
from math import pi

g = 9.80665

# Sensitivity settings for data to be parsed
# Taken from Table3 of ASM330LHH datasheet
acc_sensitivity = 0.061 # for measurement range +-2g, units mg/LSB
gyr_sensitivity = 4.37 # for measurement range +-125dps mdps/LSB


# this function parses the timestamp as given in the raw data
# to a `datetime` object
# if the timestamp is invalid return `None`
def time_parser(time_str):
    try:
        return datetime.strptime(time_str, '%H:%M:%S.%f')
    except ValueError:
        return None

# this function parses GNSS data encoded as UBX
# return `None` if invalid UBX data
def ubx_parser(msg):
    try:
        return pyubx2.UBXReader.parse(bytes.fromhex(msg))
    except pyubx2.exceptions.UBXParseError:
        return None

# this function parses the time as given in a UBX PVT message
# to a python `datetime` object
def gnss_time_parser(x):
    try:
        if x.validDate and x.validTime:
            microsec = round(x.nano, -3)/1000
            return  datetime(x.year, x.month, x.day,x.hour, x.min, x.second) + timedelta(microseconds=microsec) 
        else:
            return None
    except ValueError:
        return None

# this function parses a given hex string
# representing a number in twos complement
# and returns its value
def twos_complement(hexstr, bits):
    value = int(hexstr, 16)
    if value & (1 << (bits-1)):
        value -= 1 << bits
    return value


# this function parses a given `.csv` file and 
# returns a tuple (I, PVT, COV, BRK) returning the data
# of interest as a pandas dataframe
def parse(file):
    data = pd.read_csv(file, names=["t", "type", "data"])

    # parse timestamp str to python timestamp and sort by it
    data['t'] = data['t'].apply(lambda x: time_parser(x))
    data.sort_values(by='t', inplace=True)
    
    # drop invalid data
    data.dropna(inplace=True)

    # different types of breakpoints
    brk_idx = np.isin(data['type'], ['ARR', 'DEP', 'BRK'])

    # Extract IMU, UBX and breakpoint data from the set
    I = data[data['type'] == 'I'][['t', 'data']].reset_index(drop=True)
    U = data[data['type'] == 'U'][['t', 'data']].reset_index(drop=True)
    BRK = data.iloc[brk_idx, :].reset_index(drop = True)

    
    # align time with first received UBX package
    starttime = U['t'].iloc[0] if len(U) != 0 else time_parser('00:00:00.000000')
    U['t'] = U['t'].apply(lambda x: (x - starttime).total_seconds())
    I['t'] = I['t'].apply(lambda x: (x - starttime).total_seconds())
    BRK['t'] = BRK['t'].apply(lambda x: (x - starttime).total_seconds())

    # parse UBX data
    U['data'] = U['data'].apply(lambda x: ubx_parser(x))
    U['type'] = U['data'].apply(lambda x: x.identity)

    # drop invalid GNSS data
    U.dropna(inplace=True)

    # Extract PVT and Covariance data
    PVT = U[U['type'] == 'NAV-PVT'].reset_index(drop=True)
    COV = U[U['type'] == 'NAV-COV'].reset_index(drop=True)

    # Extract some interesting data from the PVT message
    # More data is avaliable, check 
    PVT['lon'] = PVT['data'].apply(lambda x: x.lon )
    PVT['lat'] = PVT['data'].apply(lambda x: x.lat)
    PVT['hAcc'] = PVT['data'].apply(lambda x: x.hAcc / 1000)
    PVT['alt'] = PVT['data'].apply(lambda x: x.hMSL / 1000)
    PVT['vAcc'] = PVT['data'].apply(lambda x: x.vAcc / 1000)
    PVT['speed'] = PVT['data'].apply(lambda x: x.gSpeed / 1000)
    PVT['speedAcc'] = PVT['data'].apply(lambda x: x.sAcc / 1000)
    PVT['heading'] = PVT['data'].apply(lambda x: x.headMot / 180 * pi)
    PVT['headingAcc'] = PVT['data'].apply(lambda x: x.headAcc / 180 * pi)
    PVT['fixType'] = PVT['data'].apply(lambda x: x.fixType)
    PVT['velE'] = PVT['data'].apply(lambda x: x.velE / 1000)
    PVT['velN'] = PVT['data'].apply(lambda x: x.velN / 1000)
    PVT['velD'] = PVT['data'].apply(lambda x: x.velD / 1000)
    PVT['t_gnss'] = PVT['data'].apply(lambda x: gnss_time_parser(x))
    PVT['numSV'] = PVT['data'].apply(lambda x: x.numSV)
    PVT['invalidLlh'] = PVT['data'].apply(lambda x: x.invalidLlh)
    PVT['gnssFixOK'] = PVT['data'].apply(lambda x: x.gnssFixOk)
    PVT['carrSoln'] = PVT['data'].apply(lambda x: x.carrSoln)
   

    # Drop all IMU data before the first GNSS message
    I = I.drop(I[I['t'] < 0].index)

    # remove all corrupted data
    I['data_len'] = I['data'].apply(lambda x: len(x))
    I = I.drop(I[I['data_len'] < 24].index)
    del I['data_len']

    # reindex data
    I = I.reset_index(drop=True)

    # extract gyroscope data
    I['gyr_x'] = I['data'].apply(lambda x: twos_complement(x[2:4] + x[0:2], 16) * (gyr_sensitivity/1000) *pi / 180)
    I['gyr_y'] = I['data'].apply(lambda x: twos_complement(x[6:8] + x[4:6], 16) * (gyr_sensitivity/1000) * pi/ 180)
    I['gyr_z'] = I['data'].apply(lambda x: twos_complement(x[10:12] + x[8:10], 16) * (gyr_sensitivity/1000) * pi /180)

    # extract accelerometer data (in m/s^2)
    I['acc_x'] = I['data'].apply(lambda x: twos_complement(x[14:16] + x[12:14], 16) * (acc_sensitivity * g) / 1000)
    I['acc_y'] = I['data'].apply(lambda x: twos_complement(x[18:20] + x[16:18], 16) * (acc_sensitivity* g) / 1000)
    I['acc_z'] = I['data'].apply(lambda x: twos_complement(x[22:24] + x[20:22], 16) * (acc_sensitivity * g) / 1000)

    I.dropna(inplace=True)
    del I['data']


    return (I, PVT, COV, BRK)


from matplotlib.ticker import AutoMinorLocator
import matplotlib.pyplot as plt
import math
# this function takes a tuple (I, PVT, COV, BRK) as an input
# (the same as `parse` returns)
def sample_plot(data):
    (I, PVT, COV, BRK) = data
    I['dt'] = I['t'].diff()

    multiplier = 10**(-math.floor(math.log(I['dt'].max(), 1e3))*3)

    fig, (dt_plot, gnss_plot, sv_plot)= plt.subplots(3, figsize=(12.8,7.2 ))


    perc = 0.1 # accepted imu range

    dt_plot.axhline(y = 1/1667*multiplier, color = 'r', linestyle = 'dashed')
    dt_plot.axhline(y = 1/1667*multiplier*(1+perc), color='g', linestyle='dashed')
    dt_plot.axhline(y = 1/1667*multiplier*(1-perc), color='g', linestyle='dashed')
    dt_plot.scatter(I['t'], I['dt']*multiplier, label='IMU')

    dt_plot.yaxis.set_minor_locator(AutoMinorLocator())
    dt_plot.xaxis.set_minor_locator(AutoMinorLocator())

    gnss_plot.yaxis.set_minor_locator(AutoMinorLocator())
    gnss_plot.xaxis.set_minor_locator(AutoMinorLocator())

    sv_plot.yaxis.set_minor_locator(AutoMinorLocator())
    sv_plot.xaxis.set_minor_locator(AutoMinorLocator())

    handles = ['Expected dt', f"$\pm{perc*100}\%$"]
    dt_plot.legend(handles, loc = "upper left", ncol=len(handles))

    timeUnit = f"{1/multiplier}s"
    if multiplier <= 1e9:
        timeUnit = ["s", "ms", "us", "ns"][max(0, math.floor(math.log(multiplier)/3))]

    dt_plot.set_ylabel(f'time step dt [{timeUnit}]')


    gnss_plot.plot(PVT['t'], PVT['hAcc'].apply(lambda x: x/100))
    gnss_plot.set_ylabel('GNSS Horizontal Accuracy [m]')

    sv_plot.set_ylabel('Visible Satellites')

    no_rtk = PVT[PVT['carrSoln'] == 0]
    float = PVT[PVT['carrSoln'] == 1]
    fix = PVT[PVT['carrSoln'] == 2]

    sv_plot.scatter(no_rtk['t'], no_rtk['numSV'], c='red', label="No RTK")
    sv_plot.scatter(float['t'], float['numSV'], c='orange', label="RTK float")
    sv_plot.scatter(fix['t'], fix['numSV'], c='green', label="RTK fix")

    sv_plot.legend(loc="best")
    sv_plot.set_xlabel('time [s]')

    fig.tight_layout() 

    fig.show()
