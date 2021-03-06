# -*- coding: utf-8 -*-

"""Setup module for the OCSPdash package."""

import codecs  # To use a consistent encoding
import os
import re

import setuptools

#################################################################
PACKAGES = setuptools.find_packages(where='src')
META_PATH = os.path.join('src', 'ocspdash', '__init__.py')
KEYWORDS = ['OCSP', 'X509', 'PKI', 'certificates', 'certificate revocation']
# complete classifier list: http://pypi.python.org/pypi?%3Aaction=list_classifiers
CLASSIFIERS = [
    'Development Status :: 1 - Planning',
    'Intended Audience :: Developers',
    'License :: OSI Approved :: MIT License',
    'Operating System :: OS Independent',
    'Programming Language :: Python',
    'Programming Language :: Python :: 3.7',
]
INSTALL_REQUIRES = [
    'argon2-cffi',
    'asn1crypto',
    'censys',
    'click',
    'cryptography',
    # 'flasgger',  # flasgger is temporarily disabled due to a security vulnerability
    'flask',
    'flask-admin',
    'flask-bootstrap',
    'flask-sqlalchemy',
    'jsonlines',
    'ocspbuilder',
    'oscrypto',
    'passlib',
    'python-jose',
    'requests',
    'sqlalchemy',
    'tqdm',
]
EXTRAS_REQUIRE = {}
TESTS_REQUIRE = ['tox']
ENTRY_POINTS = {
    'console_scripts': [
        'ocspdash = ocspdash.cli:main',
        'ocspscrape = ocspdash.ocspscrape:main',
    ]
}
#################################################################

HERE = os.path.abspath(os.path.dirname(__file__))


def read(*parts):
    """Build an absolute path from *parts* and return the contents of the resulting file. Assume UTF-8 encoding."""
    with codecs.open(os.path.join(HERE, *parts), 'rb', 'utf-8') as f:
        return f.read()


def find_meta(meta):
    """Extract __*meta*__ from META_FILE."""
    meta_match = re.search(
        r'^__{meta}__ = ["\']([^"\']*)["\']'.format(meta=meta), META_FILE, re.M
    )
    if meta_match:
        return meta_match.group(1)
    raise RuntimeError(f'Unable to find __{meta}__ string')


def get_long_description():
    """Get the long_description from the README.rst file. Assume UTF-8 encoding."""
    with codecs.open(os.path.join(HERE, 'README.rst'), encoding='utf-8') as f:
        long_description = f.read()
    return long_description


META_FILE = read(META_PATH)

if __name__ == '__main__':
    setuptools.setup(
        name=find_meta('title'),
        version=find_meta('version'),
        description=find_meta('description'),
        long_description=get_long_description(),
        url=find_meta('url'),
        author=find_meta('author'),
        author_email=find_meta('email'),
        maintainer=find_meta('author'),
        license=find_meta('license'),
        classifiers=CLASSIFIERS,
        keywords=KEYWORDS,
        packages=PACKAGES,
        package_dir={'': 'src'},
        install_requires=INSTALL_REQUIRES,
        extras_require=EXTRAS_REQUIRE,
        tests_require=TESTS_REQUIRE,
        entry_points=ENTRY_POINTS,
        include_package_data=True,
        zip_safe=False,
    )
