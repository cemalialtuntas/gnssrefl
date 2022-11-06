import math
import numpy as np
import os
import sys
import time
import wget

import gnssrefl.gps as g

import simplekml

# https://developers.google.com/kml/documentation/kml_tut#ground-overlays


def makeFresnelEllipse(A,B,center,azim):
    """
    make an Fresnel zone given size, center, and orientation

    Parameters
    ----------
    A : float
        semi-major axis of ellipse in meters
    B : float
        semi-minor axis of ellipse in meters
    center : float 
        center of the ellipse, provided as distance along the satellite azimuth direction
    azimuth : float
        azimuth angle of ellipse in degrees. 
        this will be clockwise positive as defined from north

    Returns
    --------
    x : numpy array of floats 
        x value of cartesian coordinates of ellipse
    y : numpy array of floats
        y value of cartesian coordinates of ellipse
    xcenter : float
        x value for center of ellipse in 2-d cartesian
    ycenter : float
        y value for center of ellipse in 2-d cartesian

    """

    # this is backwards but it works and i have stopped caring
    width =  A
    height = B
    # fro my matlab code
    angle = 360-azim  + 90

    allAngles = np.deg2rad(np.arange(0.0, 375.0, 15.0))
    # get the x and y coordinates for an ellipse centered at 0,0
    x =  width * np.cos(allAngles)
    y =  height * np.sin(allAngles)

    # rotation angle for the ellipse
    rtheta = np.radians(angle)
    # rotation array
    R = np.array([
        [np.cos(rtheta), -np.sin(rtheta)],
        [np.sin(rtheta),  np.cos(rtheta)], ])
    

#   rotate x and y into this new system
    x, y = np.dot(R, np.array([x, y]))
#   figure out center of the ellipse
    xcenter = center*np.cos(rtheta)
    ycenter = center*np.sin(rtheta)
    # print('center of the ellipse', xcenter, ycenter)
# finally, new coordinates for x and y
    x += xcenter
    y += ycenter
    return x, y, xcenter, ycenter


def FresnelZone(f,e,h):
    """
    based on GPS Tool Box Roesler and Larson (2018).
    Original source is Felipe Nievinski as published in the appendix of 
    Larson and Nievinski 2013

    Parameters
    ----------
    f : int
        frequency (1,2, or 5)
    e : float
        elevation angle (deg)
    h : float
        reflector height (m)

    Returns
    -------
    firstF: [a, b, R ] in meters where:
        a is the semi-major axis, aligned with the satellite azimuth 
        b is the semi-minor axis
        R locates the center of the ellispe on the satellite azimuth direction (theta)

    this code assumes a horizontal, untilted reflecting surface    
    """

# SOME GPSCONSTANTS	
    CLIGHT = 299792458;  # speed of light, m/sec
    FREQ = [0, 1575.42e6, 1227.6e6, 0, 0, 1176.45e6];   # GPS frequencies, Hz
    CYCLE = CLIGHT/FREQ[f]; #  wavelength per cycle (m/cycle)
    RAD2M = 0.5*CYCLE/np.pi; # % (m)
    erad = e*np.pi/180;

# check for legal frequency later

# delta = locus of points corresponding to a fixed delay;
# typically the first Fresnel zone is is the 
# "zone for which the differential phase change across
# the surface is constrained to lambda/2" (i.e. 1/2 the wavelength)
    delta = CYCLE/2; # 	% [meters]


# semi-major and semi-minor dimension
# from the appendix of Larson and Nievinski, 2013
    sin_elev = math.sin(erad);
    d = delta; 
    B = math.sqrt( (2*d*h / sin_elev) + (d/sin_elev)*(d/sin_elev) ) ; # % [meters]
    A = B / sin_elev ; #% [meters]


# determine distance to ellipse center 
    center = (h + delta/sin_elev)/ math.tan(erad)  #  	% [meters]
#    print('center distance is', center)

    return A, B, center

