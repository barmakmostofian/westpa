# Copyright (C) 2017 Matthew C. Zwier and Lillian T. Chong
#
# This file is part of WESTPA.
#
# WESTPA is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# WESTPA is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with WESTPA.  If not, see <http://www.gnu.org/licenses/>.

from westtools import (WESTMasterCommand, WESTParallelTool, WESTDataReader, IterRangeSelection, WESTSubcommand, WESTToolComponent, WESTTool,
                       ProgressIndicatorComponent)

from w_reweight import RWMatrix
import sys, argparse, os
import work_managers

# Just a shim to make sure everything works and is backwards compatible.
# We're making sure it has the appropriate functions so that it can be called
# as a regular tool, and not a subcommand.

class PAMatrix(RWMatrix):
    subcommand = 'init'
    help_text = 'averages and CIs for path-tracing kinetics analysis'
    default_output_file = 'flux_matrices.h5'
    # This isn't strictly necessary, but for the moment, here it is.
    # We really need to modify the underlying class so that we don't pull this sort of stuff if it isn't necessary.
    # That'll take some case handling, which is fine.
    #default_kinetics_file = 'assign.h5'

class WReweight(WESTMasterCommand, WESTParallelTool):
    prog='w_postanalysis_matrix'
    subcommands = [PAMatrix]
    subparsers_title = 'calculate state-to-state kinetics by tracing trajectories'
    description = '''\
Generate a colored transition matrix from a WE assignment file. The subsequent
analysis requires that the assignments are calculated using only the initial and 
final time points of each trajectory segment. This may require downsampling the
h5file generated by a WE simulation. In the future w_assign may be enhanced to optionally
generate the necessary assignment file from a h5file with intermediate time points.
Additionally, this analysis is currently only valid on simulations performed under
either equilibrium or steady-state conditions without recycling target states.

-----------------------------------------------------------------------------
Output format
-----------------------------------------------------------------------------

The output file (-o/--output, by default "reweight.h5") contains the
following datasets:

  ``/bin_populations`` [window, bin]
     The reweighted populations of each bin based on windows. Bins contain
     one color each, so to recover the original un-colored spatial bins,
     one must sum over all states.

  ``/iterations`` [iteration]
    *(Structured -- see below)*  Sparse matrix data from each
    iteration.  They are reconstructed and averaged within the
    w_reweight {kinetics/probs} routines so that observables may
    be calculated.  Each group contains 4 vectors of data:
      
      flux
        *(Floating-point)* The weight of a series of flux events
      cols
        *(Integer)* The bin from which a flux event began.
      cols
        *(Integer)* The bin into which the walker fluxed.
      obs
        *(Integer)* How many flux events were observed during this
        iteration.

-----------------------------------------------------------------------------
Command-line options
-----------------------------------------------------------------------------
'''

if __name__ == '__main__':
    print('WARNING: {} is being deprecated.  Please use w_reweight instead.'.format(WReweight.prog))
    # If we're not really supporting subcommands...
    import sys
    try:
        if sys.argv[1] != 'init':
            sys.argv.insert(1, 'init')
    except:
        sys.argv.insert(1, 'init')
    WReweight().main()
