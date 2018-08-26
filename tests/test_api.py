# -*- coding: utf-8 -*-

"""Test the functionality of the Flask API."""


def test_get_manifest_jsonl(client_function):
    """Test that /manifest.jsonl returns a 200."""
    resp = client_function.get('/api/v0/manifest.jsonl')
    assert resp.status_code == 200