def makeEllipse_latlon(freq,el,h,azim,latd,lngd):
    """
    for given fresnel zone, produces coordinates of an ellipse

    Parameters
    ----------
    freq : int
        frequency
    el : float
        elevation angle in degrees
    h : float
        reflector height in meters
    azim : float
        azimuth in degrees
    latd : float
        latitude in degrees
    lngd : float
        longitude in degrees

    Returns
    -------
    lngdnew : float
        new longitudes in degrees

    latdnew : float
        new latitudes in degrees

    """
    A,B,center = FresnelZone(freq,el,h) 
    # print(A,B,center)
    x,y,xc,yc = makeFresnelEllipse(A,B,center,azim)
    d=np.sqrt(x*x+y*y); # this is in meters  
    d=d/1000; # convert d from meters to km
    # average Radius of Earth, in km
    R=6378.14; 
    theta=np.arctan2(x,y)
# map coordinates need a reference, so use the station coordinates, in degrees and radians
    lat = latd*np.pi/180
    lng = lngd*np.pi/180
    sinlat = math.sin(lat)
    coslat = math.cos(lat)

# this will be in radians
    latnew= np.arcsin(sinlat*np.cos(d/R) + coslat*np.sin(d/R)*np.cos(theta) );

    arg1 =  np.sin(theta)*np.sin(d/R)*coslat
    arg2 =  np.cos(d/R) - sinlat*np.sin(latnew)
# new lngnew will be degrees
    lngnew = lngd + 180.0/np.pi  * np.arctan2(arg1, arg2)
# put latitude back into degrees
    latnew=latnew*180./np.pi 

    return lngnew, latnew


def ref_azel(satv,recv,up):
    """
    send satv and recv as three vectors
    up is a unit vector pointing up
    need East and North as well apparently
    """
    r=np.subtract(satv,recv) # satellite minus receiver vector
    eleA = g.elev_angle(up, r)*180/np.pi
    azimA = g.azimuth_angle(r, East, North)
    return True


def set_final_azlist(a1ang,a2ang,azlist):
    """
    given azimuth limits (a1ang,a2ang in degrees) set azlist to accommodate
    """
# we convert the azimuth tracks to -180 to 180, sort of
    if (a1ang < 0):
        kk = (azlist[:,0] > 0) & (azlist[:,0] < a2ang)
        kk2 = (azlist[:,0] > (360+a1ang)) & (azlist[:,0] < 360)
        azlist1 = azlist[kk,:]
        azlist2 = azlist[kk2,:]
        azlist = np.vstack((azlist1, azlist2))
    # these might overlap if you put in silly numbers but i don't think it will crash
    else:
        kk = (azlist[:,0] > a1ang) & (azlist[:,0] < a2ang)
        azlist = azlist[kk,:]

    return azlist

def calcAzEl_new(prn, newf,recv,u,East,North):
    """
    function to gather azel for all low elevation angle data
    this is used in the reflection zone mapping tool

    Parameters
    ----------
    prn :
    newf :

    inputs are prn number, cartesian orbits for that prn,
    cartesian position of the receiver (both in meters),
    up, east, and north are unit vectors needed to compute
    elevation angle and azimuth angle
    no longer subtracts five degrees?
    now computes the number of values in the file so that you can use 
    GPS, and other constellations
    author: kristine larson
    """
    tv = np.empty(shape=[0, 3])
    # number of values
    NV = len(newf)
    #for t in range(0,480):
    for t in range(0,NV):
        satv= [newf[t,2], newf[t,3],newf[t,4]]
        etime = newf[t,1]
        r=np.subtract(satv,recv) # satellite minus receiver vector
        eleA = g.elev_angle(u, r)*180/np.pi
        if ( (eleA >= 0) & (eleA <= 26)):
            azimA = g.azimuth_angle(r, East, North)
#            print(etime, eleA, azimA)
            newl = [prn, eleA, azimA]
            tv = np.append(tv, [newl],axis=0)
    nr,nc=tv.shape
    return tv

