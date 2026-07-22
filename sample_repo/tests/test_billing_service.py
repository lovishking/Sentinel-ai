"""Test for latency_spike archetype: billing_service.py

Fails on the buggy version (N+1 loop with sleep(0.1) per user).
Passes when the fix batches the query.
"""
import importlib
import sys
import os
import time

# Ensure sample_repo is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_calculate_total_billing_performance():
    """calculate_total_billing for 5 users must complete in < 0.5s.

    The buggy version calls get_user_balance (sleep 0.1s) per user,
    so 5 users → ≥ 0.5s. A correct fix should batch the query.
    """
    if "billing_service" in sys.modules:
        del sys.modules["billing_service"]
    import billing_service

    user_ids = [1, 2, 3, 4, 5]
    start = time.perf_counter()
    total = billing_service.calculate_total_billing(user_ids)
    elapsed = time.perf_counter() - start

    assert elapsed < 0.5, (
        f"calculate_total_billing took {elapsed:.2f}s for {len(user_ids)} users — "
        f"too slow (N+1 query bug likely still present)"
    )
    assert total == 50.0, f"Expected total 50.0, got {total}"
