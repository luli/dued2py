# -*- coding: utf-8 -*-
# Copyright CNRS 2012,
# Roman Yurchak (LULI)
# This software is governed by the CeCILL-B license under French law and
# abiding by the rules of distribution of free software.
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import sys
import os, os.path 
import re
import gzip
import socket
import getpass
import six
import time
from datetime import datetime
from io import StringIO
from multiprocessing import Pool

import numpy as np
import tables
from jinja2 import Template

def parse_one_file(args):
    """
    Read gnuplot frame and return it's content as ndarray
    """
    path, xshape = args
    # this fixes the bug with the exponent overflow (such as 1.23233-126)
    with gzip.open(path, 'rt') as fo:
        txt = fo.read()
        txt = re.sub(r'(?<=\d)-(?=\d)', 'E-', txt)
        f = StringIO(six.u(txt))
        d = np.loadtxt(f)
        #f.close()
        del f

    d = d.reshape((xshape[1], xshape[2],-1))
    return d

p = Pool()

class ParseDued(object):
    """
    Used for parsing dued gnuplot output files.

    Contains following objects:
        - d:  ndarray containing data. 
               shape: (timesteps, i_shape, j_shape, number_of_variables
                            as specified in frm\d+.gpl.gz)
        - t:   [t_0, dt, number of timesteps]

    """
    def __init__(self, folder, parallel=True, units='hedp', flash_comp=False):
        """
        Parse the forder containing dued ouput.
        Parameters:
        -----------
            - folder [str]    : path to DUED simulation folder.
            - parallel [bool] : use multithreading.
            - units [str]     : units to use in ['hedp', 'cgs']. flash_comp
                                  forces cgs.
            - flash_comp [str]: transform units and grid so it can be
                                   more easily plotted besides a flash simulation.

        """
        folder = os.path.abspath(folder)
        self.sim_path = folder
        self.data_path = os.path.join(os.path.abspath(folder),'out/gpl')
        if units not in ['hedp', 'cgs']:
            raise ValueError("'units' should be in ['hedp', 'cgs']")
        self.units = units
        self.flash_comp = flash_comp
        if flash_comp:
            self.units == "cgs"
        if not os.path.exists(self.data_path):
            print('Error: Path does not exists {0}'.format(self.data_path))
            sys.exit(1)
        self.output_name = os.path.split(folder)[1]
        frames = sorted([os.path.join(self.data_path, el)\
                for el in os.listdir(self.data_path) if re.match(r'frm\d+.gpl.gz', el)])
        self._get_shape(frames)

        if parallel:
            _map = p.map
        else:
            _map = map

        res = list(_map(parse_one_file,
            zip(frames, [self.xshape for el in range(len(frames))])))


        self.d = np.array(res)
        # cropping fantom cells, not sure this is correct
        self.d = self.d[:,1:-1,1:-1,:]
        self._reshape_data()
        print("{0} - Parsed {1:.3f} ns ({2} plot files)".format(
                    time.strftime("%H:%M:%S", time.gmtime()),
                    self.d[:,0,0,-1].max(),
                    self.d.shape[0]
                    ))

    def to_xdmf(self, filename=None):
        """
        Save to XDMF
        """
        if not filename:
            filename = self.output_name
        self._save_h5(filename, self.d)
        self._generate_xml(filename, self.d)
        print("{0} - XMDF file '{1}.xdmf', sucessfully created".format(
                    time.strftime("%H:%M:%S", time.gmtime()),
                    self.output_name,
                    ))
    def _get_shape(self, frames):
        # read array shape from header if necessary
        self.xshape = np.zeros(3, dtype=np.int)
        self.xshape[0] = len(frames)
        with gzip.open(frames[0],"rb") as f:
            header =  np.fromstring(f.readline()[7:], sep=' ')
        self.xshape[1:] = header[1:3]
        print("{0} - Expected parsing time: {1:.1f} s".format(
                time.strftime("%H:%M:%S", time.gmtime()),
                self.xshape.prod()*3e-5))


    def _reshape_data(self):
        """
        Transform DUED grid so it can be plotted side by side with FLASH output
        """
        if self.flash_comp:
            # change x and y axis
            self.d[...,[2,3]] = -self.d[...,[3,2]]
            self.d[...,[4,5]] = -self.d[...,[5,4]]
        if self.units == 'cgs':
            self.d[...,2:4] =  self.d[...,2:4]*1e-4 # to μm
            self.d[:,0,0,-1] = self.d[:,0,0,-1]*1e-9 # to ns
            #self.d[...,6:9] =  self.d[...,6:9]*11640.
            #self.d[...,10:13] =  self.d[...,10:13]*1e12

    def _save_h5(self, filename, d):
        """
        Save parsed dued output to hdf5
        """
        #zlib_filter = tables.Filters(complevel=5,complib='zlib')
        h5file = tables.openFile(filename+'.h5', mode = "w")#, filter=zlib_filter)
        for key, val in dict(X=d[...,2],Y=d[...,3],Z=np.zeros(d[...,3].shape), vel=d[...,4:6]).items():
            cgroup = h5file.createGroup(h5file.root, key)
            for idx in range(d.shape[0]):
                h5file.createArray(cgroup, 'frame_{0:04d}'.format(idx),
                            val[idx], "")

        for key, val in dict(dens=16,tele=6,tion=7,trad=8, zbar=9,pres=10,pion=11,pele=12,eint=13,eion=14,
                eele=15,Ne=17,Ni=18,densN=19, Mass=20).items():
            cgroup = h5file.createGroup(h5file.root, key) 
            for idx in range(d.shape[0]):
                h5file.createArray(cgroup, 'frame_{0:04d}'.format(idx),
                        d[idx,:-1,:-1,val], "")
        dens0 = d[0,:-1,:-1,16]
        targ = np.nan*np.ones(dens0.shape)
        for idx, val in enumerate(np.unique(dens0)):
            targ = np.where(dens0==val, idx, targ)
        h5file.createArray('/', 'targ', targ)


        with open(os.path.join(self.sim_path, 'dued.nml'), 'r') as f:
            h5file.setNodeAttr('/', 'dued_namelist', f.read())

        h5file.setNodeAttr('/', 'sim_path', self.sim_path)
        h5file.setNodeAttr('/', 'hostname', socket.gethostname())
        h5file.setNodeAttr('/', 'user', getpass.getuser())
        h5file.setNodeAttr('/', 'date', str(datetime.now()))
        h5file.setNodeAttr('/', 'shape', self.d[...,0].shape)
        h5file.createArray('/', 'time', d[:,0,0,-1]*1e-9)
        h5file.close()

    def _generate_xml(self, filename, d):
        """
        Generate XML description for the hdf5 file
        """

        tmpl = Template("""<?xml version="1.0" ?>
        <!DOCTYPE Xdmf SYSTEM "Xdmf.dtd" []>
        <Xdmf xmlns:xi="http://www.w3.org/2003/XInclude" Version="2.1">
            <Domain>
                <Grid CollectionType="Temporal" GridType="Collection">

                    {% for idx in range(d.shape[0]) %}
                    <Grid Name="Mesh" GridType="Uniform">
                        <Time Value="{{t[idx]}}" />
                        <Topology TopologyType="2DSMesh" Dimensions="{{d.shape[1]}} {{d.shape[2]}}"/>
                        <Geometry GeometryType="X_Y_Z">
                            <DataItem NumberType="Float" Precision="8" Dimensions="{{d.shape[1]}} {{d.shape[2]}}" Format="HDF">{{filename}}.h5:/X/frame_{{'%04d' % idx}}</DataItem>
                            <DataItem NumberType="Float" Precision="8" Dimensions="{{d.shape[1]}} {{d.shape[2]}}" Format="HDF">{{filename}}.h5:/Y/frame_{{'%04d' % idx}}</DataItem>
                            <DataItem NumberType="Float" Precision="8" Dimensions="{{d.shape[1]}} {{d.shape[2]}}" Format="HDF">{{filename}}.h5:/Z/frame_{{'%04d' % idx}}</DataItem>
                        </Geometry>
                        {% for el in var -%}
                        <Attribute Name="{{el.name}}" AttributeType="{{el.attr_type}}" Center="{{el.center}}">
                            <DataItem NumberType="Float" Precision="8" Dimensions="{% if not el.dim %}{{(d.shape[1]-1)}} {{(d.shape[2]-1)}}{% else %}{{(d.shape[1])}} {{(d.shape[2])}} 2{% endif %}" Format="HDF">{{filename}}.h5:/{{el.key}}/frame_{{'%04d' % idx}}</DataItem>
                        </Attribute>
                        {% endfor -%}
                    </Grid>
                    {% endfor %}

                </Grid>
          </Domain>
        </Xdmf>
        """)

        var_dict = [dict(key=el[0],name=el[1], attr_type=el[2] and 'Vector' or 'Scalar',
                        dim=el[2], center= (el[0]=='vel') and 'Node' or 'Cell') for el in [
                  ( 'dens'  , 'dens'            , 0 )  ,
                  ( 'vel'   , 'Velocity'        , 1 )  ,
                  ( 'tele'  , 'tele'            , 0 )  ,
                  ( 'tion'  , 'tion'            , 0 )  ,
                  ( 'trad'  , 'trad'            , 0 )  ,
                  ( 'zbar' , 'zbar'           , 0 )  ,
                  ( 'pres'  , 'pres'            , 0 )  ,
                  ( 'pion'  , 'pion'            , 0 )  ,
                  ( 'pele'  , 'pele'            , 0 )  ,
                  ( 'eint'  , 'eint'            , 0 )  ,
                  ( 'eion'  , 'eion'            , 0 )  ,
                  ( 'eele'  , 'eele'            , 0 )  ,
                  ( 'Ne'    , 'ne'              , 0 )  ,
                  ( 'Ni'    , 'ni'              , 0 )  ,
                  ( 'densN' , 'dens normalised' , 0 )  ,
                  ( 'Mass'  , 'cell mass'       , 0 )  ,
            ]]
            # var name, var name long, (0:scalar, 1:vector)


        with open(filename+'.xdmf','w') as f:
            f.write(tmpl.render(d=d[...,0],
            filename=filename,
            var=var_dict,
            t= d[:,0,0,-1]))

def call_from_cli():
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="""
                    This script allows to convert dued gnuplot output to XDMF format, readable by Visit.

                    Requires python2.7, numpy, jinja2 and PyTables
                """)
    parser.add_argument('folder', help='simulation folder')
    parser.add_argument('-nt', '--nothreading', help='disable threading',
            default=False, action='store_true')
    parser.add_argument('-u', '--units', help="Choose units hedp (default) or cgs",
            default='hedp', action='store')
    parser.add_argument('-c', '--flashcomp', help="Make it easier to compare with FLASH",
            default=False, action='store_true')
    parser.add_argument('--version', action='version', version='%(prog)s 0.1.1')

    if len(sys.argv)==1:
        parser.print_help()
        sys.exit(1)

    args = parser.parse_args()

    ParseDued(args.folder, parallel=(not args.nothreading), units=args.units, flash_comp=args.flashcomp).to_xdmf()