def calcAzEl_newish(prn, newf,recv,u,East,North):
    """
    function to gather azel for all low elevation angle data
    this is used in the reflection zone mapping tool

    inputs are prn number, cartesian orbits for that prn,
    cartesian position of the receiver (both in meters),
    up, east, and north are unit vectors needed to compute
    elevation angle and azimuth angle
    no longer subtracts five degrees?
    now computes the number of values in the file so that you can use
    GPS, and other constellations

    """
    tv = np.empty(shape=[0, 4])
    # number of values
    NV = len(newf)
    for t in range(0,NV):
        satv= [newf[t,2], newf[t,3],newf[t,4]]
        etime = newf[t,1]
        r=np.subtract(satv,recv) # satellite minus receiver vector
        eleA = g.elev_angle(u, r)*180/np.pi
        if ( (eleA >= 0) & (eleA <= 20)):
            azimA = g.azimuth_angle(r, East, North)
#            print(etime, eleA, azimA)
            newl = [prn, eleA, azimA, etime]
            tv = np.append(tv, [newl],axis=0)
    nr,nc=tv.shape
    return tv

def rising_setting_new(recv,el_range,obsfile):
    """
    Calculates potential rising and setting arcs

    Parameters
    ----------
    recv : list of floats
         Cartesian coordinates of station in meters
    el_range : list of floats
         elevation angles in degrees
    obsfile : str
         orbit filename

    Returns
    -------
    azlist : list of floats
        azimuth angle (deg), PRN, elevation angle (Deg)

    """
    # will put azimuth and satellite number
    azlist = np.empty(shape=[0, 3])
    # these are in degrees and meters
    lat, lon, nelev = g.xyz2llhd(recv)
    # calculate unit vectors
    u, East,North = g.up(np.pi*lat/180,np.pi*lon/180)
    # load the cartesian satellite positions
    f = np.genfromtxt(obsfile,comments='%')
    r,c = f.shape
    # print('Number of rows:', r, ' Number of columns:',c)
#   reassign the columns to make it less confusing
    sat = f[:,0]; t = f[:,1]; x = f[:,2]; y = f[:,3]; z =  f[:,4]
#   examine all 32 satellites
#   should this be more for Beidou?
    for prn in range(1,33):
        newf = f[ (f[:,0] == prn) ]
        tvsave=calcAzEl_new(prn, newf,recv,u,East,North)
        nr,nc=tvsave.shape
        for e in el_range:
            el = tvsave[:,1] - e
            for j in range(0,nr-1):
                az = round(tvsave[j,2],2)
                newl = [az, prn, e]
                if ( (el[j] > 0) & (el[j+1] < 0) ) :
                    azlist = np.append(azlist, [newl], axis=0)
                if ( (el[j] < 0) & (el[j+1] > 0) ) :
                    azlist = np.append(azlist, [newl], axis=0)

    return azlist

def write_coords(lng, lat):
    """
    Parameters
    ----------
    lng : list of floats
        longitudes in degrees
    lat : list of floats 
        latitudes in degrees

    Returns
    -------
    points : list of pairs  of long/lat
        for google maps

    """
    points = []
    data = [lng, lat]
    for i in range(len(lng)):
        coord = (data[0][i], data[1][i])
        points.append(coord)
        i+=1

    return points


