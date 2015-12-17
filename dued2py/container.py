#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright CNRS 2012,
# Roman Yurchak (LULI)
# This software is governed by the CeCILL-B license under French law and
# abiding by the rules of distribution of free software.
from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

import numpy as np
import tables

class DuedSim(object):
    def __init__(self, path):
        self.f =  tables.openFile(path, mode='r')
        shape = self.f.getNodeAttr('/','shape')[1:]
        self.shape = (shape[0]-1, shape[1]-1)
        self.time = self.f.getNode('/time').read()
        step = 0
    def read(self, field, step=None):
        if step is None:
            step = self.step
        if field == 'XY':
            X,Y =  np.rollaxis(1e4*self.f.getNode('/XY/frame_{0:04}'.format(step)
                ).read().reshape((self.shape[0]+1, self.shape[1]+1, 2)), 2)
            return -Y, -X
        elif field  in 'XY':
            return - self.f.getNode('/{0}/frame_{1:04}'.format(field, step)
                          ).read().reshape((self.shape[0]+1, self.shape[1]+1))
        elif field == "targ":
            self.f.getNode('/targ').read()
        else:
            return self.f.getNode('/{0}/frame_{1:04}'.format(field, step)
                          ).read().reshape(self.shape)
    def __del__(self):
        self.f.close()
