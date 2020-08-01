"""
This module contains the metaclass for defining and registering a particular
file format. Any class with this metaclass will be added to the registry and
therefore automatically be added to the 'automatic' file type identification.

The following static class functions will trigger special behavior:

    - id_format(file) : Takes a filename to identify the type, and return True
      if the file is that format or False if not.

    - parse(file) : Takes a file name or file-like object, parse through the
      whole thing and return it. If this method is not found, the constructor is
      called directly.

Note, id_format must be IMPLEMENTED for each class added to the registry, not
simply inherited from a base class (unless that base class is not a metaclass of
FileFormatType)
"""
from __future__ import division, print_function, absolute_import
from contextlib import closing
from parmed.utils.io import genopen
from parmed.utils.six import iteritems
from parmed.exceptions import FormatNotFound
import os

PARSER_REGISTRY = dict()
PARSER_ARGUMENTS = dict()

class FileFormatType(type):
    """
    Metaclass for registering parsers for different formats of different types
    of files.

    Parameters
    ----------
    cls : class type
        The class that is being generated by this metaclass
    name : str
        The name of the class being created
    bases : tuple of types
        Tuple of all base class types for this class
    dct : dict
        The list of options and attributes currently present in the class
    """
    def __init__(cls, name, bases, dct):
        global PARSER_REGISTRY, _CLASS_REGISTRY
        if name in PARSER_REGISTRY:
            raise ValueError('Duplicate name %s in parser registry' % name)
        if 'id_format' in dct:
            PARSER_REGISTRY[name] = cls
            if 'extra_args' in dct:
                PARSER_ARGUMENTS[name] = dct['extra_args']
            else:
                PARSER_ARGUMENTS[name] = ()
        super(FileFormatType, cls).__init__(name, bases, dct)

