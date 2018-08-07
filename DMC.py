import math
#       > which can be replaced by numpy    
#       > for a single operation, math.sqrt is faster (about 50%) than numpy.sqrt
#       > but for array operation, np.sqrt can be fater (about 500% with 5000 walkers) than math.sqrt

# import random 
#       > note numpy provides array-like random generation, faster than random module
import numpy as np
#       > prefer array than list! array structure is faster
#       > avoiding using list structure and 'for' statement, or you can use @jit decorate such blocks
import pandas as pd
#       > read or save data, a substitution for read/write() funcrion, popular in scientific computation
#       > see more at <https://pandas.pydata.org/pandas-docs/>
#       > to install : `sudo pip3 install pandas`
import os
import time
#       > record unning time
# import copy 
#       > note numpy provides copy, more friendly in array operation
from mpl_toolkits.mplot3d import Axes3D
import matplotlib.pyplot as plt
import loadfile as lf
#       > see ./loadfile.py
#       > it loads files (lf.Load, lf.Add), from the dictory keys to get the values
from numba import void, int32, float32    # import the types
from numba import jit, jitclass
#       > numba provides acceleration <refering https://numba.pydata.org>
#       > @jit : add before the self-defined function (not the class function)
#       > @jitclass : add before the class, careful with datatype
#       > to install : `sudo pip3 install numba`

# Summary of performance
#       > about 9s CPU time for 5000 walkers calculate 5000 times, 
#       > much faster than 50s CPU time for 5000 walkers calculate 1000 times of original code


global dmc_distance_eps
dmc_distance_eps = 0.0001

# for some function optimized by numba.jit, we place them here

@jit(nopython=True)
def floorcutoff(myarray, cutvalue):
    for i in range(len(myarray)):
        if(myarray[i] < cutvalue):
            myarray[i] = cutvalue
    return myarray

@jit(nopython=True)
def ceilcutoff(myarray, cutvalue):
    for i in range(len(myarray)):
        if(myarray[i] > cutvalue):
            myarray[i] = cutvalue
    return myarray

@jit(nopython=True)
def CoulombNN(PointN1, PointN2):
    R = math.sqrt( (PointN1[1]-PointN2[1])**2 + (PointN1[2]-PointN2[2])**2 + (PointN1[3]-PointN2[3])**2 )
    if R < dmc_distance_eps:
        R = dmc_distance_eps
    return 1/R

@jit(nopython=True)   
def CoulombEE(arrayPointE1, arrayPointE2):
    arrayR = np.sqrt( (arrayPointE1[:,1] - arrayPointE2[:,1])**2 + (arrayPointE1[:,2] - arrayPointE2[:,2])**2 
        + (arrayPointE1[:,3]-arrayPointE2[:,3])**2 )
    arrayR = floorcutoff(arrayR, dmc_distance_eps)
    return 1/arrayR

@jit(nopython=True)
def CoulombNE(PointN, arrayPointE):
    arrayR = np.sqrt( (PointN[1] - arrayPointE[:,1])**2 + (PointN[2] - arrayPointE[:,2])**2 
        + (PointN[3] - arrayPointE[:,3])**2 )
    arrayR = floorcutoff(arrayR, dmc_distance_eps)
    return 1/arrayR

@jit(nopython=True)
def Select_BirthOrDeath(marray):
    birthlist = []
    deathlist = []
    for k in range(len(marray)):
        if marray[k] == 1:
            # this is the most case, here we stop following judgement for faster
            continue
        elif marray[k] == 0:
            deathlist.append(k)
            continue
        elif marray[k] == 2:
            birthlist.append(k)
            continue
        elif marray[k] >= 3:
            birthlist.append(k)
            birthlist.append(k)
            continue
        else:
            pass
    return birthlist,deathlist


