"""A dashboard for the status of the top certificate authorities' OCSP responders."""
# metadata
__version__ = '0.1.0-dev'

__title__ = 'OCSPdash'
# keep the __description__ synchronized with the package docstring
__description__ = "A dashboard for the status of the top certificate authorities' OCSP responders."
__url__ = 'https://github.com/scolby33/OCSPdash'

__author__ = 'Scott Colby'
__email__ = 'scolby33@gmail.com'

__license__ = 'MIT'
__copyright__ = 'Copyright (c) 2017 Scott Colby'


from . import server_query


from json import JSONEncoder
def _default(self, obj):
    return getattr(obj.__class__, "to_json", _default.default)(obj)
_default.default = JSONEncoder().default
JSONEncoder.default = _default
