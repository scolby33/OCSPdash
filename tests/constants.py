# -*- coding: utf-8 -*-

"""Constants used in tests for OCSPdash."""

import os
import uuid

__all__ = [
    'TEST_LOCATION_NAME',
    'TEST_PUBLIC_KEY',
    'TEST_KEY_ID',
    'TEST_CONNECTION',
]

TEST_LOCATION_NAME = 'YOLO'
TEST_PUBLIC_KEY = 'LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUlHYk1CQUdCeXFHU000OUFnRUdCU3VCQkFBakE0R0dBQVFCc0orTXJLWU1OdlVPQXZnMThwd0hRTTRnMGRqbQpvaUx5WmFxeTdnQ3ZiT0FZOFo5NmxXSVV4K2NCaVJpZkJrTzlZY2M5UHBHbzA5U2E5Rlo4Z0FZTjluZ0JHR1BTCktsWjlJZUJMZWpQVlBMRk9rMmkwekxwbnVFQ1d2aFhuUE9RazFPSlo4blFOQnN2RWFndXgyRlZIQytJaFlkVVUKbFBJMU8rRzVmTHZ5ZnVnNTBBND0KLS0tLS1FTkQgUFVCTElDIEtFWS0tLS0tCg=='
TEST_KEY_ID = uuid.UUID('b4896be5-6e0b-57a6-8d6a-b4f1e11f9829')
TEST_CONNECTION = os.environ.get('OCSPDASH_TEST_CONNECTION')
