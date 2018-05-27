# -*- coding: utf-8 -*-

"""Security-related utilities for OCSPdash. Currently just the CryptContext for passlib."""

from passlib.context import CryptContext

pwd_context = CryptContext(
    schemes=['argon2'],
    deprecated='auto',
)