def make_FZ_kml(name,freq, el_list, h, lat,lng,azlist):
    """
    makes fresnel zones for given azimuth and elevation angle 
    lists.  

    Parameters
    ----------
    name : str
        output filename (kml will be added to it)
    freq : int
        frequency (1,2, or 5)
    el_list : list of floatss
        elevation angles
    h : float
        reflector height in meters
    lat : float
        latitude in deg
    lng : float 
        longitude in degrees
    azlist : list of floats
        azimuths

    """
    # starting azimuth
    nr,nc=azlist.shape
    n=0
    kml = simplekml.Kml()
    # this loop goes through all the Fresnel zone azimuths in azlist
    while (n < nr):
        azim = azlist[n,0]; el = azlist[n,2]
        k = el_list.index(el) ; # color index
        lng_el, lat_el = makeEllipse_latlon(freq,el,h,azim, lat,lng)
        points = write_coords(lng_el, lat_el)
        pname = 'ElevAngle {0}'.format(int(el))
        ls = kml.newpolygon(name=pname, altitudemode='relativeToGround')
        #ls = kml.newpolygon(name=pname)
        ls.outerboundaryis = points
        # print(points)
        if el ==el_list[0]:
            ls.style.linestyle.color = simplekml.Color.yellow
            ls.style.linestyle.width = 3
            ls.style.polystyle.color = simplekml.Color.changealphaint(50, simplekml.Color.yellow)
        elif el==el_list[1]:
            ls.style.linestyle.color = simplekml.Color.blue
            ls.style.linestyle.width = 3
            ls.style.polystyle.color = simplekml.Color.changealphaint(50, simplekml.Color.blue)
        elif el==el_list[2]:
            ls.style.linestyle.color = simplekml.Color.red
            ls.style.linestyle.width = 3
            ls.style.polystyle.color = simplekml.Color.changealphaint(50, simplekml.Color.red)
        elif el==el_list[3]:
            ls.style.linestyle.color = simplekml.Color.green
            ls.style.linestyle.width = 3
            ls.style.polystyle.color = simplekml.Color.changealphaint(50, simplekml.Color.green)
        elif el==el_list[4]:
            ls.style.linestyle.color = simplekml.Color.cyan
            ls.style.linestyle.width = 3
            ls.style.polystyle.color = simplekml.Color.changealphaint(50, simplekml.Color.cyan)
        else:
            ls.style.polystyle.color = simplekml.Color.white
            ls.style.linestyle.width = 5
        n+=1

    #print('put end of file on the geoJSON')
    azim = azlist[nr-1,0]
    # try this instead of hardwiring 5!
    el=el_list[0]
    #print('elevation angle for last one')
    #print(el_list[0])
    lng_el, lat_el = makeEllipse_latlon(freq,el,h,azim, lat,lng)
    if False:
        points = write_coords(lng_el, lat_el)

    #print(points)
    if False:
        ls = kml.newpolygon(name='A Polygon {0}'.format(n+1))
        ls.outerboundaryis = points
        ls.style.linestyle.color = simplekml.Color.yellow
        ls.style.linestyle.width = 3
        ls.style.polystyle.color = simplekml.Color.changealphaint(50, simplekml.Color.yellow)
    # save to a file
    kml.save(name +'.kml')
    return True

def set_system(system):
    """
    finds the file needed to compute orbits for reflection zones

    Parameters
    ----------
    system : str
        gps,glonass,beidou, or galileo

    Returns
    -------
    orbfile : str
        orbit filename with Cartesian coordinates for one day 

    """
    xdir = os.environ['REFL_CODE'] + '/Files/'

    if (system is None) or (system == 'gps'):
        system = 'gps'
        orbfile = xdir + 'GPSorbits_21sep17.txt'
    elif (system == 'galileo'):
        orbfile = xdir + 'GALILEOorbits_21sep17.txt'
    elif (system == 'glonass'):
        orbfile = xdir + 'GLONASSorbits_21sep17.txt'
    elif (system == 'beidou'):
        orbfile = xdir + 'BEIDOUorbits_21sep17.txt'
    else:
       print('Using GPS')
       system = 'gps'
       orbfile = xdir + 'GPSorbits_21sep17.txt'

    return orbfile

def save_reflzone_orbits():
    """
    check that orbit files exist for reflection zone code.
    downloads to $REFL_CODE$/Files directory if needed
    """
    xdir = os.environ['REFL_CODE'] + '/Files/'
    githubdir = 'https://raw.githubusercontent.com/kristinemlarson/gnssrefl/master/docs/_static/'

    for otypes in ['GPS','GLONASS','GALILEO','BEIDOU']:
        orbfile = otypes + 'orbits_21sep17.txt'
        #print( githubdir+orbfile)
        if not os.path.exists(xdir + orbfile):
            print('download from github and put in local Files directory: ', otypes)
            wget.download(githubdir+orbfile, xdir + orbfile)

