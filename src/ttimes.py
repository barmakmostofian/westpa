from __future__ import division
import os, sys, re
from optparse import OptionParser
import numpy
from wemd.util.binfiles import UniformTimeData
from wemd.analysis.probability import quantiles
from itertools import izip

class TransitionFinder(object):
    reSplitWithSpace = re.compile(r',\s*')
    def __init__(self):
        self.region_names = None
        self.region_edges = None
        self.region_name_index = None
        self.event_counts = None
        self.event_times = {}
        self.flux = {}
        self.fpts = {}
        self.tbs = {}
        self.fpt_quantiles = {}
        self.tb_quantiles = {}
        self.transition_log = None
        self.dist = None
        self.dt = None
        
        self.save_tb = {}
        self.save_fpt = {}
        self.save_flux = {}
        self.save_tb_quantiles = {}
        self.save_fpt_quantiles = {}
        
        self.output_stream = sys.stdout
        self.error_stream = sys.stderr
    
    def load_wemd_utd(self, filename):
        dist_utd = UniformTimeData()
        dist = dist_utd.mmap_array_from(open(filename, 'rb'))
        dt = dist_utd.dt
        self.dt = dt
        self.dist = dist
        return dist

    def read_config(self, config_filename):
        from ConfigParser import SafeConfigParser, NoSectionError, NoOptionError
        
        config_parser = SafeConfigParser()
        config_file = open(config_filename, 'rt')
        config_parser.readfp(config_file)
        
        # Configure the region names and boundaries
        region_name_string = config_parser.get('regions', 'region_names')
        self.region_names = self.reSplitWithSpace.split(region_name_string)
        region_edges_string = config_parser.get('regions', 'region_edges')
        self.region_edges = [float(v) for v in 
                             self.reSplitWithSpace.split(region_edges_string)]
        if len(self.region_edges) != len(self.region_names) + 1:
            raise ValueError('region names and boundaries do not match')
        self.region_name_index = dict((v,i) for (i,v) in enumerate(self.region_names))
        
        for irr1 in xrange(0,len(self.region_names)):
            for irr2 in xrange(0,len(self.region_names)):
                if abs(irr1-irr2) == 1:
                    self.flux[irr1, irr2] = []
        
        # Configure the input
        source_filename = config_parser.get('input', 'source')
        source_type = config_parser.get('input', 'source_type').lower()
        if source_type in ('wemd_utd', 'utd'):
            self.dist = self.load_wemd_utd(source_filename)
        else:
            raise ValueError('invalid or unsupported source type')
        
        # Configure the output, as much as we can at this point
        try:
            if config_parser.getboolean('output', 'save_transitions'):
                self.transition_log = open('transitions.txt', 'wt')
        except (NoSectionError, NoOptionError):
            pass
        
        # Configure the calculations
        try:
            config_tb = config_parser.get('calc', 'calc_tb')
        except (NoOptionError,NoSectionError):
            pass
        else:
            self._config_calc(config_tb, self.tbs)

        try:
            config_fpts = config_parser.get('calc', 'calc_fpt')
        except (NoOptionError,NoSectionError):
            pass
        else:
            self._config_calc(config_tb, self.fpts)

        try:
            config_tb_quantiles = config_parser.get('calc', 'calc_tb_quantiles')
        except (NoOptionError,NoSectionError):
            pass
        else:
            self._config_calc(config_tb_quantiles, self.tb_quantiles)

        try:
            config_fpt_quantiles = config_parser.get('calc', 'calc_fpt_quantiles')
        except (NoOptionError,NoSectionError):
            pass
        else:
            self._config_calc(config_fpt_quantiles, self.fpt_quantiles)

            
        for name in ('save_tb', 'save_fpt', 'save_tb_quantiles',
                     'save_fpt_quantiles', 'save_flux'):
            basename = name.split('_', 1)[-1]
            try:
                self._config_save(config_parser.get('output', name),
                                  getattr(self, name),
                                  basename,
                                  'txt')
            except (NoOptionError,NoSectionError):
                pass
        
        self.config_parser = config_parser

    def _config_calc(self, config_string, storage):
        config_string = config_string.strip()
        if config_string.lower() == 'all':
            for irr1 in xrange(0, len(self.region_names)):
                for irr2 in xrange(0, len(self.region_names)):
                    if abs(irr1-irr2) > 1:
                        storage[irr1, irr2] = []
        else:            
            calcs = self.reSplitWithSpace.split(config_string)
            for calc in calcs:
                (region1, region2) = calc.split('->')
                region1 = region1.strip()
                region2 = region2.strip()
                storage[self.region_name_index[region1],
                        self.region_name_index[region2]] = []
                        
    def _config_save(self, config_string, storage, basename, ext):
        config_string = config_string.strip()
        if config_string.lower() == 'all':
            for irr1 in xrange(0, len(self.region_names)):
                for irr2 in xrange(0, len(self.region_names)):
                    if abs(irr1-irr2) > 1:
                        storage[irr1, irr2] = '%s_%s-%s.%s' % (basename,
                                                               self.region_names[irr1],
                                                               self.region_names[irr2],
                                                               ext)
        else:
            saves = self.reSplitWithSpace.split(config_string)
            for save in saves:
                (region1, region2) = save.split('->')
                region1 = region1.strip()
                region2 = region2.strip()
                storage[self.region_name_index[region1],
                        self.region_name_index[region2]] = '%s_%s-%s.%s' \
                                                            % (basename,
                                                               region1,
                                                               region2,
                                                               ext)
       
    def find_transitions(self):
        nreg = len(self.region_names)
        completion_times = numpy.zeros((nreg,nreg), numpy.int64) - 1
        event_count = numpy.zeros((nreg,nreg), numpy.int64)
        region_edges = self.region_edges
        region_names = self.region_names
        event_times = self.event_times
        transition_log = self.transition_log
        fpts = self.fpts
        tbs = self.tbs
        dist = self.dist
        dt = self.dt
    
        for ir in xrange(0, nreg):
            q = dist[0,0]
            if region_edges[ir] <= dist[0,0] < region_edges[ir+1]:
                last_iregion = ir
                break
        else:
            raise ValueError('particle is outside specified coordinate space')
            
        for it in xrange(1, dist.shape[0]):
            q = dist[it,0]
            w = dist[it,1]
            for ir in xrange(0, nreg):
                lb = region_edges[ir]
                ub = region_edges[ir+1]
                
                if lb <= q < ub:
                    iregion = ir
                    break
            else:
                raise ValueError('particle is outside specified coordinate space')
            
            if iregion != last_iregion:        
                # Crossing event...do all the real work here
            
                completion_times[last_iregion, iregion] = it
                event_count[last_iregion, iregion] += 1
                self.flux[last_iregion, iregion].append((it,w))
                try:
                    event_times[last_iregion, iregion].append(it)
                except KeyError:
                    pass
                
                if transition_log:
                    transition_log.write('%d    %s -> %s\n' 
                                         % (it, 
                                            region_names[last_iregion], 
                                            region_names[iregion]) )
                
                for irr in xrange(1, nreg):
                    if iregion > last_iregion:
                        trans_iregion = last_iregion - irr
                        tb_iregion = trans_iregion + 1
                    else:
                        trans_iregion = last_iregion + irr
                        tb_iregion = trans_iregion - 1
                        
                    if 0 <= trans_iregion < nreg and trans_iregion != iregion:
                        if completion_times[iregion, last_iregion] > completion_times[trans_iregion, last_iregion]:
                            # Fluctuation between regions
                            #print "  cannot be a %s->%s transition" % (region_names[trans_iregion], region_names[iregion])
                            pass
                        else:
                            try:
                                type_tbs = tbs[trans_iregion, iregion]
                                type_fpts = fpts[trans_iregion, iregion]
                            except KeyError:
                                pass
                            else:
                        
                                # First passage time:  time since last transition ending in starting state
                                if completion_times[iregion, trans_iregion] >= 0:
                                    fpt = it-completion_times[iregion, trans_iregion]
                                    type_fpts.append((it,fpt,w)) 
                            
                                # Event duration: time since last transition originating from starting state
                                # trans_iregion -> trans_iregion +/- 1
                                if completion_times[trans_iregion, tb_iregion] >= 0:
                                    # Since we record the completion time of the exit of the initial region
                                    # subtract one timestep to indicate the initial time of the 
                                    # transition
                                    tb = it-completion_times[trans_iregion, tb_iregion]-1
                                    type_tbs.append((it,tb,w))
                            # Update completion times matrix
                            completion_times[trans_iregion, iregion] = it
                            event_count[trans_iregion, iregion] += 1
                last_iregion = iregion
                
        self.event_counts = event_count
        for (k,v) in self.fpts.iteritems():
            self.fpts[k] = numpy.array(v, numpy.float)
            self.fpts[k][:,0:2] *= self.dt
        for (k,v) in self.tbs.iteritems():
            self.tbs[k] = numpy.array(v, numpy.float) 
            self.tbs[k][:,0:2] *= self.dt
        for (k,v) in self.tb_quantiles.iteritems():
            self.tb_quantiles[k] = self._calc_quantiles(self.tbs, k)
        for (k,v) in self.fpt_quantiles.iteritems():
            self.fpt_quantiles[k] = self._calc_quantiles(self.fpts, k)
        for (k,v) in self.flux.iteritems():
            self.flux[k] = numpy.array(v, numpy.float)
            self.flux[k][:,0] *= self.dt
            self.flux[k][:,1] /= self.dt
    
    def _calc_quantiles(self, bucket, key):
        data = bucket[key][:,1]
        nq = min(int(len(data)/5), 100)
        dq = 1/nq
        qs = numpy.arange(dq,1,dq)
        quants = quantiles(data, qs)
        return numpy.column_stack([qs, quants])
    
    def save_results(self):
        for key in self.save_tb:
            of = open(self.save_tb[key], 'wt')
            for t in self.tbs[key][:]:
                of.write('%20.16g    %20.16g    %20.16g\n' % tuple(t))
            of.close()
                
        for key in self.save_fpt:
            of = open(self.save_fpt[key], 'wt')
            for t in self.fpts[key][:]:
                of.write('%20.16g    %20.16g    %20.16g\n' % tuple(t))
            of.close()
            
        for key in self.save_tb_quantiles:
            of = open(self.save_tb_quantiles[key], 'wt')
            for t in self.tb_quantiles[key][:]:
                of.write('%8f    %20.16g\n' % tuple(t))
            of.close()

        for key in self.save_fpt_quantiles:
            of = open(self.save_fpt_quantiles[key], 'wt')
            for t in self.fpt_quantiles[key][:]:
                of.write('%8f    %20.16g\n' % tuple(t))
            of.close()

        for key in self.save_flux:
            of = open(self.save_flux[key], 'wt')
            for t in self.flux[key][:]:
                of.write('%8f    %20.16g\n' % tuple(t))
            of.close()
            
    def summarize_results(self):
        common_keys = set(self.fpts.iterkeys()) | set(self.tbs.iterkeys())
        fpts_only = common_keys - set(self.fpts.iterkeys())
        tbs_only = common_keys - set(self.tbs.iterkeys())
        
        for key in common_keys:
            region1 = self.region_names[key[0]]
            region2 = self.region_names[key[1]]
            tb_mean = self.tbs[key][:,1].mean()
            tb_std = self.tbs[key][:,1].std()
            tb_sem = tb_std / (self.tbs[key].shape[0] ** 0.5)
            fpt_mean = self.fpts[key][:,1].mean()
            fpt_std = self.fpts[key][:,1].std()
            fpt_sem = fpt_std / (self.fpts[key].shape[0] ** 0.5)
            rrate = 1/fpt_mean
            rrate_err = fpt_sem/(fpt_mean ** 2)
            self.output_stream.write(
'''%s->%s transitions:
    Average t_b: %g
    St.Dev. t_b: %g
    S.E.M.  t_b: %g
    Average fpt: %g
    St.Dev. fpt: %g
    S.E.M.  fpt: %g
    Reaction rate (1/fpt):  %g
    Error in reaction rate: %g

''' % (region1, region2, 
       tb_mean, tb_std, tb_sem,
       fpt_mean, fpt_std, fpt_sem,
       rrate, rrate_err))
            
        for key in tbs_only:
            region1 = self.region_names[key[0]]
            region2 = self.region_names[key[1]]
            tb_mean = self.tbs[key][:,1].mean()
            tb_std = self.tbs[key][:,1].std()
            tb_sem = tb_std / (self.tbs[key].shape[0] ** 0.5)
            self.output_stream.write(
'''%s->%s transitions:
    Average t_b: %g
    St.Dev. t_b: %g
    S.E.M.  t_b: %g

''' % (region1, region2, 
       tb_mean, tb_std, tb_sem))
            
        for key in fpts_only:
            region1 = self.region_names[key[0]]
            region2 = self.region_names[key[1]]
            fpt_mean = self.fpts[key][:,1].mean()
            fpt_std = self.fpts[key][:,1].std()
            fpt_sem = fpt_std / (self.fpts[key].shape[0] ** 0.5)
            rrate = 1/fpt_mean
            rrate_err = fpt_sem/(fpt_mean ** 2)
            self.output_stream.write(
'''%s->%s transitions:
    Average fpt: %g
    St.Dev. fpt: %g
    S.E.M.  fpt: %g
    Reaction rate (1/fpt):  %g
    Error in reaction rate: %g

''' % (region1, region2, 
       tb_mean, tb_std, tb_sem,
       fpt_mean, fpt_std, fpt_sem,
       rrate, rrate_err))
            
        self.output_stream.write('Event count (R->C):\n%s\n%s\n'
                                 % (self.region_names, self.event_counts))

################################################################################
parser = OptionParser('%prog [OPTIONS] CONFIG_FILE',
                      description = 'analyze trajectories for transition times')
(opts, args) = parser.parse_args()

if len(args) != 1:
    sys.stderr.write('exactly one non-option argument is required\n')
    parser.print_help(sys.stderr)
    sys.exit(2)
    
tf = TransitionFinder()
tf.read_config(args[0])
tf.find_transitions()
tf.summarize_results()
tf.save_results()
