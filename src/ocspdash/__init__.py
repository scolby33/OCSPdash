# -*- coding: utf-8 -*-

"""A dashboard for the status of the top certificate authorities' OCSP responders."""

from distlib.database import DistributionPath as _DistributionPath
_distribution = _DistributionPath(include_egg=True).get_distribution('ocspdash')
if _distribution:
    _metadata = _distribution.metadata.todict()

    __version__ = _metadata['version']

    __title__ = _metadata['name']
    # keep the description in setup.cfg synchronized with the package docstring
    __description__ = _metadata['summary']
    __url__ = _metadata['home_page']

    __author__ = _metadata['author']
    __email__ = _metadata['author_email']

    __license__ = _metadata['license']
    __copyright__ = 'Copyright (c) 2017 Scott Colby and Charles Tapley Hoyt'

    del _metadata
else:
    import warnings
    warnings.warn('Unable to retrieve distribution metadata--is OCSPdash fully installed?', RuntimeWarning)
    del warnings

# cleanup the package namespace
del _DistributionPath, _distribution
