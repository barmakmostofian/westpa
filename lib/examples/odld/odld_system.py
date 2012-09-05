from __future__ import print_function, division
import numpy
from wemd.propagators import WEMDPropagator
from wemd.systems import WEMDSystem
from wemd.pcoords import PiecewiseRegionSet, RectilinearRegionSet

PI = numpy.pi
from numpy import sin, cos, exp
from numpy.random import normal as random_normal

pcoord_len = 21
pcoord_dtype = numpy.float32    

class ODLDPropagator(WEMDPropagator):
    def __init__(self):
        super(ODLDPropagator,self).__init__()
        
        self.coord_len = pcoord_len
        self.coord_dtype = pcoord_dtype
        self.coord_ndim = 1
        
        self.initial_pcoord = numpy.array([8.0], dtype=self.coord_dtype)
        
        self.sigma = 0.001**(0.5)
        
        self.A = 2
        self.B = 10
        self.C = 0.5
        self.x0 = 1

    def get_pcoord(self, state):
        '''Get the progress coordinate of the given basis or initial state.'''
        state.pcoord = self.initial_pcoord.copy()
                
    def gen_istate(self, basis_state, initial_state):
        initial_state.pcoord = self.initial_pcoord.copy()
        initial_state.istate_status = initial_state.ISTATE_STATUS_PREPARED
        return initial_state

    def propagate(self, segments):
        
        A, B, C, x0 = self.A, self.B, self.C, self.x0
        
        n_segs = len(segments)
    
        coords = numpy.empty((n_segs, self.coord_len, self.coord_ndim), dtype=self.coord_dtype)
        
        for iseg, segment in enumerate(segments):
            coords[iseg,0] = segment.pcoord[0]
            
        twopi_by_A = 2*PI/A
        half_B = B/2
        sigma = self.sigma
        gradfactor = self.sigma*self.sigma/2
        coord_len = self.coord_len
        for istep in xrange(1,coord_len):
            x = coords[:,istep-1,0]
            
            xarg = twopi_by_A*(x - x0)
            
            eCx = numpy.exp(C*x)
            eCx_less_one = eCx - 1.0
            
            displacements = random_normal(scale=sigma, size=(n_segs,))
            grad = half_B / (eCx_less_one*eCx_less_one)*(twopi_by_A*eCx_less_one*sin(xarg)+C*eCx*cos(xarg))
            
            newx = x - gradfactor*grad + displacements
            coords[:,istep,0] = newx
            
        for iseg, segment in enumerate(segments):
            segment.pcoord[...] = coords[iseg,:]
            segment.status = segment.SEG_STATUS_COMPLETE
    
        return segments

class ODLDSystem(WEMDSystem):
    def new_region_set(self):
        region_set = RectilinearRegionSet([[0,1.4] + list(numpy.arange(1.5, 10.1, 0.1)) + [float('inf')]])
        for bin in region_set.get_all_bins():
            bin.target_count = 48
        return region_set

    def initialize(self):
        self.pcoord_ndim = 1
        self.pcoord_dtype = pcoord_dtype
        self.pcoord_len = pcoord_len
        
