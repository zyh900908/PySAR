#! /usr/bin/env python2
############################################################
# Program is part of PySAR v1.0                            #
# Copyright(c) 2013, Heresh Fattahi                        #
# Author:  Heresh Fattahi                                  #
############################################################
# Yunjun, Jun 2017: rewrite using pysar module

import os
import sys
import argparse

import h5py
import numpy as np
import matplotlib.pyplot as plt

import pysar._readfile as readfile
import pysar._writefile as writefile
import pysar._pysar_utilities as ut
import pysar.subset as subset


################################################################################
def get_overlap_lalo(atr1, atr2):
    '''Find overlap area in lat/lon of two geocoded files
    Inputs:
        atr1/2 - dict, attribute dictionary of two input files in geo coord
    Outputs:
        W/E/S/N - float, West/East/South/North in deg 
    '''
    W1, E1, S1, N1 = ut.four_corners(atr1)
    W2, E2, S2, N2 = ut.four_corners(atr2)
    
    west = max(W1,W2)
    east = min(E1,E2)
    north = min(N1,N2)
    south = max(S1,S2)

    return west, east, south, north


################################################################################
REFERENCE='''reference:
  Wright, T. J., B. E. Parsons, and Z. Lu (2004), Toward mapping 
  surface deformation in three dimensions using InSAR, GRL, 31(1),
'''

EXAMPLE='''example:
  asc_desc.py  vel_AlosAT424_masked.h5  vel_AlosDT73_masked.h5
  asc_desc.py  vel_EnvAT134_masked.h5   vel_EnvAT256_masked.h5  16
'''

def cmdLineParse():
    parser = argparse.ArgumentParser(description='Project Asc and Desc LOS displacement to Horizontal and Vertical direction',\
                                     formatter_class=argparse.RawTextHelpFormatter,\
                                     epilog=REFERENCE+'\n'+EXAMPLE)

    parser.add_argument('file', nargs=2,\
                        help='ascending and descending files\n'+\
                             'Both files need to be geocoded in the same spatial resolution.')
    parser.add_argument('--azimuth','--az', dest='azimuth', type=float, default=90.0,\
                        help='azimuth angle (clockwise) of the direction of the horizontal movement\n'+\
                             'default is 90.0 for E-W component, assuming no N-S displacement.\n'+\
                             'i.e. azimuth angle of strike-slip fault\n\n'+\
                             'Note:\n'+\
                             'a. This assumes no deformation in its perpendicular direction\n'+\
                             'b. Near north direction can not be well resolved due to the lack of\n'+\
                             '   diversity in viewing geometry. Check exact dilution of precision for \n'+\
                             '   each component in Wright et al., 2004, GRL')
    parser.add_argument('-o','--output', dest='outfile', nargs=2, default=['up.h5','hz.h5'],\
                        help='output file name for vertical and horizontal components')

    inps = parser.parse_args()
    if inps.azimuth < 0.:
        inps.azimuth += 360.
    inps.azimuth *= np.pi/180.
    return inps


################################################################################
def main(argv):
    inps = cmdLineParse()

    ##### 1. Extract the common area of two input files
    # Basic info
    atr1 = readfile.read_attribute(inps.file[0])
    atr2 = readfile.read_attribute(inps.file[1])
    if any('X_FIRST' not in i for i in [atr1,atr2]):
        sys.exit('ERROR: Not all input files are geocoded.')

    k1 = atr1['FILE_TYPE']
    print 'Input 1st file is '+k1

    # Common AOI in lalo
    west, east, south, north = get_overlap_lalo(atr1, atr2)
    lon_step = float(atr1['X_STEP'])
    lat_step = float(atr1['Y_STEP'])
    width  = int(round((east  - west )/lon_step))
    length = int(round((south - north)/lat_step))

    # Read data in common AOI: LOS displacement, heading angle, incident angle
    u_los = np.zeros((2, width*length))
    heading = []
    incidence = []
    for i in range(len(inps.file)):
        fname = inps.file[i]
        print '---------------------'
        print 'reading '+fname
        atr = readfile.read_attribute(fname)

        [x0,x1] = subset.coord_geo2radar([west,east], atr, 'lon')
        [y0,y1] = subset.coord_geo2radar([north,south], atr, 'lat')
        V = readfile.read(fname, (x0,y0,x1,y1))[0]
        u_los[i,:] = V.flatten(0)

        heading_angle = float(atr['HEADING'])
        if heading_angle < 0.:
            heading_angle += 360.
        print 'heading angle: '+str(heading_angle)
        heading_angle *= np.pi/180.
        heading.append(heading_angle)
        
        inc_angle = float(ut.incidence_angle(atr, dimension=0))
        #print 'incidence angle: '+str(inc_angle)
        inc_angle *= np.pi/180.
        incidence.append(inc_angle)


    ##### 2. Project displacement from LOS to Horizontal and Vertical components
    # math for 3D: cos(theta)*Uz - cos(alpha)*sin(theta)*Ux + sin(alpha)*sin(theta)*Uy = Ulos
    # math for 2D: cos(theta)*Uv - sin(alpha-az)*sin(theta)*Uh = Ulos   #Uh_perp = 0.0
    # This could be easily modified to support multiple view geometry (e.g. two adjcent tracks from asc & desc) to resolve 3D

    # Design matrix
    A = np.zeros((2,2));
    for i in range(len(inps.file)):
        A[i,0] = np.cos(incidence[i])
        A[i,1] = np.sin(incidence[i]) * np.sin(heading[i]-inps.azimuth)

    A_inv = np.linalg.pinv(A)
    u_vh = np.dot(A_inv, u_los)

    u_v = np.reshape(u_vh[0,:], (length, width))
    u_h = np.reshape(u_vh[1,:], (length, width))

    ##### 3. Output
    # Attributes
    atr = atr1.copy()
    atr['WIDTH'] = str(width)
    atr['FILE_LENGTH'] = str(length)
    atr['X_FIRST'] = str(west)
    atr['Y_FIRST'] = str(north)
    atr['X_STEP'] = str(lon_step)
    atr['Y_STEP'] = str(lat_step)

    print '---------------------'
    outname = inps.outfile[0]
    print 'writing   vertical component to file: '+outname
    writefile.write(u_v, atr, outname)

    outname = inps.outfile[1]
    print 'writing horizontal component to file: '+outname
    writefile.write(u_h, atr, outname)

    print 'Done.'
    return


################################################################################
if __name__ == '__main__':
    main(sys.argv[1:])

