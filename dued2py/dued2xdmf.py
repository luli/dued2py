#!/usr/bin/python
# -*- coding: utf-8 -*-
# Roman Yurchak
# 02.2012

import sys
import os
import os.path as osp
import re
import gzip
import socket
import getpass
import time
from datetime import datetime
from StringIO import StringIO
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
    with gzip.open(path) as fo:
        with StringIO(re.sub(r'(?<=\d)-(?=\d)', 'E-', fo.read())) as f:
            d = np.loadtxt(f)

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
    def __init__(self, folder):
        """
        Parse the forder containing dued ouput.
        An example would be './dued_simulation/out/gpl/'
        """
        self.sim_path = osp.abspath(folder)
        self.data_path = osp.join(osp.abspath(folder),'out/gpl')
        if not osp.exists(self.data_path):
            print 'Error: Path does not exists {0}'.format(self.data_path)
            sys.exit(1)
        self.output_name = osp.split(folder)[1]
        frames = sorted([osp.join(self.data_path, el)  for el in os.listdir(self.data_path) if re.match(r'frm\d+.gpl.gz', el)])
        self._get_shape(frames)

        self.d = np.array(p.map(parse_one_file,
            zip(frames, [self.xshape for el in range(len(frames))])))

        # cropping fantom cells, not sure this is correct
        self.d = self.d[:,1:-1,1:-1,:]
        self._reshape_data(to_cgs=True)

    def to_xdmf(self, filename=None):
        """
        Save to XDMF
        """
        if not filename:
            filename = self.output_name
        self._save_h5(filename, self.d)
        self._generate_xml(filename, self.d)
        print "{0} - XMDF file '{1}.xdmf' sucessfully created".format(
                    time.strftime("%H:%M:%S", time.gmtime()),
                    self.output_name
                    )
    def _get_shape(self, frames):
        # read array shape from header if necessary
        self.xshape = np.zeros(3, dtype=np.int)
        self.xshape[0] = len(frames)
        with gzip.open(frames[0],"rb") as f:
            header =  np.fromstring(f.readline()[7:], sep=' ')
        self.xshape[1:] = header[1:3]
        print "{0} - Expected parsing time: {1:.1f} s".format(
                time.strftime("%H:%M:%S", time.gmtime()),
                self.xshape.prod()*3e-5)


    def _reshape_data(self, to_cgs=True):
        """
        Transform DUED grid so it can be plotted side by side with FLASH output
        """
        self.d[...,[2,3]] = -self.d[...,[3,2]]
        if to_cgs:
            self.d[...,2:4] =  self.d[...,2:4]*1e-4
            #self.d[...,6:9] =  self.d[...,6:9]*11640.
            #self.d[...,10:13] =  self.d[...,10:13]*1e12

    def _save_h5(self, filename, d):
        """
        Save parsed dued output to hdf5
        """
        #zlib_filter = tables.Filters(complevel=5,complib='zlib')
        h5file = tables.openFile(filename+'.h5', mode = "w")#, filter=zlib_filter)
        for key, val in dict(XY=d[...,2:4], V=d[...,4:6]).iteritems():
            cgroup = h5file.createGroup(h5file.root, key)
            for idx in range(d.shape[0]):
                h5file.createArray(cgroup, 'frame_{0:04d}'.format(idx),
                            val[idx].reshape((-1,2)), "")

        for key, val in dict(rho=16,Te=6,Ti=7,Tr=8, Zstar=9,P=10,Pi=11,Pe=12,E=13,Ei=14,
                Ee=15,Ne=17,Ni=18,rhoN=19, Mass=20).iteritems():
            cgroup = h5file.createGroup(h5file.root, key) 
            for idx in range(d.shape[0]):
                h5file.createArray(cgroup, 'frame_{0:04d}'.format(idx),
                        d[idx,:-1,:-1,val].reshape((-1)), "")
        rho0 = d[0,:-1,:-1,16]
        targ = np.nan*np.ones(rho0.shape)
        for idx, val in enumerate(np.unique(rho0)):
            targ = np.where(rho0==val, idx, targ)
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
                        <Geometry GeometryType="XY">
                            <DataItem NumberType="Float" Precision="8" Dimensions="{{d[0].size}} 2" Format="HDF">{{filename}}.h5:/XY/frame_{{'%04d' % idx}}</DataItem>
                        </Geometry>
                        {% for el in var -%}
                        <Attribute Name="{{el.name}}" AttributeType="{{el.attr_type}}" Center="{{el.center}}">
                            <DataItem NumberType="Float" Precision="8" Dimensions="{{(d.shape[1]-1)*(d.shape[2]-1)}}{% if el.dim %} 2{% endif %}" Format="HDF">{{filename}}.h5:/{{el.key}}/frame_{{'%04d' % idx}}</DataItem>
                        </Attribute>
                        {% endfor -%}
                    </Grid>
                    {% endfor %}

                </Grid>
          </Domain>
        </Xdmf>
        """)

        var_dict = [dict(key=el[0],name=el[1], attr_type=el[2] and 'Vector' or 'Scalar',
                        dim=el[2], center= (el[0]=='V') and 'Node' or 'Cell') for el in [
                ('rho','rho', 0),
                ('V','Velocity',1),
                ('Te','Te', 0),
                ('Ti','Ti', 0),
                ('Tr','Tr', 0),
                ('Zstar','Zstar', 0),
                ('P','P', 0),
                ('Pi','Pi', 0),
                ('Pe','Pe', 0),
                ('E','E', 0),
                ('Ei','Ei', 0),
                ('Ee','Ee', 0),
                ('Ne','ne', 0),
                ('Ni','ni', 0),
                ('rhoN','rho normalised', 0),
                ('Mass','cell mass', 0)
            ]]
            # var name, var name long, (0:scalar, 1:vector)


        with open(filename+'.xdmf','w') as f:
            f.write(tmpl.render(d=d[...,0],
            filename=filename,
            var=var_dict,
            t= d[:,0,0,-1]*1e-9))

def call_from_cli():
    import argparse

    parser = argparse.ArgumentParser(description="""
                    This script allows to convert dued gnuplot output to XDMF format, readable by Visit.

                    Requires python2.7, numpy, jinja2 and PyTables
                """)
    parser.add_argument('folder', help='simulation folder')

    args = parser.parse_args()
    ParseDued(args.folder).to_xdmf()