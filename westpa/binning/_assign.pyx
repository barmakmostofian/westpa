from __future__ import print_function,division
import cython
import numpy
cimport numpy

# Coordinates are assumed to be 32-bit floats, and bin indices are
# defined to be 16-bit ints.

from numpy import uint16, float32
from numpy cimport uint16_t, float32_t

ctypedef numpy.float32_t _fptype
  
ctypedef numpy.uint8_t bool_t
ctypedef float32_t coord_t    
ctypedef uint16_t index_t
ctypedef numpy.float64_t weight_t

bool_dtype = numpy.bool_
internal_bool_dtype = numpy.uint8
index_dtype = numpy.uint16
coord_dtype = numpy.float32

@cython.boundscheck(False)
@cython.wraparound(False)
cpdef rectilinear_assign(coord_t[:,:] coords,
                        numpy.ndarray[bool_t,ndim=1,cast=True] mask,
                        index_t[:] output,
                        boundaries,
                        index_t[:] boundlens):

    '''For bins delimited by sets boundaries on a rectilinear grid (``boundaries``),
    assign coordinates to bins, assuming C ordering of indices within the grid.
    ``boundlens`` is the number of boundaries in each dimension. 
    
    '''
    cdef:
        int icoord, idim, ibound, boundlen
        int ndim
        int ncoords = coords.shape[0]
        index_t index, stridefac
        coord_t bound
        coord_t cval

        numpy.ndarray[coord_t, ndim=1] boundvec
        numpy.ndarray[numpy.uintp_t, ndim=1] boundvecs
        coord_t* bvec
            
    # We assume greater locality across boundary vectors than across the
    # coordinate array. To exploit this locality, and only have to
    # relinquish/reacquire the GIL once, we extract pointers to the first
    # element of each boundary vector; we then release the GIL and go to
    # town on the entire data set.
    
    ndim = len(boundaries)
    boundvecs = numpy.empty((ndim,), dtype=numpy.uintp) 
    
    for 0 <= idim < ndim:
        boundvec = boundaries[idim]
        boundvecs[idim] = <numpy.uintp_t> &boundvec[0]
                
    with nogil:
        for icoord in range(ncoords):
            if not mask[icoord]:
                continue
            
            output[icoord] = 0
            stridefac = 1
    
            # backwards iteration needs signed values, so that the final != -1 works        
            for idim in range(ndim-1,-1,-1):
                found = 0
                cval = coords[icoord,idim]
                boundlen = boundlens[idim]
                bvec = <coord_t*> boundvecs[idim]
                
                if cval < bvec[0] or cval >= bvec[boundlen-1]:
                    with gil:
                        raise ValueError('coordinate value {} is out of bin space in dimension {}'.format(cval,idim))
                                    
                for ibound in range(1,boundlen):
                    if cval < bvec[ibound]:
                        index = ibound-1
                        break
                
                output[icoord] += index * stridefac
                stridefac *= boundlen-1
        
@cython.boundscheck(False)
@cython.wraparound(False)    
cpdef testfunc(coord_t[:,:] coords,
               numpy.ndarray[bool_t, ndim=1, cast=True] mask,
               index_t[:] output):
    cdef:
        index_t icoord
    
    for icoord in range(len(coords)):
        if mask[icoord]:
            if coords[icoord,0] < 0.5:
                output[icoord] = 0
            else:
                output[icoord] = 1

# optimized function applications
@cython.boundscheck(False)
@cython.wraparound(False)    
cpdef apply_down(func,
                 args,
                 kwargs,
                 coord_t[:,:] coords,
                 numpy.ndarray[bool_t, ndim=1, cast=True] mask,
                 index_t[:] output):
    '''Apply func(coord, *args, **kwargs) to each input coordinate tuple,
    skipping any for which mask is false and writing results to output.'''
    cdef:
        Py_ssize_t i, n

    n = len(output)
    for i from 0 <= i < n:
        if mask[i]:
            output[i] = func(coords[i], *args, **kwargs)

@cython.boundscheck(False)
@cython.wraparound(False)    
cpdef apply_down_argmin_across(func,
                               args,
                               kwargs,
                               func_output_len,
                               coord_t[:,:] coords,
                               numpy.ndarray[bool_t, ndim=1, cast=True] mask,
                               index_t[:] output):
    '''Apply func(coord, *args, **kwargs) to each input coordinate tuple,
    skipping any for which mask is false and writing results to output.'''
    cdef:
        Py_ssize_t icoord, iout, ncoord, nout,
        coord_t _min
        index_t _argmin
        numpy.ndarray[coord_t, ndim=1] func_output
    
    nout = func_output_len
    func_output = numpy.empty((func_output_len,), dtype=coord_dtype)

    ncoord = len(coords)
    for icoord from 0 <= icoord < ncoord:
        if mask[icoord]:
            func_output = func(coords[icoord], *args, **kwargs)
            if len(func_output) != func_output_len:
                raise TypeError('function returned a vector of length {} (expected length {})'
                                .format(len(func_output), func_output_len))
            
            # find minimum value
            _min = func_output[0]
            _argmin = 0
            for iout from 1 <= iout < nout:
                if func_output[iout] < _min:
                    _min = func_output[iout]
                    _argmin = iout
                    
            output[icoord] = _argmin
                
