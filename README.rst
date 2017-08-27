OCSPdash |python_versions| |license| |develop_build|
====================================================
A dashboard for the status of the top certificate authorities' OCSP responders.

.. |python_versions| image:: https://img.shields.io/badge/python->%3D3.6-blue.svg?style=flat-square
    :alt: Supports Python 3.6
.. |license| image:: https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square
    :alt: MIT License
.. |develop_build| image:: https://travis-ci.org/scolby33/OCSPdash.svg?branch=develop
    :target: https://travis-ci.org/scolby33/OCSPdash
    :alt: Development Build Status

Installation
------------
At the moment, installation must be performed via GitHub:

.. code-block:: sh

    $ pip install git+https://github.com/scolby33/OCSPdash.git

:code:`OCSPdash` supports only Python 3.6 or later.

Changelog
---------
Changes as of 22 August 2017

- Create a pretty results page using Bootstrap styles
- Major refactoring of the ServerQuery class to be a subclass of the Censys API class
- Create models and associated database schemata
- Create a manager class to encapsulate working with the models and implement caching logic to reduce the number of (slow) API requests used
- Added lots of type hinting information
- Created a working webapp to display the results information and interact with the DB
- Major updates to the CLI to allow it to run the webapp and local DB updates
- Lots of small changes to get things working as a unified whole
- Set a custom User-Agent for all usages of Requests via a custom :code:`Session` object


Changes as of 16 August 2017

- Initial implementation of the OCSP server testing functionality

Contributing
------------
There are many ways to contribute to an open-source project, but the two most common are reporting bugs and contributing code.

If you have a bug or issue to report, please visit the `issues page on GitHub <https://github.com/scolby33/folderhash/issues>`_ and open an issue there.

If you want to make a code contribution, feel free to open a pull request!

License
-------

MIT. See the :code:`LICENSE.rst` file for the full text of the license.
