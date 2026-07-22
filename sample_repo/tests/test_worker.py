"""Test for oom archetype: worker.py

Fails on the buggy version (unbounded global_cache growth).
Passes when the fix adds cache eviction / max size.
"""
import importlib
import sys
import os

# Ensure sample_repo is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_process_event_bounds_cache():
    """Calling process_event many times must not let cache grow unbounded.

    After 2000 calls the cache (however it is named internally) must
    contain at most 1000 entries, proving that an eviction policy exists.
    """
    if "worker" in sys.modules:
        del sys.modules["worker"]
    import worker

    for i in range(2000):
        worker.process_event({"id": i, "data": "x"})

    # The module should expose global_cache (or equivalent); check its size
    cache = getattr(worker, "global_cache", None)
    assert cache is not None, "worker module must expose global_cache"
    assert len(cache) <= 1000, (
        f"global_cache has {len(cache)} entries after 2000 events — "
        f"expected ≤ 1000 (unbounded growth bug)"
    )