# optimized lookup table routine
@cython.boundscheck(False)
@cython.wraparound(False)    
cpdef output_map(index_t[:] output,
                 index_t[:] omap,
                 numpy.ndarray[bool_t, ndim=1, cast=True] mask):
    '''For each output for which mask is true, execute output[i] = omap[output[i]]'''

    cdef:
        Py_ssize_t i, ncoords, nmappings
        index_t o
        
    ncoords = len(output)
    nmappings = len(omap)
    with nogil:
        for i from 0 <= i < ncoords:
            if mask[i]:
                o = output[i]
                if o >= nmappings:
                    with gil:
                        raise IndexError('value {} not available in output table'.format(o))
                output[i] = omap[o]

@cython.boundscheck(False)
@cython.wraparound(False)    
cpdef assign_and_label(Py_ssize_t nsegs_lb, 
                       Py_ssize_t nsegs_ub,
                       long[:] parent_ids, # only for given segments
                       object assign,
                       Py_ssize_t nstates,
                       index_t[:] state_map,
                       index_t[:] last_labels, # must be for all segments
                       object pcoords # only for given segments
                       ):
    '''Assign trajectories to bins and last-visted macrostates for each timepoint.'''
    
    cdef:
        Py_ssize_t ipt, nsegs, npts, iseg
        index_t[:,:] _assignments, _trajlabels
        index_t[:] seg_assignments
        long seg_id, parent_id, msegid
        index_t ptlabel
    
    nsegs = nsegs_ub - nsegs_lb
    npts = pcoords.shape[1]
    assignments = numpy.empty((nsegs,npts), index_dtype)
    trajlabels = numpy.empty((nsegs,npts), index_dtype)
    
    _assignments = assignments
    _trajlabels = trajlabels
    mask = numpy.ones((npts,), numpy.bool_)
    
    for iseg in range(nsegs):
        assign(pcoords[iseg,:], mask, assignments[iseg,:])
    
    if state_map is not None:
        with nogil:
            for iseg in range(nsegs):
                seg_id = iseg+nsegs_lb        
                parent_id = parent_ids[iseg]
                if state_map is not None:
                    for ipt in range(npts):
                        ptlabel = state_map[_assignments[iseg,ipt]]
                        if ptlabel == nstates: # unknown state/transition region 
                            if ipt == 0:
                                if parent_id < 0:
                                    # We have started a trajectory in a transition region
                                    _trajlabels[iseg,ipt] = nstates
                                else:
                                    # We can inherit the ending point from the previous iteration
                                    # This should be nstates (unknown_state) for the first iteration
                                    _trajlabels[iseg,ipt] = last_labels[parent_id]
                            else:
                                # We are currently in a transition region, but we care about the last state we visited,
                                # so inherit that state from the previous point
                                _trajlabels[iseg,ipt] = _trajlabels[iseg,ipt-1]
                        else:
                            _trajlabels[iseg,ipt] = ptlabel
    else:
        trajlabels.fill(nstates)
            
    return assignments, trajlabels

@cython.cdivision(True)
@cython.boundscheck(False)
@cython.wraparound(False)    
cpdef accumulate_labeled_populations(weight_t[:]  weights,
                                     index_t[:,:] bin_assignments,
                                     index_t[:,:] label_assignments,
                                     weight_t[:,:] labeled_bin_pops):
    '''For a set of segments in one iteration, calculate the average population in each bin, with
    separation by last-visited macrostate.'''
    cdef:
        Py_ssize_t nsegs, npts, nbins, nstates, seg_id, ipt
        index_t assignment, traj_assignment
        weight_t ptwt
        
    nstates = labeled_bin_pops.shape[0] # this will generally be n_valid_states + 1 (for unknown state)
    nbins = labeled_bin_pops.shape[1]   # this may be n_valid_bins + 1 (for unknown bin)
    nsegs = bin_assignments.shape[0]
    npts = bin_assignments.shape[1]
    
    with nogil:
        for seg_id in range(nsegs):
            ptwt = weights[seg_id] / npts
            for ipt in range(npts):
                assignment = bin_assignments[seg_id,ipt]
                if assignment >= nbins:
                    with gil:
                        raise ValueError('invalid bin assignment for segment {} point {}'.format(seg_id, ipt))

                traj_assignment = label_assignments[seg_id,ipt]
                if traj_assignment >= nstates:
                    with gil:
                        raise ValueError('invalid trajectory label for segment {} point {}'.format(seg_id, ipt))
                
                labeled_bin_pops[traj_assignment,assignment] += ptwt
