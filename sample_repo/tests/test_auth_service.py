"""Test for crash_loop archetype: auth_service.py

Fails on the buggy version (process_user dereferences None).
Passes when the fix adds a None guard.
"""
import importlib
import sys
import os

# Ensure sample_repo is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_process_user_handles_missing_user():
    """process_user must NOT raise AttributeError when the user is not found."""
    # Re-import to pick up any patches applied to the file
    if "auth_service" in sys.modules:
        del sys.modules["auth_service"]
    import auth_service

    # Calling with an ID that returns None from the DB should not crash
    try:
        result = auth_service.process_user(999)
    except AttributeError:
        raise AssertionError(
            "process_user raised AttributeError — it must handle None users gracefully"
        )

    # The function should return None (or some sentinel) instead of crashing
    assert result is None or isinstance(result, str)
