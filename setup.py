#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright CNRS 2012,
# Roman Yurchak (LULI)
# This software is governed by the CeCILL-B license under French law and
# abiding by the rules of distribution of free software.
from setuptools import setup

setup(name='dued2py',
      version='0.1.2',
      description='DUED gnuplot output to hdf5. It can then be read from VisiIt or matplotlib.',
      author='Roman Yurchak',
      author_email='roman.yurchak@polytechnique.edu',
      packages=['dued2py'],
      install_requires=[
              "numpy >= 1.6",
              "setuptools >= 16.0",
              "tables",
              "six",
              "jinja2"
              ],
      entry_points = {
          'console_scripts': ['dued2py = dued2py.dued2xdmf:call_from_cli']
        }
     )

