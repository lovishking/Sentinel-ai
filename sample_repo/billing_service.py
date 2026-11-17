def calculate_total_billing(user_ids: list):
    if not user_ids:
        return 0.0
    balances = get_user_balances(user_ids)
    return sum(balances.get(user_id, 0.0) for user_id in user_ids)


def get_user_balances(user_ids: list) -> dict:
    """Fetch all requested balances in one batch."""
    import time

    time.sleep(0.1)  # Simulate one batched database request.
    return {user_id: 10.0 for user_id in user_ids}

def get_user_balance(user_id: int):
    """Compatibility helper for callers that need one user's balance."""
    import time

    time.sleep(0.1)
    return 10.0