def load_file(filename, *args, **kwargs):
    """
    Identifies the file format of the specified file and returns its parsed
    contents.

    Parameters
    ----------
    filename : str
        The name of the file to try to parse. If the filename starts with
        http:// or https:// or ftp://, it is treated like a URL and the file will be
        loaded directly from its remote location on the web
    structure : object, optional
        For some classes, such as the Mol2 file class, the default return object
        is not a Structure, but can be made to return a Structure if the
        ``structure=True`` keyword argument is passed. To facilitate writing
        easy code, the ``structure`` keyword is always processed and only passed
        on to the correct file parser if that parser accepts the structure
        keyword. There is no default, as each parser has its own default.
    natom : int, optional
        This is needed for some coordinate file classes, but not others. This is
        treated the same as ``structure``, above. It is the # of atoms expected
    hasbox : bool, optional
        Same as ``structure``, but indicates whether the coordinate file has
        unit cell dimensions
    skip_bonds : bool, optional
        Same as ``structure``, but indicates whether or not bond searching will
        be skipped if the topology file format does not contain bond information
        (like PDB, GRO, and PQR files).
    *args : other positional arguments
        Some formats accept positional arguments. These will be passed along
    **kwargs : other options
        Some formats can only be instantiated with other options besides just a
        file name.

    Returns
    -------
    object
        The returned object is the result of the parsing function of the class
        associated with the file format being parsed

    Notes
    -----
    Compressed files are supported and detected by filename extension. This
    applies both to local and remote files. The following names are supported:

        - ``.gz`` : gzip compressed file
        - ``.bz2`` : bzip2 compressed file

    SDF file is loaded via `rdkit` package.

    Examples
    --------

    Load a Mol2 file

    >>> load_file('tripos1.mol2')
    <ResidueTemplate DAN: 31 atoms; 33 bonds; head=None; tail=None>

    Load a Mol2 file as a Structure

    >>> load_file('tripos1.mol2', structure=True)
    <Structure 31 atoms; 1 residues; 33 bonds; NOT parametrized>

    Load an Amber topology file

    >>> load_file('trx.prmtop', xyz='trx.inpcrd')
    <AmberParm 1654 atoms; 108 residues; 1670 bonds; parametrized>

    Load a CHARMM PSF file

    >>> load_file('ala_ala_ala.psf')
    <CharmmPsfFile 33 atoms; 3 residues; 32 bonds; NOT parametrized>

    Load a PDB and CIF file

    >>> load_file('4lzt.pdb')
    <Structure 1164 atoms; 274 residues; 0 bonds; PBC (triclinic); NOT parametrized>
    >>> load_file('4LZT.cif')
    <Structure 1164 atoms; 274 residues; 0 bonds; PBC (triclinic); NOT parametrized>

    Load a Gromacs topology file -- only works with Gromacs installed

    >>> load_file('1aki.ff99sbildn.top')
    <GromacsTopologyFile 40560 atoms [9650 EPs]; 9779 residues; 30934 bonds; parametrized>

    Load a SDF file -- only works with rdkit installed

    >>> load_file('mol.sdf', structure=True)
    <Structure 34 atoms; 1 residues; 66 bonds; NOT parametrized>

    Raises
    ------
    IOError
        If ``filename`` does not exist

    parmed.exceptions.FormatNotFound
        If no suitable file format can be identified, a TypeError is raised

    TypeError
        If the identified format requires additional arguments that are not
        provided as keyword arguments in addition to the file name
    """
    global PARSER_REGISTRY, PARSER_ARGUMENTS

    # Check that the file actually exists and that we can read it
    if filename.startswith('http://') or filename.startswith('https://')\
            or filename.startswith('ftp://'):
        # This raises IOError if it does not exist; assert silences linters
        with closing(genopen(filename)) as f:
            assert f
    elif not os.path.exists(filename):
        raise IOError('%s does not exist' % filename)
    elif not os.access(filename, os.R_OK):
        raise IOError('%s does not have read permissions set' % filename)

    for name, cls in iteritems(PARSER_REGISTRY):
        if not hasattr(cls, 'id_format'):
            continue
        try:
            if cls.id_format(filename):
                break
        except UnicodeDecodeError:
            continue
    else:
        # We found no file format
        raise FormatNotFound('Could not identify file format')

    # We found a file format that is compatible. Parse it!
    other_args = PARSER_ARGUMENTS[name]
    for arg in other_args:
        if not arg in kwargs:
            raise TypeError('%s constructor expects %s keyword argument' %
                            name, arg)
    # Pass on the following keywords IFF the target function accepts a target
    # keyword. Otherwise, get rid of it: structure, natom, hasbox, skip_bonds
    if hasattr(cls, 'parse'):
        _prune_argument(cls.parse, kwargs, 'structure')
        _prune_argument(cls.parse, kwargs, 'natom')
        _prune_argument(cls.parse, kwargs, 'hasbox')
        _prune_argument(cls.parse, kwargs, 'skip_bonds')
        return cls.parse(filename, *args, **kwargs)
    elif hasattr(cls, 'open_old'):
        _prune_argument(cls.open_old, kwargs, 'structure')
        _prune_argument(cls.open_old, kwargs, 'natom')
        _prune_argument(cls.open_old, kwargs, 'hasbox')
        _prune_argument(cls.open_old, kwargs, 'skip_bonds')
        return cls.open_old(filename, *args, **kwargs)
    elif hasattr(cls, 'open'):
        _prune_argument(cls.open, kwargs, 'structure')
        _prune_argument(cls.open, kwargs, 'natom')
        _prune_argument(cls.open, kwargs, 'hasbox')
        _prune_argument(cls.open, kwargs, 'skip_bonds')
        return cls.open(filename, *args, **kwargs)
    _prune_argument(cls.__init__, kwargs, 'structure')
    _prune_argument(cls.__init__, kwargs, 'natom')
    _prune_argument(cls.__init__, kwargs, 'hasbox')
    _prune_argument(cls.__init__, kwargs, 'skip_bonds')
    return cls(filename, *args, **kwargs)

def _prune_argument(func, kwargs, keyword):
    if keyword in kwargs:
        if (keyword not in
                func.__code__.co_varnames[:func.__code__.co_argcount]):
            kwargs.pop(keyword)
