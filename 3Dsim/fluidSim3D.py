#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Jun 20 15:43:30 2018

@author: Dave
"""

import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import scipy.stats as st
import plotly as plo
import plotly.plotly as py
import plotly.graph_objs as go
import scipy.integrate as integrate
from readDSMC.py import dsmcQuant

# =============================================================================
# Constant Initialization
# =============================================================================

kb = 1.38 * 10**-23
NA = 6.022 * 10**23
T = 4 # Ambient temperature (K)
T_s = 4 # Species temperature (K) for initial velocity distributions
m = 0.004 / NA # Ambient gas mass (kg)
M = .190061 / NA # Species mass (kg)
massParam = 2 * m / (m + M)
n = 10**21 # m^-3
cross = 4 * np.pi * (140 * 10**(-12))**2 # two-helium cross sectional area
cross *= 4 # Rough estimate of He-YbOH cross sectional area

def set_derived_quants():
    global U, vMean, vMeanM, coll_freq, dt
    U = 1.5 * kb * T
    vMean = 2 * (2 * kb * T / (m * np.pi))**0.5
    vMeanM = 2 * (2 * kb * T_s / (M * np.pi))**0.5

    coll_freq = n * cross * vMeanM * (1 + M/m)**0.5 # Approximately n*cross*vMean
    dt = 0.01 / coll_freq # ∆t satisfying E[# collisions in 100∆t] = 1.

set_derived_quants()

# Remember to set form-dependent parameters below.


# =============================================================================
# Probability Distribution Functions
# =============================================================================

# Define a PDF ~ sin(x) to be used for random determination of azimuthal velocity angle
class theta_pdf(st.rv_continuous):
    def _pdf(self,x):
        return np.sin(x)/2  # Normalized over its range [0, pi]
theta_cv = theta_pdf(a=0, b=np.pi, name='theta_pdf') # theta_cv.rvs() for value

# Define a PDF ~ cos(x) to be used for random determination of impact angle
class Theta_pdf(st.rv_continuous):
    def _pdf(self,x):
        return -np.cos(x)  # Normalized over its range [pi/2, pi]
Theta_cv = Theta_pdf(a=np.pi/2, b=np.pi, name='Theta_pdf') # Theta_cv.rvs() for value

def set_derived_PDFs():
    global vel_cv, coll_vel_cv, species_vel_cv

    # Maxwell-Boltzmann Velocity Distribution for ambient molecules
    class vel_pdf(st.rv_continuous):
        def _pdf(self,x):
            return (m/(2*np.pi*kb*T))**1.5 * 4*np.pi * x**2 * np.exp(-m*x**2/(2*kb*T))  # x is velocity
    vel_cv = vel_pdf(a=0, b=5*vMean, name='vel_pdf') # vel_cv.rvs() for value

    # Maxwell-Boltzmann Velocity Distribution weighted by Bayesian influence to get P(v|collision)
    class coll_vel_pdf(st.rv_continuous):
        def _pdf(self,x):
            # x is ambient gas molecule velocity
            v_s = (vx**2+vy**2+vz**2)**0.5
            norm = integrate.quad(lambda x: (x**2 + v_s**2)**0.5 * (m/(2*np.pi*kb*T))**1.5 * \
                                  4*np.pi * x**2 * np.exp(-m*x**2/(2*kb*T)), 0, 8*vMean)[0]
            return ((x**2 + v_s**2)**0.5 / norm) * (m/(2*np.pi*kb*T))**1.5 * (\
                   4*np.pi * x**2 * np.exp(-m*x**2/(2*kb*T)))
    coll_vel_cv = coll_vel_pdf(a=0, b=8*vMean, name='coll_vel_pdf') # coll_vel_cv.rvs() for value

    # Maxwell-Boltzmann Velocity Distribution for species molecules
    # Used exclusively for setting initial velocities at a specified T_s
    class species_vel_pdf(st.rv_continuous):
        def _pdf(self,x):
            return (M/(2*np.pi*kb*T_s))**1.5 * 4*np.pi * x**2 * np.exp(-M*x**2/(2*kb*T_s))
    species_vel_cv = species_vel_pdf(a=0, b=5*vMeanM, name='species_vel_pdf') # species_vel_cv.rvs()

set_derived_PDFs()


# =============================================================================
# Form-dependent parameter setup
# =============================================================================

def dsmcQuant(x0, y0, z0, col, filename='ds2ff.dat'):
    '''
    Read & Interpolate quantities from an axially symmetric DSMC FF file.
    Col parameter: 2 = number density, 7 = temperature, 4 = velocities
    '''
    r0 = (x0**2 + y0**2)**0.5
    f = np.loadtxt(filename, skiprows=1) # Assumes only first row isn't data.
    quants = f[:, col]
    zs = f[:, 0] # DSMC calls these 'x' values
    rs = f[:, 1] # DSMC calls these 'y' values
    dists = (zs-z0)**2 + (rs-r0)**2

    # Find 3 nearest (r, z) points to (r0, z0).
    ind1 = np.argmin(dists)
    z1, r1, quant1 = zs[ind1], rs[ind1], quants[ind1]

    dists[ind1] = np.amax(dists)
    ind2 = np.argmin(dists)
    z2, r2, quant2 = zs[ind2], rs[ind2], quants[ind2]

    dists[ind2] = np.amax(dists)
    ind3 = np.argmin(dists)
    z3, r3, quant3 = zs[ind3], rs[ind3], quants[ind3]

    # solve quant_i = A * z_i + B * r_i + C for A, B, C using 3 nearest (r_i, z_i).
    left = np.array([[z1, r1, 1], [z2, r2, 1], [z3, r3, 1]])
    right = np.array([quant1, quant2, quant3])
    a, b, c = np.linalg.solve(left, right)

    quant0 = a * z0 + b * r0 + c

    print(quant1, quant2, quant3, quant0)

    if col == 4:
        vz = quant0
        vr = dsmcQuant(x0, y0, z0, 5, filename)
        vPerpCw = dsmcQuant(x0, y0, z0, 6, filename)

        theta = np.arctan2(y0, x0)
        rot = np.pi/2 - theta
        vx = np.cos(rot) * vPerpCw + np.sin(rot) * vr
        vy = -np.sin(rot) * vPerpCw + np.cos(rot) * vr

        return vx, vy, vz

    return quant0

def inBounds(x, y, z, form='box'):
    '''
    Return Boolean value for whether or not a position is within
    the boundary of "form".
    '''
    if form in ['box', 'curvedFlowBox']:
        inside = abs(x) <= 0.05 and abs(y) <= 0.05 and abs(z) <= 0.05
    return inside

def setAmbientFlow(x, y, z, form='box'):
    '''
    Given position of species molecule, set ambient flow velocities to known
    (DSMC-generated) local values.
    '''
    global xFlow, yFlow, zFlow
    if form in ['box', 'open']:
        xFlow, yFlow, zFlow = 0, 0, 0
    elif form == 'curvedFlowBox':
        r = (x**2+y**2)**0.5
        radFlow = -5*z*np.exp(-0.4*abs(5*z+1)) * 100 * r
        xFlow = x * radFlow / r * 100
        yFlow = y * radFlow / r * 100
        zFlow = 0.2 * 100

def setAmbientDensity(x, y, z, form='box'):
    '''
    Given position of species molecule, set ambient density to known
    (DSMC-generated) local value.
    '''
    global n
    if form in ['box', 'curvedFlowBox', 'open']:
        n = n

def setAmbientTemp(x, y, z, form='box'):
    '''
    Given position of species molecule, set ambient temperature to known
    (DSMC-generated) local value.
    '''
    global T
    if form in ['box', 'curvedFlowBox', 'open']:
        T = T

def updateParams(x, y, z, form='box'):
    setAmbientFlow(x, y, z, form)
    setAmbientDensity(x, y, z, form)
    setAmbientTemp(x, y, z, form)
    set_derived_quants()
    set_derived_PDFs()

# =============================================================================
# Helper Functions
# =============================================================================

def initial_species_velocity(T_s0):
    '''
    Given species temperature, return randomized (Boltzmann) speed in a
    randomized (spherically uniform) direction.
    '''
    global T_s
    T_s_holder = T_s
    T_s = T_s0
    set_derived_quants()
    set_derived_PDFs()
    v0 = species_vel_cv.rvs()
    T_s = T_s_holder # Return to thermalized value
    set_derived_quants()
    set_derived_PDFs()
    theta = theta_cv.rvs()
    phi = np.random.uniform(0, 2*np.pi)
    vx, vy, vz = (v0*np.sin(theta)*np.cos(phi), v0*np.sin(theta)\
                       *np.sin(phi), v0*np.cos(theta))
    return vx, vy, vz

def initial_species_position(L=0.01):
    '''
    Return a random position in a cube of side length L around the origin.
    '''
    x = np.random.uniform(-L/2, L/2)
    y = np.random.uniform(-L/2, L/2)
    z = np.random.uniform(-L/2, L/2)
    return x, y, z

def numClose(x, y, z, xs, ys, zs, dist=0.008):
    '''
    Gives the number of particles in xs,ys,zs within a cube of length 'dist'
    around a particle at x, y, z.
    '''
    num_close = -1 # Will always see ≥ 1 close particle (itself)
    for i in range(len(xs)):
        if abs(x-xs[i]) < dist and abs(y-ys[i]) < dist and abs(z-zs[i]) < dist:
            num_close += 1
    return num_close

def collide():
    '''
    For current values of position (giving ambient flow rate) and velocity,
    increment vx, vy, vz according to collision physics.
    '''
    global vx, vy, vz
    v = coll_vel_cv.rvs() # Modified Maxwell Distribution for ambient molecule
    Theta = Theta_cv.rvs()
    Phi = np.random.uniform(0, 2*np.pi)
    theta = theta_cv.rvs()
    phi = np.random.uniform(0, 2*np.pi)
    vx_amb = v * np.sin(theta) * np.cos(phi) + xFlow - vx
    vy_amb = v * np.sin(theta) * np.sin(phi) + yFlow - vy
    vz_amb = v * np.cos(theta) + zFlow - vz
    v_amb = (vx_amb**2 + vy_amb**2 + vz_amb**2)**0.5
    B = (vy_amb**2 + vz_amb**2 + (vx_amb-v_amb**2/vx_amb)**2)**-0.5

    vx += (v_amb * massParam * np.cos(Theta) * \
           (np.sin(Theta) * np.cos(Phi) * B * (vx_amb-v_amb**2/vx_amb)\
            + vx_amb * np.cos(Theta)/v_amb))

    vy += (v_amb * massParam * np.cos(Theta) * \
           (np.sin(Theta)*np.cos(Phi)*B*vy_amb + np.sin(Theta)*np.sin(Phi)*\
            (vz_amb/v_amb*B*(vx_amb-v_amb**2/vx_amb)-vx_amb*B*vz_amb/v_amb)\
            + np.cos(Theta)*vy_amb/v_amb))

    vz += (v_amb * massParam * np.cos(Theta) * \
           (np.sin(Theta)*np.cos(Phi)*B*vz_amb + np.sin(Theta)*np.sin(Phi)*\
            (vx_amb*B*vy_amb/v_amb-vy_amb/v_amb*B*(vx_amb-v_amb**2/vx_amb))\
            + np.cos(Theta)*vz_amb/v_amb))


# =============================================================================
# Simulation & Data Retrieval
# =============================================================================

def pathTrace(x0=0, y0=0, z0=0, T_s0=4, form='box'):
    '''
    Track and return a list of sequential positions over time on a given path.
    '''
    global vx, vy, vz, t # Global velocities used for collide() and updating PDFs
    x, y, z = x0, y0, z0
    vx, vy, vz = initial_species_velocity(T_s0)
    t = 0
    xs = [0]
    ys = [0]
    zs = [0]

    while inBounds(x, y, z, form):
        # Typically takes 5-20 ms to leave box
        updateParams(x, y, z, form)
        if np.random.uniform() < 0.01: # 1/100 chance of collision
            collide()
        t += dt
        x += vx * dt
        y += vy * dt
        z += vz * dt
        xs.append(x)
        ys.append(y)
        zs.append(z)

    print("Time to wall: "+str(t)+" seconds")
    return xs, ys, zs

def getDensityTrend(filename):
    '''
    Record mean time to hit wall for a range of ambient densities.
    '''
    global n
    with open(filename, 'w') as f:
        f.write("n (per cu. m)   mean iterations   mean time to stick   sig iter   sig time\n")
        for density in [10**9, 10**9*5, 10**10, 10**10*5, 10**11, 10**11*5, 10**12]:
            n = density
            lens = []
            times = []
            for j in range(1000):
                xs, ys, zs = pathTrace()
                lens.append(len(xs))
                times.append(t)
            meanLen = str(np.mean(lens))
            meanTime = str(np.mean(times))
            stdLen = str(np.std(lens)/(len(lens)**0.5))
            stdTime = str(np.std(times)/(len(times)**0.5))
            f.write('%.1E'%n+' '+meanLen+' '+meanTime+' '+stdLen+' '+stdTime+'\n')
    f.close()

def getData(t1=0.00005, t2=0.0015, step=0.00005, trials=400, x0=0, y0=0, z0=0, T_s0=4):
    '''
    For a range of total times, record expected values of final position,
    square-distance, and speed near end of path.
    '''
    global vx, vy, vz
    updateParams(x0, y0, z0, 'open')
    with open('_'.join(map(str,[int(1e6*t1), int(1e6*t2), int(T_s0), int(xFlow), \
                                int(M/m), int(np.log10(float(n)))]))+'.dat', 'w') as f:
        f.write('   '.join(['time (s)','xAvg (m)','yAvg (m)', 'zAvg (m)', 'SqrAvg (sq. m)',\
                          'SpeedAvg (m/s)','sigX','sigY', 'sigZ', 'sigSqr','sigSpeed'])+'\n')
        for time in np.arange(t1, t2, step):
            print(time)
            xs = []
            ys = []
            zs = []
            squares = []
            speedAvgs = []
            for j in range(trials):
                print(j)
                t = 0
                x, y, z = x0, y0, z0
                vx, vy, vz = initial_species_velocity(T_s0)
                speeds = []
                while t < time:
                    updateParams(x, y, z, 'open')
                    if np.random.uniform() < 0.01: # 1/100 chance of collision
                        collide()
                    t += dt
                    x += vx * dt
                    y += vy * dt
                    z += vz * dt
                    if t > 0.8 * time:
                        speeds.append((vx**2 + vy**2 + vz**2)**0.5)
                speedAvgs.append(np.mean(speeds))
                squares.append(x**2+y**2+z**2)
                xs.append(x)
                ys.append(y)
                zs.append(z)
            meanx = str(np.mean(xs))
            meany = str(np.mean(ys))
            meanz = str(np.mean(zs))
            meanSq = str(np.mean(squares))
            meanSpeed = str(np.mean(speedAvgs))
            stdx = str(np.std(xs)/(len(xs)**0.5))
            stdy = str(np.std(ys)/(len(ys)**0.5))
            stdz = str(np.std(zs)/(len(zs)**0.5))
            stdSq = str(np.std(squares)/(len(squares)**0.5))
            stdSpeed = str(np.std(speedAvgs)/(len(speedAvgs)**0.5))
            f.write(' '.join([str(time),meanx,meany,meanz,meanSq,meanSpeed,\
                              stdx,stdy,stdz,stdSq,stdSpeed])+'\n')
    f.close()

def endPosition(T_s0=4, L0=0.01, form='curvedFlowBox'):
    '''
    Return the final position of a particle somewhere on the (10cm)^3 box.
    Initial position determined randomly in a cube around the origin.
    '''
    global vx, vy, vz
    x, y, z = initial_species_position(L0)
    vx, vy, vz = initial_species_velocity(T_s0)

    while inBounds(x, y, z, form):
        # Typically takes few ms to leave box
        updateParams(x, y, z, form)
        if np.random.uniform() < 0.01: # 1/100 chance of collision
            collide()
        x += vx * dt
        y += vy * dt
        z += vz * dt

    return x, y, z


# =============================================================================
# Image-generating functions
# =============================================================================

def showPaths(filename):
    '''
    Generate a scatter plot of 1000 equally t-spaced points from each of
    three independent paths generated by pathTrace().
    '''
    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')

    for j in range(1, 4):
        xs, ys, zs = pathTrace()
        for i in range(0, len(xs), int(len(xs)/1000)):
            if j == 1 :
                colour = plt.cm.Greens(int(264. * i / len(xs)))
            elif j == 2:
                colour = plt.cm.Blues(int(264. * i / len(xs)))
            else:
                colour = plt.cm.Reds(int(264. * i / len(xs)))
            ax.scatter(xs[i], ys[i], zs[i], s=.5, c=colour)

    ax.set_xlim(-.05, .05)
    ax.set_ylim(-.05, .05)
    ax.set_zlim(-.05, .05)
    plt.title("Paths of a Heavy Particle, n = %.0E" %n)
    ax.set_xlabel('x, meters')
    ax.set_ylabel('y, meters')
    ax.set_zlabel('z, meters')
    plt.savefig(filename)
    plt.show()

def showWalls(filename):
    '''
    Generate a scatter plot of final positions of molecules as determined by
    the endPosition function parameters.
    '''
    with open("finalPositions.dat", "w") as f:
        for j in range(120):
            print(j)
            x, y, z = endPosition()
            f.write("%.5f %.5f %.5f \n"%(x, y, z))
            colour = plt.cm.Greens(int(64 + 200 * abs(y) / 0.05)) # color = y coord
            plt.plot(x, z, c=colour, marker='+', ms=13)
    f.close()

    plt.hlines(0.05, -.05, .05, colors='gray', linewidths=.5)
    plt.hlines(-0.05, -.05, .05, colors='gray', linewidths=.5)
    plt.vlines(0.05, -.05, .05, colors='gray', linewidths=.5)
    plt.vlines(-0.05, -.05, .05, colors='gray', linewidths=.5)
    plt.xlim(-.055, .055)
    plt.ylim(-.055, .055)
    plt.title("Final Positions of a Heavy Particle")
    plt.xlabel('x, meters')
    plt.ylabel('z, meters')
    plt.savefig(filename)
    plt.show()

def pointEmitter(filename="ConstantFlowEmitter.dat", x0=0, y0=0, z0=0, T_s0=4, form='box'):
    '''
    Assuming constant-rate emission of species molecules of random velocities
    (determined by a T = T_s0 thermal distribution) from (x0, y0, z0), record
    the positions of all emitted particles after some time, assign each
    particle a density, and plot them with density-scaling color values.
    '''
    global vx, vy, vz
    xs, ys, zs = [], [], []
    for time in np.arange(0.01, 6, 0.01): # ms
        print(time)
        x, y, z = x0, y0, z0
        vx, vy, vz = initial_species_velocity(T_s0)
        t = 0
        while t < time * 1e-3:
            updateParams(x, y, z, form)
            if np.random.uniform() < 0.01: # 1/100 chance of collision
                collide()
            t += dt
            x += vx * dt
            y += vy * dt
            z += vz * dt
        xs.append(x)
        ys.append(y)
        zs.append(z)

    densities = []
    for i in range(len(xs)):
        densities.append(numClose(xs[i], ys[i], zs[i], xs, ys, zs))

    trace = go.Scatter3d(x=xs, y=ys, z=zs, mode='markers', \
        marker=dict(size=12,color=densities,colorscale='Rainbow',opacity=0.8))
    fig = go.Figure(data=[trace], layout=go.Layout())
    plo.offline.plot(fig, filename='simple-3d-scatter')

    with open(filename, 'w') as f:
        for i in range(len(xs)):
            f.write(str(xs[i])+' '+str(ys[i])+' '+str(zs[i])+'\n')
    f.close()