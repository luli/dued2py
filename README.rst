========================
     dued2py
========================


Overview
========

This module allows to read the simulation output of the DUED code and convert it to a VisIt readable format (hdf5 with a xdmf description file).


Dependencies
============

A Python version 2.7 should be installed together with the Numpy, PyTables and Jinja2 modules.


Installation notes
==================

```
$ python setup.py install --user
```

Example of use
==============

```
$ dued2py folder_with_dued_output_files/
```