#spec = [
#    ('time_Displacement', float32), 
#    ('time_CalcPotential', float32),
#    ('time_BirthOrDeath', float32),
#    ('time_total', float32),
#    ('mass', float32),
#    ('dt', float32),
#    ('calctimes', int32),
#    ('alpha',float32),
#    ('sigma',float32),
#    ('nelectrons', int32),
#    ('nnuclei', int32),
#    ('nwalkers_initial', int32),
#    ('nwalkers_current', int32),
#    ('nwalkers_max', int32),
#    ('walkers', float32[:,:,:]),
#    ('nuclei', float32[:,:]),
#    ('potential', float32[:]),
#    ('ERseries', float32[:]),
#    ('ER', float32),
#]
# @jitclass(spec)     
# BUGS: it seems that jitclass doesn't support 'exit()' and 'os' module
#           > you may fix this bug to decorate this class, more operation refering <https://numba.pydata.org/doc.html>
class DMC:
    # parameters list, move arguments to 'DMC.rc' file; revise them in the DMC.file
    #     ( examples.rc )
    # mass          = 1
    # dt            = 0.01
    # calctimes     = 1000
    # alpha         = 1.0
    # nelectrons    = 2
    # nnuclei       = 2
    # nwalkers_max     = 10000
    # nwalkers_initial = 5000
    
    # ( treat followings as class's attributes, though without statements)
    #
    # walkers       > the array records walkers
    # nuclei        > the array records nuclei
    # potential     > the array records Potential of each walker
    
    def __init__(self, DMC_rcfile, NUC_csvfile):
        # read arguments from a file, see more in 'loadfile.py', default DMC_rcfile='DMC.rc'
        # NUC_csvfile is the file of nuclei coordinares ( recommend *.csv format)
        if( os.path.isfile(DMC_rcfile) ):
            self.myload = lf.Load(DMC_rcfile)
            # mass should move in array[0], if for different particles
            self.mass = self.myload.args['mass']
            self.dt = self.myload.args['dt']
            self.calctimes = int( self.myload.args['calctimes'] )
            self.alpha = self.myload.args['alpha']
            self.nelectrons = int( self.myload.args['nelectrons'] )
            self.nnuclei = int( self.myload.args['nnuclei'] )
            self.nwalkers_max = int( self.myload.args['nwalkers_max'] )
            self.nwalkers_initial = int( self.myload.args['nwalkers_initial'] )
            
            self.sigma = np.sqrt( self.dt/self.mass )
            self.nwalkers_current = self.nwalkers_initial
        else:
            print("error, %s doesn't exist"%DMC_rcfile)
            exit()
        
        # read the configuration of nuclei
        # 4-d array note as [mass, x, y, z]
        self.nuclei = np.zeros((self.nnuclei, 4))
        # simply initialze as:
        #   >   self.nuclei[0,:] = [1836, -0.699, 0.000, 0.000]
        #   >   self.nuclei[1,:] = [1836,  0.699, 0.000, 0.000]
        # or may read nuclei coordinates from (csv-like) data-file (for example, named as 'NUC.csv'):
        if( os.path.isfile(NUC_csvfile) ):
            self.nuclei = (pd.read_csv(NUC_csvfile,header=None)).values
        else:
            print("error, %s doesn't exist"%NUC_csvfile)
            exit()
        
        # creat walkers array
        # with array_like_structure:   [ number_of_walker,  number_of_e,  4-d coordinates ]
        self.walkers = np.zeros(( self.nwalkers_max, self.nelectrons, 4))
        # avoid electron too closed for each walker, so we give different electron different positioin 
        #       > alternative to read from an ELE_csvfile
        for i in range(self.nelectrons):
            self.walkers[:,i,0] = 1.000 # electron mass, you can revise for the miu meson-eletron mixture
            self.walkers[:,i,1] = 1.000 * np.cos( np.pi*i/(self.nelectrons) )
            self.walkers[:,i,2] = 1.000 * np.sin( np.pi*i/(self.nelectrons) )
            self.walkers[:,i,3] = 0.000
        
        # creat matrix recording potential
        self.potential = np.zeros((self.nwalkers_max))
        # creat time-potential series
        self.ERseries = np.zeros((self.calctimes))
    
    def CalcPotential(self):
        self.potential = 0
        # calculate interaction of NN and NE  (note, here operate array directly)
        for i in range(self.nnuclei):
            for j in range(i+1,self.nnuclei):
                self.potential += CoulombNN(self.nuclei[i,:], self.nuclei[j,:])
            for j in range(self.nelectrons):
                self.potential -= CoulombNE( self.nuclei[i,:], self.walkers[:,j,:] )
        # calculate interaction of EE
        for i in range(self.nelectrons):
            for j in range(i+1,self.nelectrons):
                self.potential += CoulombEE( self.walkers[:,i,:], self.walkers[:,j,:] )
        self.ER = self.potential[0:self.nwalkers_current].mean() * self.alpha * float(self.nwalkers_current)/float(self.nwalkers_initial)
        return

    def Displacement(self):
        # following (actually has been optimized by numpy moduel itself), costing almot 60% of running time
        #       > and wothout further better improvement even though put it out the class body with @jit decorator
        #       > THIS IS THE RATE-DETERMINING-STEP, and for stochastic method code it should to be RDS
        #       > it means now the optimization almost reach the python's limit; for fater rate, refering C/Fortran 
        self.walkers[:self.nwalkers_current,:,1:4] += np.random.normal(0.0000, self.sigma, (self.nwalkers_current, self.nelectrons, 3))
        # NOTE: if for different particle, sigma should be array-like
        return

    def BirthOrDeath(self):
        # t1 = time.clock()
        # select the indice of death and birth, for function 'range()' is static, can't add/remove on-the-fly
        W = 1.000 - ( self.potential[:self.nwalkers_current] - self.ER ) *self.dt
        m = np.floor( W + np.random.uniform(0, 1, self.nwalkers_current) )
        # following fuction place before the DMC class, for @jit optimization
        birthlist, deathlist = Select_BirthOrDeath( m )
        
        # t2 = time.clock()
        # give births
        for birthindex in birthlist:
            # birth in original dead walkers (or called relive)
            if( len(deathlist) > 0 ):
                self.walkers[deathlist[-1],:,:] = np.copy( self.walkers[birthindex,:,:] )
                deathlist.pop()
                continue
            # add new walkers
            if( self.nwalkers_current < self.nwalkers_max):
                self.walkers[self.nwalkers_current,:,:] = np.copy( self.walkers[birthindex,:,:] )
                self.nwalkers_current += 1
            else:
                print('error: overfolw! Please enlarge the nwalkers_max')
                exit()
        # t3 = time.clock()
        # give extra deaths
        while(len(deathlist) > 0):
            if(self.nwalkers_current-1 in deathlist):
                self.nwalkers_current -= 1
                continue
            self.walkers[deathlist[-1],:,:] = np.copy( self.walkers[self.nwalkers_current-1,:,:] )
            deathlist.pop()
            self.nwalkers_current -= 1
        # t4 = time.clock()
        # print('using time: select:birth:death   %.1f:%.1f:%.1f'%tuple(100/(t4-t1)*np.array([t2-t1,t3-t2,t4-t3])))
        # for orginal code, test show that select waste 99% time
        # so vectorize selection block, lower down time to 60%
               
    def DoJob(self):
        self.time_Displacement = 0
        self.time_CalcPotential = 0
        self.time_BirthOrDeath = 0
        time_begin = time.clock()
        for i in range(self.calctimes):
            t1 = time.clock()
            self.Displacement()
            t2 = time.clock()
            self.CalcPotential()
            t3 = time.clock()
            self.BirthOrDeath()
            t4 = time.clock()
            self.time_Displacement += (t2-t1)
            self.time_CalcPotential += (t3-t2)
            self.time_BirthOrDeath += (t4-t3)
            self.ERseries[i] = self.ER
            if( ( i%( self.calctimes//10 )) == 0 ):
                print('Processing %d %% : '%(100*i//self.calctimes) )
                print('      Current alive = %d'%self.nwalkers_current)
                print('      Current ER    = %.10f\n'%self.ER)
        print('Job done!')
        time_end = time.clock()
        self.time_total = time_end - time_begin
        
    def ReJob(self):
        # read the lastest calulation
        self.walkers = (pd.read_csv('restart.csv',header=None)).values
        
    def SummaryJob(self):
        print( 'Analytical ground state energy = %.10f\n'%(-1.165) )
        print( 'Numerical ground state energy  = %.10f\n'%self.ERseries[self.calctimes//2:].mean() )
        print('CPU running time: %f '%self.time_total)
        print('    time_Displacement  : %f %%'%(100*self.time_Displacement/self.time_total) )
        print('    time_CaclPotential : %f %%'%(100*self.time_CalcPotential/self.time_total) )
        print('    time_BirthOrDeath  : %f %%'%(100*self.time_BirthOrDeath/self.time_total) )
        # if save for a restart
        #       > 2-d array only, should reshape the walkers
        #       > if read to plot density distribution, please reshape back
        restart_coords = pd.DataFrame( self.walkers[0:self.nwalkers_current,:,:].reshape((self.nwalkers_current,-1)) )
        restart_coords.to_csv('restart.csv', header=None)
        save_ers = pd.DataFrame(self.ERseries)
        save_ers.to_csv('ERs.csv', header=None)
        
        # plot the RMSD
        if('Flag_Plot_RMSD' in self.myload.args and self.myload.args['Flag_Plot_RMSD']==1):
            plt.plot(self.dt*np.arange(self.calctimes), self.ERseries, 'r--')
            plt.xlabel(self.myload.args['Plot_Xlabel'])
            plt.ylabel(self.myload.args['Plot_Ylabel'])
            plt.savefig('PlotConvergence.png')
            if('Flag_Plot_Show' in self.myload.args and self.myload.args['Flag_Plot_Show']==1):
                plt.show()
        
        # plot density
        if('Flag_Plot_DIST' in self.myload.args and self.myload.args['Flag_Plot_DIST']==1):
            fig = plt.figure()
            ax = fig.add_subplot(111, projection='3d')
            for i in range(self.nnuclei):
                xn = self.nuclei[i,1]
                yn = self.nuclei[i,2]
                zn = self.nuclei[i,3]
                ax.scatter(xn, yn, zn, s=50, c='k', marker='o')
            for i in range(self.nelectrons):
                xs = self.walkers[:self.nwalkers_current,i,1].reshape(self.nwalkers_current)
                ys = self.walkers[:self.nwalkers_current,i,2].reshape(self.nwalkers_current)
                zs = self.walkers[:self.nwalkers_current,i,3].reshape(self.nwalkers_current)
                ax.scatter(xs, ys, zs, s=1, c=(i/self.nelectrons,0,1-i/self.nelectrons), marker='.', alpha=0.3)
            ax.set_xlabel('X Label')
            ax.set_ylabel('Y Label')
            ax.set_zlabel('Z Label')
            ax.set_xlim((-4,4))
            ax.set_ylim((-4,4))
            ax.set_zlim((-4,4))
            ax.set_title('Distribution of Walkers')
            plt.savefig('PlotDistribution.png')
            if('Flag_Plot_Show' in self.myload.args and self.myload.args['Flag_Plot_Show']==1):
                plt.show()
                

if __name__ == '__main__':
    myDMC = DMC('DMC.rc','NUC.csv')
    myDMC.DoJob()
    myDMC.SummaryJob()














